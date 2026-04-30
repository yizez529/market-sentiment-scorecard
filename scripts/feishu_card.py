"""
feishu_card.py
推送飞书互动卡片：摘要 + GitHub Pages 链接（链接里附完整指标指南）。
"""
import os
import json
import time
from typing import Dict


def color_for_zone(zone: str) -> str:
    return {
        "extreme_oversold": "green",
        "severe_oversold": "green",
        "moderate_oversold": "blue",
        "neutral": "grey",
        "moderate_overbought": "yellow",
        "severe_overbought": "orange",
        "extreme_overbought": "red",
    }.get(zone, "grey")


def emoji_for_score(score: float) -> str:
    if score >= 85: return "🔴"
    if score >= 70: return "🟠"
    if score >= 55: return "🟡"
    if score >= 45: return "⚪"
    if score >= 30: return "🔵"
    if score >= 15: return "🟢"
    return "🟢🟢"


def build_card(score: Dict, analysis: Dict, indicators: Dict, page_url: str) -> Dict:
    """构造飞书互动卡片"""
    composite = score["composite_score"]
    status_label = score["status_label"]
    zone = score["status_zone"]
    color = color_for_zone(zone)
    emoji = emoji_for_score(composite)

    a = analysis.get("analysis", {})
    headline = a.get("headline", f"评分 {composite}")
    drivers = a.get("main_drivers", [])
    advice = a.get("investment_advice", {})
    verdict = a.get("verdict", "")
    next_watch = a.get("next_to_watch", [])
    key_changes = a.get("key_changes", "")

    today = indicators.get("as_of_date", "")

    # 维度分数 mini-summary
    dim_summary = []
    dim_zh = {
        "volatility": "波动率", "sentiment": "情绪", "spx_breadth": "SPX广度",
        "credit": "信用", "ndx": "NDX", "cta": "CTA", "momentum": "动量",
    }
    for k, v in score["dimensions"].items():
        s = v["score"]
        bar_emoji = "🔴" if s >= 80 else "🟠" if s >= 65 else "⚪" if s >= 35 else "🟢"
        dim_summary.append(f"{bar_emoji} **{dim_zh[k]}** {s:.0f}")

    drivers_text = "\n".join(f"• {d}" for d in drivers[:5]) if drivers else "—"
    next_watch_text = "\n".join(f"• {w}" for w in next_watch[:3]) if next_watch else "—"

    # 维度 2 列布局（飞书卡片用 column_set）
    dim_columns = [
        {
            "tag": "column",
            "width": "weighted",
            "weight": 1,
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(dim_summary[:4])}}
            ],
        },
        {
            "tag": "column",
            "width": "weighted",
            "weight": 1,
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(dim_summary[4:])}}
            ],
        },
    ]

    elements = [
        # 综合分数 hero
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"### {emoji} 综合评分 **{composite}** · {status_label}\n_{headline}_"
            },
        },
        {"tag": "hr"},
        # 关键驱动
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**🔑 核心驱动**\n{drivers_text}"
            },
        },
    ]

    # vs 上期变化
    if key_changes and key_changes not in ("N/A", "first_run"):
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**📊 vs 昨日变化**\n{key_changes}"
            },
        })

    elements.append({"tag": "hr"})

    # 维度评分（双列）
    elements.append({
        "tag": "div",
        "text": {"tag": "lark_md", "content": "**七维度评分**"}
    })
    elements.append({
        "tag": "column_set",
        "flex_mode": "none",
        "background_style": "default",
        "columns": dim_columns,
    })

    elements.append({"tag": "hr"})

    # 投资建议
    advice_md = (
        f"**💡 投资建议**\n"
        f"• **仓位**：{advice.get('position', 'N/A')}\n"
        f"• **对冲**：{advice.get('hedge', 'N/A')}\n"
        f"• **不要**：{advice.get('do_not', 'N/A')}\n"
        f"• **触发**：{advice.get('trigger_to_act', 'N/A')}"
    )
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": advice_md}})

    # 关键观察
    if next_watch:
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**👀 未来 3-7 天关注**\n{next_watch_text}"}
        })

    elements.append({"tag": "hr"})

    # Verdict + 链接
    verdict_md = f"**🎯 决断**：{verdict}" if verdict else ""
    elements.append({
        "tag": "div",
        "text": {"tag": "lark_md", "content": verdict_md}
    })

    # 跳转完整 dashboard 按钮
    elements.append({
        "tag": "action",
        "actions": [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "📊 查看完整 Dashboard + 指标指南"},
                "url": page_url,
                "type": "primary",
            }
        ],
    })

    elements.append({
        "tag": "note",
        "elements": [
            {"tag": "plain_text", "content": f"{today} · Claude Opus 4.7 · 7维度加权"}
        ],
    })

    card = {
        "config": {"wide_screen_mode": True, "enable_forward": True},
        "header": {
            "title": {"tag": "plain_text", "content": "🇺🇸 美股市场情绪日报"},
            "template": color,
        },
        "elements": elements,
    }
    return card


def send_to_feishu(webhook: str, card: Dict) -> Dict:
    """带重试的飞书推送"""
    import requests
    payload = {"msg_type": "interactive", "card": card}
    last_err = None
    for attempt in range(3):
        try:
            r = requests.post(
                webhook,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
            data = r.json()
            print(f"  Feishu attempt {attempt+1}: status={r.status_code}, body={json.dumps(data, ensure_ascii=False)[:500]}")
            if r.status_code == 200 and data.get("code") in (0, None):
                return data
            last_err = data
        except Exception as e:
            print(f"  Feishu attempt {attempt+1} error: {e}")
            last_err = str(e)
        time.sleep(2 ** attempt)
    return {"error": "all_retries_failed", "last_err": last_err}


if __name__ == "__main__":
    import sys
    score_path = os.environ.get("SCORE_FILE", "/tmp/score.json")
    analysis_path = os.environ.get("ANALYSIS_FILE", "/tmp/analysis.json")
    indicators_path = os.environ.get("INDICATORS_FILE", "/tmp/indicators.json")
    page_url = os.environ.get(
        "PAGE_URL",
        "https://github.com/yizez529/market-sentiment-scorecard"
    )
    webhook = os.environ.get("FEISHU_WEBHOOK")

    if not webhook:
        print("ERROR: FEISHU_WEBHOOK env var missing")
        sys.exit(1)

    with open(score_path) as f: score = json.load(f)
    with open(analysis_path) as f: analysis = json.load(f)
    with open(indicators_path) as f: indicators = json.load(f)

    card = build_card(score, analysis, indicators, page_url)
    result = send_to_feishu(webhook, card)
    if result.get("code") == 0 or result.get("code") is None:
        print("✅ Feishu card sent")
    else:
        print(f"❌ Feishu send failed: {result}")
        sys.exit(1)
