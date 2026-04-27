"""
Composite Score Backtest
========================
Long top-100 / short bottom-100 by composite score.
Equal-weighted, monthly rebalancing.

Methodology
-----------
Fundamental signals (F-Score, Gross Profitability, Accruals, Valuation):
  - Computed from Compustat fiscal-year-end (Q4) rows for every year in the data.
  - Assume available 3 months after fiscal year-end to avoid look-ahead bias.
  - Forward-filled within each stock until a newer annual report arrives.

Momentum: 12-1 month cumulative return (CRSP). Updated every month.

Composite: equal-weighted average of 5 cross-sectional percentile ranks.
  Requires >= 3 signals present (same rule as quant_metrics.parquet).

Portfolio: each month, rank all scored stocks by composite.
  Long top-100, short bottom-100, equal-weighted. Hold 1 month.

Benchmark: CRSP VW market return (FF mktrf + rf).

CAPM: OLS of monthly excess returns on market excess return (no intercept=alpha).

Usage
-----
    cd Stock-Analysis-Dashboard
    python backtest/run_backtest.py
"""

import os
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from scipy import stats as scipy_stats

warnings.filterwarnings("ignore")

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)

CRSP_PATH      = os.path.join(ROOT, "data", "crsp_m.dta")
COMPUSTAT_PATH = os.path.join(ROOT, "data", "compustat_with_permno.parquet")
FF_PATH        = os.path.join(ROOT, "data", "ff5_plus_mom.dta")
OUTPUT_DIR     = _HERE

# ── Parameters ────────────────────────────────────────────────────────────────
TOP_N         = 100   # stocks in long book
BOTTOM_N      = 100   # stocks in short book
REPORTING_LAG = 3     # months after fiscal year-end before data is assumed available
MIN_SIGNALS   = 3     # minimum of 5 signals needed for composite score
MIN_STOCKS    = 150   # skip a month if fewer scored stocks available
START_YM      = 199601  # YYYYMM — backtest start (need ~2 years of prior CRSP for momentum)
MOM_MIN_OBS   = 8     # min monthly observations in the 11-month momentum window


# =============================================================================
# STEP 1 — CRSP MONTHLY PANEL
# =============================================================================
def load_crsp():
    print("Loading CRSP monthly...")
    df = pd.read_stata(CRSP_PATH, convert_categoricals=False)
    df = df[df["SHRCD"].isin([10, 11])].copy()   # ordinary common shares only
    df["date"]   = pd.to_datetime(df["date"])
    df["RET"]    = pd.to_numeric(df["RET"], errors="coerce")
    df["PERMNO"] = df["PERMNO"].astype(int)
    df           = df.dropna(subset=["RET"])
    df["ym_int"] = df["date"].dt.year * 100 + df["date"].dt.month
    df           = df[["PERMNO", "ym_int", "RET"]].sort_values(["PERMNO", "ym_int"])
    df           = df.rename(columns={"PERMNO": "permno"})
    print(f"  {df['permno'].nunique():,} stocks, {df['ym_int'].nunique()} months "
          f"({df['ym_int'].min()} – {df['ym_int'].max()})")
    return df.reset_index(drop=True)


def add_momentum(crsp: pd.DataFrame) -> pd.DataFrame:
    """12-1 month momentum: log-return sum of months t-12 to t-2."""
    print("Computing 12-1 month momentum...")
    crsp = crsp.sort_values(["permno", "ym_int"]).copy()
    crsp["log_ret"] = np.log1p(crsp["RET"])
    grp = crsp.groupby("permno")["log_ret"]
    crsp["mom_12_1"] = np.expm1(
        grp.transform(lambda s: s.shift(2).rolling(11, min_periods=MOM_MIN_OBS).sum())
    )
    return crsp


def add_forward_return(crsp: pd.DataFrame) -> pd.DataFrame:
    """ret_fwd = next month's return (the return earned by holding this month's portfolio)."""
    crsp = crsp.sort_values(["permno", "ym_int"])
    crsp["ret_fwd"] = crsp.groupby("permno")["RET"].shift(-1)
    return crsp


# =============================================================================
# STEP 2 — COMPUSTAT FUNDAMENTAL SIGNALS (all fiscal years)
# =============================================================================
_COMP_COLS = [
    "gvkey", "permno", "tic", "datadate", "fyearq", "fqtr",
    "iby", "oancfy", "atq",
    "dlttq", "actq", "lctq", "cshoq",
    "saley", "cogsy",
    "mkvaltq", "dlcq", "cheq", "oibdpy",
]


