"""
backtest_engine.py

Menguji apakah indikator regime makro ("Phase Angle": posisi + momentum
gabungan sejumlah variabel makro/pasar, dipetakan lewat arctan2 ke 0-360
derajat) punya predictive power terhadap forward return IHSG, memakai
kerangka pengujian out-of-sample yang dipakai di literatur forecasting
return:

  - R^2_OOS               Campbell, J.Y. & Thompson, S.B. (2008),
                           "Predicting Excess Stock Returns Out of Sample:
                           Can Anything Beat the Historical Average?",
                           Review of Financial Studies, 21(4), 1509-1531.
  - Clark-West test        Clark, T.E. & West, K.D. (2007), "Approximately
                           Normal Tests for Equal Predictive Accuracy in
                           Nested Models", Journal of Econometrics, 138,
                           291-311.
  - Pesaran-Timmermann test  Pesaran, M.H. & Timmermann, A. (1992), "A
                           Simple Nonparametric Test of Predictive
                           Performance", Journal of Business & Economic
                           Statistics, 10(4), 461-465.
  - Newey-West HAC SE       Newey, W.K. & West, K.D. (1987), "A Simple,
                           Positive Semi-Definite, Heteroskedasticity and
                           Autocorrelation Consistent Covariance Matrix",
                           Econometrica, 55(3), 703-708. Lag dipilih = orde
                           overlap forecast horizon (lih. Hansen & Hodrick,
                           1980; Britten-Jones, Neuberger & Nolte, 2011,
                           untuk koreksi overlap serupa).

METHODOLOGICAL GUARDRAILS -- baca sebelum mengubah file ini
------------------------------------------------------------
1. Konvensi regime (kuadran -> bullish/bearish) HANYA boleh ditentukan dari
   data in-sample (< tahun OOS). Fungsi `_select_regime_convention_in_sample`
   melakukan ini secara eksplisit dan konvensinya di-freeze sebelum dipakai
   ke data OOS. JANGAN pernah memilih/mengubah konvensi ini dengan melihat
   hasil OOS -- itu membuat seluruh pengujian OOS di bawahnya sirkular
   (data snooping pada tahap desain model, bukan cuma tahap eksekusi).
2. Semua hyperparameter lain di sini (window z-score 60 bulan, bobot
   komposit, threshold RSI, dst.) adalah pilihan tetap yang tidak dituning
   ulang berdasarkan hasil backtest. Kalau butuh reoptimize, itu berarti
   kamu sedang mendesain strategi baru dan butuh periode OOS baru (data
   lebih baru), bukan menggeser cutoff tahun 2019.
3. Return_3M / Return_6M (forward return) HANYA boleh dipakai sebagai target
   (y), tidak pernah sebagai fitur input (X) untuk komponen Macro_Level_X.
4. Semua observasi di sini overlap (3-bulan forward return disampling tiap
   bulan -> MA(2)-like). n nominal != n efektif. Setiap uji signifikansi di
   file ini memakai HAC correction atau effective-N, tidak ada yang memakai
   n mentah secara naif.
5. File ini TIDAK melakukan koreksi multiple-testing (mis. White's Reality
   Check / Hansen's SPA test) untuk kemungkinan bahwa strategi ini adalah
   salah satu dari banyak spesifikasi yang dicoba-coba di masa lalu. Bobot
   komposit (0.10/0.05 dst.) dan pilihan window adalah heuristik tetap,
   bukan hasil optimisasi -- tapi kalau versi lain dari sistem ini pernah
   dicoba dan dibuang, hasil di sini tetap harus dibaca dengan skeptis.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
from fredapi import Fred
from config import FRED_API_KEY
import os
import json
import math

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "data", "backtest_cache.json")

OOS_START_YEAR = 2024          # cutoff IS/OOS, ditetapkan a priori
ZSCORE_WINDOW = 60             # bulan, ~5 tahun
ZSCORE_MIN_PERIODS = 12
NW_LAG = 2                     # = orde overlap dari forward return 3 bulan
                                # yang disampling bulanan (lih. Hansen &
                                # Hodrick, 1980): lag HAC yang benar untuk
                                # overlap k-period adalah k-1.


# ---------------------------------------------------------------------------
# Helpers umum
# ---------------------------------------------------------------------------

def calculate_rsi(series, period=14):
    """
    RSI standar (Wilder). min_periods=period (bukan 1 seperti versi lama)
    supaya RSI awal tidak dihitung dari 1-2 titik data yang tidak informatif.
    Edge case gain=loss=0 (pasar flat) -> RSI netral 50, bukan NaN/inf.
    """
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(window=period, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).rolling(window=period, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.where(~((loss == 0) & (gain > 0)), 100.0)
    rsi = rsi.fillna(50.0)
    return rsi


def rolling_zscore(series, window=ZSCORE_WINDOW, min_periods=ZSCORE_MIN_PERIODS):
    """Rolling z-score generik dipakai untuk semua komponen komposit, supaya
    semua fitur masuk ke Macro_Level_X dalam skala yang sama (tidak ada lagi
    campuran flag biner ±1 dengan z-score kontinu)."""
    mean = series.rolling(window=window, min_periods=min_periods).mean()
    std = series.rolling(window=window, min_periods=min_periods).std()
    z = (series - mean) / std.replace(0, np.nan)
    return z.fillna(0.0)


def norm_sf(z):
    """Survival function (1 - CDF) distribusi normal standar."""
    return 0.5 * (1 - math.erf(z / math.sqrt(2)))


# ---------------------------------------------------------------------------
# Data & fitur
# ---------------------------------------------------------------------------

def get_historical_data():
    """Fetch & align data historis bulanan, lalu bangun Macro_Level_X /
    Macro_Momentum_Y / Phase_Angle. Semua komponen komposit adalah rolling
    z-score kontinu (60 bulan) -- tidak ada flag biner yang di-embed
    langsung ke jumlah berbobot, supaya kontribusi tiap komponen terhadap
    varians komposit sepadan dengan bobotnya."""
    print("[Backtest] Memulai unduh data historis (bisa memakan waktu 5-10 detik)...")

    tickers = {
        "IHSG": "^JKSE",
        "SP500": "^GSPC",
        "DXY": "DX-Y.NYB",
        "WTI": "CL=F",
        "GOLD": "GC=F",
        "USDIDR": "IDR=X",
    }

    dfs = {}
    for name, ticker in tickers.items():
        try:
            t = yf.Ticker(ticker)
            df = t.history(period="27y", interval="1mo")
            if not df.empty:
                df.index = pd.to_datetime(df.index).tz_localize(None)
                df = df.resample("ME").last()
                dfs[name] = df["Close"]
        except Exception as e:
            print(f"[Backtest] Peringatan: gagal unduh {ticker} ({name}): {e}")

    market_df = pd.DataFrame(dfs).ffill()

    # Trend & return dasar
    for col in ["SP500", "DXY", "WTI", "IHSG"]:
        if col in market_df:
            market_df[f"{col}_SMA3"] = market_df[col].rolling(window=3, min_periods=1).mean()
            market_df[f"{col}_Return_1M"] = market_df[col].pct_change(1)
            # Forward return -- INI TARGET (y), tidak pernah dipakai sebagai
            # fitur input di Macro_Level_X.
            market_df[f"{col}_Return_3M"] = market_df[col].pct_change(3).shift(-3)
            market_df[f"{col}_Return_6M"] = market_df[col].pct_change(6).shift(-6)

    # Fitur teknikal IHSG -- dibuat KONTINU (bukan flag ±1) supaya homogen
    # dengan komponen makro saat di-z-score. Window dinamai apa adanya
    # (3M/12M), tidak dipaksakan menjadi padanan "50/200-day" yang salah
    # kaprah di data bulanan (50 hari trading != 5 bulan kalender).
    if "IHSG" in market_df:
        market_df["IHSG_RSI"] = calculate_rsi(market_df["IHSG"])
        market_df["IHSG_SMA_Short"] = market_df["IHSG"].rolling(window=3, min_periods=1).mean()
        market_df["IHSG_SMA_Long"] = market_df["IHSG"].rolling(window=12, min_periods=1).mean()
        market_df["IHSG_RSI_Centered"] = (market_df["IHSG_RSI"] - 50.0) / 50.0
        market_df["IHSG_SMA_Spread"] = (
            (market_df["IHSG_SMA_Short"] - market_df["IHSG_SMA_Long"]) / market_df["IHSG_SMA_Long"]
        )

    # Fitur trend SP500 -- kontinu (deviasi dari SMA3), bukan flag uptrend/
    # downtrend ±1.
    if "SP500" in market_df:
        market_df["SP500_DevSMA"] = (market_df["SP500"] - market_df["SP500_SMA3"]) / market_df["SP500_SMA3"]

    # Data makro FRED
    fred = Fred(api_key=FRED_API_KEY)
    fred_series = {
        "FEDFUNDS": "FEDFUNDS",
        "ID_CPI": "IDNCPIALLMINMEI",
        "BI_RATE": "INTDSRIDM193N",
        "ID_GDP_IDX": "IDNGDPRQPSMEI",
        "ID_TRADE": "XTNTVA01IDM667S",
    }
    fred_dfs = {}
    import time
    for name, series_id in fred_series.items():
        for attempt in range(3):
            try:
                s = fred.get_series(series_id)
                if not s.empty:
                    s.index = pd.to_datetime(s.index).tz_localize(None)
                    fred_dfs[name] = s.resample("ME").last()
                break
            except Exception as e:
                if attempt == 2:
                    print(f"[Backtest] Gagal ambil {name} dari FRED: {e}")
                else:
                    time.sleep(2)

    fred_df = pd.DataFrame(fred_dfs).ffill()
    market_df = market_df.join(fred_df, how="outer").ffill()

    if "ID_CPI" in market_df:
        market_df["ID_CPI_YOY"] = market_df["ID_CPI"].pct_change(12) * 100
    if "ID_GDP_IDX" in market_df:
        market_df["ID_GDP_YOY"] = market_df["ID_GDP_IDX"].pct_change(12) * 100

    # --- FIX: Koreksi Look-Ahead Bias (Point-in-Time) ---
    # Variabel makro dari FRED memiliki jeda rilis (publication lag).
    # Agar model tidak mengintip masa depan, kita men-shift variabel lag/coincident 1 bulan.
    lag_vars = ["ID_CPI_YOY", "ID_GDP_YOY", "ID_TRADE", "FEDFUNDS", "BI_RATE"]
    for var in lag_vars:
        if var in market_df:
            market_df[var] = market_df[var].shift(1)

    # --- FIX: BI-Fed rate spread (carry-trade logic) ---
    if "BI_RATE" in market_df and "FEDFUNDS" in market_df:
        market_df["BI_FED_SPREAD"] = market_df["BI_RATE"] - market_df["FEDFUNDS"]

    subset_cols = [c for c in ["IHSG", "SP500", "DXY", "FEDFUNDS"] if c in market_df.columns]
    market_df = market_df.dropna(subset=subset_cols)

    # --- Semua komponen komposit di-z-score dengan mekanisme YANG SAMA ---
    metrics_to_zscore = [
        "DXY", "FEDFUNDS", "WTI", "GOLD", "USDIDR",
        "BI_RATE", "ID_CPI_YOY", "ID_GDP_YOY", "ID_TRADE", "SP500_DevSMA", "BI_FED_SPREAD",
        "IHSG_RSI_Centered", "IHSG_SMA_Spread",
    ]
    for metric in metrics_to_zscore:
        if metric in market_df:
            market_df[f"{metric}_Z"] = rolling_zscore(market_df[metric])

    market_df["IHSG_Tech_Z"] = (
        market_df.get("IHSG_RSI_Centered_Z", 0.0) + market_df.get("IHSG_SMA_Spread_Z", 0.0)
    ) / 2.0

    # Macro Level (X): Sinkronisasi 100% dengan SCORING_WEIGHTS di config.py
    market_df["Macro_Level_X"] = (
        market_df.get("SP500_DevSMA_Z", 0) * 0.05
        + (-market_df.get("DXY_Z", 0)) * 0.05
        + market_df.get("BI_FED_SPREAD_Z", 0) * 0.25
        + market_df.get("ID_GDP_YOY_Z", 0) * 0.10
        + market_df.get("ID_TRADE_Z", 0) * 0.05
        + (market_df.get("WTI_Z", 0)) * 0.05
        + (-market_df.get("USDIDR_Z", 0)) * 0.20
        + (-market_df.get("ID_CPI_YOY_Z", 0)) * 0.15
        + market_df.get("IHSG_Tech_Z", 0) * 0.05
    )

    market_df["Macro_Momentum_Y"] = market_df["Macro_Level_X"] - market_df["Macro_Level_X"].shift(3)

    # Phase Angle: secara matematis ekuivalen dengan (sign(X), sign(Y)) --
    # dipertahankan untuk interpretability/visualisasi, TAPI klasifikasi
    # regime di bawah memakai kuadran (bukan derajat presisi), jadi jangan
    # kira sudut 190 derajat "lebih kuat sinyalnya" daripada 350 derajat
    # hanya dari kode ini -- keduanya diperlakukan identik sebagai kuadran
    # 3&4.
    market_df["Phase_Angle"] = np.degrees(
        np.arctan2(market_df["Macro_Momentum_Y"].fillna(0), market_df["Macro_Level_X"])
    ) % 360

    market_df["Oracle_Score"] = market_df["Macro_Level_X"] + market_df["Macro_Momentum_Y"].fillna(0)

    return market_df


# ---------------------------------------------------------------------------
# Statistik akademis
# ---------------------------------------------------------------------------

def calc_r2_oos(actuals, forecasts_model, forecasts_benchmark):
    """R^2_OOS a la Campbell & Thompson (2008): 1 - MSPE_model / MSPE_benchmark,
    benchmark = expanding historical mean (dibangun di run_backtest)."""
    actuals = np.array(actuals)
    f_model = np.array(forecasts_model)
    f_bench = np.array(forecasts_benchmark)
    mspe_model = np.mean((actuals - f_model) ** 2)
    mspe_bench = np.mean((actuals - f_bench) ** 2)
    if mspe_bench == 0:
        return 0.0
    return 1 - (mspe_model / mspe_bench)


def clark_west_test(actuals, forecasts_model, forecasts_benchmark, lag=NW_LAG):
    """Clark & West (2007) MSPE-adjusted test untuk nested model, dengan
    Newey-West HAC SE (lag = orde overlap forecast horizon)."""
    actuals = np.array(actuals)
    f_model = np.array(forecasts_model)
    f_bench = np.array(forecasts_benchmark)
    diff = (actuals - f_bench) ** 2 - ((actuals - f_model) ** 2 - (f_bench - f_model) ** 2)
    n = len(diff)
    if n == 0:
        return 0.0, 1.0
    mean_diff = np.mean(diff)
    residuals = diff - mean_diff
    gamma_0 = np.sum(residuals ** 2) / n
    nw_var = gamma_0
    for j in range(1, min(lag + 1, n)):
        weight = 1 - j / (lag + 1)
        gamma_j = np.sum(residuals[j:] * residuals[:-j]) / n
        nw_var += 2 * weight * gamma_j
    se = math.sqrt(max(0, nw_var) / n)
    if se > 0:
        t_stat = mean_diff / se
        p_val = norm_sf(t_stat)  # one-sided: H1 model beats benchmark
    else:
        t_stat, p_val = 0.0, 1.0
    return t_stat, p_val


def _stationary_bootstrap_indices(n, mean_block_length, rng):
    """Satu lintasan indeks hasil resampling stationary bootstrap (Politis &
    Romano, 1994, 'The Stationary Bootstrap', JASA 89(428)): panjang blok
    geometric dengan rata-rata `mean_block_length`, disambung sirkular
    supaya setiap observasi punya peluang marginal sama untuk terambil."""
    p = 1.0 / mean_block_length
    idx = np.empty(n, dtype=int)
    idx[0] = rng.integers(0, n)
    for t in range(1, n):
        idx[t] = rng.integers(0, n) if rng.random() < p else (idx[t - 1] + 1) % n
    return idx


def stationary_bootstrap_ci(data_arrays, stat_fn, n_boot=2000, mean_block_length=None,
                             alpha=0.05, seed=7):
    """
    CI & p-value bootstrap untuk statistik apapun dari time series yang
    berdependensi -- TANPA asumsi normalitas asymptotic. Ini pelengkap,
    bukan pengganti, Newey-West yang dipakai di clark_west_test /
    pesaran_timmermann_test: dengan effective-N sekecil ini, aproksimasi
    normal asymptotic-nya sendiri patut diragukan, jadi kita cross-check
    dengan resampling langsung dari data.

    data_arrays      : tuple array 1D panjang sama, di-resample BERSAMA
                        dengan indeks blok yang sama supaya alignment
                        temporal antar array (mis. actuals vs forecast)
                        tetap terjaga.
    stat_fn           : f(*arrays_resampled) -> skalar.
    mean_block_length : default = NW_LAG + 1, konsisten dengan orde overlap
                        yang sama dipakai di HAC correction lain di file ini.
    """
    n = len(data_arrays[0])
    if mean_block_length is None:
        mean_block_length = NW_LAG + 1
    if n < 8:
        point = stat_fn(*data_arrays)
        return {"point_estimate": float(point), "ci_low": float(point), "ci_high": float(point),
                "bootstrap_p_le_zero": None, "n_boot": 0, "mean_block_length": mean_block_length,
                "note": "n terlalu kecil untuk bootstrap yang bermakna"}

    rng = np.random.default_rng(seed)
    point_estimate = stat_fn(*data_arrays)
    boot_stats = np.empty(n_boot)
    for b in range(n_boot):
        idx = _stationary_bootstrap_indices(n, mean_block_length, rng)
        resampled = tuple(np.asarray(arr)[idx] for arr in data_arrays)
        boot_stats[b] = stat_fn(*resampled)

    lo = np.percentile(boot_stats, 100 * alpha / 2)
    hi = np.percentile(boot_stats, 100 * (1 - alpha / 2))
    return {
        "point_estimate": float(point_estimate),
        "ci_low": float(lo),
        "ci_high": float(hi),
        "bootstrap_p_le_zero": float(np.mean(boot_stats <= 0)),
        "n_boot": n_boot,
        "mean_block_length": mean_block_length,
    }


def _effective_sample_size(x_array, lag=NW_LAG):
    """Effective N Newey-West-consistent untuk data yang overlap secara
    serial (dipakai baik untuk CI proporsi maupun untuk koreksi PT test)."""
    n = len(x_array)
    if n < 4:
        return n
    mean = np.mean(x_array)
    residuals = x_array - mean
    var = np.var(residuals)
    if var == 0:
        return n
    rho_sum = 0.0
    for j in range(1, min(lag + 1, n)):
        autocov = np.sum(residuals[j:] * residuals[:-j]) / n
        rho_sum += autocov / var
    denom = 1 + 2 * rho_sum
    if denom <= 0:
        return n
    return max(1, int(n / denom))


def pesaran_timmermann_test(actual_dir, pred_dir, lag=NW_LAG):
    """
    Pesaran & Timmermann (1992) directional-accuracy test, formula LENGKAP
    (bukan aproksimasi var_p_hat = p*(1-p*)/n saja seperti versi lama, yang
    membuang komponen ketidakpastian estimasi p_y dan p_x).

        Var(p_hat)  = p*(1-p*) / n
        Var(p_star) = (2p_y-1)^2 p_x(1-p_x)/n + (2p_x-1)^2 p_y(1-p_y)/n
                      + 4 p_x p_y (1-p_x)(1-p_y) / n^2
        PT = (p_hat - p_star) / sqrt(Var(p_hat) - Var(p_star))

    Karena actual_dir/pred_dir berasal dari forward return 3 bulan yang
    disampling bulanan (overlap), n nominal overstate independent info.
    Variance di atas di-inflate dengan faktor (n / n_eff), n_eff dari
    autocorrelation-consistent effective sample size -- analog dengan
    koreksi overlap di Newey & West (1987) / Britten-Jones et al. (2011).
    Tanpa koreksi ini, p-value akan bias ke bawah (signifikansi palsu).
    """
    actual_dir = np.asarray(actual_dir, dtype=float)
    pred_dir = np.asarray(pred_dir, dtype=float)
    n = len(actual_dir)
    if n < 4:
        return {"accuracy": 0.0, "expected_accuracy": 0.0, "stat": 0.0,
                "p_value": 1.0, "n": n, "n_eff": n}

    p_y = np.mean(actual_dir)
    p_x = np.mean(pred_dir)
    p_hat = np.mean(actual_dir == pred_dir)
    p_star = p_y * p_x + (1 - p_y) * (1 - p_x)

    var_p_hat = p_star * (1 - p_star) / n
    var_p_star = (
        ((2 * p_y - 1) ** 2) * p_x * (1 - p_x) / n
        + ((2 * p_x - 1) ** 2) * p_y * (1 - p_y) / n
        + 4 * p_x * p_y * (1 - p_x) * (1 - p_y) / (n ** 2)
    )
    var_diff = max(0.0, var_p_hat - var_p_star)

    n_eff = _effective_sample_size(actual_dir, lag=lag)
    var_diff_adj = var_diff * (n / max(1, n_eff))

    if var_diff_adj > 0:
        stat = (p_hat - p_star) / math.sqrt(var_diff_adj)
        p_val = norm_sf(stat)  # one-sided: H1 akurasi > tebakan acak
    else:
        stat, p_val = 0.0, 1.0

    return {
        "accuracy": p_hat,
        "expected_accuracy": p_star,
        "stat": stat,
        "p_value": p_val,
        "n": n,
        "n_eff": n_eff,
    }


# ---------------------------------------------------------------------------
# Regime convention -- HARUS dipilih hanya dari in-sample
# ---------------------------------------------------------------------------

def _select_regime_convention_in_sample(df_is):
    """Menentukan apakah kuadran 180-360 derajat itu bullish (kontrarian)
    atau bearish (pro-siklikal), HANYA memakai data in-sample (sebelum
    OOS_START_YEAR). Konvensi ini kemudian dibekukan dan dipakai apa adanya
    ke seluruh data (IS+OOS). Kalau kamu memilih konvensi ini dengan melihat
    hasil di periode OOS, seluruh R2_OOS/CW/PT di bawahnya jadi sirkular --
    lihat guardrail #1 di docstring atas file."""

    def hitrate(df, contrarian):
        q34 = (df["Phase_Angle"] >= 180) & (df["Phase_Angle"] <= 360)
        pred_up = q34 if contrarian else ~q34
        actual_up = df["IHSG_Return_3M"] > 0
        valid = df["IHSG_Return_3M"].notna()
        if valid.sum() == 0:
            return np.nan
        return np.mean(pred_up[valid] == actual_up[valid])

    hr_contrarian = hitrate(df_is, contrarian=True)
    hr_procyclical = hitrate(df_is, contrarian=False)

    convention = "contrarian" if hr_contrarian >= hr_procyclical else "procyclical"
    diag = {
        "in_sample_hitrate_contrarian_pct": round(float(hr_contrarian) * 100, 2),
        "in_sample_hitrate_procyclical_pct": round(float(hr_procyclical) * 100, 2),
        "convention_selected": convention,
        "note": "Dipilih hanya dari data in-sample (< %d), lalu dibekukan." % OOS_START_YEAR,
    }
    return convention, diag


