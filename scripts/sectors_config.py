"""
sectors_config.py
26 个板块的清单。每个板块定义：
- key: 内部 id
- name_zh: 中文名（飞书+dashboard 显示）
- root: theme-sector-radar 的根编号（用于 dashboard 分组）
- type: 'etf' (单 ETF) 或 'basket' (等权篮子)
- ticker / tickers: 数据源
- benchmark: 相对强度对比基准（默认 SPY，部分用 QQQ 更合理）
- key_stocks: 3-5 只最具代表性的个股（用于计算"本板块最值得操作的 3 只"）
"""

SECTORS = [
    # ===== 根 1: AI 物理层 =====
    {
        "key": "ai_semis", "name_zh": "AI 半导体", "root": "AI物理层",
        "type": "etf", "ticker": "SMH", "benchmark": "SPY",
        "components": "NVDA AMD AVGO MRVL TSM",
        "key_stocks": ["NVDA", "AMD", "AVGO", "TSM", "MRVL"],
    },
    {
        "key": "semi_equipment", "name_zh": "半导体设备", "root": "AI物理层",
        "type": "etf", "ticker": "SOXX", "benchmark": "SPY",
        "components": "ASML AMAT LRCX KLAC",
        "key_stocks": ["ASML", "AMAT", "LRCX", "KLAC", "ONTO"],
    },
    {
        "key": "optical_networking", "name_zh": "光互连/网络", "root": "AI物理层",
        "type": "basket", "tickers": ["COHR", "LITE", "CIEN", "ANET", "CRDO"],
        "benchmark": "SPY",
        "components": "COHR LITE CIEN ANET CRDO",
        "key_stocks": ["COHR", "LITE", "CIEN", "ANET", "CRDO"],
    },
    {
        "key": "quantum", "name_zh": "量子计算", "root": "AI物理层",
        "type": "basket", "tickers": ["IONQ", "RGTI", "QBTS", "QUBT"],
        "benchmark": "QQQ",
        "components": "IONQ RGTI QBTS QUBT",
        "key_stocks": ["IONQ", "RGTI", "QBTS", "QUBT"],
    },

    # ===== 根 2: AI 数据中心物理设施 =====
    {
        "key": "neocloud", "name_zh": "Neocloud", "root": "AI数据中心",
        "type": "basket", "tickers": ["CRWV", "NBIS", "IREN", "APLD", "CIFR"],
        "benchmark": "SPY",
        "components": "CRWV NBIS IREN APLD CIFR",
        "key_stocks": ["CRWV", "NBIS", "IREN", "APLD", "CIFR"],
    },
    {
        "key": "power_grid", "name_zh": "电力/数据中心电气", "root": "AI数据中心",
        "type": "basket", "tickers": ["GEV", "ETN", "PWR", "HUBB"],
        "benchmark": "SPY",
        "components": "GEV ETN PWR HUBB",
        "key_stocks": ["GEV", "ETN", "PWR", "HUBB"],
    },
    {
        "key": "datacenter_reit", "name_zh": "数据中心 REIT/冷却", "root": "AI数据中心",
        "type": "basket", "tickers": ["VRT", "MOD", "DLR", "EQIX"],
        "benchmark": "SPY",
        "components": "VRT MOD DLR EQIX",
        "key_stocks": ["VRT", "MOD", "DLR", "EQIX"],
    },

    # ===== 根 3: 软件 / AI 应用层 =====
    {
        "key": "megacap_tech", "name_zh": "大型科技", "root": "软件应用层",
        "type": "etf", "ticker": "XLK", "benchmark": "SPY",
        "components": "AAPL MSFT GOOGL META",
        "key_stocks": ["AAPL", "MSFT", "GOOGL", "META", "NVDA"],
    },
    {
        "key": "saas", "name_zh": "软件 SaaS", "root": "软件应用层",
        "type": "etf", "ticker": "IGV", "benchmark": "QQQ",
        "components": "NOW CRM SNOW DDOG MDB",
        "key_stocks": ["NOW", "CRM", "SNOW", "DDOG", "MDB"],
    },
    {
        "key": "cybersecurity", "name_zh": "网络安全", "root": "软件应用层",
        "type": "etf", "ticker": "CIBR", "benchmark": "QQQ",
        "components": "CRWD PANW ZS S OKTA",
        "key_stocks": ["CRWD", "PANW", "ZS", "S", "OKTA"],
    },

    # ===== 根 4: 自主系统 =====
    {
        "key": "autonomy", "name_zh": "自动驾驶/机器人", "root": "自主系统",
        "type": "basket", "tickers": ["TSLA", "UBER", "MBLY", "AMBA", "SYM"],
        "benchmark": "QQQ",
        "components": "TSLA UBER MBLY AMBA SYM",
        "key_stocks": ["TSLA", "UBER", "MBLY", "AMBA", "SYM"],
    },

    # ===== 根 5: 国防与航天 =====
    {
        "key": "defense_space", "name_zh": "国防/航天", "root": "国防航天",
        "type": "basket", "tickers": ["LMT", "RTX", "GD", "NOC", "PLTR", "RKLB", "ASTS"],
        "benchmark": "SPY",
        "components": "ITA + PLTR RKLB ASTS",
        "key_stocks": ["LMT", "RTX", "PLTR", "RKLB", "ASTS"],
    },

    # ===== 根 6: 能源转型 / 公用事业 =====
    {
        "key": "energy", "name_zh": "传统能源", "root": "能源公用",
        "type": "etf", "ticker": "XLE", "benchmark": "SPY",
        "components": "XOM CVX EOG",
        "key_stocks": ["XOM", "CVX", "EOG", "SLB", "COP"],
    },
    {
        "key": "nuclear", "name_zh": "核 / SMR", "root": "能源公用",
        "type": "basket", "tickers": ["OKLO", "SMR", "NNE", "NLR"],
        "benchmark": "SPY",
        "components": "OKLO SMR NNE NLR",
        "key_stocks": ["OKLO", "SMR", "NNE", "NLR"],
    },
    {
        "key": "utilities", "name_zh": "公用事业", "root": "能源公用",
        "type": "etf", "ticker": "XLU", "benchmark": "SPY",
        "components": "NEE SO DUK",
        "key_stocks": ["NEE", "SO", "DUK", "AEP", "CEG"],
    },

    # ===== 根 7: 医疗 =====
    {
        "key": "healthcare", "name_zh": "医疗保健", "root": "医疗",
        "type": "etf", "ticker": "XLV", "benchmark": "SPY",
        "components": "UNH LLY JNJ",
        "key_stocks": ["UNH", "LLY", "JNJ", "ABT", "MDT"],
    },
    {
        "key": "glp1", "name_zh": "GLP-1 减重药", "root": "医疗",
        "type": "basket", "tickers": ["LLY", "NVO", "VKTX"],
        "benchmark": "XLV",
        "components": "LLY NVO VKTX",
        "key_stocks": ["LLY", "NVO", "VKTX"],
    },
    {
        "key": "medicare_advantage", "name_zh": "Medicare Advantage", "root": "医疗",
        "type": "basket", "tickers": ["HUM", "UNH", "CVS", "CI", "ELV"],
        "benchmark": "XLV",
        "components": "HUM UNH CVS CI ELV",
        "key_stocks": ["HUM", "UNH", "CVS", "CI", "ELV"],
    },

    # ===== 根 8: 金融 =====
    {
        "key": "financials", "name_zh": "金融", "root": "金融",
        "type": "etf", "ticker": "XLF", "benchmark": "SPY",
        "components": "JPM BAC WFC",
        "key_stocks": ["JPM", "BAC", "GS", "MS", "WFC"],
    },

    # ===== 根 9: 中国 / 新兴市场 =====
    {
        "key": "china_tech", "name_zh": "中概互联", "root": "中国新兴市场",
        "type": "etf", "ticker": "KWEB", "benchmark": "SPY",
        "components": "BABA PDD JD TCEHY",
        "key_stocks": ["BABA", "PDD", "JD", "BIDU", "NTES"],
    },

    # ===== 根 10: 加密 / BTC 生态 =====
    {
        "key": "btc_spot", "name_zh": "BTC 现货", "root": "加密BTC",
        "type": "etf", "ticker": "IBIT", "benchmark": "SPY",
        "components": "IBIT (BTC spot ETF)",
        "key_stocks": ["IBIT", "FBTC", "MSTR"],  # ETF 作为个股代理
    },
    {
        "key": "btc_miners", "name_zh": "BTC 矿企", "root": "加密BTC",
        "type": "etf", "ticker": "WGMI", "benchmark": "IBIT",
        "components": "MARA RIOT CLSK BTBT",
        "key_stocks": ["MARA", "RIOT", "CLSK", "CIFR", "BTBT"],
    },
    {
        "key": "crypto_brokers", "name_zh": "加密交易所/经纪", "root": "加密BTC",
        "type": "basket", "tickers": ["COIN", "HOOD", "MSTR"],
        "benchmark": "IBIT",
        "components": "COIN HOOD MSTR",
        "key_stocks": ["COIN", "HOOD", "MSTR"],
    },

    # ===== 根 12: 消费 / 工业 =====
    {
        "key": "industrials", "name_zh": "工业", "root": "消费工业",
        "type": "etf", "ticker": "XLI", "benchmark": "SPY",
        "components": "GE BA CAT",
        "key_stocks": ["GE", "BA", "CAT", "HON", "DE"],
    },
    {
        "key": "homebuilders", "name_zh": "房屋建造", "root": "消费工业",
        "type": "etf", "ticker": "XHB", "benchmark": "SPY",
        "components": "DHI LEN PHM (利率敏感)",
        "key_stocks": ["DHI", "LEN", "PHM", "NVR", "TOL"],
    },
    {
        "key": "commercial_aero", "name_zh": "商用航空", "root": "消费工业",
        "type": "basket", "tickers": ["BA", "RTX", "TDG", "HEI"],
        "benchmark": "SPY",
        "components": "BA RTX TDG HEI",
        "key_stocks": ["BA", "RTX", "TDG", "HEI"],
    },
]


def get_all_tickers():
    """返回所有需要从 yfinance 抓的 ticker（去重，含 key_stocks）"""
    all_tickers = set()
    for s in SECTORS:
        if s["type"] == "etf":
            all_tickers.add(s["ticker"])
        else:
            all_tickers.update(s["tickers"])
        all_tickers.add(s["benchmark"])
        # key_stocks 也纳入 batch（大部分和 basket tickers 重合，额外增量不多）
        all_tickers.update(s.get("key_stocks", []))
    all_tickers.update(["SPY", "QQQ"])
    return sorted(all_tickers)


if __name__ == "__main__":
    print(f"Total sectors: {len(SECTORS)}")
    print(f"Unique tickers to fetch (含 key_stocks): {len(get_all_tickers())}")
    print("\nSectors by root:")
    from collections import defaultdict
    by_root = defaultdict(list)
    for s in SECTORS:
        by_root[s["root"]].append(s["name_zh"])
    for root, names in by_root.items():
        print(f"  {root}: {', '.join(names)}")
