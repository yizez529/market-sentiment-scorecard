"""
data_guard.py
数据完整性兜底校验层：在异常警报真正推送前，用独立数据源交叉校验 yfinance 的读数，
拦截缓存脏读、行错位、单点异常值导致的"假异常"。

背景：2026-08-06 anomaly_sentinel 曾误报 "SPX 单日暴涨 2.19%"，事后核实真实数据
8/4 +1.79% / 8/5 -0.17%，两天都对不上，判断是 yfinance 抓取层的脏读——history.json
里 2026-07-24 与 2026-07-27 的 SPX/NDX/VIX/VXN/CTA 快照完全相同（跨了一个周末+一个
交易日不该完全不变），是同类问题的先例。

三层防线（只在指标已经触发异常阈值时才启用，保持哨兵日常"轻量"的定位）：
1. 陈旧缓存检测 —— 本次快照与上次持久化快照逐字段比对，日期变了但数值分毫不差 → 判定陈旧
2. 跨源交叉校验 —— SPX 用 FRED SP500 同日收盘价核对；NDX 用 FRED NASDAQCOM 做方向/量级粗核对
3. 三步核验落地 —— 校验不通过 → 不推送为"确认异常"；无法校验（无源可比）→ 明确标注"未核实"，
   不伪装成精确结论（对应 Aaron 的"数据分析三步核验铁律"）

用法（在 anomaly_check.py 里，仅当 check_anomalies() 返回非空时调用）：
    from data_guard import run_guard_for
    guard_results = run_guard_for({"SPX", "NDX"}, indicators, fred_api_key, data_dir)
    # guard_results["SPX"]["trusted"] -> True / False / None
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Set

import requests

CACHE_FILENAME = "_last_fetch_cache.json"

# 容忍度配置
TOLERANCE = {
    "SPX_vs_FRED_pct": 0.15,                # SPX 与 FRED SP500 同日收盘价允许的最大相对误差
    "NDX_vs_NASDAQCOM_diff_pp": 3.0,        # NDX 与 FRED NASDAQCOM 涨跌幅允许的最大百分点差（不同指数，放宽）
}


def _fred_series_latest(series_id: str, api_key: str, limit: int = 5) -> Optional[list]:
    """拉取 FRED 某个指数点位序列的最近若干条 observation（原始点位，不做单位换算）"""
    if not api_key:
        return None
    url = (
        f"https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}&api_key={api_key}&file_type=json"
        f"&sort_order=desc&limit={limit}"
    )
    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        obs = [o for o in data.get("observations", []) if o.get("value") not in (".", None)]
        return obs or None
    except Exception:
        return None


def cross_validate_spx(spx_yf: Dict[str, Any], fred_api_key: str) -> Dict[str, Any]:
    """
    用 FRED SP500 序列核对 yfinance 的 SPX 收盘价。
    FRED SP500 通常在美股收盘当晚（CDT 傍晚）就更新，早于哨兵北京时间 10 点的运行窗口，
    时效性足够做同日核对。
    """
    result: Dict[str, Any] = {"checked": False, "trusted": None, "note": ""}
    obs = _fred_series_latest("SP500", fred_api_key, limit=5)
    if not obs:
        result["note"] = "FRED SP500 拉取失败或无 API key，跳过交叉校验"
        return result

    yf_as_of = spx_yf.get("as_of")
    yf_current = spx_yf.get("current")
    if yf_as_of is None or yf_current is None:
        result["note"] = "yfinance SPX 数据缺失，无法校验"
        return result

    fred_match = next((o for o in obs if o["date"] == yf_as_of), None)
    if fred_match is None:
        result["checked"] = True
        result["trusted"] = False
        result["note"] = (
            f"FRED 尚无 {yf_as_of} 的观测值（FRED 最新日期={obs[0]['date']}），"
            f"yfinance 的 as_of 日期可疑（可能读到未完全确认的数据，或日期本身错位）"
        )
        return result

    fred_val = float(fred_match["value"])
    diff_pct = abs(yf_current - fred_val) / fred_val * 100
    result["checked"] = True
    result["fred_value"] = fred_val
    result["fred_date"] = fred_match["date"]
    result["diff_pct"] = round(diff_pct, 3)
    result["trusted"] = diff_pct <= TOLERANCE["SPX_vs_FRED_pct"]
    result["note"] = f"yfinance={yf_current} vs FRED SP500={fred_val}（{fred_match['date']}），偏差 {diff_pct:.2f}%"
    return result


def cross_validate_ndx(ndx_yf: Dict[str, Any], fred_api_key: str) -> Dict[str, Any]:
    """
    NDX(^NDX, Nasdaq-100) 没有免费的对应 FRED 序列，退而求其次用 NASDAQCOM(Nasdaq Composite)
    做方向 + 量级的粗校验：两者绝大多数交易日同涨同跌，且当日涨跌幅差距很少超过 3 个百分点。
    这不是精确校验，只用来拦截"方向都反了"或"量级离谱"这类明显脏读。
    """
    result: Dict[str, Any] = {"checked": False, "trusted": None, "note": ""}
    obs = _fred_series_latest("NASDAQCOM", fred_api_key, limit=5)
    if not obs or len(obs) < 2:
        result["note"] = "FRED NASDAQCOM 数据不足，跳过交叉校验"
        return result

    ndx_as_of = ndx_yf.get("as_of")
    ndx_change = ndx_yf.get("change_pct")
    if ndx_as_of is None or ndx_change is None:
        result["note"] = "yfinance NDX 数据缺失，无法校验"
        return result

    idx = next((i for i, o in enumerate(obs) if o["date"] == ndx_as_of), None)
    if idx is None or idx + 1 >= len(obs):
        result["checked"] = True
        result["trusted"] = False
        result["note"] = f"FRED NASDAQCOM 尚无 {ndx_as_of} 的可比数据"
        return result

    cur = float(obs[idx]["value"])
    prev = float(obs[idx + 1]["value"])
    nasdaqcom_change = (cur / prev - 1) * 100

    diff = abs(ndx_change - nasdaqcom_change)
    same_direction = (ndx_change >= 0) == (nasdaqcom_change >= 0)
    result["checked"] = True
    result["nasdaqcom_change_pct"] = round(nasdaqcom_change, 2)
    result["diff_pp"] = round(diff, 2)
    result["trusted"] = same_direction and diff <= TOLERANCE["NDX_vs_NASDAQCOM_diff_pp"]
    result["note"] = f"yfinance NDX={ndx_change:+.2f}% vs FRED NASDAQCOM={nasdaqcom_change:+.2f}%，差 {diff:.2f}pp"
    return result


def check_stale_cache(market_core: Dict[str, Any], data_dir: Path) -> Dict[str, Any]:
    """
    检测本次抓取是否与上一次持久化的快照完全一致（日期变了但数值分毫不差 = 大概率脏读缓存）。
    先例：history.json 里 2026-07-24 与 2026-07-27 的 SPX/NDX/VIX/VXN/CTA 完全相同。
    """
    cache_path = data_dir / CACHE_FILENAME
    result: Dict[str, Any] = {"checked": False, "is_stale": False, "note": ""}

    keys = ["SPX", "NDX", "VIX", "VXN"]
    current_snapshot = {k: market_core.get(k, {}).get("current") for k in keys}
    current_as_of = {k: market_core.get(k, {}).get("as_of") for k in keys}

    if cache_path.exists():
        try:
            with open(cache_path) as f:
                last = json.load(f)
            last_snapshot = last.get("snapshot", {})
            last_as_of = last.get("as_of", {})

            dates_changed = any(
                current_as_of.get(k) != last_as_of.get(k)
                for k in keys
                if current_as_of.get(k) and last_as_of.get(k)
            )
            values_identical = all(
                current_snapshot.get(k) == last_snapshot.get(k)
                for k in keys
                if current_snapshot.get(k) is not None
            )

            result["checked"] = True
            if values_identical and dates_changed:
                result["is_stale"] = True
                result["note"] = f"⚠️ 日期已变化但 {keys} 数值与上次完全相同，疑似缓存脏读"
            elif values_identical and not dates_changed:
                result["is_stale"] = False
                result["note"] = "与上次快照日期相同，属正常重复（非新交易日）"
            else:
                result["is_stale"] = False
                result["note"] = "快照与上次不同，正常更新"
        except Exception as e:
            result["note"] = f"读取上次缓存失败: {e}"
    else:
        result["note"] = "无历史缓存，首次运行，无法比对"

    # 无论校验结果如何，都把这次快照写回去，供下次比对
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(
                {
                    "snapshot": current_snapshot,
                    "as_of": current_as_of,
                    "written_at_utc": datetime.utcnow().isoformat() + "Z",
                },
                f,
            )
    except Exception as e:
        result["note"] += f" | 写入缓存失败: {e}"

    return result


def guard_indicator(
    indicator_name: str,
    market_core: Dict[str, Any],
    fred_api_key: str,
    stale_result: Dict[str, Any],
) -> Dict[str, Any]:
    """汇总单个指标（SPX / NDX）的所有校验结果，给出 trusted 结论。"""
    guard: Dict[str, Any] = {"indicator": indicator_name, "stale_cache": stale_result}

    if indicator_name == "SPX":
        cv = cross_validate_spx(market_core.get("SPX", {}), fred_api_key)
    elif indicator_name == "NDX":
        cv = cross_validate_ndx(market_core.get("NDX", {}), fred_api_key)
    else:
        cv = {"checked": False, "trusted": None, "note": "该指标暂无交叉校验"}

    guard["cross_validation"] = cv

    if stale_result.get("is_stale"):
        guard["trusted"] = False
        guard["reason"] = "疑似缓存陈旧（数值与上次完全相同但日期已变）"
    elif cv.get("checked") and cv.get("trusted") is False:
        guard["trusted"] = False
        guard["reason"] = "跨源交叉校验不通过"
    elif cv.get("checked") and cv.get("trusted") is True:
        guard["trusted"] = True
        guard["reason"] = "跨源交叉校验通过"
    else:
        # 无法确认 ≠ 确认没问题。按三步核验铁律：明确说"无法确认"，不冒充精确结论。
        guard["trusted"] = None
        guard["reason"] = "无可用交叉源，未能验证——不应直接当作已确认的真实异常"

    return guard


def run_guard_for(
    indicator_names: Set[str],
    indicators: Dict[str, Any],
    fred_api_key: str,
    data_dir: Path,
) -> Dict[str, Dict[str, Any]]:
    """
    主入口：只对已经触发异常阈值的指标做兜底校验（保持哨兵日常轻量，无异常时不产生这层开销）。
    indicator_names: 例如 {"SPX", "NDX"}
    """
    market_core = indicators.get("market", {})
    stale = check_stale_cache(market_core, data_dir)

    out: Dict[str, Dict[str, Any]] = {}
    for name in indicator_names:
        if name in ("SPX", "NDX"):
            out[name] = guard_indicator(name, market_core, fred_api_key, stale)
    return out


def build_integrity_notice_card(distrusted: list, page_url: str) -> Dict[str, Any]:
    """
    数据完整性告警卡片（灰色主题，区别于红/橙的真实异常警报）：
    告诉 Aaron "抓到了看似异常的数值，但没通过校验，判定为疑似脏读，本次不当真实异常处理"，
    而不是悄无声息地吞掉，也不是硬着头皮当真实数据推送。
    """
    lines = []
    for a in distrusted:
        g = a.get("_guard", {})
        cv = g.get("cross_validation", {})
        lines.append(f"❌ **{a['summary']}**\n   {g.get('reason', '')} — {cv.get('note', g.get('stale_cache', {}).get('note', ''))}")

    return {
        "config": {"wide_screen_mode": True, "enable_forward": True},
        "header": {
            "title": {"tag": "plain_text", "content": "🔧 数据完整性告警（非真实异常）"},
            "template": "grey",
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        "检测到疑似异常的原始读数，但**未通过跨源校验**，"
                        "判定为抓取层脏读（yfinance 缓存/行错位等），本次**不作为真实市场异常推送**。\n\n"
                        + "\n\n".join(lines)
                    ),
                },
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "建议：如果你在别的渠道也看到当天市场有大幅波动，请手动核实；如果没有，大概率就是本次抓取的问题，无需处理。",
                },
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "📊 查看 Dashboard"},
                        "url": page_url,
                        "type": "default",
                    }
                ],
            },
        ],
    }