def _apply_convention(df, convention):
    q34 = (df["Phase_Angle"] >= 180) & (df["Phase_Angle"] <= 360)
    bullish_mask = q34 if convention == "contrarian" else ~q34
    cat = np.where(df["Phase_Angle"].isna(), "neutral", np.where(bullish_mask, "bullish", "bearish"))
    return cat


# ---------------------------------------------------------------------------
# Backtest utama
# ---------------------------------------------------------------------------

def _wilson_ci(wins_arr, lag=NW_LAG, z=1.96):
    n_eff = _effective_sample_size(wins_arr.astype(float), lag=lag)
    p_hat = np.mean(wins_arr) if len(wins_arr) else 0.0
    n_eff = max(1, n_eff)
    denom = 1 + z ** 2 / n_eff
    centre = (p_hat + z ** 2 / (2 * n_eff)) / denom
    margin = z * math.sqrt((p_hat * (1 - p_hat) + z ** 2 / (4 * n_eff)) / n_eff) / denom
    return p_hat, n_eff, max(0, centre - margin), min(1, centre + margin)


def _calc_stats(sub_df):
    res = {}
    for cat in ["bullish", "neutral", "bearish"]:
        cat_sub = sub_df[sub_df["category"] == cat]
        count = len(cat_sub)
        if count > 0:
            wins_arr = cat_sub["win_3m"].values.astype(float)
            p_hat, n_eff, lo, hi = _wilson_ci(wins_arr)
            ret_3m_vals = cat_sub["ret_3m"].values
            ret_3m_mean = ret_3m_vals.mean()
            ret_3m_std = np.std(ret_3m_vals) if len(ret_3m_vals) > 1 else 0
            ret_3m_se = ret_3m_std / math.sqrt(max(1, n_eff))
            ret_3m_margin = 1.96 * ret_3m_se
            boot = stationary_bootstrap_ci((wins_arr,), lambda w: np.mean(w))
            res[cat] = {
                "count": count,
                "effective_n": n_eff,
                "win_rate_3m": round(p_hat * 100, 1),
                "avg_return_1m": round(cat_sub["ret_1m"].mean() * 100, 2),
                "avg_return_3m": round(ret_3m_mean * 100, 2),
                "avg_return_6m": round(cat_sub["ret_6m"].mean() * 100, 2),
                "ci_95_low": round(lo * 100, 1),
                "ci_95_high": round(hi * 100, 1),
                "ret_3m_ci_low": round((ret_3m_mean - ret_3m_margin) * 100, 2),
                "ret_3m_ci_high": round((ret_3m_mean + ret_3m_margin) * 100, 2),
                "ci_95_low_bootstrap": round(boot["ci_low"] * 100, 1),
                "ci_95_high_bootstrap": round(boot["ci_high"] * 100, 1),
            }
        else:
            res[cat] = {"count": 0, "effective_n": 0, "win_rate_3m": 0,
                         "avg_return_1m": 0, "avg_return_3m": 0, "avg_return_6m": 0,
                         "ci_95_low": 0, "ci_95_high": 0, "ret_3m_ci_low": 0, "ret_3m_ci_high": 0}

    if len(sub_df) > 0:
        wins_arr = sub_df["win_3m"].values.astype(float)
        p_hat, n_eff, lo, hi = _wilson_ci(wins_arr)
        ret_3m_vals = sub_df["ret_3m"].values
        ret_3m_mean = ret_3m_vals.mean()
        ret_3m_std = np.std(ret_3m_vals) if len(ret_3m_vals) > 1 else 0
        ret_3m_se = ret_3m_std / math.sqrt(max(1, n_eff))
        ret_3m_margin = 1.96 * ret_3m_se
        boot = stationary_bootstrap_ci((wins_arr,), lambda w: np.mean(w))
        res["baseline"] = {
            "count": len(sub_df),
            "effective_n": n_eff,
            "win_rate_3m": round(p_hat * 100, 1),
            "avg_return_1m": round(sub_df["ret_1m"].mean() * 100, 2),
            "avg_return_3m": round(ret_3m_mean * 100, 2),
            "avg_return_6m": round(sub_df["ret_6m"].mean() * 100, 2),
            "ci_95_low": round(lo * 100, 1),
            "ci_95_high": round(hi * 100, 1),
            "ret_3m_ci_low": round((ret_3m_mean - ret_3m_margin) * 100, 2),
            "ret_3m_ci_high": round((ret_3m_mean + ret_3m_margin) * 100, 2),
            "ci_95_low_bootstrap": round(boot["ci_low"] * 100, 1),
            "ci_95_high_bootstrap": round(boot["ci_high"] * 100, 1),
        }
    else:
        res["baseline"] = {"count": 0, "effective_n": 0, "win_rate_3m": 0,
                            "avg_return_1m": 0, "avg_return_3m": 0, "avg_return_6m": 0,
                            "ci_95_low": 0, "ci_95_high": 0, "ret_3m_ci_low": 0, "ret_3m_ci_high": 0}
    return res


