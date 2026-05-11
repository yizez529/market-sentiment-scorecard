"""
score_sectors.py
对每个板块计算 3 维度评分 → 0-100 综合分 → 7 档标签。

3 维度（Aaron 锁定）：
- 趋势 (40%)：距 200MA + 距 50MA
- 动量 (30%)：14 日 RSI + 5d/20d 变化率
- 相对强度 (30%)：vs benchmark 的 1m + 3m 超额

7 档标签（Aaron 锁定）：
- 0-15  严重超卖    🟢🟢
- 15-35 超卖/抄底候选 🟢
- 35-50 偏弱/值得观察 🔵
- 50-65 中性偏强    ⚪
- 65-80 偏强/持有   🟡
- 80-92 严重超买/减仓 🟠
- 92-100 极度超买   🔴
"""
import json
import os
from typing import Dict, Any, Tuple, List, Optional

import numpy as np

from sectors_config import SECTORS


def linear_score(value, low: float, high: float, invert: bool = False) -> float:
    """value 落在 low-high → 0-100 分（invert 时反向）"""
    if value is None:
        return 50.0
    if high == low:
        return 50.0
    pct = (value - low) / (high - low)
    pct = max(0.0, min(1.0, pct))
    s = pct * 100
    return 100 - s if invert else s


def score_trend(metrics: Dict) -> Tuple[float, Dict]:
    """趋势：距 200MA + 距 50MA"""
    components = []
    notes = {}

    ma200 = metrics.get("ma200_dist_pct")
    ma50 = metrics.get("ma50_dist_pct")

    if ma200 is not None:
        # -15% → 0 分；+15% → 100 分（板块比 SPX 极值更宽）
        s = linear_score(ma200, -15, 15)
        components.append((s, 0.6))
        notes["MA200 dist"] = f"{ma200:+.1f}% → {s:.0f}"

    if ma50 is not None:
        s = linear_score(ma50, -10, 10)
        components.append((s, 0.4))
        notes["MA50 dist"] = f"{ma50:+.1f}% → {s:.0f}"

    if not components:
        return 50.0, {"components": notes}
    total_w = sum(w for _, w in components)
    return sum(s * w for s, w in components) / total_w, {"components": notes}


def score_momentum(metrics: Dict) -> Tuple[float, Dict]:
    """动量：RSI14 + 5d + 20d 变化率"""
    components = []
    notes = {}

    rsi = metrics.get("rsi14")
    if rsi is not None:
        # RSI 25 → 0 分；75 → 100 分
        s = linear_score(rsi, 25, 75)
        components.append((s, 0.5))
        notes["RSI14"] = f"{rsi:.0f} → {s:.0f}"

    ret_5d = metrics.get("ret_5d")
    if ret_5d is not None:
        # 5 日 -8% → 0 分；+8% → 100 分
        s = linear_score(ret_5d, -8, 8)
        components.append((s, 0.2))
        notes["5d return"] = f"{ret_5d:+.1f}% → {s:.0f}"

    ret_20d = metrics.get("ret_20d")
    if ret_20d is not None:
        # 20 日 -15% → 0 分；+15% → 100 分
        s = linear_score(ret_20d, -15, 15)
        components.append((s, 0.3))
        notes["20d return"] = f"{ret_20d:+.1f}% → {s:.0f}"

    if not components:
        return 50.0, {"components": notes}
    total_w = sum(w for _, w in components)
    return sum(s * w for s, w in components) / total_w, {"components": notes}


def score_relative_strength(metrics: Dict) -> Tuple[float, Dict]:
    """相对强度：1m + 3m vs benchmark"""
    components = []
    notes = {}

    rs_1m = metrics.get("rs_1m_vs_bm")
    if rs_1m is not None:
        # -8% → 0；+8% → 100（板块跑输跑赢的常见极值）
        s = linear_score(rs_1m, -8, 8)
        components.append((s, 0.4))
        notes["1m RS"] = f"{rs_1m:+.1f}% → {s:.0f}"

    rs_3m = metrics.get("rs_3m_vs_bm")
    if rs_3m is not None:
        # -20% → 0；+20% → 100
        s = linear_score(rs_3m, -20, 20)
        components.append((s, 0.6))
        notes["3m RS"] = f"{rs_3m:+.1f}% → {s:.0f}"

    if not components:
        return 50.0, {"components": notes}
    total_w = sum(w for _, w in components)
    return sum(s * w for s, w in components) / total_w, {"components": notes}


