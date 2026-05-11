"""
fetch_fundamentals.py
为每个板块抓取基本面数据：Forward PE / EPS revision / PEG

策略：
- ETF 板块（14个）：yfinance ETF info["forwardPE"]，省 FMP 配额
- Basket 板块（12个）：FMP analyst-estimates 拿每 ticker forward EPS → 计算等权 basket forward PE
- 失败不阻塞主流程，标记 N/A
- z-score 用 sectors_pe_benchmarks 表（过渡期）或累积历史（>60 天后）
"""
import os
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

import requests
import yfinance as yf
import numpy as np

from sectors_config import SECTORS
from sectors_pe_benchmarks import get_benchmark


FMP_BASE = "https://financialmodelingprep.com/stable"
FMP_KEY = os.environ.get("FMP_API_KEY", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
}


def fmp_get(endpoint: str, params: dict = None) -> Optional[Any]:
    if not FMP_KEY:
        return None
    url = f"{FMP_BASE}/{endpoint}"
    params = params or {}
    params["apikey"] = FMP_KEY

    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=12)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                print(f"  [FMP] 429 rate limit, sleeping...")
                time.sleep(10 * (attempt + 1))
                continue
            if r.status_code in (401, 403):
                print(f"  [FMP] auth error {r.status_code}, plan may not cover this endpoint")
                return None
            print(f"  [FMP] {endpoint} status {r.status_code}: {r.text[:200]}")
            return None
        except Exception as e:
            print(f"  [FMP] {endpoint} error attempt {attempt+1}: {e}")
            time.sleep(2 ** attempt)
    return None


def get_etf_forward_pe(ticker: str) -> Optional[float]:
    """ETF forward PE from yfinance"""
    try:
        info = yf.Ticker(ticker).info
        fwd_pe = info.get("forwardPE")
        if fwd_pe and 0 < fwd_pe < 200:
            return round(float(fwd_pe), 2)
        trailing = info.get("trailingPE")
        if trailing and 0 < trailing < 200:
            return round(float(trailing), 2)
    except Exception as e:
        print(f"  [yfinance] {ticker} info failed: {e}")
    return None


def get_current_price(ticker: str) -> Optional[float]:
    try:
        t = yf.Ticker(ticker)
        try:
            return float(t.fast_info["last_price"])
        except Exception:
            hist = t.history(period="2d")
            if len(hist) > 0:
                return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return None


def get_stock_estimates_from_fmp(ticker: str) -> Optional[Dict]:
    """从 FMP 拿单股 forward EPS estimates (annual)"""
    data = fmp_get("analyst-estimates", {"symbol": ticker, "period": "annual", "limit": 4})
    if not data or not isinstance(data, list):
        return None

    today = datetime.utcnow().date()
    future_years = []
    for rec in data:
        try:
            rec_date = datetime.strptime(rec.get("date", ""), "%Y-%m-%d").date()
            if rec_date > today:
                future_years.append((rec_date, rec))
        except Exception:
            continue
    future_years.sort(key=lambda x: x[0])

    if len(future_years) < 1:
        return None

    cy_rec = future_years[0][1]
    ny_rec = future_years[1][1] if len(future_years) >= 2 else None

    return {
        "current_year_eps_avg": cy_rec.get("epsAvg"),
        "next_year_eps_avg": ny_rec.get("epsAvg") if ny_rec else None,
        "current_year_date": cy_rec.get("date"),
    }


def compute_basket_forward_pe(tickers: List[str]) -> Optional[Dict]:
    """等权篮子 forward PE / EPS growth / PEG"""
    fpes = []
    growths = []
    epss = []
    for t in tickers:
        est = get_stock_estimates_from_fmp(t)
        if not est:
            continue
        cy_eps = est.get("current_year_eps_avg")
        ny_eps = est.get("next_year_eps_avg")
        if not cy_eps or cy_eps <= 0:
            continue
        price = get_current_price(t)
        if price is None:
            continue
        fpe = price / cy_eps
        if 0 < fpe < 200:
            fpes.append(fpe)
            epss.append(cy_eps)
        if ny_eps and ny_eps > 0:
            growth = (ny_eps / cy_eps - 1) * 100
            if -100 < growth < 500:
                growths.append(growth)

    if not fpes:
        return None

    forward_pe = round(np.mean(fpes), 2)
    eps_growth = round(np.mean(growths), 2) if growths else None
    peg = None
    if eps_growth and eps_growth > 0:
        peg = round(forward_pe / eps_growth, 2)

    return {
        "forward_pe": forward_pe,
        "eps_growth_pct": eps_growth,
        "peg": peg,
        "n_tickers_with_data": len(fpes),
        "avg_eps_estimate": round(np.mean(epss), 3),
    }