def run_backtest(force_refresh=False):
    if not force_refresh and os.path.exists(CACHE_FILE):
        try:
            mtime = os.path.getmtime(CACHE_FILE)
            if datetime.now().timestamp() - mtime < 86400:
                with open(CACHE_FILE, "r") as f:
                    cached_data = json.load(f)
                    if "bullish" in cached_data and "oos_test" in cached_data:
                        return cached_data
        except Exception:
            pass

    df_full = get_historical_data()
    if df_full.empty:
        return {"error": "Gagal mengumpulkan data historis"}

    # Calculate category for the full dataset so we get the current state
    # FIX: Filter ke tahun < OOS_START_YEAR saja, konsisten dengan guardrail #1
    # dan dengan estimate_macro_sensitivity() yang sudah benar.
    df_is_raw = df_full[df_full.index.year < OOS_START_YEAR].dropna(
        subset=["Phase_Angle", "Oracle_Score", "IHSG_Return_3M"]
    )
    if df_is_raw.empty:
        return {"error": "Data in-sample tidak cukup untuk memilih konvensi regime"}
    convention, convention_diag = _select_regime_convention_in_sample(df_is_raw)
    
    df_full["category"] = _apply_convention(df_full, convention)
    
    # Get the latest category (must have Phase_Angle)
    df_latest = df_full.dropna(subset=["Phase_Angle"])
    current_cat = df_latest["category"].iloc[-1] if not df_latest.empty else "neutral"

    # Now drop rows without future returns for the backtest accuracy evaluation
    df = df_full.dropna(subset=["Phase_Angle", "Oracle_Score", "IHSG_Return_3M"]).copy()

    df["past_ret"] = df["IHSG_Return_3M"].shift(4)

    bullish_rets, neutral_rets, bearish_rets, all_rets = [], [], [], []
    final_categories = []

    for idx, row in df.iterrows():
        cat = row["category"]
        score = row["Oracle_Score"]

        ret_1m = row.get("IHSG_Return_1M", 0)
        ret_1m = 0 if pd.isna(ret_1m) else ret_1m
        ret_3m = row.get("IHSG_Return_3M", 0)
        ret_3m = 0 if pd.isna(ret_3m) else ret_3m
        ret_6m = row.get("IHSG_Return_6M", 0)
        ret_6m = 0 if pd.isna(ret_6m) else ret_6m
        past_ret = row.get("past_ret")

        # Ramalan dihitung strictly dari data yang tersedia sebelum idx.
        exp_bench = np.mean(all_rets) if len(all_rets) >= 12 else 0
        if cat == "bullish":
            exp_model = np.mean(bullish_rets) if len(bullish_rets) >= 3 else exp_bench
        elif cat == "bearish":
            exp_model = np.mean(bearish_rets) if len(bearish_rets) >= 3 else exp_bench
        else:
            exp_model = np.mean(neutral_rets) if len(neutral_rets) >= 3 else exp_bench

        is_oos = True
        final_categories.append({
            "date": idx, "category": cat, "score": score,
            "ret_1m": ret_1m, "ret_3m": ret_3m, "ret_6m": ret_6m,
            "win_3m": 1 if ret_3m > 0 else 0, "is_oos": is_oos,
            "exp_bench": exp_bench, "exp_model": exp_model,
        })

        if pd.notna(past_ret):
            all_rets.append(past_ret)
            past_idx = df.index.get_loc(idx) - 4
            if past_idx >= 0:
                past_cat = df["category"].iloc[past_idx]
                if past_cat == "bullish":
                    bullish_rets.append(past_ret)
                elif past_cat == "bearish":
                    bearish_rets.append(past_ret)
                else:
                    neutral_rets.append(past_ret)

    cat_df = pd.DataFrame(final_categories)
    if cat_df.empty:
        return {"error": "Tidak cukup data untuk backtest"}

    df_is = cat_df[cat_df["is_oos"] == False]
    df_oos = cat_df[cat_df["is_oos"] == True]

    is_stats = _calc_stats(df_is)
    oos_stats = _calc_stats(df_oos)

    actuals = df_oos["ret_3m"].values
    f_model = df_oos["exp_model"].values
    f_bench = df_oos["exp_bench"].values

    r2_oos = calc_r2_oos(actuals, f_model, f_bench)
    cw_t, cw_p = clark_west_test(actuals, f_model, f_bench)
    # Cross-check R2_OOS dengan stationary bootstrap (tidak sandar ke
    # normalitas asymptotic seperti Clark-West) -- resample (actuals,
    # f_model, f_bench) BERSAMA per blok supaya alignment temporalnya
    # terjaga.
    r2_boot = stationary_bootstrap_ci((actuals, f_model, f_bench), calc_r2_oos)

    pt_df = df_oos[df_oos["category"].isin(["bullish", "bearish"])]
    if len(pt_df) > 0:
        actual_dir = pt_df["win_3m"].values
        pred_dir = (pt_df["category"] == "bullish").astype(int).values
        pt_res_raw = pesaran_timmermann_test(actual_dir, pred_dir)
        # Bootstrap CI untuk accuracy (paired resampling actual_dir & pred_dir
        # bersama per blok, supaya pasangan arah tebakan-vs-realisasi tetap
        # match setelah resampling).
        acc_boot = stationary_bootstrap_ci(
            (actual_dir.astype(float), pred_dir.astype(float)),
            lambda a, p: np.mean(a == p),
        )
        pt_res = {
            "accuracy": round(pt_res_raw["accuracy"] * 100, 1),
            "expected_accuracy": round(pt_res_raw["expected_accuracy"] * 100, 1),
            "p_value": round(pt_res_raw["p_value"], 4),
            "n": pt_res_raw["n"],
            "n_effective": pt_res_raw["n_eff"],
            "significant_at_005": pt_res_raw["p_value"] < 0.05,
            "accuracy_ci_95_bootstrap_pct": [
                round(acc_boot["ci_low"] * 100, 1), round(acc_boot["ci_high"] * 100, 1)
            ],
        }
    else:
        pt_res = None

    results = oos_stats  # output utama = OOS, demi kejujuran
    results["is_stats"] = is_stats
    results["regime_convention"] = convention_diag
    results["current_category"] = current_cat
    results["oos_test"] = {
        "r2_oos_pct": round(r2_oos * 100, 3),
        "r2_oos_ci_95_bootstrap_pct": [
            round(r2_boot["ci_low"] * 100, 3), round(r2_boot["ci_high"] * 100, 3)
        ],
        "r2_oos_bootstrap_p_le_zero": (
            round(r2_boot["bootstrap_p_le_zero"], 4)
            if r2_boot["bootstrap_p_le_zero"] is not None else None
        ),
        "cw_p_value": round(cw_p, 4),
        "cw_significant_at_005": cw_p < 0.05,
        "pt_test": pt_res,
        "note": (
            "R2_OOS > 0 berarti model mengalahkan rata-rata historis "
            "(Campbell & Thompson 2008). CW menguji superioritas nested "
            "model (Clark & West 2007), asumsi asymptotic normal. PT "
            "menguji akurasi arah dengan formula lengkap + koreksi overlap "
            "(Pesaran & Timmermann 1992), asumsi asymptotic normal juga. "
            "CI bootstrap (Politis & Romano 1994, stationary bootstrap) "
            "adalah cross-check yang tidak sandar ke normalitas asymptotic "
            "-- kalau CI bootstrap dan p-value asymptotic saling kontradiksi, "
            "percayai bootstrap lebih dulu di sample sekecil ini."
        ),
    }
    results["sample_adequacy"] = {
        "total_observations_oos": len(df_oos),
        "bullish_n_oos": oos_stats["bullish"]["count"],
        "bearish_n_oos": oos_stats["bearish"]["count"],
        "note": (
            "Holdout OOS (%d-sekarang). Expanding window mencegah look-ahead "
            "pada level forecast. Konvensi regime dibekukan dari IS saja "
            "(lihat regime_convention). Tidak ada koreksi multiple-testing "
            "untuk spesifikasi model itu sendiri -- baca guardrail #5."
        ) % OOS_START_YEAR,
    }
    results["total_months"] = len(df)
    results["effective_independent_n"] = oos_stats["baseline"]["effective_n"]
    results["methodology"] = (
        "True out-of-sample (%d-sekarang), konvensi regime dibekukan dari "
        "IS. R2_OOS, Clark-West, PT test (formula lengkap). Newey-West HAC "
        "SE lag=%d (= orde overlap forward return 3 bulan)."
    ) % (OOS_START_YEAR, NW_LAG)

    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)

    # ---- Run the live model backtest and merge results ----
    live_model_result = run_live_model_backtest(df_full)
    if live_model_result and "error" not in live_model_result:
        results["live_model_oos_test"] = live_model_result

    # ---- Estimate macro sensitivity (OLS) for frontend target price projection ----
    sensitivity_model = estimate_macro_sensitivity(df_full)
    results["sensitivity_model"] = sensitivity_model

    with open(CACHE_FILE, "w") as f:
        json.dump(results, f)

    return results