def load_fundamental_signals() -> pd.DataFrame:
    """
    Returns one row per (permno, available_ym) with all fundamental signals.
    available_ym = fiscal year-end + REPORTING_LAG months (look-ahead-bias-free).
    """
    print("Loading Compustat fundamentals...")
    df = pd.read_parquet(COMPUSTAT_PATH, engine="fastparquet", columns=_COMP_COLS)

    df = df[df["fqtr"] == 4].copy()             # fiscal year-end rows only
    df = df.dropna(subset=["atq"])
    df = df[df["atq"] > 0]
    df["datadate"] = pd.to_datetime(df["datadate"])
    df["permno"]   = pd.to_numeric(df["permno"], errors="coerce")
    df             = df.dropna(subset=["permno"])
    df["permno"]   = df["permno"].astype(int)
    df             = df.sort_values(["gvkey", "fyearq"]).reset_index(drop=True)
    print(f"  {df['permno'].nunique():,} firms across {df['fyearq'].nunique()} fiscal years")

    # ── F-Score (needs 1-year lags) ──────────────────────────────────────────
    lag_cols = ["iby","oancfy","atq","dlttq","actq","lctq","cshoq","saley","cogsy"]
    grp = df.groupby("gvkey")
    for c in lag_cols:
        df[f"{c}_lag"] = grp[c].shift(1)

    df["roa"]          = df["iby"]    / df["atq"]
    df["roa_lag"]      = df["iby_lag"]  / df["atq_lag"]
    df["cfo_assets"]   = df["oancfy"]  / df["atq"]
    df["leverage"]     = df["dlttq"]   / df["atq"]
    df["leverage_lag"] = df["dlttq_lag"] / df["atq_lag"]
    df["cur_ratio"]    = df["actq"]   / df["lctq"]
    df["cur_ratio_lag"]= df["actq_lag"] / df["lctq_lag"]
    df["gm"]           = (df["saley"] - df["cogsy"]) / df["saley"].replace(0, np.nan)
    df["gm_lag"]       = (df["saley_lag"] - df["cogsy_lag"]) / df["saley_lag"].replace(0, np.nan)
    df["ato"]          = df["saley"]  / df["atq"]
    df["ato_lag"]      = df["saley_lag"] / df["atq_lag"]

    f_map = {
        "F1": df["roa"]        > 0,
        "F2": df["oancfy"]     > 0,
        "F3": df["roa"]        > df["roa_lag"],
        "F4": df["cfo_assets"] > df["roa"],
        "F5": df["leverage"]   < df["leverage_lag"],
        "F6": df["cur_ratio"]  > df["cur_ratio_lag"],
        "F7": df["cshoq"]      <= df["cshoq_lag"],
        "F8": df["gm"]         > df["gm_lag"],
        "F9": df["ato"]        > df["ato_lag"],
    }
    for k, cond in f_map.items():
        df[k] = cond.astype(float)

    has_lags = df[["roa_lag","leverage_lag","cur_ratio_lag",
                   "cshoq_lag","gm_lag","ato_lag"]].notna().all(axis=1)
    f_cols = [f"F{i}" for i in range(1, 10)]
    df.loc[~has_lags, f_cols] = np.nan
    df["fscore"] = df[f_cols].sum(axis=1)
    df.loc[~has_lags, "fscore"] = np.nan

    # ── Other signals ─────────────────────────────────────────────────────────
    df["gp_ratio"]       = np.where(df["saley"] > 0,
                                    (df["saley"] - df["cogsy"]) / df["atq"], np.nan)
    df["accruals_ratio"] = (df["iby"] - df["oancfy"]) / df["atq"]

    total_debt   = df["dlttq"].fillna(0) + df["dlcq"].fillna(0)
    cash         = df["cheq"].fillna(0)
    ev           = df["mkvaltq"].fillna(0) + total_debt - cash
    df["ev_ebitda"] = np.where(df["oibdpy"] > 0, ev / df["oibdpy"], np.nan)
    df["pe_ratio"]  = np.where(
        (df["iby"] > 0) & (df["mkvaltq"].fillna(0) > 0),
        df["mkvaltq"] / df["iby"], np.nan)

    # ── Available date ─────────────────────────────────────────────────────────
    avail_date       = df["datadate"] + pd.DateOffset(months=REPORTING_LAG)
    df["avail_int"]  = avail_date.dt.year * 100 + avail_date.dt.month

    keep = ["permno", "tic", "avail_int", "fyearq",
            "fscore", "gp_ratio", "accruals_ratio", "ev_ebitda", "pe_ratio"]
    fund = df[keep].dropna(subset=["permno"]).copy()

    # keep latest per (permno, avail_int) in case of rare duplicates
    fund = (fund.sort_values(["permno","avail_int","fyearq"])
               .groupby(["permno","avail_int"]).last()
               .reset_index())
    return fund


# =============================================================================
# STEP 3 — MERGE CRSP + FUNDAMENTALS (forward-fill within each stock)
# =============================================================================
def merge_panel(crsp: pd.DataFrame, fund: pd.DataFrame) -> pd.DataFrame:
    """
    Left join fund onto crsp at exact avail_int months, then forward-fill.
    Produces one row per (permno, ym_int) with both return and fundamental data.
    """
    print("Merging CRSP and fundamentals (forward-fill)...")
    fund_cols = ["tic", "fscore", "gp_ratio", "accruals_ratio", "ev_ebitda", "pe_ratio"]

    panel = crsp.merge(
        fund[["permno","avail_int"] + fund_cols],
        left_on=["permno","ym_int"],
        right_on=["permno","avail_int"],
        how="left"
    )
    panel = panel.sort_values(["permno","ym_int"]).reset_index(drop=True)

    # Forward-fill within each stock so last-reported fundamentals persist
    for col in fund_cols:
        panel[col] = panel.groupby("permno")[col].ffill()

    print(f"  Panel: {len(panel):,} rows, {panel['permno'].nunique():,} stocks")
    return panel


