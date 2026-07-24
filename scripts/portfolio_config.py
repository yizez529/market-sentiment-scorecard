"""
portfolio_config.py
Aaron 的持仓配置 + regime 设定。
用于周报的 Portfolio Overlay 模块和异常哨兵的持仓冲击检测。
"""

# ========== Regime 设定 ==========
# 手动切换：normal / low_guidance / crisis
# - normal: Powell 时代，前瞻指引充分，标准阈值
# - low_guidance: Warsh 时代，取消前瞻指引，行动阈值收紧 5 分
# - crisis: 重大流动性/系统性事件，行动阈值收紧 10 分
REGIME = "low_guidance"

REGIME_MODIFIERS = {
    "normal": {"threshold_shift": 0, "label": "正常指引", "vix_complacency": 15},
    "low_guidance": {"threshold_shift": -5, "label": "Warsh低指引模式", "vix_complacency": 16},
    "crisis": {"threshold_shift": -10, "label": "危机模式", "vix_complacency": 12},
}

# ========== 持仓清单（2024-07-24 更新）==========
# 分层：high_weight (含期权等价权重 > 3%), medium_weight (1-3%), small/options (< 1%)
# 每个 ticker 标注映射的板块 key（与 sectors_config.py 对齐）

PORTFOLIO = {
    "high_weight": {
        # ticker: (sector_key, combined_weight_pct, note)
        "GOOGL": ("big_tech", 9.10, "正股"),
        "AVAV": ("drone", 10.29, "正股6.85% + Aug 175C 3.44%"),
        "CEG": ("ai_power", 8.88, "正股6.49% + Aug 280C 2.39%"),
        "QCOM": ("ai_semi", 7.38, "正股4.58% + Mar27 180C 2.80%"),
        "MSFT": ("big_tech", 6.48, "正股2.82% + 多档LEAPS ~3.66%"),
        "NOW": ("software_saas", 6.04, "正股1.89% + 多档LEAPS ~4.15%"),
        "HOOD": ("crypto_exchange", 5.56, "正股"),
        "PLTR": ("defense", 5.67, "纯期权：多档LEAPS"),
        "AVGO": ("ai_semi", 5.49, "正股"),
        "RKLB": ("commercial_space", 5.56, "正股4.62% + Oct 100C 0.94%"),
        "CRCL": ("crypto_exchange", 5.19, "正股 Circle"),
        "APP": ("software_saas", 3.88, "正股3.81% + Jul 490C 0.07%"),
        "GLW": ("optical_interconnect", 3.66, "正股3.50% + Jul 190C 0.16%"),
        "MOD": ("dc_cooling", 3.44, "正股"),
        "NET": ("cybersecurity", 3.12, "正股"),
        "ISRG": ("healthcare", 3.12, "正股"),
    },
    "medium_weight": {
        "MDA": ("commercial_space", 2.60, "正股"),
        "LEU": ("nuclear_smr", 2.20, "正股"),
        "SNOW": ("software_saas", 1.95, "正股"),
        "NFLX": ("big_tech", 1.48, "期权"),
        "AKAM": ("cybersecurity", 1.46, "多档期权"),
        "TRI": ("software_saas", 1.45, "多档期权"),  # agent data workflow
    },
    "small_and_options": {
        # < 1% 权重的期权和小仓位
        "BEX": ("dc_self_power", 0.92, "2x做多BE ETF"),
        "PONY": ("autonomous_ev", 0.85, "LEAPS"),
        "07709_HK": ("memory", 1.85, "港股南方两倍做多海力士"),
        "SDGR": ("software_saas", 0.73, "期权"),
        "ETN": ("ai_power_equip", 0.71, "期权"),
        "GPCR": ("healthcare", 0.69, "期权"),
        "CECO": ("dc_cooling", 0.69, "期权"),
        "01357_HK": ("big_tech", 0.69, "港股美图公司"),
        "JOBY": ("autonomous_ev", 0.62, "LEAPS"),
        "VEEV": ("software_saas", 0.48, "期权"),
        "VRT": ("dc_cooling", 0.44, "期权"),
        "CRM": ("software_saas", 0.40, "期权"),
        "AMKR": ("semi_equip", 0.40, "期权"),  # 封测
        "ON": ("ai_semi", 0.34, "期权"),
        "FORM": ("semi_equip", 0.31, "期权"),
        "KLIC": ("semi_equip", 0.31, "期权"),
        "COHU": ("semi_equip", 0.30, "期权"),
        "IONQ": ("quantum", 0.29, "期权"),
        "PL": ("commercial_space", 0.93, "LEAPS"),
        "RDW": ("commercial_space", 1.23, "LEAPS"),
        "MP": ("industrial", 0.27, "期权"),
        "GNRC": ("ai_power_equip", 0.21, "期权"),
        "MCD": ("industrial", 0.15, "期权"),
        "DKNG": ("big_tech", 0.14, "期权"),
        "UBER": ("autonomous_ev", 0.18, "期权"),
        "BSX": ("healthcare", 0.14, "期权"),
        "TEAM": ("software_saas", 0.13, "期权"),
        "09611_HK": ("big_tech", 0.75, "港股龙旗科技"),
    },
    "short_and_hedge": {
        # 空头 / 对冲仓位（权重为负）
        "HUM": ("medicare_advantage", -3.11, "做空正股-2.51% + Aug 330P 0.60%"),
        "STX": ("memory", -0.83, "做空正股"),
        "DAMD": ("ai_semi", -0.28, "2x做空AMD ETF"),
    },
}


def get_all_tickers() -> dict:
    """返回 {ticker: (sector_key, weight, note)} 的扁平字典"""
    flat = {}
    for tier in ("high_weight", "medium_weight", "small_and_options", "short_and_hedge"):
        for ticker, info in PORTFOLIO[tier].items():
            flat[ticker] = info
    return flat


def get_sector_exposure() -> dict:
    """按板块汇总净暴露权重"""
    exposure = {}
    for ticker, (sector_key, weight, note) in get_all_tickers().items():
        if sector_key not in exposure:
            exposure[sector_key] = {"net_weight": 0, "tickers": []}
        exposure[sector_key]["net_weight"] += weight
        exposure[sector_key]["tickers"].append((ticker, weight, note))
    # 排序
    for k in exposure:
        exposure[k]["tickers"].sort(key=lambda x: abs(x[1]), reverse=True)
    return exposure


def get_regime_modifier() -> dict:
    """返回当前 regime 的修正参数"""
    return REGIME_MODIFIERS.get(REGIME, REGIME_MODIFIERS["normal"])
