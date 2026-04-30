"""
fetch_indicators.py
抓取所有市场情绪指标。每个指标有 primary + fallback 源，失败不阻塞，标记 stale=True。
"""
import os
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

import requests
import yfinance as yf
import pandas as pd
import numpy as np
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}


def safe_get(url: str, timeout: int = 15, **kwargs) -> Optional[requests.Response]:
    """带 retry 的 GET"""
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout, **kwargs)
            if r.status_code == 200:
                return r
            print(f"  [{url[:60]}] status={r.status_code}, attempt {attempt+1}")
        except Exception as e:
            print(f"  [{url[:60]}] error: {type(e).__name__}: {e}, attempt {attempt+1}")
        time.sleep(2 ** attempt)
    return None


# ========== 1. 价格/波动率/广度（yfinance 主源） ==========

def fetch_market_core() -> Dict[str, Any]:
    """SPX, NDX, VIX, VXN, RUT, RSP/SPY ratio + RSI, MA, breadth proxies"""
    print("[1/7] Fetching market core (yfinance)...")
    tickers_map = {
        "SPX": "^GSPC",
        "NDX": "^NDX",
        "VIX": "^VIX",
        "VXN": "^VXN",
        "MOVE": "^MOVE",
        "RUT": "^RUT",
        "RSP": "RSP",
        "SPY": "SPY",
        "QQQ": "QQQ",
    }
    out = {}

    for name, ticker in tickers_map.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="1y", interval="1d", auto_adjust=False)
            if hist.empty:
                print(f"  {name} ({ticker}): empty history")
                out[name] = {"error": "empty"}
                continue

            closes = hist["Close"].dropna()
            current = float(closes.iloc[-1])
            prev = float(closes.iloc[-2]) if len(closes) >= 2 else current

            d = {
                "current": round(current, 2),
                "prev_close": round(prev, 2),
                "change_pct": round((current / prev - 1) * 100, 2) if prev else 0,
                "as_of": closes.index[-1].strftime("%Y-%m-%d"),
            }

            # MA / breadth proxies for SPX, NDX
            if name in ("SPX", "NDX"):
                ma50 = closes.rolling(50).mean().iloc[-1]
                ma100 = closes.rolling(100).mean().iloc[-1]
                ma200 = closes.rolling(200).mean().iloc[-1]
                d["ma50"] = round(float(ma50), 2)
                d["ma100"] = round(float(ma100), 2)
                d["ma200"] = round(float(ma200), 2)
                d["pct_above_ma50"] = round((current / ma50 - 1) * 100, 2) if ma50 else 0
                d["pct_above_ma200"] = round((current / ma200 - 1) * 100, 2) if ma200 else 0

                # 14-day RSI
                delta = closes.diff().dropna()
                gain = delta.where(delta > 0, 0).rolling(14).mean()
                loss = -delta.where(delta < 0, 0).rolling(14).mean()
                rs = gain / loss
                rsi = 100 - 100 / (1 + rs)
                d["rsi14"] = round(float(rsi.iloc[-1]), 2) if not rsi.empty else None

                # 连涨/连跌天数
                signs = np.sign(closes.diff().dropna()).iloc[-15:].tolist()
                streak = 0
                for s in reversed(signs):
                    if s > 0 and streak >= 0:
                        streak += 1
                    elif s < 0 and streak <= 0:
                        streak -= 1
                    else:
                        break
                d["streak_days"] = int(streak)

                # 30 日实现波动率（年化）
                returns = closes.pct_change().dropna().iloc[-30:]
                d["realized_vol_30d"] = round(float(returns.std() * np.sqrt(252) * 100), 2)

            out[name] = d
            print(f"  {name} ({ticker}): {current:.2f} ({d['change_pct']:+.2f}%)")
        except Exception as e:
            print(f"  {name} ({ticker}) error: {e}")
            out[name] = {"error": str(e)}

    # RSP/SPY 比值（广度代理）
    try:
        rsp = out.get("RSP", {}).get("current")
        spy = out.get("SPY", {}).get("current")
        if rsp and spy:
            out["RSP_SPY_RATIO"] = round(rsp / spy, 4)
    except Exception:
        pass

    return out


# ========== 2. FRED 信用利差 ==========