# =============================================================================
# STEP 4 — CROSS-SECTIONAL COMPOSITE SCORE
# =============================================================================
def build_composite(panel: pd.DataFrame) -> pd.DataFrame:
    """Add cross-sectional percentile ranks and composite score to panel."""
    print("Computing composite scores...")

    def cs_rank(s):
        return s.rank(pct=True, na_option="keep") * 100

    panel["fscore_pct"]    = panel.groupby("ym_int")["fscore"].transform(cs_rank)
    panel["gp_pct"]        = panel.groupby("ym_int")["gp_ratio"].transform(cs_rank)
    panel["accruals_q_pct"]= 100 - panel.groupby("ym_int")["accruals_ratio"].transform(cs_rank)
    panel["ev_pct_raw"]    = panel.groupby("ym_int")["ev_ebitda"].transform(cs_rank)
    panel["pe_pct_raw"]    = panel.groupby("ym_int")["pe_ratio"].transform(cs_rank)
    panel["mom_pct"]       = panel.groupby("ym_int")["mom_12_1"].transform(cs_rank)

    # Valuation: invert (cheaper = better), average whichever multiples are available
    ev_val = (100 - panel["ev_pct_raw"]).where(panel["ev_ebitda"].notna())
    pe_val = (100 - panel["pe_pct_raw"]).where(panel["pe_ratio"].notna())
    n_val  = panel["ev_ebitda"].notna().astype(int) + panel["pe_ratio"].notna().astype(int)
    panel["value_pct"] = (ev_val.fillna(0) + pe_val.fillna(0)) / n_val.replace(0, np.nan)

    sig_cols = ["fscore_pct","gp_pct","accruals_q_pct","value_pct","mom_pct"]
    panel["n_signals"] = panel[sig_cols].notna().sum(axis=1)
    panel["composite"] = panel[sig_cols].mean(axis=1, skipna=True)
    panel.loc[panel["n_signals"] < MIN_SIGNALS, "composite"] = np.nan

    return panel


# =============================================================================
# STEP 5 — PORTFOLIO CONSTRUCTION
# =============================================================================
def build_portfolios(panel: pd.DataFrame) -> pd.DataFrame:
    """
    Each month: rank by composite, assign long (top 100) / short (bottom 100).
    Skips months with fewer than MIN_STOCKS scored stocks.
    """
    print("Constructing portfolios...")
    scored = panel.dropna(subset=["composite","ret_fwd"]).copy()
    scored = scored[scored["ym_int"] >= START_YM]

    month_counts = scored.groupby("ym_int")["composite"].count()
    valid_months = month_counts[month_counts >= MIN_STOCKS].index
    scored = scored[scored["ym_int"].isin(valid_months)]

    # Ascending rank: rank 1 = lowest composite (short), rank N = highest (long)
    scored["rank_asc"]   = scored.groupby("ym_int")["composite"].rank(
        ascending=True, method="first", na_option="keep")
    scored["n_in_month"] = scored.groupby("ym_int")["composite"].transform("count")

    scored["book"] = "neutral"
    scored.loc[scored["rank_asc"] <= BOTTOM_N,
               "book"] = "short"
    scored.loc[scored["rank_asc"] > scored["n_in_month"] - TOP_N,
               "book"] = "long"

    port = scored[scored["book"].isin(["long","short"])].copy()
    print(f"  {port['ym_int'].nunique()} portfolio months, "
          f"avg {port.groupby('ym_int').size().mean():.0f} positions/month")
    return port


def monthly_returns(port: pd.DataFrame) -> pd.DataFrame:
    """Equal-weighted average return per (month, book)."""
    ret = (port.groupby(["ym_int","book"])["ret_fwd"]
               .mean()
               .unstack("book")
               .reset_index())
    ret.columns.name = None
    ret["ls_spread"] = ret["long"] - ret["short"]
    ret["date"] = pd.to_datetime(ret["ym_int"].astype(str), format="%Y%m")
    return ret.sort_values("date").reset_index(drop=True)


# =============================================================================
# STEP 6 — FAMA-FRENCH FACTORS
# =============================================================================
def load_ff_factors() -> pd.DataFrame:
    print("Loading FF factors...")
    ff = pd.read_stata(FF_PATH, convert_categoricals=False)
    ff["dateff"] = pd.to_datetime(ff["dateff"])
    ff["ym_int"] = ff["dateff"].dt.year * 100 + ff["dateff"].dt.month
    # FF data already in decimal (confirmed: mktrf ~[-0.15, 0.18])
    return ff[["ym_int","mktrf","rf"]].dropna()


# =============================================================================
# STEP 7 — CAPM REGRESSION
# =============================================================================
def ols_capm(y: np.ndarray, x: np.ndarray, label: str) -> dict:
    """
    OLS: y = alpha + beta * x
    Returns annualized alpha, beta, R², t-stat and p-value on alpha.
    """
    mask = ~(np.isnan(y) | np.isnan(x))
    y, x = y[mask], x[mask]
    n = len(y)

    xbar, ybar = x.mean(), y.mean()
    Sxx = ((x - xbar) ** 2).sum()
    Sxy = ((x - xbar) * (y - ybar)).sum()

    beta  = Sxy / Sxx
    alpha = ybar - beta * xbar

    resid  = y - (alpha + beta * x)
    s2     = (resid ** 2).sum() / (n - 2)
    se_alpha = np.sqrt(s2 * (1 / n + xbar ** 2 / Sxx))
    se_beta  = np.sqrt(s2 / Sxx)

    t_alpha = alpha / se_alpha
    p_alpha = 2 * (1 - scipy_stats.t.cdf(abs(t_alpha), df=n - 2))
    r2      = 1 - (resid ** 2).sum() / ((y - ybar) ** 2).sum()

    ann_alpha = alpha * 12
    stars = "***" if p_alpha < 0.01 else ("**" if p_alpha < 0.05 else
            ("*" if p_alpha < 0.10 else ""))

    print(f"\n  {label}:")
    print(f"    Alpha (annualized): {ann_alpha*100:+.2f}%{stars}  "
          f"(t = {t_alpha:.2f}, p = {p_alpha:.3f})")
    print(f"    Beta:               {beta:.3f}  (se = {se_beta:.3f})")
    print(f"    R²:                 {r2:.3f}")
    print(f"    N months:           {n}")

    return dict(label=label, alpha_monthly=alpha, alpha_ann=ann_alpha,
                beta=beta, r2=r2, t_alpha=t_alpha, p_alpha=p_alpha, n=n)