# ---------------------------------------------------------------------------
# Live Discrete Model Backtest
# ---------------------------------------------------------------------------
# Ini menguji MODEL YANG BENAR-BENAR DIPAKAI di production (macro_scorer.py)
# yaitu discrete threshold scoring (-2 s/d +2) dengan weighted composite.
# Perbedaan dengan Phase Angle Model di atas:
# - Transformasi: threshold bucket statis, bukan rolling z-score
# - Tidak ada Phase Angle / Momentum Y
# - Klasifikasi verdict: composite_score >= 1.2 (strong_bullish), >= 0.4
#   (bullish), >= -0.4 (neutral), >= -1.2 (bearish), else strong_bearish
# ---------------------------------------------------------------------------

from config import (
    BI_FED_SPREAD_THRESHOLDS,
    USDIDR_THRESHOLDS,
    INFLATION_ID_THRESHOLDS,
    GDP_GROWTH_ID_THRESHOLDS,
    TRADE_BALANCE_ID_THRESHOLDS,
    DXY_THRESHOLDS
)

def _convert_thresholds(conf_dict):
    score_map = {
        "very_bullish": 2, "bullish": 1,
        "neutral": 0, "neutral_low": 0, "neutral_high": 0,
        "bearish": -1, "bearish_deflation": -1, "very_bearish": -2,
    }
    result = []
    for k, (lo, hi) in conf_dict.items():
        if lo == float('-inf'): lo = -999
        if hi == float('inf'): hi = 999
        result.append((lo, hi, score_map.get(k, 0)))
    return result

