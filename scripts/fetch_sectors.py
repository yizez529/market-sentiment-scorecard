"""
fetch_sectors.py
批量抓所有板块 ETF 和 basket 成分的价格、MA、RSI、相对强度。
yfinance batch download 一次拿全部 ticker → 内存里聚合篮子 → 计算指标。
"""
import os
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List

import yfinance as yf
import pandas as pd
import numpy as np

from sectors_config import SECTORS, get_all_tickers


def compute_rsi(closes: pd.Series, period: int = 14) -> float:
    """14 日 RSI"""
    delta = closes.diff().dropna()
    if len(delta) < period:
        return None
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    val = rsi.iloc[-1]
    return None if pd.isna(val) else round(float(val), 2)


def compute_ma_distance(closes: pd.Series, n: int) -> float:
    """距 N 日均线偏离 %"""
    if len(closes) < n:
        return None
    ma = closes.rolling(n).mean().iloc[-1]
    if pd.isna(ma) or ma == 0:
        return None
    return round((closes.iloc[-1] / ma - 1) * 100, 2)


def compute_pct_change(closes: pd.Series, days: int) -> float:
    """N 日收益率 %"""
    if len(closes) <= days:
        return None
    past = closes.iloc[-days - 1]
    if past == 0:
        return None
    return round((closes.iloc[-1] / past - 1) * 100, 2)


def compute_basket_series(price_data: pd.DataFrame, tickers: List[str]) -> pd.Series:
    """
    等权篮子总收益时间序列。
    用每个 ticker 的 normalized close（首日=1）平均，避免高价票主导。
    """
    closes_list = []
    for t in tickers:
        if t not in price_data.columns:
            continue
        s = price_data[t].dropna()
        if len(s) < 60:  # 数据太少跳过
            continue
        normalized = s / s.iloc[0]
        closes_list.append(normalized)

    if not closes_list:
        return None

    # 对齐 index 然后取平均
    df = pd.concat(closes_list, axis=1).dropna()
    if df.empty:
        return None
    return df.mean(axis=1)


def compute_etf_metrics(closes: pd.Series, benchmark_closes: pd.Series) -> Dict[str, Any]:
    """计算单个 ETF 或 basket 的所有指标"""
    if closes is None or len(closes) < 50:
        return {"error": "insufficient_data"}

    current = float(closes.iloc[-1])
    prev = float(closes.iloc[-2]) if len(closes) >= 2 else current

    metrics = {
        "current": round(current, 2),
        "change_1d_pct": round((current / prev - 1) * 100, 2) if prev else 0,
        "ma50_dist_pct": compute_ma_distance(closes, 50),
        "ma200_dist_pct": compute_ma_distance(closes, 200),
        "rsi14": compute_rsi(closes, 14),
        "ret_5d": compute_pct_change(closes, 5),
        "ret_20d": compute_pct_change(closes, 20),
        "ret_60d": compute_pct_change(closes, 60),
    }

    # 相对强度 vs benchmark
    if benchmark_closes is not None and len(benchmark_closes) >= 60:
        # 1 个月超额（~21 日）
        if len(closes) >= 22 and len(benchmark_closes) >= 22:
            etf_1m = (closes.iloc[-1] / closes.iloc[-22] - 1) * 100
            bm_1m = (benchmark_closes.iloc[-1] / benchmark_closes.iloc[-22] - 1) * 100
            metrics["rs_1m_vs_bm"] = round(etf_1m - bm_1m, 2)
        # 3 个月超额（~63 日）
        if len(closes) >= 64 and len(benchmark_closes) >= 64:
            etf_3m = (closes.iloc[-1] / closes.iloc[-64] - 1) * 100
            bm_3m = (benchmark_closes.iloc[-1] / benchmark_closes.iloc[-64] - 1) * 100
            metrics["rs_3m_vs_bm"] = round(etf_3m - bm_3m, 2)

    return metrics


def fetch_all_sectors() -> Dict[str, Any]:
    """主流程：batch 下载所有 ticker，然后逐板块计算指标"""
    all_tickers = get_all_tickers()
    print(f"[sectors] Batch downloading {len(all_tickers)} tickers from yfinance...")

    # 一次性下载（明显比逐个 Ticker.history 快）
    end = datetime.utcnow()
    start = end - timedelta(days=400)
    try:
        data = yf.download(
            tickers=all_tickers,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval="1d",
            auto_adjust=False,
            progress=False,
            group_by="ticker",
            threads=True,
        )
    except Exception as e:
        print(f"[sectors] yfinance batch download failed: {e}")
        return {"error": f"yfinance_batch_failed: {e}", "sectors": {}}

    # 解析成 ticker -> close series 的字典
    price_data = pd.DataFrame()
    for t in all_tickers:
        try:
            if (t, "Close") in data.columns:
                price_data[t] = data[(t, "Close")]
            elif t in data.columns and "Close" in data[t].columns:
                price_data[t] = data[t]["Close"]
        except Exception:
            continue

    available = [t for t in all_tickers if t in price_data.columns and not price_data[t].isna().all()]
    print(f"[sectors] Got data for {len(available)}/{len(all_tickers)} tickers")
    missing = set(all_tickers) - set(available)
    if missing:
        print(f"[sectors] Missing: {sorted(missing)}")

    # 逐板块计算
    results = {}
    for sector in SECTORS:
        key = sector["key"]
        name = sector["name_zh"]

        # 取板块价格序列
        if sector["type"] == "etf":
            ticker = sector["ticker"]
            if ticker not in price_data.columns:
                print(f"  ⚠️  {name} ({ticker}): no data")
                results[key] = {"error": "no_data", "sector": sector}
                continue
            closes = price_data[ticker].dropna()
        else:
            tickers = sector["tickers"]
            closes = compute_basket_series(price_data, tickers)
            if closes is None:
                print(f"  ⚠️  {name} (basket): no usable data")
                results[key] = {"error": "no_basket_data", "sector": sector}
                continue

        # 取 benchmark 价格序列
        bm_ticker = sector["benchmark"]
        bm_closes = None
        if bm_ticker in price_data.columns:
            bm_closes = price_data[bm_ticker].dropna()

        metrics = compute_etf_metrics(closes, bm_closes)
        metrics["sector"] = {
            "key": key,
            "name_zh": name,
            "root": sector["root"],
            "type": sector["type"],
            "ticker_or_basket": sector.get("ticker") or "+".join(sector.get("tickers", [])),
            "components": sector["components"],
            "benchmark": bm_ticker,
        }
        results[key] = metrics

        # 摘要打印
        if "error" not in metrics:
            print(
                f"  ✓ {name:18s}: ma200 {metrics.get('ma200_dist_pct', 'N/A'):>6}% "
                f"RSI {metrics.get('rsi14', 'N/A'):>5}  "
                f"3M RS {metrics.get('rs_3m_vs_bm', 'N/A'):>6}%"
            )

    return {
        "timestamp_utc": datetime.utcnow().isoformat() + "Z",
        "as_of_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "sectors": results,
    }


if __name__ == "__main__":
    out = fetch_all_sectors()
    out_path = os.environ.get("OUTPUT_FILE", "/tmp/sectors.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\n✅ Saved to {out_path}")
    print(f"Sectors with data: {sum(1 for v in out['sectors'].values() if 'error' not in v)}/{len(out['sectors'])}")