def compute_perf_stats(ret: pd.Series, rf: pd.Series) -> dict:
    r  = ret.dropna()
    n  = len(r)
    if n == 0:
        return {}
    ann_ret = (1 + r).prod() ** (12 / n) - 1
    ann_vol = r.std() * np.sqrt(12)
    sharpe  = (r.mean() - rf.reindex(r.index).mean()) / r.std() * np.sqrt(12)
    cum     = (1 + r).cumprod()
    max_dd  = (cum / cum.cummax() - 1).min()
    return dict(ann_ret=ann_ret, ann_vol=ann_vol, sharpe=sharpe,
                max_dd=max_dd, n=n)


def performance_summary(ret: pd.Series, rf: pd.Series, label: str) -> dict:
    stats = compute_perf_stats(ret, rf)
    if not stats:
        return stats
    print(f"\n  {label}:")
    print(f"    Ann. Return:   {stats['ann_ret']*100:+.1f}%")
    print(f"    Ann. Vol:      {stats['ann_vol']*100:.1f}%")
    print(f"    Sharpe:        {stats['sharpe']:.2f}")
    print(f"    Max Drawdown:  {stats['max_dd']*100:.1f}%")
    return stats


# =============================================================================
# STEP 8 — CHART
# =============================================================================
def plot_results(monthly: pd.DataFrame, output_dir: str) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(13, 9), facecolor="white")
    fig.suptitle(
        "Composite Score Strategy — Long Top 100 / Short Bottom 100\n"
        "Equal-Weighted, Monthly Rebalancing",
        fontsize=13, fontweight="bold", y=0.98
    )

    # ── Panel A: Cumulative returns (log scale) ──────────────────────────────
    ax = axes[0]
    specs = [
        ("long",      "Long Book (top 100)",    "#1565C0", 2.2, "-"),
        ("short",     "Short Book (bottom 100)","#C62828", 2.2, "-"),
        ("mkt_total", "S&P 500 (CRSP VW mkt)",  "#757575", 1.8, "--"),
        ("ls_spread", "Long–Short Spread",       "#2E7D32", 2.5, "-"),
    ]
    for col, lbl, color, lw, ls in specs:
        cum = (1 + monthly[col]).cumprod()
        ax.plot(monthly["date"], cum, label=lbl, color=color, linewidth=lw,
                linestyle=ls)

    ax.axhline(1.0, color="black", linewidth=0.5, linestyle=":", alpha=0.4)
    ax.set_yscale("log")
    ax.set_ylabel("Cumulative Return  ($1 initial)", fontsize=10)
    ax.legend(loc="upper left", fontsize=9, framealpha=0.85)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.grid(True, alpha=0.25, which="both")
    ax.tick_params(axis="x", labelsize=9)

    # ── Panel B: Rolling 12-month Sharpe of L-S Spread ───────────────────────
    ax2 = axes[1]
    ls = monthly["ls_spread"]
    rolling_sharpe = (ls.rolling(12).mean() / ls.rolling(12).std()) * np.sqrt(12)
    ax2.plot(monthly["date"], rolling_sharpe, color="#2E7D32", linewidth=1.5)
    ax2.axhline(0, color="black", linewidth=0.8, linestyle="--", alpha=0.6)
    ax2.fill_between(monthly["date"], rolling_sharpe, 0,
                     where=rolling_sharpe.fillna(0) >= 0,
                     alpha=0.20, color="#2E7D32", interpolate=True)
    ax2.fill_between(monthly["date"], rolling_sharpe, 0,
                     where=rolling_sharpe.fillna(0) < 0,
                     alpha=0.20, color="#C62828", interpolate=True)
    ax2.set_ylabel("Sharpe Ratio (annualized)", fontsize=10)
    ax2.set_title("12-Month Rolling Sharpe — Long–Short Spread", fontsize=11)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax2.xaxis.set_major_locator(mdates.YearLocator(2))
    ax2.grid(True, alpha=0.25)
    ax2.tick_params(axis="x", labelsize=9)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    out = os.path.join(output_dir, "backtest_performance.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    print(f"\n  Chart saved: {out}")
    plt.close()


# =============================================================================
# STEP 9 — EXCEL EXPORT
# =============================================================================
def export_excel(
    monthly: pd.DataFrame,
    port: pd.DataFrame,
    perf: dict,          # {label: stats_dict}
    capm: dict,          # {label: capm_dict}
    chart_path: str,
    output_dir: str,
) -> str:
    """
    Write three-sheet Excel workbook:
      1. Summary   — performance + CAPM tables, methodology notes, embedded chart
      2. Monthly Returns — full time-series of portfolio and market returns
      3. Latest Holdings — long and short books for the most recent month
    Returns the path to the saved file.
    """
    import xlsxwriter

    out_path = os.path.join(output_dir, "backtest_results.xlsx")
    wb = xlsxwriter.Workbook(out_path)

    # ── Colour palette ────────────────────────────────────────────────────────
    NAVY    = "#1A237E"
    BLUE    = "#1565C0"
    BLUE_LT = "#E3F2FD"
    RED     = "#B71C1C"
    RED_LT  = "#FFEBEE"
    GREEN   = "#1B5E20"
    GREEN_LT= "#E8F5E9"
    GRAY    = "#455A64"
    GRAY_LT = "#F5F5F5"
    WHITE   = "#FFFFFF"
    YELLOW  = "#FFF9C4"

    # ── Shared formats ────────────────────────────────────────────────────────
    def fmt(bold=False, bg=WHITE, fg="#212121", border=1, size=10,
            align="left", valign="vcenter", num_format=None,
            italic=False, wrap=False):
        d = dict(bold=bold, bg_color=bg, font_color=fg, border=border,
                 font_size=size, align=align, valign=valign, italic=italic,
                 text_wrap=wrap)
        if num_format:
            d["num_format"] = num_format
        return wb.add_format(d)

    # title / section / header / data variants
    F_TITLE   = fmt(bold=True, bg=NAVY,  fg=WHITE, size=14, align="center", border=0)
    F_SUB     = fmt(italic=True, bg=GRAY_LT, fg=GRAY, size=9, align="center", border=0)
    F_SEC     = fmt(bold=True, bg=BLUE,  fg=WHITE, size=10, align="left")
    F_HDR     = fmt(bold=True, bg=BLUE_LT, fg=NAVY, size=9, align="center")
    F_HDR_L   = fmt(bold=True, bg=BLUE_LT, fg=NAVY, size=9, align="left")
    F_DATA    = fmt(size=10, align="right")
    F_DATA_L  = fmt(size=10, align="left")
    F_DATA_Z  = fmt(size=10, bg=GRAY_LT, align="right")   # zebra
    F_DATA_ZL = fmt(size=10, bg=GRAY_LT, align="left")

    # number formats
    F_PCT     = fmt(size=10, align="right",  num_format="0.0%")
    F_PCT_Z   = fmt(size=10, bg=GRAY_LT, align="right", num_format="0.0%")
    F_PCT2    = fmt(size=10, align="right",  num_format="0.00%")
    F_PCT2_Z  = fmt(size=10, bg=GRAY_LT, align="right", num_format="0.00%")
    F_DEC2    = fmt(size=10, align="right",  num_format="0.00")
    F_DEC2_Z  = fmt(size=10, bg=GRAY_LT, align="right", num_format="0.00")
    F_DEC3    = fmt(size=10, align="right",  num_format="0.000")
    F_DEC3_Z  = fmt(size=10, bg=GRAY_LT, align="right", num_format="0.000")
    F_INT     = fmt(size=10, align="right",  num_format="0")
    F_INT_Z   = fmt(size=10, bg=GRAY_LT, align="right", num_format="0")

    # book-coloured label cells
    F_LONG    = fmt(bold=True, bg=BLUE_LT,  fg=BLUE,  size=10, align="left")
    F_SHORT   = fmt(bold=True, bg=RED_LT,   fg=RED,   size=10, align="left")
    F_LS      = fmt(bold=True, bg=GREEN_LT, fg=GREEN, size=10, align="left")
    F_MKT     = fmt(bold=True, bg=GRAY_LT,  fg=GRAY,  size=10, align="left")

    F_LONG_PCT  = fmt(bold=True, bg=BLUE_LT,  fg=BLUE,  size=10, align="right", num_format="0.0%")
    F_SHORT_PCT = fmt(bold=True, bg=RED_LT,   fg=RED,   size=10, align="right", num_format="0.0%")
    F_LS_PCT    = fmt(bold=True, bg=GREEN_LT, fg=GREEN, size=10, align="right", num_format="0.0%")
    F_MKT_PCT   = fmt(bold=True, bg=GRAY_LT,  fg=GRAY,  size=10, align="right", num_format="0.0%")
    F_LONG_DEC  = fmt(bold=True, bg=BLUE_LT,  fg=BLUE,  size=10, align="right", num_format="0.00")
    F_SHORT_DEC = fmt(bold=True, bg=RED_LT,   fg=RED,   size=10, align="right", num_format="0.00")
    F_LS_DEC    = fmt(bold=True, bg=GREEN_LT, fg=GREEN, size=10, align="right", num_format="0.00")
    F_MKT_DEC   = fmt(bold=True, bg=GRAY_LT,  fg=GRAY,  size=10, align="right", num_format="0.00")

    F_NOTE    = fmt(italic=True, fg=GRAY, size=9, border=0, wrap=True)
    F_DATE    = fmt(size=10, align="left",  num_format="mmm yyyy")
    F_DATE_Z  = fmt(size=10, bg=GRAY_LT, align="left", num_format="mmm yyyy")

    # stars format
    F_STAR    = fmt(bold=True, fg=NAVY, size=10, align="center")
    F_STAR_Z  = fmt(bold=True, fg=NAVY, bg=GRAY_LT, size=10, align="center")

    start_str = monthly["date"].min().strftime("%b %Y")
    end_str   = monthly["date"].max().strftime("%b %Y")
    n_months  = len(monthly)

    # =========================================================================
    # SHEET 1 — SUMMARY
    # =========================================================================
    ws1 = wb.add_worksheet("Summary")
    ws1.set_zoom(90)
    ws1.set_column("A:A", 26)
    ws1.set_column("B:B", 14)
    ws1.set_column("C:C", 14)
    ws1.set_column("D:D", 13)
    ws1.set_column("E:E", 13)
    ws1.set_column("F:F", 10)
    ws1.set_column("G:G", 10)
    ws1.set_column("H:H", 10)
    ws1.freeze_panes(0, 0)

    row = 0
    # Title
    ws1.merge_range(row, 0, row, 7, "Composite Score Backtest — Results Summary", F_TITLE)
    ws1.set_row(row, 24)
    row += 1
    ws1.merge_range(row, 0, row, 7,
        f"Long Top-100 / Short Bottom-100  |  Equal-Weighted, Monthly Rebalancing  |  "
        f"{start_str} – {end_str}  |  Data: CRSP + Compustat (3-month reporting lag)",
        F_SUB)
    ws1.set_row(row, 16)
    row += 2

    # ── Section A: Performance ────────────────────────────────────────────────
    ws1.merge_range(row, 0, row, 7, "A.  PERFORMANCE METRICS", F_SEC)
    row += 1

    hdrs = ["Portfolio", "Ann. Return", "Ann. Volatility", "Sharpe Ratio",
            "Max Drawdown", "N Months"]
    col_fmts_hdr = [F_HDR_L, F_HDR, F_HDR, F_HDR, F_HDR, F_HDR]
    for c, (h, f) in enumerate(zip(hdrs, col_fmts_hdr)):
        ws1.write(row, c, h, f)
    row += 1

    book_colors = {
        "Long Book (Top 100)":    (F_LONG,  F_LONG_PCT,  F_LONG_PCT,  F_LONG_PCT,  F_LONG_PCT,  F_INT),
        "Short Book (Bottom 100)":(F_SHORT, F_SHORT_PCT, F_SHORT_PCT, F_SHORT_PCT, F_SHORT_PCT, F_INT),
        "Long–Short Spread":      (F_LS,    F_LS_PCT,    F_LS_PCT,    F_LS_DEC,    F_LS_PCT,    F_INT),
        "Market (S&P 500 proxy)": (F_MKT,  F_MKT_PCT,   F_MKT_PCT,   F_MKT_DEC,   F_MKT_PCT,   F_INT),
    }
    perf_order = ["Long Book (Top 100)", "Short Book (Bottom 100)",
                  "Long–Short Spread", "Market (S&P 500 proxy)"]
    for label in perf_order:
        p = perf[label]
        fmts = book_colors[label]
        ws1.write(row, 0, label,              fmts[0])
        ws1.write(row, 1, p["ann_ret"],       fmts[1])
        ws1.write(row, 2, p["ann_vol"],       fmts[2])
        ws1.write(row, 3, p["sharpe"],        fmts[3])
        ws1.write(row, 4, p["max_dd"],        fmts[4])
        ws1.write(row, 5, p["n"],             fmts[5])
        row += 1

    row += 1  # blank

    # ── Section B: CAPM ───────────────────────────────────────────────────────
    ws1.merge_range(row, 0, row, 7, "B.  CAPM ANALYSIS  (OLS: Excess Return = α + β·MktRF)", F_SEC)
    row += 1

    hdrs2 = ["Portfolio", "α Monthly", "α Annualized", "t-stat (α)",
             "p-value", "Sig.", "β (Market)", "R²"]
    for c, h in enumerate(hdrs2):
        ws1.write(row, c, h, F_HDR if c > 0 else F_HDR_L)
    row += 1

    capm_order = ["Long Book (Top 100)", "Short Book (Bottom 100)", "Long–Short Spread"]
    for label in capm_order:
        c_data = capm[label]
        z = (row % 2 == 0)
        lf   = F_DATA_ZL if z else F_DATA_L
        pf   = F_PCT2_Z  if z else F_PCT2
        df2  = F_DEC2_Z  if z else F_DEC2
        df3  = F_DEC3_Z  if z else F_DEC3
        sf   = F_STAR_Z  if z else F_STAR

        stars = ("***" if c_data["p_alpha"] < 0.01
                 else ("**" if c_data["p_alpha"] < 0.05
                       else ("*" if c_data["p_alpha"] < 0.10 else "")))

        ws1.write(row, 0, label,                    lf)
        ws1.write(row, 1, c_data["alpha_monthly"],  pf)
        ws1.write(row, 2, c_data["alpha_ann"],      pf)
        ws1.write(row, 3, c_data["t_alpha"],        df2)
        ws1.write(row, 4, c_data["p_alpha"],        df3)
        ws1.write(row, 5, stars,                    sf)
        ws1.write(row, 6, c_data["beta"],           df3)
        ws1.write(row, 7, c_data["r2"],             df3)
        row += 1

    row += 1
    ws1.merge_range(row, 0, row, 7,
        "Significance: *** p < 0.01  |  ** p < 0.05  |  * p < 0.10  "
        "|  Benchmark = CRSP VW market (FF mktrf + rf)", F_NOTE)
    row += 2

    # ── Section C: Methodology ────────────────────────────────────────────────
    ws1.merge_range(row, 0, row, 7, "C.  METHODOLOGY", F_SEC)
    row += 1
    notes = [
        ("Signals (5):",
         "Piotroski F-Score · Gross Profitability (Novy-Marx 2013) · "
         "Accruals / Earnings Quality (Sloan 1996) · Valuation (EV/EBITDA + P/E, inverted) · "
         "12-1M Price Momentum (Jegadeesh & Titman 1993)"),
        ("Composite Score:",
         "Equal-weighted average of 5 cross-sectional percentile ranks (0–100). "
         "Requires ≥ 3 signals present. Higher = better quality/value/momentum."),
        ("Reporting Lag:",
         "Fundamental data assumed available 3 months after fiscal year-end to prevent "
         "look-ahead bias. Scores forward-filled until next annual update."),
        ("Rebalancing:",
         "Monthly. Top-100 by composite = Long Book. Bottom-100 = Short Book. "
         "Equal-weighted within each book. Forward return = next calendar month."),
        ("Benchmark:",
         "CRSP value-weighted market return (Ken French data library: mktrf + rf). "
         "Used as S&P 500 proxy."),
        ("Data Vintage:",
         "CRSP monthly file + Compustat quarterly file, both through December 2024. "
         "Blake Stanley, FIN 372T — UT Austin, Spring 2026."),
    ]
    for label, text in notes:
        ws1.set_row(row, 28)
        ws1.write(row, 0, label, fmt(bold=True, size=9, bg=GRAY_LT,
                                     fg=NAVY, border=1, valign="top"))
        ws1.merge_range(row, 1, row, 7, text,
                        fmt(size=9, border=1, wrap=True, valign="top",
                            bg=WHITE, fg="#424242"))
        row += 1

    row += 1

    # Embed chart
    if os.path.exists(chart_path):
        ws1.insert_image(row, 0, chart_path,
                         {"x_scale": 0.85, "y_scale": 0.85, "x_offset": 4})

    # =========================================================================
    # SHEET 2 — MONTHLY RETURNS
    # =========================================================================
    ws2 = wb.add_worksheet("Monthly Returns")
    ws2.set_zoom(90)
    ws2.freeze_panes(2, 1)
    ws2.set_column("A:A", 12)
    ws2.set_column("B:M", 13)

    # Title row
    ws2.merge_range(0, 0, 0, 11, "Monthly Portfolio Returns — Composite Score Backtest", F_TITLE)
    ws2.set_row(0, 22)

    cols = [
        ("Date",               "date",       False),
        ("Long Book",          "long",       True),
        ("Short Book",         "short",      True),
        ("Long–Short Spread",  "ls_spread",  True),
        ("Market (S&P 500)",   "mkt_total",  True),
        ("Risk-Free Rate",     "rf",         True),
        ("Long (Excess)",      "long_exc",   True),
        ("Short (Excess)",     "short_exc",  True),
        ("Long Cum. Return",   "_long_cum",  True),
        ("Short Cum. Return",  "_short_cum", True),
        ("L-S Cum. Return",    "_ls_cum",    True),
        ("Market Cum. Return", "_mkt_cum",   True),
    ]

    # Compute cumulative return columns
    m = monthly.reset_index(drop=True).copy()
    m["_long_cum"]  = (1 + m["long"]).cumprod() - 1
    m["_short_cum"] = (1 + m["short"]).cumprod() - 1
    m["_ls_cum"]    = (1 + m["ls_spread"]).cumprod() - 1
    m["_mkt_cum"]   = (1 + m["mkt_total"]).cumprod() - 1

    # Headers
    for c, (h, _, _is_pct) in enumerate(cols):
        ws2.write(1, c, h, F_HDR if c > 0 else F_HDR_L)

    # Data rows
    for i, (_, row_data) in enumerate(m.iterrows()):
        r = i + 2
        z = (i % 2 == 0)
        date_fmt = F_DATE_Z if z else F_DATE
        num_fmt  = F_PCT_Z  if z else F_PCT
        ws2.write_datetime(r, 0, row_data["date"].to_pydatetime(), date_fmt)
        for c, (_, col_key, is_pct) in enumerate(cols[1:], start=1):
            val = row_data.get(col_key, None)
            if val is None or (isinstance(val, float) and np.isnan(val)):
                ws2.write_blank(r, c, None, num_fmt)
            else:
                ws2.write_number(r, c, val, num_fmt)

    ws2.autofilter(1, 0, 1 + len(m), len(cols) - 1)

    # =========================================================================
    # SHEET 3 — LATEST HOLDINGS
    # =========================================================================
    ws3 = wb.add_worksheet("Latest Holdings")
    ws3.set_zoom(90)
    ws3.set_column("A:A", 7)   # rank
    ws3.set_column("B:B", 9)   # permno
    ws3.set_column("C:C", 9)   # ticker
    ws3.set_column("D:D", 13)  # composite
    ws3.set_column("E:I", 13)  # signal pcts

    last_ym  = port["ym_int"].max()
    last_date = pd.to_datetime(str(last_ym), format="%Y%m").strftime("%B %Y")
    long_snap  = port[(port["ym_int"] == last_ym) & (port["book"] == "long")].copy()
    short_snap = port[(port["ym_int"] == last_ym) & (port["book"] == "short")].copy()
    long_snap  = long_snap.sort_values("composite", ascending=False).reset_index(drop=True)
    short_snap = short_snap.sort_values("composite", ascending=True).reset_index(drop=True)

    ws3.merge_range(0, 0, 0, 8,
        f"Latest Portfolio Holdings — {last_date} (as of composite scores available that month)",
        F_TITLE)
    ws3.set_row(0, 22)

    snap_cols = [
        ("Rank",          None,             F_INT,   F_INT_Z),
        ("PERMNO",        "permno",         F_DATA,  F_DATA_Z),
        ("Ticker",        "tic",            F_DATA_L,F_DATA_ZL),
        ("Composite",     "composite",      F_DEC2,  F_DEC2_Z),
        ("F-Score Pct",   "fscore_pct",     F_DEC2,  F_DEC2_Z),
        ("GP Pct",        "gp_pct",         F_DEC2,  F_DEC2_Z),
        ("Accruals Pct",  "accruals_q_pct", F_DEC2,  F_DEC2_Z),
        ("Value Pct",     "value_pct",      F_DEC2,  F_DEC2_Z),
        ("Mom Pct",       "mom_pct",        F_DEC2,  F_DEC2_Z),
    ]

    def write_book_section(ws, start_row, snap, section_title, sec_fmt, hdr_fmt):
        ws.merge_range(start_row, 0, start_row, 8, section_title, sec_fmt)
        start_row += 1
        for c, (h, _, _f, _fz) in enumerate(snap_cols):
            ws.write(start_row, c, h, hdr_fmt)
        start_row += 1
        for i, (_, row_data) in enumerate(snap.iterrows()):
            z = (i % 2 == 0)
            for c, (_, col_key, nf, nfz) in enumerate(snap_cols):
                f = nfz if z else nf
                if col_key is None:
                    ws.write_number(start_row + i, c, i + 1, f)
                else:
                    val = row_data.get(col_key, None)
                    if val is None or (isinstance(val, float) and np.isnan(val)):
                        ws.write_blank(start_row + i, c, None, f)
                    elif isinstance(val, str):
                        ws.write_string(start_row + i, c, val, f)
                    else:
                        ws.write_number(start_row + i, c, val, f)
        return start_row + len(snap) + 1

    F_LONG_SEC  = fmt(bold=True, bg=BLUE,  fg=WHITE, size=11)
    F_SHORT_SEC = fmt(bold=True, bg=RED,   fg=WHITE, size=11)
    F_LONG_HDR  = fmt(bold=True, bg=BLUE_LT, fg=NAVY, size=9, align="center")
    F_SHORT_HDR = fmt(bold=True, bg=RED_LT,  fg=RED,  size=9, align="center")

    next_row = write_book_section(
        ws3, 1, long_snap,
        f"LONG BOOK  (Top {len(long_snap)} by Composite Score — {last_date})",
        F_LONG_SEC, F_LONG_HDR)

    next_row += 1  # gap
    write_book_section(
        ws3, next_row, short_snap,
        f"SHORT BOOK  (Bottom {len(short_snap)} by Composite Score — {last_date})",
        F_SHORT_SEC, F_SHORT_HDR)

    # ── Close ─────────────────────────────────────────────────────────────────
    wb.close()
    print(f"  Excel saved: {out_path}")
    return out_path


# =============================================================================
# MAIN
# =============================================================================
def main():
    print("=" * 65)
    print("  Composite Score Backtest")
    print(f"  Long top-{TOP_N} / Short bottom-{BOTTOM_N}, equal-weighted")
    print(f"  Reporting lag: {REPORTING_LAG} months | Min signals: {MIN_SIGNALS}/5")
    print("=" * 65)

    # ── Data preparation ──────────────────────────────────────────────────────
    crsp  = load_crsp()
    crsp  = add_momentum(crsp)
    crsp  = add_forward_return(crsp)
    fund  = load_fundamental_signals()
    panel = merge_panel(crsp, fund)
    panel = build_composite(panel)

    # ── Portfolio ─────────────────────────────────────────────────────────────
    port    = build_portfolios(panel)
    # Preserve signal pct columns needed for the holdings sheet
    port = port.copy()
    monthly = monthly_returns(port)

    # ── Merge FF factors ──────────────────────────────────────────────────────
    ff      = load_ff_factors()
    monthly = monthly.merge(ff, on="ym_int", how="inner")
    monthly["mkt_total"]  = monthly["mktrf"] + monthly["rf"]
    monthly["long_exc"]   = monthly["long"]      - monthly["rf"]
    monthly["short_exc"]  = monthly["short"]     - monthly["rf"]
    # L-S spread is self-financing; no rf subtraction needed
    monthly.index = monthly["date"]

    start_str = monthly["date"].min().strftime("%b %Y")
    end_str   = monthly["date"].max().strftime("%b %Y")

    # ── CAPM ──────────────────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  CAPM Alpha & Beta  ({start_str} – {end_str})")
    print("  (*** p<0.01  ** p<0.05  * p<0.10)")
    print("="*65)
    mktrf = monthly["mktrf"].values

    capm_long  = ols_capm(monthly["long_exc"].values,  mktrf, "Long Book  (top 100)")
    capm_short = ols_capm(monthly["short_exc"].values, mktrf, "Short Book (bottom 100)")
    capm_ls    = ols_capm(monthly["ls_spread"].values, mktrf, "Long–Short Spread")

    # ── Performance summary ───────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  Performance Summary  ({start_str} – {end_str})")
    print("="*65)
    rf_idx = monthly["rf"].reindex(monthly.index)
    perf = {
        "Long Book (Top 100)":     performance_summary(monthly["long"],      rf_idx, "Long Book  (top 100)"),
        "Short Book (Bottom 100)": performance_summary(monthly["short"],     rf_idx, "Short Book (bottom 100)"),
        "Long–Short Spread":       performance_summary(monthly["ls_spread"], rf_idx, "Long–Short Spread"),
        "Market (S&P 500 proxy)":  performance_summary(monthly["mkt_total"], rf_idx, "S&P 500 proxy (CRSP VW)"),
    }

    # ── Chart ─────────────────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print("  Generating chart...")
    print("="*65)
    chart_path = os.path.join(OUTPUT_DIR, "backtest_performance.png")
    plot_results(monthly, OUTPUT_DIR)

    # ── Excel ─────────────────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print("  Exporting Excel workbook...")
    print("="*65)
    capm_dict = {
        "Long Book (Top 100)":     capm_long,
        "Short Book (Bottom 100)": capm_short,
        "Long–Short Spread":       capm_ls,
    }
    # Map perf keys to Excel export keys (excel uses "Market (S&P 500 proxy)")
    perf_xl = {
        "Long Book (Top 100)":     perf["Long Book (Top 100)"],
        "Short Book (Bottom 100)": perf["Short Book (Bottom 100)"],
        "Long–Short Spread":       perf["Long–Short Spread"],
        "Market (S&P 500 proxy)":  perf["Market (S&P 500 proxy)"],
    }
    export_excel(monthly, port, perf_xl, capm_dict, chart_path, OUTPUT_DIR)

    print("\nDone.")
    return monthly, capm_long, capm_short, capm_ls


if __name__ == "__main__":
    main()