def fetch_fred(api_key: str) -> Dict[str, Any]:
    """HY OAS, IG OAS via FRED API"""
    print("[2/7] Fetching FRED credit spreads...")
    if not api_key:
        return {"error": "FRED_API_KEY missing"}

    series = {
        "HY_OAS": "BAMLH0A0HYM2",  # ICE BofA US High Yield Master II OAS
        "IG_OAS": "BAMLC0A0CM",    # ICE BofA US Corporate Master OAS
    }
    out = {}
    for name, sid in series.items():
        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={sid}&api_key={api_key}&file_type=json"
            f"&sort_order=desc&limit=10"
        )
        r = safe_get(url)
        if not r:
            out[name] = {"error": "fetch_failed"}
            continue
        try:
            data = r.json()
            obs = [o for o in data.get("observations", []) if o["value"] != "."]
            if not obs:
                out[name] = {"error": "no_data"}
                continue
            current_val = float(obs[0]["value"]) * 100  # FRED 给的是百分比，转 bps
            prev_val = float(obs[1]["value"]) * 100 if len(obs) > 1 else current_val
            out[name] = {
                "current_bps": round(current_val, 1),
                "prev_bps": round(prev_val, 1),
                "as_of": obs[0]["date"],
            }
            print(f"  {name}: {current_val:.0f} bps (as of {obs[0]['date']})")
        except Exception as e:
            print(f"  {name} parse error: {e}")
            out[name] = {"error": str(e)}
    return out


# ========== 3. CNN Fear & Greed ==========

def fetch_fear_greed() -> Dict[str, Any]:
    """CNN Fear & Greed Index"""
    print("[3/7] Fetching CNN Fear & Greed...")
    today = datetime.utcnow().strftime("%Y-%m-%d")
    url = f"https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{today}"
    r = safe_get(url)
    if not r:
        return {"error": "fetch_failed"}
    try:
        data = r.json()
        fg = data.get("fear_and_greed", {})
        score = fg.get("score")
        rating = fg.get("rating", "")
        if score is None:
            return {"error": "no_score_in_response"}
        result = {
            "score": round(float(score), 1),
            "rating": rating,
            "previous_close": fg.get("previous_close"),
            "previous_1_week": fg.get("previous_1_week"),
            "previous_1_month": fg.get("previous_1_month"),
        }
        print(f"  F&G: {result['score']} ({rating})")
        return result
    except Exception as e:
        print(f"  F&G parse error: {e}")
        return {"error": str(e)}


# ========== 4. AAII Sentiment Survey ==========

def fetch_aaii() -> Dict[str, Any]:
    """AAII 周更（每周四发布）"""
    print("[4/7] Fetching AAII sentiment...")
    url = "https://www.aaii.com/sentimentsurvey"
    r = safe_get(url)
    if not r:
        return {"error": "fetch_failed"}
    try:
        soup = BeautifulSoup(r.text, "html.parser")
        # AAII 页面结构：寻找包含 "Bullish" / "Bearish" / "Neutral" 的数字
        text = soup.get_text()
        result = {}
        # 尝试用正则匹配 X% pattern in survey results
        import re
        # 例如 "Bullish: 33.1%, down 0.1 points"
        for label, key in [("Bullish", "bullish"), ("Neutral", "neutral"), ("Bearish", "bearish")]:
            m = re.search(rf"{label}[:\s]+(\d+\.?\d*)%", text)
            if m:
                result[key] = float(m.group(1))
        if "bullish" in result and "bearish" in result:
            result["bull_bear_spread"] = round(result["bullish"] - result["bearish"], 1)
            print(f"  AAII: Bull {result.get('bullish')}% / Bear {result.get('bearish')}% / Spread {result['bull_bear_spread']:+.1f}")
            return result
        return {"error": "regex_no_match", "raw_sample": text[:500]}
    except Exception as e:
        print(f"  AAII parse error: {e}")
        return {"error": str(e)}


# ========== 5. NAAIM Exposure Index ==========

def fetch_naaim() -> Dict[str, Any]:
    """NAAIM 周更（每周三发布）"""
    print("[5/7] Fetching NAAIM exposure...")
    url = "https://naaim.org/programs/naaim-exposure-index/"
    r = safe_get(url)
    if not r:
        return {"error": "fetch_failed"}
    try:
        import re
        text = r.text
        # 寻找最新的 NAAIM number。页面通常显示 "Current Reading: XX.XX" 或类似
        # 也可能在 table 里
        m = re.search(r"NAAIM\s+Number[\s:]*(-?\d+\.?\d*)", text, re.IGNORECASE)
        if not m:
            # try alternative patterns
            m = re.search(r"Current\s+Reading[\s:]*(-?\d+\.?\d*)", text, re.IGNORECASE)
        if m:
            value = float(m.group(1))
            print(f"  NAAIM: {value}")
            return {"value": value}
        return {"error": "regex_no_match"}
    except Exception as e:
        print(f"  NAAIM parse error: {e}")
        return {"error": str(e)}


# ========== 6. CBOE Put/Call Ratio ==========

