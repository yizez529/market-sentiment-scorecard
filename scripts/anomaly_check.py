"""
anomaly_check.py
异常哨兵：每个交易日快速检测关键指标是否触发异常阈值。
无异常 → 静默退出（exit 0，不推送）
有异常 → 跑完整评分 + 推送异常警报卡片到飞书（exit 0）
"""
import os
import sys
import json
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# ========== 异常阈值配置 ==========
ANOMALY_THRESHOLDS = {
    "SPX_daily_pct": 2.0,      # SPX 单日涨跌 >= ±2%
    "NDX_daily_pct": 2.5,      # NDX 单日涨跌 >= ±2.5%
    "VIX_daily_change_pct": 25, # VIX 单日变化 >= +25% (相对值)
    "VIX_absolute": [25, 30, 40],  # VIX 突破这些关口
    "HY_OAS_daily_bp": 30,     # HY OAS 单日变化 >= +30bp
}


def check_anomalies(indicators: dict) -> list:
    """
    检测是否触发异常阈值。
    返回触发的异常列表，空列表 = 无异常。
    """
    market = indicators.get("market", {})
    fred = indicators.get("fred", {})

    triggered = []

    # 1. SPX 单日涨跌
    spx = market.get("SPX", {})
    spx_change = spx.get("change_pct")
    if spx_change is not None and abs(spx_change) >= ANOMALY_THRESHOLDS["SPX_daily_pct"]:
        direction = "暴涨" if spx_change > 0 else "暴跌"
        triggered.append({
            "indicator": "SPX",
            "type": "daily_move",
            "value": spx_change,
            "threshold": ANOMALY_THRESHOLDS["SPX_daily_pct"],
            "emoji": "📈" if spx_change > 0 else "📉",
            "summary": f"SPX 单日{direction} {spx_change:+.2f}%",
        })

    # 2. NDX 单日涨跌
    ndx = market.get("NDX", {})
    ndx_change = ndx.get("change_pct")
    if ndx_change is not None and abs(ndx_change) >= ANOMALY_THRESHOLDS["NDX_daily_pct"]:
        direction = "暴涨" if ndx_change > 0 else "暴跌"
        triggered.append({
            "indicator": "NDX",
            "type": "daily_move",
            "value": ndx_change,
            "threshold": ANOMALY_THRESHOLDS["NDX_daily_pct"],
            "emoji": "📈" if ndx_change > 0 else "📉",
            "summary": f"NDX 单日{direction} {ndx_change:+.2f}%",
        })

    # 3. VIX 日变化（相对值）
    vix_data = market.get("VIX", {})
    vix_current = vix_data.get("current")
    vix_prev = vix_data.get("previous_close")
    if vix_current is not None and vix_prev is not None and vix_prev > 0:
        vix_change_pct = ((vix_current - vix_prev) / vix_prev) * 100
        if vix_change_pct >= ANOMALY_THRESHOLDS["VIX_daily_change_pct"]:
            triggered.append({
                "indicator": "VIX",
                "type": "spike",
                "value": vix_change_pct,
                "threshold": ANOMALY_THRESHOLDS["VIX_daily_change_pct"],
                "emoji": "🚨",
                "summary": f"VIX 飙升 {vix_change_pct:+.1f}% ({vix_prev:.1f} → {vix_current:.1f})",
            })

    # 4. VIX 绝对水平突破关口
    if vix_current is not None:
        for level in ANOMALY_THRESHOLDS["VIX_absolute"]:
            if vix_current >= level and (vix_prev is None or vix_prev < level):
                triggered.append({
                    "indicator": "VIX",
                    "type": "level_breach",
                    "value": vix_current,
                    "threshold": level,
                    "emoji": "⚠️" if level < 40 else "🔥",
                    "summary": f"VIX 突破 {level} 关口 (当前 {vix_current:.1f})",
                })
                break  # 只报最高突破的关口

    # 5. HY OAS 单日变化
    hy_data = fred.get("HY_OAS", {})
    hy_current = hy_data.get("current_bps")
    hy_prev = hy_data.get("previous_bps")
    if hy_current is not None and hy_prev is not None:
        hy_change = hy_current - hy_prev
        if hy_change >= ANOMALY_THRESHOLDS["HY_OAS_daily_bp"]:
            triggered.append({
                "indicator": "HY_OAS",
                "type": "spread_widening",
                "value": hy_change,
                "threshold": ANOMALY_THRESHOLDS["HY_OAS_daily_bp"],
                "emoji": "💀",
                "summary": f"HY OAS 单日扩大 {hy_change:+.0f}bp ({hy_prev:.0f} → {hy_current:.0f}bp)",
            })

    return triggered


