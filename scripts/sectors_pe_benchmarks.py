"""
sectors_pe_benchmarks.py
板块 5Y Forward PE 历史均值/标准差 benchmark 表。
过渡期（前 90 天）用这张表算近似 z-score；之后切换到累积历史。

数据来源：FactSet / Yardeni / 各 ETF 历史 (2021-2026 区间)
覆盖 2022 熊市、2023 反弹、2024 AI 高峰、2025 关税回调
"""

PE_BENCHMARKS = {
    # === 根 1: AI 物理层 ===
    "ai_semis":          {"mean": 24.5, "std": 5.0,  "note": "SMH 5Y avg ~24-25x"},
    "semi_equipment":    {"mean": 22.0, "std": 4.5,  "note": "SOXX 5Y avg ~22x"},
    "optical_networking":{"mean": 28.0, "std": 8.0,  "note": "光学 basket，2024 LITE 重估"},
    "quantum":           {"mean": None, "std": None, "note": "多数公司亏损"},

    # === 根 2: AI 数据中心 ===
    "neocloud":          {"mean": None, "std": None, "note": "新兴公司多亏损或 IPO 不久"},
    "dc_self_power":     {"mean": None, "std": None, "note": "FLNC/FCEL/BE 多数亏损，GEV 有盈利但混合"},
    "ai_power_equip":    {"mean": 22.0, "std": 4.0,  "note": "ETN/PWR 5Y avg ~22x"},
    "dc_cooling":        {"mean": 32.0, "std": 7.0,  "note": "VRT/MOD 成长估值"},

    # === 根 3: 软件应用层 ===
    "megacap_tech":      {"mean": 26.0, "std": 4.5,  "note": "XLK 5Y avg ~26x"},
    "saas":              {"mean": 32.0, "std": 7.0,  "note": "IGV 2021 高 50x，2022 低 22x"},
    "cybersecurity":     {"mean": 35.0, "std": 6.5,  "note": "CIBR 5Y avg ~35x"},

    # === 根 4: 自主系统 ===
    "autonomy":          {"mean": 40.0, "std": 12.0, "note": "TSLA 60-90x 主导，分散度大"},

    # === 根 5-7: 国防 / 商业航天 / 无人机 ===
    "defense":           {"mean": 22.0, "std": 4.0,  "note": "LMT/RTX/GD 5Y avg ~22x"},
    "commercial_space":  {"mean": None, "std": None, "note": "RKLB/ASTS/RDW 多数亏损"},
    "drones":            {"mean": 30.0, "std": 6.0,  "note": "AVAV/KTOS 国防成长"},

    # === 根 8: AI 电力 ===
    "ai_power":          {"mean": 20.0, "std": 5.0,  "note": "CEG/TLN/VST 电力 IPP"},

    # === 根 9: 能源公用 ===
    "energy":            {"mean": 13.0, "std": 3.5,  "note": "XLE 5Y avg ~13x"},
    "nuclear":           {"mean": 25.0, "std": 8.0,  "note": "OKLO/SMR 亏损 + NLR 成熟核电，混合"},
    "utilities":         {"mean": 18.0, "std": 2.5,  "note": "XLU 5Y avg ~18x"},

    # === 根 10: 存储 ===
    "storage":           {"mean": 15.0, "std": 5.0,  "note": "MU/WDC/STX 周期性大，5Y avg ~15x"},

    # === 根 11: 医疗 ===
    "healthcare":        {"mean": 17.5, "std": 2.5,  "note": "XLV 5Y avg ~17-18x"},
    "glp1":              {"mean": 32.0, "std": 8.0,  "note": "LLY 5Y avg ~35x"},
    "medicare_advantage":{"mean": 16.0, "std": 4.0,  "note": "HUM/UNH 5Y avg 16-18x，2024 MCR 危机后压缩"},

    # === 根 12: 金融 ===
    "financials":        {"mean": 13.0, "std": 2.5,  "note": "XLF 5Y avg ~13x"},

    # === 根 13: 中国 ===
    "china_tech":        {"mean": 12.0, "std": 4.0,  "note": "KWEB 2021 监管打击后压缩"},

    # === 根 14: 加密 BTC ===
    "btc_spot":          {"mean": None, "std": None, "note": "BTC 现货 ETF 无传统 PE"},
    "btc_miners":        {"mean": None, "std": None, "note": "矿企盈利波动极大"},
    "crypto_brokers":    {"mean": 22.0, "std": 12.0, "note": "COIN/HOOD 跨牛熊周期波动大"},

    # === 根 15: 消费工业 ===
    "industrials":       {"mean": 18.0, "std": 2.5,  "note": "XLI 5Y avg ~18x"},
    "homebuilders":      {"mean": 11.0, "std": 3.0,  "note": "XHB 5Y avg ~10-12x"},
    "commercial_aero":   {"mean": 20.0, "std": 5.0,  "note": "BA/RTX/TDG 5Y avg ~20x"},
}


def get_benchmark(sector_key: str):
    bm = PE_BENCHMARKS.get(sector_key)
    if not bm or bm["mean"] is None:
        return None
    return bm


if __name__ == "__main__":
    has_bm = sum(1 for v in PE_BENCHMARKS.values() if v["mean"] is not None)
    print(f"Total: {len(PE_BENCHMARKS)} sectors")
    print(f"With benchmark: {has_bm}")
    print(f"Without (no traditional PE): {len(PE_BENCHMARKS) - has_bm}")
