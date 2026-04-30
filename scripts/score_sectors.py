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
from typing import Dict, Any, Tuple


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


def score_all_sectors(sectors_data: Dict) -> Dict:
    """对所有板块评分并排序"""
    sectors = sectors_data.get("sectors", {})
    scored = []

    for key, metrics in sectors.items():
        result = score_sector(metrics)
        if "error" not in result:
            scored.append(result)

    # 按分数降序（高的在前 = 最超买在前）
    scored_sorted = sorted(scored, key=lambda x: x["composite"], reverse=True)

    # Top 5 / Bottom 5 提取（飞书卡片用）
    top5_overbought = scored_sorted[:5]
    top5_oversold = sorted(scored_sorted[-5:], key=lambda x: x["composite"])  # 最低分在前

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
