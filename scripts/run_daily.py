"""
run_daily.py
主流程：抓取 → 评分 → Claude 分析 → 生成 HTML → 推送飞书 → 写历史。
任何一步失败都尝试推送降级告警，不静默退出。
"""
import os
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

# 加 scripts 到 path
sys.path.insert(0, str(Path(__file__).parent))

from fetch_indicators import fetch_all
from calculate_score import calculate_composite
from claude_analysis import call_claude
from generate_html import render_html, CSS
from feishu_card import build_card, send_to_feishu


def write_history(score: dict, analysis: dict, indicators: dict, history_path: str):
    """append 到 history.json"""
    history = []
    if os.path.exists(history_path):
        try:
            with open(history_path) as f:
                history = json.load(f)
        except Exception:
            history = []
    if not isinstance(history, list):
        history = []

    snapshot = {
        "as_of": indicators.get("as_of_date"),
        "timestamp_utc": indicators.get("timestamp_utc"),
        "composite_score": score["composite_score"],
        "status_label": score["status_label"],
        "status_zone": score["status_zone"],
        "dimension_scores": {k: v["score"] for k, v in score["dimensions"].items()},
        "headline": analysis.get("analysis", {}).get("headline", ""),
        "verdict": analysis.get("analysis", {}).get("verdict", ""),
        "key_indicators_snapshot": {
            "VIX": indicators.get("market", {}).get("VIX", {}).get("current"),
            "VXN": indicators.get("market", {}).get("VXN", {}).get("current"),
            "SPX": indicators.get("market", {}).get("SPX", {}).get("current"),
            "NDX": indicators.get("market", {}).get("NDX", {}).get("current"),
            "HY_OAS": indicators.get("fred", {}).get("HY_OAS", {}).get("current_bps"),
            "fear_greed": indicators.get("fear_greed", {}).get("score"),
            "AAII_spread": indicators.get("aaii", {}).get("bull_bear_spread"),
            "CTA_proxy_pct": indicators.get("cta", {}).get("estimated_percentile"),
        },
    }

    # 同日覆盖（如果当天跑了多次）
    today = snapshot["as_of"]
    history = [h for h in history if h.get("as_of") != today]
    history.append(snapshot)
    history = sorted(history, key=lambda x: x.get("as_of", ""))[-365:]  # 只留 1 年

    os.makedirs(os.path.dirname(history_path) or ".", exist_ok=True)
    with open(history_path, "w") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    print(f"✅ History updated ({len(history)} entries)")


def main():
    # 路径配置
    repo_root = Path(__file__).resolve().parents[1]
    docs_dir = repo_root / "docs"
    archive_dir = docs_dir / "archive"
    data_dir = repo_root / "data"
    history_path = str(data_dir / "history.json")

    docs_dir.mkdir(exist_ok=True)
    archive_dir.mkdir(exist_ok=True)
    data_dir.mkdir(exist_ok=True)

    page_url = os.environ.get(
        "PAGE_URL",
        "https://yizez529.github.io/market-sentiment-scorecard/"
    )
    webhook = os.environ.get("FEISHU_WEBHOOK")
    if not webhook:
        print("⚠️  FEISHU_WEBHOOK not set; will skip Feishu push")

    # === 1. Fetch indicators ===
    print("\n" + "=" * 60)
    print("STEP 1: Fetch indicators")
    print("=" * 60)
    indicators = fetch_all()
    indicators_file = "/tmp/indicators.json"
    with open(indicators_file, "w") as f:
        json.dump(indicators, f, indent=2, default=str)

    # === 2. Calculate score ===
    print("\n" + "=" * 60)
    print("STEP 2: Calculate composite score")
    print("=" * 60)
    score = calculate_composite(indicators)
    print(f"\n综合评分: {score['composite_score']} ({score['status_label']})")
    for k, v in score["dimensions"].items():
        print(f"  {k:12s}: {v['score']:5.1f} (权重 {v['weight']*100:.0f}%)")
    score_file = "/tmp/score.json"
    with open(score_file, "w") as f:
        json.dump(score, f, indent=2, ensure_ascii=False)

    # === 3. Claude analysis ===
    print("\n" + "=" * 60)
    print("STEP 3: Claude Opus 4.7 analysis")
    print("=" * 60)
    history_for_context = None
    if os.path.exists(history_path):
        try:
            with open(history_path) as f:
                hist_list = json.load(f)
            if hist_list:
                history_for_context = hist_list[-1]
        except Exception:
            pass

    try:
        analysis = call_claude(indicators, score, history_for_context)
    except Exception as e:
        print(f"❌ Claude failed: {e}")
        traceback.print_exc()
        analysis = {
            "analysis": {
                "headline": f"评分 {score['composite_score']} ({score['status_label']}) — Claude 分析失败",
                "main_drivers": [f"Claude API 错误: {str(e)[:100]}"],
                "key_changes": "N/A",
                "dimension_highlights": {},
                "investment_advice": {
                    "position": "N/A", "hedge": "N/A",
                    "do_not": "N/A", "trigger_to_act": "N/A",
                },
                "next_to_watch": [],
                "verdict": "Claude 分析失败请检查 GitHub Actions 日志",
            },
            "error": str(e),
        }

    analysis_file = "/tmp/analysis.json"
    with open(analysis_file, "w") as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)

    # === 4. Write history ===
    print("\n" + "=" * 60)
    print("STEP 4: Update history")
    print("=" * 60)
    write_history(score, analysis, indicators, history_path)

    # 重新读 history（用于 chart）
    with open(history_path) as f:
        history = json.load(f)

    # === 5. Generate HTML ===
    print("\n" + "=" * 60)
    print("STEP 5: Generate HTML dashboard")
    print("=" * 60)
    html = render_html(score, indicators, analysis, history)
    today = indicators.get("as_of_date", datetime.utcnow().strftime("%Y-%m-%d"))

    with open(docs_dir / "index.html", "w", encoding="utf-8") as f:
        f.write(html)
    with open(archive_dir / f"{today}.html", "w", encoding="utf-8") as f:
        f.write(html)
    with open(docs_dir / "style.css", "w", encoding="utf-8") as f:
        f.write(CSS)
    print(f"✅ HTML generated: docs/index.html, docs/archive/{today}.html")

    # === 6. Push to Feishu ===
    print("\n" + "=" * 60)
    print("STEP 6: Push to Feishu")
    print("=" * 60)
    if webhook:
        # 完整 archive URL（指向当日，确保历史链接也有效）
        archive_url = f"{page_url.rstrip('/')}/archive/{today}.html"
        card = build_card(score, analysis, indicators, archive_url)
        result = send_to_feishu(webhook, card)
        if result.get("code") == 0:
            print("✅ Feishu pushed successfully")
        else:
            print(f"⚠️  Feishu push failed: {result}")
    else:
        print("Skipped (no FEISHU_WEBHOOK)")

    # === 7. Summary ===
    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)
    print(f"Date: {today}")
    print(f"Composite score: {score['composite_score']} ({score['status_label']})")
    print(f"Page URL: {page_url}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        traceback.print_exc()
        # 尝试推个降级告警
        webhook = os.environ.get("FEISHU_WEBHOOK")
        if webhook:
            try:
                import requests
                requests.post(
                    webhook,
                    json={
                        "msg_type": "text",
                        "content": {"text": f"⚠️ market-sentiment-scorecard 运行失败: {str(e)[:200]}\n请检查 GitHub Actions 日志"},
                    },
                    timeout=10,
                )
            except Exception:
                pass
        sys.exit(1)
