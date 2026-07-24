"""
divergence_detector.py
检测 7 维度之间的方向性背离。
背离是最有价值的交易信号之一——当多个维度方向相反时，往往意味着市场定价失衡。
"""
from typing import Dict, List, Any


# 高价值背离模式定义
DIVERGENCE_PATTERNS = [
    {
        "name": "假恐慌",
        "emoji": "🎭",
        "description": "波动率飙升但信用市场平静 → 大概率是技术性/情绪性过度反应，可逆",
        "conditions": {
            "oversold": ["volatility"],   # 这些维度超卖（< 35）
            "normal_or_overbought": ["credit"],   # 这些维度正常或偏高（> 45）
        },
        "severity": "high",
        "action": "逆向做多窗口",
    },
    {
        "name": "隐性风险",
        "emoji": "🐍",
        "description": "价格动量和NDX都超买但信用利差开始恶化 → 表面繁荣，底层在裂",
        "conditions": {
            "overbought": ["momentum", "ndx"],   # 这些维度超买（> 65）
            "oversold_or_falling": ["credit"],     # 信用维度低于 45 或明显下降
        },
        "severity": "critical",
        "action": "减仓+加对冲",
    },
    {
        "name": "聪明钱散户分歧",
        "emoji": "🔀",
        "description": "散户情绪极度贪婪但CTA/量化仓位在下降 → 机构在减仓，散户在追顶",
        "conditions": {
            "overbought": ["sentiment"],  # 散户极度贪婪
            "falling_or_normal": ["cta"],  # CTA 仓位不高或在降
        },
        "severity": "high",
        "action": "警惕短期回调",
    },
    {
        "name": "超卖中的安全信号",
        "emoji": "🛡️",
        "description": "价格超卖但信用利差平稳+CTA未极端 → 回调有底，不是系统性风险",
        "conditions": {
            "oversold": ["momentum", "spx_breadth"],
            "normal_or_overbought": ["credit", "cta"],
        },
        "severity": "medium",
        "action": "分批建仓",
    },
    {
        "name": "全面超买无分歧",
        "emoji": "🌡️",
        "description": "所有维度一致超买 → 市场过热但方向一致，注意拐点信号",
        "conditions": {
            "all_overbought": ["volatility", "sentiment", "momentum", "ndx", "credit"],
        },
        "severity": "high",
        "action": "减仓10-20%，买尾部put保护",
    },
]


def classify_dimension(score: float) -> str:
    """将维度分数分类为方向性标签"""
    if score < 25:
        return "extreme_oversold"
    elif score < 35:
        return "oversold"
    elif score < 45:
        return "mild_oversold"
    elif score < 55:
        return "neutral"
    elif score < 65:
        return "mild_overbought"
    elif score < 75:
        return "overbought"
    else:
        return "extreme_overbought"


def detect_divergences(dimension_scores: Dict[str, float],
                       previous_scores: Dict[str, float] = None) -> List[Dict[str, Any]]:
    """
    检测跨维度背离。
    dimension_scores: {"volatility": 72.5, "sentiment": 45.2, ...}
    previous_scores: 上期的维度分数（用于检测"正在下降"的条件）
    返回检测到的背离列表。
    """
    detected = []

    for pattern in DIVERGENCE_PATTERNS:
        conditions = pattern["conditions"]
        matched = True

        # 检查 oversold 条件
        if "oversold" in conditions:
            for dim in conditions["oversold"]:
                if dim in dimension_scores and dimension_scores[dim] >= 35:
                    matched = False
                    break

        # 检查 overbought 条件
        if matched and "overbought" in conditions:
            for dim in conditions["overbought"]:
                if dim in dimension_scores and dimension_scores[dim] < 65:
                    matched = False
                    break

        # 检查 normal_or_overbought 条件
        if matched and "normal_or_overbought" in conditions:
            for dim in conditions["normal_or_overbought"]:
                if dim in dimension_scores and dimension_scores[dim] < 45:
                    matched = False
                    break

        # 检查 falling_or_normal 条件（需要 previous_scores）
        if matched and "falling_or_normal" in conditions:
            for dim in conditions["falling_or_normal"]:
                if dim in dimension_scores:
                    # 如果没有上期数据，只检查是否不在超买
                    if dimension_scores[dim] > 65:
                        # 如果有上期数据，检查是否在下降
                        if previous_scores and dim in previous_scores:
                            if dimension_scores[dim] >= previous_scores[dim]:
                                matched = False
                                break
                        else:
                            matched = False
                            break

        # 检查 oversold_or_falling 条件
        if matched and "oversold_or_falling" in conditions:
            for dim in conditions["oversold_or_falling"]:
                if dim in dimension_scores:
                    is_low = dimension_scores[dim] < 45
                    is_falling = False
                    if previous_scores and dim in previous_scores:
                        is_falling = dimension_scores[dim] < previous_scores[dim] - 5
                    if not (is_low or is_falling):
                        matched = False
                        break

        # 检查 all_overbought 条件
        if matched and "all_overbought" in conditions:
            for dim in conditions["all_overbought"]:
                if dim in dimension_scores and dimension_scores[dim] < 60:
                    matched = False
                    break

        if matched:
            # 计算涉及维度的具体分数
            involved_dims = set()
            for cond_key in conditions:
                involved_dims.update(conditions[cond_key])

            dim_details = {
                dim: {
                    "score": dimension_scores.get(dim),
                    "direction": classify_dimension(dimension_scores.get(dim, 50)),
                }
                for dim in involved_dims
                if dim in dimension_scores
            }

            detected.append({
                "pattern": pattern["name"],
                "emoji": pattern["emoji"],
                "description": pattern["description"],
                "severity": pattern["severity"],
                "action": pattern["action"],
                "dimensions_involved": dim_details,
            })

    return detected


def format_divergences_for_feishu(divergences: List[Dict]) -> str:
    """格式化背离检测结果为飞书 markdown"""
    if not divergences:
        return "✅ 本周无显著跨维度背离"

    lines = ["**⚡ 背离警报**"]
    for d in divergences:
        severity_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡"}.get(d["severity"], "⚪")
        lines.append(f"\n{d['emoji']} **{d['pattern']}** {severity_emoji}")
        lines.append(f"   {d['description']}")

        dims_str = " | ".join(
            f"{dim}: {info['score']:.0f}({info['direction']})"
            for dim, info in d["dimensions_involved"].items()
        )
        lines.append(f"   📊 {dims_str}")
        lines.append(f"   💡 **建议**: {d['action']}")

    return "\n".join(lines)


if __name__ == "__main__":
    # 测试用例
    test_scores = {
        "volatility": 28,  # 超卖 - VIX 飙升
        "sentiment": 35,
        "spx_breadth": 40,
        "credit": 62,       # 正常 - 信用市场平静
        "ndx": 45,
        "cta": 55,
        "momentum": 38,
    }
    results = detect_divergences(test_scores)
    print(f"检测到 {len(results)} 个背离:")
    for r in results:
        print(f"  {r['emoji']} {r['pattern']}: {r['description']}")
    print()
    print(format_divergences_for_feishu(results))