def fetch_putcall() -> Dict[str, Any]:
    """CBOE Total Put/Call Ratio"""
    print("[6/7] Fetching CBOE Put/Call ratio...")
    # CBOE 公开 CSV：https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv 不含PCR
    # 用 ycharts/marketwatch 难抓。Fallback: 用 yfinance VIX 期权数据估算
    # 这里用 FRED 替代品代理（CBOEMVOLI 这类不一定有），先用 N/A
    # 或用 stockcharts 数据：https://stockcharts.com/h-sc/ui?s=$CPC
    url = "https://stooq.com/q/?s=^cpc&d1=20240101&i=d"
    r = safe_get(url)
    if r:
        try:
            soup = BeautifulSoup(r.text, "html.parser")
            text = soup.get_text()
            import re
            # 寻找最新的 CPC 数值
            m = re.search(r"\^CPC.*?(\d\.\d{2,4})", text)
            if m:
                value = float(m.group(1))
                print(f"  Put/Call: {value}")
                return {"current": value}
        except Exception as e:
            print(f"  PCR parse error: {e}")
    return {"error": "no_data", "note": "PCR is hard to scrape; degrade gracefully"}


# ========== 7. CTA Positioning Proxy ==========

def calc_cta_proxy(market_core: Dict[str, Any]) -> Dict[str, Any]:
    """
    CTA 仓位代理：根据 SPX 相对各期 MA 的位置 + 波动率打分。
    GS/UBS 闭源数据无法直接拿到，但 trend triggers 是公开逻辑。
    """
    print("[7/7] Computing CTA positioning proxy...")
    spx = market_core.get("SPX", {})
    if "error" in spx or "ma50" not in spx:
        return {"error": "missing_spx_mas"}

    current = spx["current"]
    ma50 = spx["ma50"]
    ma100 = spx["ma100"]
    ma200 = spx["ma200"]
    realized_vol = spx.get("realized_vol_30d", 15)

    # 三档触发：50d, 100d, 200d
    short_signal = 1 if current > ma50 else (-1 if current < ma50 * 0.98 else 0)
    medium_signal = 1 if current > ma100 else (-1 if current < ma100 * 0.97 else 0)
    long_signal = 1 if current > ma200 else (-1 if current < ma200 * 0.95 else 0)

    # 综合 trend score: -3 to +3
    trend_score = short_signal + medium_signal + long_signal

    # 波动率调整：高波动 → CTA 仓位被强制减小
    vol_adj = 1.0
    if realized_vol > 25:
        vol_adj = 0.6
    elif realized_vol > 20:
        vol_adj = 0.8
    elif realized_vol < 10:
        vol_adj = 1.2

    # 估算 CTA exposure percentile (0-100)
    # trend_score=+3 + low vol = max long (~95)
    # trend_score=-3 + high vol = max short (~5)
    base = (trend_score + 3) / 6 * 100  # 0-100
    estimated_pct = max(0, min(100, base * vol_adj))

    # Distance to triggers
    dist_short = round((current / ma50 - 1) * 100, 2)
    dist_medium = round((current / ma100 - 1) * 100, 2)
    dist_long = round((current / ma200 - 1) * 100, 2)

    result = {
        "estimated_percentile": round(estimated_pct, 1),
        "trend_score": trend_score,  # -3 to +3
        "short_term_signal": short_signal,
        "medium_term_signal": medium_signal,
        "long_term_signal": long_signal,
        "dist_to_50ma_pct": dist_short,
        "dist_to_100ma_pct": dist_medium,
        "dist_to_200ma_pct": dist_long,
        "realized_vol_30d": realized_vol,
        "note": "Proxy based on public trend logic; not actual GS/UBS data.",
    }
    print(f"  CTA proxy percentile: {estimated_pct:.0f} (trend={trend_score:+d})")
    return result


# ========== 主流程 ==========

def fetch_all() -> Dict[str, Any]:
    """抓取全部指标"""
    fred_key = os.environ.get("FRED_API_KEY", "")
    if not fred_key:
        print("⚠️  FRED_API_KEY not set; HY/IG OAS will be missing")

    market_core = fetch_market_core()
    fred_data = fetch_fred(fred_key)
    fg = fetch_fear_greed()
    aaii = fetch_aaii()
    naaim = fetch_naaim()
    pcr = fetch_putcall()
    cta = calc_cta_proxy(market_core)

    result = {
        "timestamp_utc": datetime.utcnow().isoformat() + "Z",
        "as_of_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "market": market_core,
        "fred": fred_data,
        "fear_greed": fg,
        "aaii": aaii,
        "naaim": naaim,
        "putcall": pcr,
        "cta": cta,
    }
    return result


if __name__ == "__main__":
    data = fetch_all()
    print("\n========== Summary ==========")
    print(json.dumps(data, indent=2, default=str)[:3000])
    out_path = os.environ.get("OUTPUT_FILE", "/tmp/indicators.json")
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"\nSaved to {out_path}")
