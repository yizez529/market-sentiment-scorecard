"""
claude_analysis.py
调用 Claude Opus 4.7 生成中文情绪分析。
- 三重 JSON 容错（per skill best practice）
- 首次失败就 dump 完整原始输出
- 使用 prompt caching 降低成本（system prompt 不变）
"""
import os
import json
import re
import sys
from datetime import datetime
from typing import Dict, Any

import anthropic


MODEL = "claude-opus-4-7"
MAX_TOKENS = 8000  # 26 板块简评 + sector_rotation_summary + 原宏观分析


SYSTEM_PROMPT = """你是 Aaron 的美股市场情绪分析师。Aaron 是资深 buy-side 投资人，习惯结构化、conclusion-first 的中文输出。

你的任务：根据传入的指标数据 + 7 维度宏观评分 + 26 个板块评分，生成每日市场情绪报告。

# 宏观 7 维度框架（不要在输出里再次解释，Aaron 已经熟悉）：
1. 波动率（18%）：VIX, VXN, MOVE
2. 情绪（14%）：F&G, AAII, NAAIM
3. SPX 广度（12%）：%>200MA, %>50MA, RSP/SPY
4. 信用（14%）：HY OAS, IG OAS
5. NDX 专项（12%）：NDX RSI, %>200MA, 连涨天数, QQQ vs SPY
6. CTA / 量化（14%）：CTA 仓位百分位代理, Put/Call
7. 价格动量（16%）：SPX RSI, 连涨天数, MA 偏离

# 宏观评分区间含义：
- 0-15: 极度超卖（恐慌底）→ 全力建仓
- 15-30: 严重超卖 → 大幅加仓
- 30-45: 偏超卖 → 加仓
- 45-55: 中性 → 持仓不动
- 55-70: 偏超买 → 停止加仓
- 70-85: 严重超买 → 部分减仓 (10-25%)
- 85-100: 极度超买（顶部）→ 大幅减仓 (30-50%)

# 板块评分区间（与宏观相同方向但不同分档）：
- 0-15: 严重超卖   - 15-35: 超卖/抄底候选   - 35-50: 偏弱/值得观察
- 50-65: 中性偏强  - 65-80: 偏强/持有       - 80-92: 严重超买/减仓
- 92-100: 极度超买

# 输出要求（严格 JSON，禁止 markdown fence 或前言）：
{
  "headline": "一句话总结 (15-25 字)，包含分数和状态",
  "main_drivers": ["3-5 条最重要的驱动因素，每条 20-40 字"],
  "key_changes": "vs 昨日 / vs 上期 的关键变化（如有），50-100 字",
  "dimension_highlights": {
    "波动率": "1-2 句，重点指出极值或异常",
    "情绪": "1-2 句",
    "SPX 广度": "1-2 句",
    "信用": "1-2 句",
    "NDX": "1-2 句",
    "CTA / 量化": "1-2 句",
    "价格动量": "1-2 句"
  },
  "investment_advice": {
    "position": "仓位建议（具体百分比）",
    "hedge": "对冲建议（具体工具）",
    "do_not": "明确不要做的事",
    "trigger_to_act": "什么信号出现时改变立场"
  },
  "next_to_watch": ["未来 3-7 天关键事件 / 数据 / 触发位"],
  "verdict": "一句给 Aaron 的最终决断（25-40 字）",
  "sector_comments": {
    "<sector_key>": "一句板块简评（20-40 字），点出关键驱动或风险",
    "...": "对每一个传入的板块都要给一句简评"
  },
  "sector_rotation_summary": "一句话总结当期板块轮动主旋律（30-60 字），如：'AI/Neocloud 极致超买，能源/中概深度超卖，资金从 Tech 向 Defensive 轮动初现'"
}

# 风格要求：
- 写作风格：直接、简洁、conclusion-first，避免废话
- 使用具体数字（如 "VIX 18.7"，不要 "VIX 较低"）
- 引用历史可比时点（如 "类似 2025/4 但更温和"）
- 不要重复 Aaron 已知的框架内容
- 中文输出，但保留英文专业术语（VIX, F&G, OAS, CTA, RSI, MA, ETF 名等不翻译）
- 板块简评必须 actionable，不要泛泛而谈（坏例："AI 半导体走强" / 好例："SMH RSI 78 + 距 200MA +22%，CTA 已满仓，等回踩 50MA 再加仓而非追涨"）

# 严格规则：
- 只输出一个有效 JSON 对象，不要任何前言、解释、markdown fence
- 所有字段必填，缺数据用 "N/A" 字符串
- sector_comments 必须包含传入的每一个 sector_key（不可遗漏）
- JSON 内字符串使用中文双引号 " " 也是错的——只用 ASCII " "
"""