def build_anomaly_card(anomalies: list, score: dict, analysis: dict,
                       indicators: dict, page_url: str,
                       sectors_scored: dict = None, temperatures: dict = None) -> dict:
    """构造异常警报飞书卡片（红色/橙色主题，区别于蓝色周报）"""
    from portfolio_config import get_all_tickers

    composite = score["composite_score"]
    status_label = score["status_label"]
    today = indicators.get("as_of_date", "")

    a = analysis.get("analysis", {})
    verdict = a.get("verdict", "")
    drivers = a.get("main_drivers", [])
    advice = a.get("investment_advice", {})

    # 根据异常严重程度选颜色
    has_vix_40 = any(t["indicator"] == "VIX" and t.get("threshold") == 40 for t in anomalies)
    has_hy_spike = any(t["indicator"] == "HY_OAS" for t in anomalies)
    header_color = "red" if (has_vix_40 or has_hy_spike) else "orange"

    # 异常摘要
    anomaly_lines = []
    for t in anomalies:
        anomaly_lines.append(f"{t['emoji']} **{t['summary']}**")
    anomaly_text = "\n".join(anomaly_lines)

    # 受冲击的持仓
    portfolio_impact = []
    all_tickers = get_all_tickers()
    if sectors_scored and "all_scored" in sectors_scored:
        # 找出评分变化最大的板块
        extreme_sectors = [
            s for s in sectors_scored["all_scored"]
            if s["composite"] < 30 or s["composite"] > 80
        ]
        for sec in extreme_sectors:
            sec_key = sec["sector"]["key"]
            for ticker, (t_sector, weight, note) in all_tickers.items():
                if t_sector == sec_key and abs(weight) > 0.5:
                    direction = "超买" if sec["composite"] > 80 else "超卖"
                    portfolio_impact.append(
                        f"• `{ticker}` ({weight:+.1f}%) 在 {sec['sector']['name_zh']} ({direction} {sec['composite']:.0f})"
                    )

    elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"### 🚨 异常触发\n{anomaly_text}"
            },
        },
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**综合评分 {composite} · {status_label}**\n"
                    f"{''.join('• ' + d + chr(10) for d in drivers[:3])}"
                )
            },
        },
    ]

    if portfolio_impact:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "**📋 持仓冲击**\n" + "\n".join(portfolio_impact[:8])
            },
        })

    # 投资建议
    elements.append({"tag": "hr"})
    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": (
                f"**💡 建议**\n"
                f"• 仓位：{advice.get('position', 'N/A')}\n"
                f"• 对冲：{advice.get('hedge', 'N/A')}\n"
                f"• 不要：{advice.get('do_not', 'N/A')}"
            )
        },
    })

    if verdict:
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**🎯 决断**：{verdict}"}
        })

    elements.append({
        "tag": "action",
        "actions": [{
            "tag": "button",
            "text": {"tag": "plain_text", "content": "📊 查看完整 Dashboard"},
            "url": page_url,
            "type": "primary",
        }],
    })
    elements.append({
        "tag": "note",
        "elements": [
            {"tag": "plain_text", "content": f"{today} · 异常哨兵自动触发 · Claude Opus 4.7"}
        ],
    })

    return {
        "config": {"wide_screen_mode": True, "enable_forward": True},
        "header": {
            "title": {"tag": "plain_text", "content": "⚠️ 美股异常警报"},
            "template": header_color,
        },
        "elements": elements,
    }