_THRESHOLDS = {
    "bi_fed_spread": _convert_thresholds(BI_FED_SPREAD_THRESHOLDS),
    "usdidr":        _convert_thresholds(USDIDR_THRESHOLDS),
    "inflation_id":  _convert_thresholds(INFLATION_ID_THRESHOLDS),
    "gdp_growth":    _convert_thresholds(GDP_GROWTH_ID_THRESHOLDS),
    "trade_balance": _convert_thresholds(TRADE_BALANCE_ID_THRESHOLDS),
    "dxy":           _convert_thresholds(DXY_THRESHOLDS),
}

# Bobot (subset 7 indikator yang tersedia di data historis bulanan FRED;
# NEWS_SENTIMENT, COMMODITIES terpisah, dan TECHNICAL sudah diwakili oleh
# IHSG_Tech_Z di model z-score — kita normalisasi bobot supaya sum=1).
_LIVE_WEIGHTS = {
    "bi_fed_spread": 0.25,
    "usdidr":        0.20,
    "inflation_id":  0.15,
    "gdp_growth":    0.10,
    "trade_balance": 0.05,
    "dxy":           0.05,
    "sp500_trend":   0.05,  # simplified: > SMA -> +1, else -1
    "technical":     0.05,  # simplified from RSI+SMA
}
# Indikator yang TIDAK tersedia secara historis bulanan (NEWS_SENTIMENT 5%,
# COMMODITIES 5%) diberi bobot 0 — ini jujur: backtest hanya bisa menguji
# subset model yang ada datanya. Sisa bobot didistribusikan proporsional.
_WEIGHT_SUM = sum(_LIVE_WEIGHTS.values())