def call_claude(indicators: Dict, score: Dict, history: Dict = None, sectors_scored: Dict = None) -> Dict[str, Any]:
    """调用 Opus 4.7 生成分析（含板块简评）"""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    client = anthropic.Anthropic(api_key=api_key)

    # 构造用户消息
    today = datetime.utcnow().strftime("%Y-%m-%d")

    # 板块数据精简版给 LLM（只传必要字段，节省 token）
    sectors_compact = []
    if sectors_scored and "all_scored" in sectors_scored:
        for s in sectors_scored["all_scored"]:
            sectors_compact.append({
                "key": s["sector"]["key"],
                "name_zh": s["sector"]["name_zh"],
                "ticker": s["sector"]["ticker_or_basket"],
                "components": s["sector"]["components"],
                "composite": s["composite"],
                "label": s["label"],
                "trend": s["dimensions"]["trend"]["score"],
                "momentum": s["dimensions"]["momentum"]["score"],
                "rs": s["dimensions"]["relative_strength"]["score"],
                "ma200_dist": s["raw_metrics"].get("ma200_dist_pct"),
                "ma50_dist": s["raw_metrics"].get("ma50_dist_pct"),
                "rsi14": s["raw_metrics"].get("rsi14"),
                "rs_3m": s["raw_metrics"].get("rs_3m_vs_bm"),
            })

    user_payload = {
        "today": today,
        "composite_score": score["composite_score"],
        "status_label": score["status_label"],
        "dimension_scores": {
            k: v["score"] for k, v in score["dimensions"].items()
        },
        "key_indicators": _summarize_indicators(indicators),
        "previous_snapshot": history if history else "first_run",
        "sectors": sectors_compact,
    }

    sectors_note = ""
    if sectors_compact:
        sector_keys = [s["key"] for s in sectors_compact]
        sectors_note = (
            f"\n\n板块数据共 {len(sectors_compact)} 个，sector_comments 必须给每一个 key 一句简评："
            f"\n{', '.join(sector_keys)}"
        )

    user_msg = (
        f"以下是今日（{today}）的指标数据、宏观 7 维度评分、{len(sectors_compact)} 个板块评分。"
        f"请按 system prompt 的格式输出 JSON 报告。\n\n"
        f"```json\n{json.dumps(user_payload, indent=2, ensure_ascii=False)}\n```"
        f"{sectors_note}\n\n"
        f"再次提醒：只输出一个有效 JSON，不要 markdown fence 或前言。"
    )

    # 调用 API（带 prompt caching）
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {"role": "user", "content": user_msg},
        ],
    )

    raw_text = response.content[0].text
    usage = response.usage

    print(f"\n[Claude] Model: {MODEL}")
    print(f"[Claude] Input tokens: {usage.input_tokens}")
    print(f"[Claude] Output tokens: {usage.output_tokens}")
    if hasattr(usage, "cache_creation_input_tokens"):
        print(f"[Claude] Cache creation: {usage.cache_creation_input_tokens}")
    if hasattr(usage, "cache_read_input_tokens"):
        print(f"[Claude] Cache read: {usage.cache_read_input_tokens}")
    print(f"[Claude] Raw output length: {len(raw_text)} chars")
    print(f"[Claude] First 400 chars: {raw_text[:400]}")
    print(f"[Claude] Last 200 chars: {raw_text[-200:]}")

    # 三重 JSON 容错解析
    parsed = parse_json_robust(raw_text)
    return {
        "analysis": parsed,
        "raw": raw_text,
        "usage": {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0),
            "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0),
        },
        "model": MODEL,
    }


def parse_json_robust(text: str) -> Dict:
    """三重 JSON 容错解析"""
    # 第一层：直接解析
    try:
        return json.loads(text.strip())
    except Exception as e1:
        print(f"  [parse] Layer 1 (direct json.loads) failed: {e1}")

    # 第二层：去 fence
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned, flags=re.MULTILINE)
    try:
        return json.loads(cleaned.strip())
    except Exception as e2:
        print(f"  [parse] Layer 2 (strip fences) failed: {e2}")

    # 第三层：切第一个 { 到最后一个 }
    first = text.find("{")
    last = text.rfind("}")
    if first >= 0 and last > first:
        candidate = text[first:last + 1]
        try:
            return json.loads(candidate)
        except Exception as e3:
            print(f"  [parse] Layer 3 (brace slice) failed: {e3}")

    # 第四层：正则找所有 JSON 对象，取最大能 parse 的
    objects = re.findall(r"\{[\s\S]*\}", text)
    parsed_objs = []
    for obj_str in objects:
        try:
            parsed_objs.append((len(obj_str), json.loads(obj_str)))
        except Exception:
            continue
    if parsed_objs:
        parsed_objs.sort(key=lambda x: x[0], reverse=True)
        print(f"  [parse] Layer 4 (regex search) found {len(parsed_objs)} valid; using largest")
        return parsed_objs[0][1]

    raise ValueError(
        f"All JSON parsing layers failed. "
        f"Raw output (length {len(text)}): {text[:1000]}"
    )


