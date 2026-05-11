"""
fundamentals_temperature.py
板块【基本面温度】4 档标签。和 0-100 技术评分【正交】，不混算。

🔥 基本面加速     EPS revision 上调 + 估值合理 → 超买中能继续超买（2024 模式）
📈 估值合理       Forward PE z 中性 + EPS 平稳 → 涨得有道理
⚠️ 估值 stretched Forward PE z > +1.5 + EPS 持平 → 涨的是估值不是基本面
🚨 估值+EPS 双背离 Forward PE z > +2 + EPS 下修 → 1999/2021 末期模式
❓ 数据不足        N/A 板块（量子/Neocloud/BTC 等）
"""
from typing import Dict


def classify_temperature(fundamentals: Dict) -> Dict:
    fwd_pe = fundamentals.get("forward_pe")
    fwd_pe_z = fundamentals.get("forward_pe_zscore")
    rev_3m = fundamentals.get("eps_revision_3m_pct")
    peg = fundamentals.get("peg")
    growth = fundamentals.get("eps_growth_pct")

    # 数据不足
    if fwd_pe is None and fwd_pe_z is None:
        return {
            "label": "数据不足", "emoji": "❓", "code": "no_data",
            "explanation": "基本面数据缺失（如量子/Neocloud/BTC 无传统 PE 概念）",
            "raw": fundamentals,
        }

    # 🚨 估值 + EPS 双背离
    if fwd_pe_z is not None and fwd_pe_z > 2.0:
        if rev_3m is not None and rev_3m < 0:
            return {
                "label": "估值+EPS 双背离", "emoji": "🚨", "code": "danger",
                "explanation": f"Forward PE z={fwd_pe_z:+.1f}（>+2σ）且 EPS 3M revision {rev_3m:+.1f}% 下修。1999 末期/2021/12 模式。",
                "raw": fundamentals,
            }
        if rev_3m is None and peg is not None and peg > 3:
            return {
                "label": "估值偏离基本面", "emoji": "🚨", "code": "danger",
                "explanation": f"Forward PE z={fwd_pe_z:+.1f}（>+2σ）且 PEG={peg:.1f}（>3）。",
                "raw": fundamentals,
            }

    # ⚠️ 估值 stretched
    if fwd_pe_z is not None and fwd_pe_z > 1.5:
        if rev_3m is None or rev_3m <= 5:
            rev_str = f"{rev_3m:+.1f}%" if rev_3m is not None else "未知"
            return {
                "label": "估值 stretched", "emoji": "⚠️", "code": "warning",
                "explanation": f"Forward PE z={fwd_pe_z:+.1f}（>+1.5σ）但 EPS 3M revision {rev_str}。涨的是估值不是基本面。",
                "raw": fundamentals,
            }

    # 🔥 基本面加速
    if rev_3m is not None and rev_3m > 5:
        peg_str = f"，PEG {peg:.1f}" if peg else ""
        return {
            "label": "基本面加速", "emoji": "🔥", "code": "accelerating",
            "explanation": f"EPS 3M revision {rev_3m:+.1f}% 强力上修{peg_str}。即使技术超买也能继续（2024 AI/GLP-1 模式）。",
            "raw": fundamentals,
        }

    # 没有 revision 但 PEG 健康
    if rev_3m is None and peg is not None and peg < 1.5 and fwd_pe_z is not None and fwd_pe_z < 0.5:
        return {
            "label": "高增长低估值", "emoji": "🔥", "code": "accelerating",
            "explanation": f"PEG={peg:.1f}（<1.5）且 Forward PE z={fwd_pe_z:+.1f}（低于历史均值）。",
            "raw": fundamentals,
        }

    # 📈 估值合理
    return {
        "label": "估值合理", "emoji": "📈", "code": "fair",
        "explanation": _fair_explanation(fwd_pe, fwd_pe_z, rev_3m, peg),
        "raw": fundamentals,
    }


def _fair_explanation(fwd_pe, fwd_pe_z, rev_3m, peg):
    parts = []
    if fwd_pe is not None: parts.append(f"Forward PE {fwd_pe:.1f}x")
    if fwd_pe_z is not None: parts.append(f"z={fwd_pe_z:+.1f}")
    if rev_3m is not None: parts.append(f"EPS 3M revision {rev_3m:+.1f}%")
    if peg is not None: parts.append(f"PEG {peg:.1f}")
    return "估值在历史均值附近、基本面平稳。" + (" / ".join(parts) if parts else "")


def classify_all_sectors(fundamentals_data: Dict) -> Dict:
    results = {}
    for key, fund in fundamentals_data.get("sectors", {}).items():
        results[key] = classify_temperature(fund)
    return results


if __name__ == "__main__":
    import os, json

    inp = os.environ.get("INPUT_FILE", "/tmp/fundamentals.json")
    out = os.environ.get("OUTPUT_FILE", "/tmp/temperatures.json")

    with open(inp) as f: data = json.load(f)
    temps = classify_all_sectors(data)

    print(f"\n=== 板块基本面温度 ===")
    for k, t in temps.items():
        print(f"  {t['emoji']} {k:25s} {t['label']:18s}")

    by_code = {}
    for t in temps.values():
        by_code.setdefault(t["code"], []).append(t)
    print(f"\n=== 温度分布 ===")
    for code, lst in sorted(by_code.items()):
        print(f"  {lst[0]['emoji']} {code}: {len(lst)} 个")

    with open(out, "w") as f:
        json.dump(temps, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Saved to {out}")