def label_for_score(score: float) -> Dict[str, str]:
    """7 档标签"""
    if score < 15:
        return {"label": "严重超卖", "emoji": "🟢🟢", "zone": "extreme_oversold", "color": "success"}
    if score < 35:
        return {"label": "超卖/抄底候选", "emoji": "🟢", "zone": "oversold", "color": "success"}
    if score < 50:
        return {"label": "偏弱/值得观察", "emoji": "🔵", "zone": "weak", "color": "info"}
    if score < 65:
        return {"label": "中性偏强", "emoji": "⚪", "zone": "neutral_strong", "color": "default"}
    if score < 80:
        return {"label": "偏强/持有", "emoji": "🟡", "zone": "strong", "color": "warning"}
    if score < 92:
        return {"label": "严重超买/减仓", "emoji": "🟠", "zone": "severe_overbought", "color": "warning"}
    return {"label": "极度超买", "emoji": "🔴", "zone": "extreme_overbought", "color": "danger"}


WEIGHTS = {"trend": 0.4, "momentum": 0.3, "relative_strength": 0.3}


# ========== 辅助计算（per-stock 指标用，不依赖 fetch_sectors）==========

def compute_rsi(closes, period: int = 14) -> Optional[float]:
    delta = closes.diff().dropna()
    if len(delta) < period:
        return None
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    val = rsi.iloc[-1]
    return None if (hasattr(val, '__class__') and val != val) else round(float(val), 2)


def compute_ma_distance(closes, n: int) -> Optional[float]:
    if len(closes) < n:
        return None
    ma = closes.rolling(n).mean().iloc[-1]
    if ma == 0 or ma != ma:
        return None
    return round((closes.iloc[-1] / ma - 1) * 100, 2)


def compute_pct_change(closes, days: int) -> Optional[float]:
    if len(closes) <= days:
        return None
    past = closes.iloc[-days - 1]
    if past == 0:
        return None
    return round((closes.iloc[-1] / past - 1) * 100, 2)


# ========== Per-stock 评分 ==========

def score_single_stock(ticker: str, price_data) -> Optional[Dict]:
    """
    对单只股票算简化的情绪分数（RSI + MA 距离 + 20日变化率）
    返回：{ticker, rsi14, ma200_dist, ma50_dist, ret_20d, score_raw}
    """
    if ticker not in price_data.columns:
        return None
    closes = price_data[ticker].dropna()
    if len(closes) < 50:
        return None

    rsi = compute_rsi(closes, 14)
    ma200_dist = compute_ma_distance(closes, 200)
    ma50_dist = compute_ma_distance(closes, 50)
    ret_20d = compute_pct_change(closes, 20)

    # 综合极值分：RSI (0-100) + MA dist 线性映射
    rsi_score = rsi if rsi else 50
    ma200_score = linear_score(ma200_dist, -15, 15) if ma200_dist else 50
    # 简单等权综合
    raw = (rsi_score * 0.5 + ma200_score * 0.5)

    return {
        "ticker": ticker,
        "rsi14": rsi,
        "ma200_dist_pct": ma200_dist,
        "ma50_dist_pct": ma50_dist,
        "ret_20d": ret_20d,
        "score_raw": round(raw, 1),
    }


def get_top3_picks(sector_key: str, sector_score: float, key_stocks: List[str], price_data) -> List[Dict]:
    """
    根据板块分数决定"操作方向"，然后选最具代表性的 3 只。

    超买板块（>65）：选最 stretched 的 3 只（减仓候选）
      → 按 score_raw 降序，最高的最 stretched
    超卖板块（<35）：选最被砸的 3 只（买入候选）
      → 按 score_raw 升序，最低的最超卖
    中性板块（35-65）：选动量最强的 3 只（动量领涨）
      → 按 ret_20d 降序
    """
    stocks = []
    for t in key_stocks:
        info = score_single_stock(t, price_data)
        if info:
            stocks.append(info)

    if not stocks:
        return []

    if sector_score >= 65:
        # 超买 → 减仓候选 → score 最高排前
        sorted_stocks = sorted(stocks, key=lambda x: x["score_raw"], reverse=True)
        action_label = "减仓候选"
        action_emoji = "🔴"
    elif sector_score <= 35:
        # 超卖 → 买入候选 → score 最低排前
        sorted_stocks = sorted(stocks, key=lambda x: x["score_raw"])
        action_label = "买入候选"
        action_emoji = "🟢"
    else:
        # 中性 → 动量领涨 → ret_20d 最高排前
        sorted_stocks = sorted(stocks, key=lambda x: (x["ret_20d"] or -999), reverse=True)
        action_label = "动量领涨"
        action_emoji = "⚪"

    top3 = sorted_stocks[:3]
    result = []
    for s in top3:
        result.append({
            "ticker": s["ticker"],
            "rsi14": s["rsi14"],
            "ma200_dist_pct": s["ma200_dist_pct"],
            "ret_20d": s["ret_20d"],
            "score_raw": s["score_raw"],
            "action_label": action_label,
            "action_emoji": action_emoji,
        })
    return result