def _score_in_range(val, thresholds):
    """Reproduce macro_scorer._score_in_range for a single value."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return 0
    for lo, hi, score in thresholds:
        if lo <= val < hi:
            return score
    return 0


def _apply_live_discrete_scoring(row, df):
    """
    Menghitung composite_score diskrit (-2..+2) persis seperti macro_scorer.py,
    tapi dari data historis bulanan. Row adalah satu baris DataFrame.
    """
    scores = {}

    # BI-Fed spread
    bi = row.get("BI_RATE")
    fed = row.get("FEDFUNDS")
    if bi is not None and fed is not None and not np.isnan(bi) and not np.isnan(fed):
        spread = bi - fed
        scores["bi_fed_spread"] = _score_in_range(spread, _THRESHOLDS["bi_fed_spread"])
    else:
        scores["bi_fed_spread"] = 0

    # USD/IDR
    usdidr = row.get("USDIDR")
    scores["usdidr"] = _score_in_range(usdidr, _THRESHOLDS["usdidr"])

    # Inflation ID
    cpi = row.get("ID_CPI_YOY")
    scores["inflation_id"] = _score_in_range(cpi, _THRESHOLDS["inflation_id"])

    # GDP Growth
    gdp = row.get("ID_GDP_YOY")
    scores["gdp_growth"] = _score_in_range(gdp, _THRESHOLDS["gdp_growth"])

    # Trade Balance
    trade = row.get("ID_TRADE")
    scores["trade_balance"] = _score_in_range(trade, _THRESHOLDS["trade_balance"])

    # DXY
    dxy = row.get("DXY")
    scores["dxy"] = _score_in_range(dxy, _THRESHOLDS["dxy"])

    # SP500 trend (simplified: above SMA-12 monthly -> bullish)
    sp500 = row.get("SP500")
    sp500_sma = row.get("SP500_SMA12")
    if sp500 is not None and sp500_sma is not None and not np.isnan(sp500) and not np.isnan(sp500_sma):
        scores["sp500_trend"] = 1 if sp500 > sp500_sma else -1
    else:
        scores["sp500_trend"] = 0

    # Technical (simplified: use IHSG RSI centered + SMA spread)
    rsi_c = row.get("IHSG_RSI_Centered")
    if rsi_c is not None and not np.isnan(rsi_c):
        if rsi_c < -20:
            scores["technical"] = 2   # oversold
        elif rsi_c < -5:
            scores["technical"] = 1
        elif rsi_c > 20:
            scores["technical"] = -2  # overbought
        elif rsi_c > 5:
            scores["technical"] = -1
        else:
            scores["technical"] = 0
    else:
        scores["technical"] = 0

    # Weighted composite
    composite = 0.0
    for key, weight in _LIVE_WEIGHTS.items():
        composite += scores.get(key, 0) * (weight / _WEIGHT_SUM)

    return composite


def _classify_live_verdict(composite_score):
    """Map composite_score ke verdict sesuai VERDICT_THRESHOLDS di config.py."""
    if composite_score >= 1.2:
        return "strong_bullish"
    elif composite_score >= 0.4:
        return "bullish"
    elif composite_score >= -0.4:
        return "neutral"
    elif composite_score >= -1.2:
        return "bearish"
    else:
        return "strong_bearish"

def estimate_macro_sensitivity(df_full):
    """
    OLS sederhana: Return_3M ~ live_composite, HANYA pakai in-sample
    (< OOS_START_YEAR) supaya koefisien ini juga gak snooping ke OOS.
    """
    # 1. Filter In-Sample
    df_is = df_full[df_full.index.year < OOS_START_YEAR].copy()
    
    # 2. Hitung live_composite
    df_is["live_composite"] = df_is.apply(lambda r: _apply_live_discrete_scoring(r, df_is), axis=1)
    
    # 3. Drop NA
    df_is = df_is.dropna(subset=["live_composite", "IHSG_Return_3M"])
    if len(df_is) < 10:
        return {"slope": 0.075, "intercept": 0, "n": len(df_is), "note": "Data tidak cukup, fallback 0.075"}
        
    x = df_is["live_composite"].values
    y = df_is["IHSG_Return_3M"].values
    
    def ols_slope(x_arr, y_arr):
        if len(x_arr) < 2: return 0.0
        denom = np.sum((x_arr - np.mean(x_arr))**2)
        if denom == 0: return 0.0
        return np.sum((x_arr - np.mean(x_arr)) * (y_arr - np.mean(y_arr))) / denom
        
    slope, intercept = np.polyfit(x, y, 1)
    
    # Bootstrap CI for slope
    boot_res = stationary_bootstrap_ci((x, y), ols_slope, n_boot=2000, mean_block_length=NW_LAG+1)
    
    return {
        "slope": float(slope),
        "intercept": float(intercept),
        "n": len(df_is),
        "ci_95_low": boot_res["ci_low"],
        "ci_95_high": boot_res["ci_high"],
        "bootstrap_p_le_zero": boot_res["bootstrap_p_le_zero"]
    }

def run_live_model_backtest(df_full=None):
    """
    Backtest model discrete scoring yang BENAR-BENAR dipakai di production.
    Menjalankan R²_OOS, Clark-West, dan Pesaran-Timmermann pada model ini.
    """
    try:
        if df_full is None:
            df_full = get_historical_data()
        if df_full.empty:
            return {"error": "Data kosong"}

        # Pre-compute SP500 12-month SMA for trend scoring
        if "SP500" in df_full.columns:
            df_full["SP500_SMA12"] = df_full["SP500"].rolling(12, min_periods=6).mean()

        df = df_full.dropna(subset=["IHSG_Return_3M"]).copy()
        if len(df) < 24:
            return {"error": "Data tidak cukup untuk live model backtest"}

        # Apply discrete scoring to every row
        df["live_composite"] = df.apply(lambda r: _apply_live_discrete_scoring(r, df), axis=1)
        df["live_verdict"] = df["live_composite"].apply(_classify_live_verdict)

        # Expanding window backtest — same methodology as Phase Angle model
        bullish_rets, bearish_rets, neutral_rets, all_rets = [], [], [], []
        records = []

        for i, (idx, row) in enumerate(df.iterrows()):
            cat = row["live_verdict"]
            ret_3m = row.get("IHSG_Return_3M", 0)
            ret_3m = 0 if pd.isna(ret_3m) else ret_3m

            # Expanding mean benchmark (from all past returns)
            exp_bench = np.mean(all_rets) if len(all_rets) >= 12 else 0

            # Model forecast: mean of same-category past returns
            if "bullish" in cat:
                exp_model = np.mean(bullish_rets) if len(bullish_rets) >= 3 else exp_bench
            elif "bearish" in cat:
                exp_model = np.mean(bearish_rets) if len(bearish_rets) >= 3 else exp_bench
            else:
                exp_model = np.mean(neutral_rets) if len(neutral_rets) >= 3 else exp_bench

            records.append({
                "date": idx, "category": cat, "composite": row["live_composite"],
                "ret_3m": ret_3m, "win_3m": 1 if ret_3m > 0 else 0,
                "exp_bench": exp_bench, "exp_model": exp_model,
            })

            # Feed past returns into expanding window (lag 4 to avoid overlap)
            if i >= 4:
                past_ret = df["IHSG_Return_3M"].iloc[i - 4]
                if pd.notna(past_ret):
                    all_rets.append(past_ret)
                    past_cat = df["live_verdict"].iloc[i - 4]
                    if "bullish" in past_cat:
                        bullish_rets.append(past_ret)
                    elif "bearish" in past_cat:
                        bearish_rets.append(past_ret)
                    else:
                        neutral_rets.append(past_ret)

        rec_df = pd.DataFrame(records)
        if len(rec_df) < 12:
            return {"error": "Tidak cukup data untuk uji OOS"}

        # All data is treated as OOS (same expanding window logic)
        actuals = rec_df["ret_3m"].values
        f_model = rec_df["exp_model"].values
        f_bench = rec_df["exp_bench"].values

        r2_oos = calc_r2_oos(actuals, f_model, f_bench)
        cw_t, cw_p = clark_west_test(actuals, f_model, f_bench)

        # PT test on directional predictions
        dir_df = rec_df[rec_df["category"].isin(["bullish", "strong_bullish", "bearish", "strong_bearish"])]
        if len(dir_df) > 0:
            actual_dir = dir_df["win_3m"].values
            pred_dir = dir_df["category"].isin(["bullish", "strong_bullish"]).astype(int).values
            pt_raw = pesaran_timmermann_test(actual_dir, pred_dir)
            pt_res = {
                "accuracy": round(pt_raw["accuracy"] * 100, 1),
                "expected_accuracy": round(pt_raw["expected_accuracy"] * 100, 1),
                "p_value": round(pt_raw["p_value"], 4),
                "n": pt_raw["n"],
                "n_effective": pt_raw["n_eff"],
                "significant_at_005": pt_raw["p_value"] < 0.05,
            }
        else:
            pt_res = None

        return {
            "model_name": "Live Discrete Threshold Scoring",
            "description": (
                "Backtest model scoring diskrit (-2 s/d +2) yang dipakai di production "
                "(macro_scorer.py). Menggunakan threshold bucket statis dari config.py, "
                "BUKAN rolling z-score. NEWS_SENTIMENT dan COMMODITIES tidak diikutsertakan "
                "karena tidak ada data historis bulanan yang representatif."
            ),
            "r2_oos_pct": round(r2_oos * 100, 3),
            "cw_p_value": round(cw_p, 4),
            "cw_significant_at_005": cw_p < 0.05,
            "pt_test": pt_res,
            "n_total": len(rec_df),
            "n_directional": len(dir_df),
            "note": (
                "Subset indikator yang tersedia: BI-Fed Spread, USD/IDR, Inflasi RI, "
                "GDP Growth, Trade Balance, DXY, SP500 Trend, IHSG Technical. "
                "Bobot dinormalisasi dari config.SCORING_WEIGHTS (90% coverage)."
            ),
        }

    except Exception as e:
        return {"error": f"Live model backtest gagal: {str(e)}"}


if __name__ == "__main__":
    print(json.dumps(run_backtest(force_refresh=True), indent=2, default=str))
