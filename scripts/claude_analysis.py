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
MAX_TOKENS = 12000  # 31 板块简评 + 背离分析 + 持仓覆盖 + 周末事件


SYSTEM_PROMPT_WEEKLY = """你是 Aaron 的美股市场情绪分析师。Aaron 是资深 buy-side 投资人，习惯结构化、conclusion-first 的中文输出。

你的任务：根据传入的指标数据 + 7 维度宏观评分 + 31 个板块评分 + 背离检测 + 持仓覆盖，生成**周度**市场情绪报告。

# 当前 Regime: Warsh 低指引模式
美联储已取消前瞻指引，沟通透明度大幅降低。行动阈值已系统性收紧 5 分。
这意味着：VIX 基线上移、宏观数据对市场的脉冲式影响更大、政策不确定性溢价永久性上升。

# 宏观 7 维度框架（不要在输出里再次解释，Aaron 已经熟悉）：
1. 波动率（18%）：VIX, VXN, MOVE
2. 情绪（14%）：F&G, AAII, NAAIM
3. SPX 广度（12%）：%>200MA, %>50MA, RSP/SPY
4. 信用（14%）：HY OAS, IG OAS
5. NDX 专项（12%）：NDX RSI, %>200MA, 连涨天数, QQQ vs SPY
6. CTA / 量化（14%）：CTA 仓位百分位代理, Put/Call
7. 价格动量（16%）：SPX RSI, 连涨天数, MA 偏离

# 评分区间含义（已含 Warsh regime -5 调整）：
- 0-10: 极度超卖 → 全力建仓
- 10-25: 严重超卖 → 大幅加仓
- 25-40: 偏超卖 → 加仓
- 40-50: 中性 → 持仓不动
- 50-65: 偏超买 → 停止加仓
- 65-80: 严重超买 → 部分减仓 (10-25%)
- 80-100: 极度超买 → 大幅减仓 (30-50%)

# 板块基本面温度（与技术评分正交，不混算）：
- 🔥 基本面加速 / 📈 估值合理 / ⚠️ 估值 stretched / 🚨 估值+EPS 双背离 / ❓ 数据不足

# 输出要求（严格 JSON，禁止 markdown fence 或前言）：
{
  "headline": "一句话总结 (15-25 字)，包含分数和状态",
  "main_drivers": ["3-5 条最重要的驱动因素，每条 20-40 字"],
  "weekly_delta_summary": "本周 vs 上周的关键变化总结（80-150 字），强调趋势方向而非静态数字",
  "divergence_interpretation": "对传入的背离检测结果做定性判断（如有背离则 50-100 字，无背离则写'本周无显著背离'）",
  "dimension_highlights": {
    "波动率": "1-2 句",
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
  "portfolio_risk_note": "基于 Aaron 持仓数据，指出当前最值得关注的 2-3 个持仓风险或机会（50-100 字）",
  "weekend_events": ["2-4 条周末发生的/下周即将发生的可能影响市场的关键事件"],
  "next_to_watch": ["未来一周关键事件 / 数据 / 触发位"],
  "verdict": "一句给 Aaron 的最终决断（25-40 字）",
  "sector_comments": {
    "<sector_key>": "一句板块简评（25-50 字），结合技术评分 + 基本面温度做交叉判断"
  },
  "sector_rotation_summary": "一句话总结当期板块轮动主旋律（30-60 字）"
}

# 风格要求：
- 写作风格：直接、简洁、conclusion-first，避免废话
- 使用具体数字（如 "VIX 18.7"，不要 "VIX 较低"）
- 引用历史可比时点（如 "类似 2025/4 但更温和"）
- 不要重复 Aaron 已知的框架内容
- 中文输出，保留英文专业术语
- 板块简评必须 actionable，结合"技术分数 + 温度标签"做交叉判断
- 周报强调趋势性变化，不要逐日流水账

# 严格规则：
- 只输出一个有效 JSON 对象，不要任何前言、解释、markdown fence
- 所有字段必填，缺数据用 "N/A" 字符串
- sector_comments 必须包含传入的每一个 sector_key（不可遗漏）
"""

SYSTEM_PROMPT_ANOMALY = """你是 Aaron 的美股市场异常分析师。当市场出现异常波动时，你需要快速诊断原因并给出行动建议。

异常已被自动检测触发，你的任务是：
1. 判断这是技术性修正还是基本面恶化
2. 判断这是事件驱动还是流动性事件
3. 给出 Aaron 持仓层面的具体行动建议

# 输出要求（严格 JSON）：
{
  "headline": "异常事件一句话总结（15-25 字）",
  "main_drivers": ["导致异常的 2-3 个核心原因"],
  "diagnosis": "技术性修正/基本面恶化/事件驱动/流动性事件 + 50-80 字解释",
  "investment_advice": {
    "position": "具体仓位动作",
    "hedge": "具体对冲建议",
    "do_not": "绝不要做的事"
  },
  "verdict": "一句决断（25-40 字）"
}

只输出 JSON，不要前言。中文输出，保留英文术语。
"""