def score_sector(metrics: Dict) -> Dict:
    """对单板块算评分"""
    if "error" in metrics:
        return {"error": metrics["error"], "sector": metrics.get("sector", {})}

    trend_s, trend_notes = score_trend(metrics)
    momentum_s, momentum_notes = score_momentum(metrics)
    rs_s, rs_notes = score_relative_strength(metrics)

    composite = (
        trend_s * WEIGHTS["trend"]
        + momentum_s * WEIGHTS["momentum"]
        + rs_s * WEIGHTS["relative_strength"]
    )
    composite = round(composite, 1)

    label_info = label_for_score(composite)

    return {
        "sector": metrics["sector"],
        "composite": composite,
        **label_info,
        "dimensions": {
            "trend": {"score": round(trend_s, 1), "weight": WEIGHTS["trend"], "details": trend_notes},
            "momentum": {"score": round(momentum_s, 1), "weight": WEIGHTS["momentum"], "details": momentum_notes},
            "relative_strength": {"score": round(rs_s, 1), "weight": WEIGHTS["relative_strength"], "details": rs_notes},
        },
        "raw_metrics": {k: v for k, v in metrics.items() if k != "sector"},
    }


def score_all_sectors(sectors_data: Dict, price_data=None) -> Dict:
    """对所有板块评分并排序，附加每板块 top3 操作候选"""
    sectors = sectors_data.get("sectors", {})
    scored = []

    # 建立 sector_key → key_stocks 映射
    key_stocks_map = {s["key"]: s.get("key_stocks", []) for s in SECTORS}

    for key, metrics in sectors.items():
        result = score_sector(metrics)
        if "error" not in result:
            # 计算 top3 操作候选
            if price_data is not None:
                ks = key_stocks_map.get(key, [])
                top3 = get_top3_picks(key, result["composite"], ks, price_data)
            else:
                top3 = []
            result["top3_picks"] = top3
            scored.append(result)

    scored_sorted = sorted(scored, key=lambda x: x["composite"], reverse=True)
    top5_overbought = scored_sorted[:5]
    top5_oversold = sorted(scored_sorted[-5:], key=lambda x: x["composite"])

    return {
        "as_of_date": sectors_data.get("as_of_date"),
        "timestamp_utc": sectors_data.get("timestamp_utc"),
        "all_scored": scored_sorted,
        "top5_overbought": top5_overbought,
        "top5_oversold": top5_oversold,
        "errors": [s for s in sectors.values() if "error" in s.get("sector", {}) or "error" in s],
        "total_sectors": len(sectors),
        "scored_count": len(scored),
    }


if __name__ == "__main__":
    inp = os.environ.get("INPUT_FILE", "/tmp/sectors.json")
    out = os.environ.get("OUTPUT_FILE", "/tmp/sectors_scored.json")

    with open(inp) as f:
        data = json.load(f)

    result = score_all_sectors(data)

    print(f"\n=== Top 5 最超买 ===")
    for s in result["top5_overbought"]:
        print(f"  {s['emoji']} {s['sector']['name_zh']:18s} {s['composite']:>5.1f}  ({s['label']})")

    print(f"\n=== Top 5 最超卖 ===")
    for s in result["top5_oversold"]:
        print(f"  {s['emoji']} {s['sector']['name_zh']:18s} {s['composite']:>5.1f}  ({s['label']})")

    print(f"\n=== 全部 {result['scored_count']}/{result['total_sectors']} 板块 ===")
    for s in result["all_scored"]:
        print(f"  {s['emoji']} {s['sector']['name_zh']:18s} {s['composite']:>5.1f}  ({s['label']})")

    with open(out, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Saved to {out}")