def compute_pe_zscore(forward_pe: Optional[float], sector_key: str, fundamentals_history: List[Dict] = None) -> tuple:
    """返回 (z_score, source)。source = 'historical' or 'benchmark'"""
    if forward_pe is None:
        return None, None

    # 优先用累积历史 (>=60 天)
    if fundamentals_history and len(fundamentals_history) >= 60:
        sector_pes = []
        for h in fundamentals_history:
            pe = h.get("sectors", {}).get(sector_key, {}).get("forward_pe")
            if pe and 0 < pe < 200:
                sector_pes.append(pe)
        if len(sector_pes) >= 60:
            mean = np.mean(sector_pes)
            std = np.std(sector_pes)
            if std > 0:
                return round((forward_pe - mean) / std, 2), "historical"

    # Fallback: 用预设 benchmark
    bm = get_benchmark(sector_key)
    if bm and bm["std"] > 0:
        return round((forward_pe - bm["mean"]) / bm["std"], 2), "benchmark"

    return None, None


def compute_eps_revision_3m(sector_key: str, current_eps: Optional[float], fundamentals_history: List[Dict] = None) -> Optional[float]:
    """从累积历史算 3M EPS revision %"""
    if current_eps is None or not fundamentals_history:
        return None
    target_date = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d")
    closest_past = None
    for h in fundamentals_history:
        if h.get("as_of_date", "") <= target_date:
            past_eps = h.get("sectors", {}).get(sector_key, {}).get("avg_eps_estimate")
            if past_eps and past_eps > 0:
                closest_past = past_eps
    if closest_past is None or closest_past <= 0:
        return None
    return round((current_eps / closest_past - 1) * 100, 2)


def fetch_all_fundamentals(fundamentals_history: List[Dict] = None) -> Dict[str, Any]:
    print(f"[fundamentals] Starting fetch for {len(SECTORS)} sectors")
    print(f"[fundamentals] FMP key: {'✓ set' if FMP_KEY else '✗ MISSING (basket sectors will be N/A)'}")

    results = {}
    fmp_calls_used = 0

    for sector in SECTORS:
        key = sector["key"]
        name = sector["name_zh"]

        if sector["type"] == "etf":
            ticker = sector["ticker"]
            forward_pe = get_etf_forward_pe(ticker)
            results[key] = {
                "sector_key": key, "name_zh": name,
                "method": "etf_yfinance",
                "forward_pe": forward_pe,
                "eps_growth_pct": None, "peg": None,
                "avg_eps_estimate": None,
                "n_tickers_with_data": 1 if forward_pe else 0,
            }
            print(f"  {name:18s} ETF {ticker}: forward PE = {forward_pe}")
        else:
            tickers = sector["tickers"]
            data = compute_basket_forward_pe(tickers) if FMP_KEY else None
            fmp_calls_used += len(tickers)

            if data:
                results[key] = {
                    "sector_key": key, "name_zh": name,
                    "method": "basket_fmp",
                    "forward_pe": data["forward_pe"],
                    "eps_growth_pct": data["eps_growth_pct"],
                    "peg": data["peg"],
                    "avg_eps_estimate": data["avg_eps_estimate"],
                    "n_tickers_with_data": data["n_tickers_with_data"],
                }
                print(f"  {name:18s} Basket: PE={data['forward_pe']}, growth={data['eps_growth_pct']}%, PEG={data['peg']} ({data['n_tickers_with_data']}/{len(tickers)})")
            else:
                results[key] = {
                    "sector_key": key, "name_zh": name,
                    "method": "basket_fmp_failed",
                    "forward_pe": None, "eps_growth_pct": None,
                    "peg": None, "avg_eps_estimate": None,
                    "n_tickers_with_data": 0,
                    "note": "FMP failed or no FMP_KEY",
                }
                print(f"  {name:18s} Basket: FAILED")

        # z-score
        z, source = compute_pe_zscore(results[key]["forward_pe"], key, fundamentals_history)
        results[key]["forward_pe_zscore"] = z
        results[key]["zscore_source"] = source

        # EPS revision (累积历史>0 天才可能有值)
        revision = compute_eps_revision_3m(key, results[key].get("avg_eps_estimate"), fundamentals_history)
        results[key]["eps_revision_3m_pct"] = revision

    print(f"\n[fundamentals] FMP calls: ~{fmp_calls_used} (limit 250/day)")

    return {
        "timestamp_utc": datetime.utcnow().isoformat() + "Z",
        "as_of_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "sectors": results,
        "fmp_calls_used": fmp_calls_used,
        "history_days_accumulated": len(fundamentals_history) if fundamentals_history else 0,
    }


if __name__ == "__main__":
    history_path = os.environ.get("FUNDAMENTALS_HISTORY", "data/fundamentals_history.json")
    history = []
    if os.path.exists(history_path):
        try:
            with open(history_path) as f:
                history = json.load(f)
        except Exception:
            history = []

    out = fetch_all_fundamentals(history)
    out_path = os.environ.get("OUTPUT_FILE", "/tmp/fundamentals.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\n✅ Saved to {out_path}")
    print(f"Sectors with forward_pe: {sum(1 for s in out['sectors'].values() if s.get('forward_pe'))}/{len(out['sectors'])}")