# 保持向后兼容
SYSTEM_PROMPT = SYSTEM_PROMPT_WEEKLY


def call_claude(indicators: Dict, score: Dict, history: Dict = None,
                sectors_scored: Dict = None, temperatures: Dict = None,
                anomaly_mode: bool = False, anomalies: list = None,
                divergences: list = None, portfolio_exposure: dict = None) -> Dict[str, Any]:
    """调用 Opus 4.7 生成分析（周报模式或异常模式）"""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    client = anthropic.Anthropic(api_key=api_key)

    today = datetime.utcnow().strftime("%Y-%m-%d")

    # 选择 system prompt
    system_prompt = SYSTEM_PROMPT_ANOMALY if anomaly_mode else SYSTEM_PROMPT_WEEKLY

    sectors_compact = []
    if sectors_scored and "all_scored" in sectors_scored:
        for s in sectors_scored["all_scored"]:
            sec_key = s["sector"]["key"]
            payload = {
                "key": sec_key,
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
            }
            if temperatures and sec_key in temperatures:
                t = temperatures[sec_key]
                payload["temperature"] = {
                    "emoji": t.get("emoji"),
                    "label": t.get("label"),
                    "code": t.get("code"),
                    "explanation": t.get("explanation"),
                    "forward_pe": t.get("raw", {}).get("forward_pe"),
                    "forward_pe_zscore": t.get("raw", {}).get("forward_pe_zscore"),
                    "eps_revision_3m_pct": t.get("raw", {}).get("eps_revision_3m_pct"),
                    "peg": t.get("raw", {}).get("peg"),
                }
            sectors_compact.append(payload)

    user_payload = {
        "today": today,
        "report_type": "anomaly_alert" if anomaly_mode else "weekly",
        "regime": score.get("regime", "Warsh低指引模式"),
        "regime_shift": score.get("regime_shift", -5),
        "composite_score": score["composite_score"],
        "status_label": score["status_label"],
        "dimension_scores": {
            k: v["score"] for k, v in score["dimensions"].items()
        },
        "key_indicators": _summarize_indicators(indicators),
        "previous_snapshot": history if history else "first_run",
        "sectors": sectors_compact,
    }

    # 添加背离检测结果
    if divergences:
        user_payload["divergences_detected"] = divergences

    # 添加持仓暴露
    if portfolio_exposure:
        # 只传高权重板块暴露
        top_exposures = sorted(
            portfolio_exposure.items(),
            key=lambda x: abs(x[1]["net_weight"]),
            reverse=True,
        )[:15]
        user_payload["portfolio_exposure"] = {
            k: {"net_weight": v["net_weight"], "tickers": [t[0] for t in v["tickers"][:5]]}
            for k, v in top_exposures
        }

    # 添加异常信息
    if anomaly_mode and anomalies:
        user_payload["anomalies_triggered"] = anomalies

    sectors_note = ""
    if sectors_compact and not anomaly_mode:
        sector_keys = [s["key"] for s in sectors_compact]
        sectors_note = (
            f"\n\n板块数据共 {len(sectors_compact)} 个，sector_comments 必须给每一个 key 一句简评："
            f"\n{', '.join(sector_keys)}"
        )

    if anomaly_mode:
        user_msg = (
            f"以下是今日（{today}）的异常警报数据。"
            f"请按 system prompt 的格式输出 JSON 分析。\n\n"
            f"```json\n{json.dumps(user_payload, indent=2, ensure_ascii=False)}\n```\n\n"
            f"只输出 JSON，不要前言。"
        )
    else:
        user_msg = (
            f"以下是本周（截至 {today}）的指标数据、宏观 7 维度评分、{len(sectors_compact)} 个板块评分。"
            f"请按 system prompt 的格式输出 JSON 周报。\n\n"
            f"```json\n{json.dumps(user_payload, indent=2, ensure_ascii=False)}\n```"
            f"{sectors_note}\n\n"
            f"再次提醒：只输出一个有效 JSON，不要 markdown fence 或前言。"
        )

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": system_prompt,
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
    temperatures_path = os.environ.get("TEMPERATURES_FILE", "/tmp/temperatures.json")
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

    temperatures = None
    if os.path.exists(temperatures_path):
        try:
            with open(temperatures_path) as f:
                temperatures = json.load(f)
        except Exception as e:
            print(f"  [temperatures] failed to load: {e}")

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
        result = call_claude(indicators, score, history, sectors_scored, temperatures)
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