def _summarize_indicators(indicators: Dict) -> Dict:
    """提炼最关键的指标值传给 Claude（避免 prompt 过长）"""
    market = indicators.get("market", {})
    fred = indicators.get("fred", {})
    cta = indicators.get("cta", {})

    return {
        "VIX": market.get("VIX", {}).get("current"),
        "VXN": market.get("VXN", {}).get("current"),
        "MOVE": market.get("MOVE", {}).get("current"),
        "SPX_close": market.get("SPX", {}).get("current"),
        "SPX_rsi14": market.get("SPX", {}).get("rsi14"),
        "SPX_streak": market.get("SPX", {}).get("streak_days"),
        "SPX_pct_above_200ma": market.get("SPX", {}).get("pct_above_ma200"),
        "SPX_realized_vol_30d": market.get("SPX", {}).get("realized_vol_30d"),
        "NDX_close": market.get("NDX", {}).get("current"),
        "NDX_rsi14": market.get("NDX", {}).get("rsi14"),
        "NDX_streak": market.get("NDX", {}).get("streak_days"),
        "NDX_pct_above_200ma": market.get("NDX", {}).get("pct_above_ma200"),
        "HY_OAS_bps": fred.get("HY_OAS", {}).get("current_bps"),
        "IG_OAS_bps": fred.get("IG_OAS", {}).get("current_bps"),
        "fear_greed": indicators.get("fear_greed", {}).get("score"),
        "fear_greed_rating": indicators.get("fear_greed", {}).get("rating"),
        "AAII_bullish": indicators.get("aaii", {}).get("bullish"),
        "AAII_bearish": indicators.get("aaii", {}).get("bearish"),
        "AAII_spread": indicators.get("aaii", {}).get("bull_bear_spread"),
        "NAAIM": indicators.get("naaim", {}).get("value"),
        "PutCall": indicators.get("putcall", {}).get("current"),
        "CTA_percentile_proxy": cta.get("estimated_percentile"),
        "CTA_trend_score": cta.get("trend_score"),
    }


if __name__ == "__main__":
    indicators_path = os.environ.get("INDICATORS_FILE", "/tmp/indicators.json")
    score_path = os.environ.get("SCORE_FILE", "/tmp/score.json")
    sectors_path = os.environ.get("SECTORS_SCORED_FILE", "/tmp/sectors_scored.json")
    history_path = os.environ.get("HISTORY_FILE", "data/history.json")
    out_path = os.environ.get("OUTPUT_FILE", "/tmp/analysis.json")

    with open(indicators_path) as f:
        indicators = json.load(f)
    with open(score_path) as f:
        score = json.load(f)

    sectors_scored = None
    if os.path.exists(sectors_path):
        try:
            with open(sectors_path) as f:
                sectors_scored = json.load(f)
        except Exception as e:
            print(f"  [sectors] failed to load: {e}")

    history = None
    if os.path.exists(history_path):
        try:
            with open(history_path) as f:
                history_data = json.load(f)
            if isinstance(history_data, list) and history_data:
                history = history_data[-1]
        except Exception as e:
            print(f"  [history] failed to load: {e}")

    try:
        result = call_claude(indicators, score, history, sectors_scored)
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Analysis saved to {out_path}")
        print(f"\nHeadline: {result['analysis'].get('headline', '(missing)')}")
    except Exception as e:
        # 即使失败，也写一个 fallback analysis 让 pipeline 继续
        print(f"\n❌ Claude analysis failed: {e}")
        sector_comments_fallback = {}
        if sectors_scored and "all_scored" in sectors_scored:
            for s in sectors_scored["all_scored"]:
                sector_comments_fallback[s["sector"]["key"]] = f"{s['label']} (评分 {s['composite']})"
        fallback = {
            "analysis": {
                "headline": f"评分 {score['composite_score']} ({score['status_label']}) — Claude 分析失败",
                "main_drivers": ["Claude API 调用失败，仅显示原始评分"],
                "key_changes": "N/A",
                "dimension_highlights": {k: "N/A" for k in score["dimensions"].keys()},
                "investment_advice": {
                    "position": "请参考评分自行决策",
                    "hedge": "N/A",
                    "do_not": "N/A",
                    "trigger_to_act": "N/A",
                },
                "next_to_watch": [],
                "verdict": f"原始评分 {score['composite_score']}，Claude 分析失败请检查日志",
                "sector_comments": sector_comments_fallback,
                "sector_rotation_summary": "N/A (Claude 分析失败)",
            },
            "error": str(e),
            "model": MODEL,
        }
        with open(out_path, "w") as f:
            json.dump(fallback, f, indent=2, ensure_ascii=False)
        sys.exit(1)
