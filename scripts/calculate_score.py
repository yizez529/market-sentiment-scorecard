"""
calculate_score.py
基于抓取到的指标数据，计算 7 维度子评分和综合加权评分（0-100）。
0 = 极度超卖（恐慌底），100 = 极度超买（顶部）。
"""
import json
import os
from typing import Dict, Any, Tuple


# ========== 7 维度权重 ==========
WEIGHTS = {
    "volatility": 0.18,    # 波动率
    "sentiment": 0.14,     # 情绪调查
    "spx_breadth": 0.12,   # SPX 广度
    "credit": 0.14,        # 信用利差
    "ndx": 0.12,           # NDX 专项
    "cta": 0.14,           # CTA / 量化
    "momentum": 0.16,      # 价格动量
}


def linear_score(value: float, low: float, high: float, invert: bool = False) -> float:
    """
    把一个值线性映射到 0-100 分数。
    low → 0 分（如果 invert=False）/ 100 分（如果 invert=True）
    high → 100 分 / 0 分
    invert=True: 值越高 = 分数越低（适合 fear-style 指标）
    """
    if high == low:
        return 50.0
    pct = (value - low) / (high - low)
    pct = max(0.0, min(1.0, pct))
    score = pct * 100
    return 100 - score if invert else score


# ========== 1. 波动率维度 ==========