def main():
    """异常哨兵主流程"""
    repo_root = Path(__file__).resolve().parents[1]
    data_dir = repo_root / "data"
    docs_dir = repo_root / "docs"

    page_url = os.environ.get(
        "PAGE_URL",
        "https://yizez529.github.io/market-sentiment-scorecard/"
    )
    webhook = os.environ.get("FEISHU_WEBHOOK")

    # Step 1: 快速抓取指标
    print("=" * 60)
    print("ANOMALY SENTINEL: Quick fetch")
    print("=" * 60)

    from fetch_indicators import fetch_all
    indicators = fetch_all()

    # Step 2: 检测异常
    print("\n" + "=" * 60)
    print("ANOMALY SENTINEL: Check thresholds")
    print("=" * 60)

    anomalies = check_anomalies(indicators)

    if not anomalies:
        print("✅ 无异常触发，静默退出")
        return  # 正常退出，不推送

    print(f"🚨 检测到 {len(anomalies)} 个异常:")
    for a in anomalies:
        print(f"  {a['emoji']} {a['summary']}")

    # Step 3: 有异常，跑完整评分
    print("\n" + "=" * 60)
    print("ANOMALY SENTINEL: Full scoring (anomaly triggered)")
    print("=" * 60)

    from calculate_score import calculate_composite
    score = calculate_composite(indicators)
    print(f"综合评分: {score['composite_score']} ({score['status_label']})")

    # 板块评分
    sectors_scored = None
    temperatures = None
    try:
        from fetch_sectors import fetch_all_sectors
        from score_sectors import score_all_sectors
        sectors_data = fetch_all_sectors()
        price_data = sectors_data.pop("_price_data", None)
        sectors_scored = score_all_sectors(sectors_data, price_data)
    except Exception as e:
        print(f"⚠️ Sectors failed: {e}")

    # Claude 分析（异常模式 prompt）
    print("\n" + "=" * 60)
    print("ANOMALY SENTINEL: Claude analysis")
    print("=" * 60)

    history = None
    history_path = str(data_dir / "history.json")
    if os.path.exists(history_path):
        try:
            with open(history_path) as f:
                hist = json.load(f)
            if hist:
                history = hist[-1]
        except Exception:
            pass

    try:
        from claude_analysis import call_claude
        analysis = call_claude(indicators, score, history, sectors_scored, temperatures,
                               anomaly_mode=True, anomalies=anomalies)
    except Exception as e:
        print(f"❌ Claude failed: {e}")
        traceback.print_exc()
        analysis = {
            "analysis": {
                "headline": f"异常警报 — 评分 {score['composite_score']}",
                "main_drivers": [a["summary"] for a in anomalies],
                "verdict": "Claude 分析失败，请手动检查",
                "investment_advice": {"position": "N/A", "hedge": "N/A", "do_not": "N/A"},
            }
        }

    # Step 4: 推送异常警报
    print("\n" + "=" * 60)
    print("ANOMALY SENTINEL: Push alert")
    print("=" * 60)

    if webhook:
        card = build_anomaly_card(
            anomalies, score, analysis, indicators, page_url,
            sectors_scored, temperatures
        )
        from feishu_card import send_to_feishu
        result = send_to_feishu(webhook, card)
        if result.get("code") == 0:
            print("✅ 异常警报已推送")
        else:
            print(f"⚠️ 推送失败: {result}")
    else:
        print("跳过（无 FEISHU_WEBHOOK）")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Fatal: {e}")
        traceback.print_exc()
        webhook = os.environ.get("FEISHU_WEBHOOK")
        if webhook:
            try:
                import requests
                requests.post(webhook, json={
                    "msg_type": "text",
                    "content": {"text": f"⚠️ anomaly-sentinel 运行失败: {str(e)[:200]}"},
                }, timeout=10)
            except Exception:
                pass
        sys.exit(1)