def score_volatility(data: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """
    VIX, VXN, MOVE → 综合波动率评分
    VIX 低（如 12）= 100 分（complacency）
    VIX 高（如 50）= 0 分（panic）
    """
    market = data.get("market", {})
    vix = market.get("VIX", {}).get("current")
    vxn = market.get("VXN", {}).get("current")
    move = market.get("MOVE", {}).get("current")

    notes = {}
    components = []

    if vix is not None:
        # VIX 12 = 100, VIX 50 = 0
        s = linear_score(vix, 12, 50, invert=True)
        components.append((s, 0.5))
        notes["VIX"] = f"{vix} → {s:.0f}"
    if vxn is not None:
        s = linear_score(vxn, 16, 55, invert=True)
        components.append((s, 0.3))
        notes["VXN"] = f"{vxn} → {s:.0f}"
    if move is not None and isinstance(move, (int, float)):
        s = linear_score(move, 70, 180, invert=True)
        components.append((s, 0.2))
        notes["MOVE"] = f"{move} → {s:.0f}"

    if not components:
        return 50.0, {"error": "no volatility data", "components": notes}

    total_w = sum(w for _, w in components)
    score = sum(s * w for s, w in components) / total_w
    return score, {"components": notes, "score": round(score, 1)}


# ========== 2. 情绪维度 ==========

def score_sentiment(data: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """
    F&G, AAII Bull-Bear Spread, NAAIM
    """
    fg = data.get("fear_greed", {}).get("score")
    aaii = data.get("aaii", {})
    naaim = data.get("naaim", {}).get("value")

    notes = {}
    components = []

    if fg is not None:
        # F&G 直接就是 0-100，0 = 恐慌（超卖）, 100 = 贪婪（超买），与我们方向一致
        components.append((fg, 0.5))
        notes["F&G"] = f"{fg} → {fg:.0f}"

    if "bull_bear_spread" in aaii:
        # Spread -40 = 极恐 = 0 分; Spread +40 = 极贪 = 100 分
        spread = aaii["bull_bear_spread"]
        s = linear_score(spread, -40, 40, invert=False)
        components.append((s, 0.3))
        notes["AAII spread"] = f"{spread:+.1f}% → {s:.0f}"

    if naaim is not None:
        # NAAIM 0-200，约 30 = 防御 = 0 分; 100 = 满仓 = 100 分
        s = linear_score(naaim, 30, 100, invert=False)
        components.append((s, 0.2))
        notes["NAAIM"] = f"{naaim} → {s:.0f}"

    if not components:
        return 50.0, {"error": "no sentiment data", "components": notes}

    total_w = sum(w for _, w in components)
    score = sum(s * w for s, w in components) / total_w
    return score, {"components": notes, "score": round(score, 1)}


# ========== 3. SPX 广度维度 ==========

def score_spx_breadth(data: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """
    SPX vs 200MA + RUT 相对强度 + 等权 vs 市值加权
    """
    market = data.get("market", {})
    spx = market.get("SPX", {})
    rsp_spy = data.get("market", {}).get("RSP_SPY_RATIO")

    notes = {}
    components = []

    pct_above_200 = spx.get("pct_above_ma200")
    pct_above_50 = spx.get("pct_above_ma50")

    if pct_above_200 is not None:
        # SPX 距离 200MA: -10% = 0 分（深度回调）, +10% = 100 分（过热）
        s = linear_score(pct_above_200, -10, 10, invert=False)
        components.append((s, 0.5))
        notes["SPX vs 200MA"] = f"{pct_above_200:+.2f}% → {s:.0f}"

    if pct_above_50 is not None:
        s = linear_score(pct_above_50, -8, 8, invert=False)
        components.append((s, 0.3))
        notes["SPX vs 50MA"] = f"{pct_above_50:+.2f}% → {s:.0f}"

    if rsp_spy is not None:
        # RSP/SPY 比值变化是广度指标，但绝对值不易解读，给中性分数
        notes["RSP/SPY"] = f"{rsp_spy:.4f}"
        components.append((50, 0.2))  # neutral weight, just record

    if not components:
        return 50.0, {"error": "no breadth data", "components": notes}

    total_w = sum(w for _, w in components)
    score = sum(s * w for s, w in components) / total_w
    return score, {"components": notes, "score": round(score, 1)}


# ========== 4. 信用利差维度 ==========

def score_credit(data: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """
    HY OAS, IG OAS
    利差紧 = 高估值 = 高分（超买）
    利差宽 = 恐慌 = 低分（超卖）
    """
    fred = data.get("fred", {})
    hy = fred.get("HY_OAS", {}).get("current_bps")
    ig = fred.get("IG_OAS", {}).get("current_bps")

    notes = {}
    components = []

    if hy is not None:
        # HY 250bps = 100 分（极致紧）, 800bps = 0 分（恐慌）
        s = linear_score(hy, 250, 800, invert=True)
        components.append((s, 0.6))
        notes["HY OAS"] = f"{hy:.0f}bps → {s:.0f}"

    if ig is not None:
        # IG 70bps = 100 分, 200bps = 0 分
        s = linear_score(ig, 70, 200, invert=True)
        components.append((s, 0.4))
        notes["IG OAS"] = f"{ig:.0f}bps → {s:.0f}"

    if not components:
        return 50.0, {"error": "no credit data", "components": notes}

    total_w = sum(w for _, w in components)
    score = sum(s * w for s, w in components) / total_w
    return score, {"components": notes, "score": round(score, 1)}


# ========== 5. NDX 专项维度 ==========

def score_ndx(data: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """
    NDX 距离 200MA + NDX RSI + 连涨天数 + QQQ vs SPY 动量
    """
    market = data.get("market", {})
    ndx = market.get("NDX", {})
    qqq = market.get("QQQ", {})
    spy = market.get("SPY", {})

    notes = {}
    components = []

    pct_above_200 = ndx.get("pct_above_ma200")
    rsi = ndx.get("rsi14")
    streak = ndx.get("streak_days", 0)

    if pct_above_200 is not None:
        # NDX 比 SPX 更易极端：-12% = 0, +12% = 100
        s = linear_score(pct_above_200, -12, 12, invert=False)
        components.append((s, 0.35))
        notes["NDX vs 200MA"] = f"{pct_above_200:+.2f}% → {s:.0f}"

    if rsi is not None:
        # RSI 25 = 0 分, RSI 80 = 100 分
        s = linear_score(rsi, 25, 80, invert=False)
        components.append((s, 0.25))
        notes["NDX RSI14"] = f"{rsi:.1f} → {s:.0f}"

    if streak is not None:
        # 连涨/连跌天数： -8 = 0 分, +12 = 100 分
        s = linear_score(streak, -8, 12, invert=False)
        components.append((s, 0.2))
        notes["NDX streak"] = f"{streak:+d} 天 → {s:.0f}"

    # QQQ 动量 vs SPY
    qqq_5d = qqq.get("change_pct", 0)
    spy_5d = spy.get("change_pct", 0)
    rel_momentum = qqq_5d - spy_5d
    if qqq.get("current") and spy.get("current"):
        s = linear_score(rel_momentum, -3, 3, invert=False)
        components.append((s, 0.2))
        notes["QQQ-SPY 单日动量"] = f"{rel_momentum:+.2f}% → {s:.0f}"

    if not components:
        return 50.0, {"error": "no NDX data", "components": notes}

    total_w = sum(w for _, w in components)
    score = sum(s * w for s, w in components) / total_w
    return score, {"components": notes, "score": round(score, 1)}


# ========== 6. CTA / 量化维度 ==========

def score_cta(data: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """
    CTA 估算仓位百分位 + Put/Call ratio
    高仓位（>85th）= 高分（超买/风险）
    低仓位（<20th）= 低分（潜在反向买入）
    """
    cta = data.get("cta", {})
    pcr = data.get("putcall", {}).get("current")

    notes = {}
    components = []

    pct = cta.get("estimated_percentile")
    if pct is not None:
        # 直接用百分位（已经是 0-100）
        components.append((pct, 0.7))
        notes["CTA 仓位百分位（代理）"] = f"{pct:.0f} → {pct:.0f}"

    if pcr is not None:
        # P/C ratio 0.6 = 100 分（极度贪婪 call buying）, 1.3 = 0 分（极度恐慌 put buying）
        s = linear_score(pcr, 0.6, 1.3, invert=True)
        components.append((s, 0.3))
        notes["Put/Call"] = f"{pcr:.2f} → {s:.0f}"

    if not components:
        return 50.0, {"error": "no CTA data", "components": notes}

    total_w = sum(w for _, w in components)
    score = sum(s * w for s, w in components) / total_w
    return score, {"components": notes, "score": round(score, 1)}


# ========== 7. 价格动量维度 ==========

def score_momentum(data: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """
    SPX RSI + 连涨天数 + 距 200MA 的偏离绝对值
    """
    market = data.get("market", {})
    spx = market.get("SPX", {})

    notes = {}
    components = []

    rsi = spx.get("rsi14")
    streak = spx.get("streak_days", 0)
    pct_above_200 = spx.get("pct_above_ma200")
    realized_vol = spx.get("realized_vol_30d")

    if rsi is not None:
        # SPX RSI 25 = 0 分, 75 = 100 分
        s = linear_score(rsi, 25, 75, invert=False)
        components.append((s, 0.35))
        notes["SPX RSI14"] = f"{rsi:.1f} → {s:.0f}"

    if streak is not None:
        s = linear_score(streak, -7, 10, invert=False)
        components.append((s, 0.25))
        notes["SPX streak"] = f"{streak:+d} 天 → {s:.0f}"

    if pct_above_200 is not None:
        s = linear_score(pct_above_200, -8, 8, invert=False)
        components.append((s, 0.25))
        notes["SPX vs 200MA"] = f"{pct_above_200:+.2f}% → {s:.0f}"

    if realized_vol is not None:
        # Realized vol 高 → 价格在动 → 不一定是 momentum 方向，给低权重
        # 反向：高 vol = 不稳定，给中性
        notes["SPX 30d 实际波动率"] = f"{realized_vol:.1f}%"
        components.append((50, 0.15))

    if not components:
        return 50.0, {"error": "no momentum data", "components": notes}

    total_w = sum(w for _, w in components)
    score = sum(s * w for s, w in components) / total_w
    return score, {"components": notes, "score": round(score, 1)}


# ========== 主流程 ==========

def calculate_composite(indicators: Dict[str, Any]) -> Dict[str, Any]:
    """计算 7 维度子评分 + 加权综合评分"""
    scores = {
        "volatility": score_volatility(indicators),
        "sentiment": score_sentiment(indicators),
        "spx_breadth": score_spx_breadth(indicators),
        "credit": score_credit(indicators),
        "ndx": score_ndx(indicators),
        "cta": score_cta(indicators),
        "momentum": score_momentum(indicators),
    }

    composite = sum(scores[k][0] * WEIGHTS[k] for k in WEIGHTS)
    composite = round(composite, 1)

    # 状态分类
    if composite < 15:
        status_label = "极度超卖 / 恐慌底"
        status_color = "success"
        status_zone = "extreme_oversold"
    elif composite < 30:
        status_label = "严重超卖"
        status_color = "success"
        status_zone = "severe_oversold"
    elif composite < 45:
        status_label = "偏超卖"
        status_color = "info"
        status_zone = "moderate_oversold"
    elif composite < 55:
        status_label = "中性"
        status_color = "default"
        status_zone = "neutral"
    elif composite < 70:
        status_label = "偏超买"
        status_color = "warning"
        status_zone = "moderate_overbought"
    elif composite < 85:
        status_label = "严重超买"
        status_color = "warning"
        status_zone = "severe_overbought"
    else:
        status_label = "极度超买 / 顶部"
        status_color = "danger"
        status_zone = "extreme_overbought"

    return {
        "composite_score": composite,
        "status_label": status_label,
        "status_color": status_color,
        "status_zone": status_zone,
        "weights": WEIGHTS,
        "dimensions": {
            k: {
                "score": round(scores[k][0], 1),
                "weight": WEIGHTS[k],
                "weighted": round(scores[k][0] * WEIGHTS[k], 2),
                "details": scores[k][1],
            }
            for k in WEIGHTS
        },
    }


if __name__ == "__main__":
    inp = os.environ.get("INPUT_FILE", "/tmp/indicators.json")
    out = os.environ.get("OUTPUT_FILE", "/tmp/score.json")
    with open(inp) as f:
        indicators = json.load(f)
    result = calculate_composite(indicators)
    print(f"\n综合评分: {result['composite_score']}")
    print(f"状态: {result['status_label']}")
    print(f"\n各维度子评分:")
    for k, v in result["dimensions"].items():
        print(f"  {k:12s}: {v['score']:5.1f} (权重 {v['weight']*100:.0f}%)")
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved to {out}")
