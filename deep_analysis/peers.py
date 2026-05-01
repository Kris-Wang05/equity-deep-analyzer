"""
同行对标映射：industry / sector → 主要竞争对手 ticker 列表。
覆盖不到的回退到 sector ETF 单独对比。
"""

# Sector → 板块 ETF（粗）
SECTOR_ETF = {
    "Technology": "XLK",
    "Energy": "XLE",
    "Utilities": "XLU",
    "Industrials": "XLI",
    "Healthcare": "XLV",
    "Health Care": "XLV",
    "Consumer Cyclical": "XLY",
    "Consumer Discretionary": "XLY",
    "Consumer Defensive": "XLP",
    "Consumer Staples": "XLP",
    "Financial Services": "XLF",
    "Financial": "XLF",
    "Financials": "XLF",
    "Basic Materials": "XLB",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}

# Industry (lower-case substring) → 细分行业 ETF（精）
# 优先级高于 SECTOR_ETF。半导体设备走 SMH 比 XLK 准得多。
# 关键字按子串匹配，最长匹配优先。
INDUSTRY_ETF = {
    "semiconductor equipment": "SMH",
    "semiconductors": "SMH",
    "software—infrastructure": "IGV",
    "software—application": "IGV",
    "software": "IGV",
    "internet content": "FDN",
    "internet retail": "XRT",
    "communication equipment": "IYW",
    "biotechnology": "XBI",
    "drug manufacturers": "XPH",
    "medical devices": "IHI",
    "medical instruments": "IHI",
    "healthcare plans": "IHF",
    "oil & gas e&p": "XOP",
    "oil & gas equipment": "OIH",
    "oil & gas integrated": "XLE",
    "oil & gas refining": "XLE",
    "oil & gas midstream": "AMLP",
    "banks—diversified": "KBE",
    "banks—regional": "KRE",
    "banks": "KBE",
    "insurance": "KIE",
    "asset management": "XLF",
    "credit services": "IPAY",
    "capital markets": "IAI",
    "aerospace": "ITA",
    "defense": "ITA",
    "auto manufacturers": "CARZ",
    "auto parts": "CARZ",
    "airlines": "JETS",
    "trucking": "IYT",
    "railroads": "IYT",
    "steel": "SLX",
    "copper": "COPX",
    "gold": "GDX",
    "specialty chemicals": "XLB",
    "reit": "VNQ",
    "reit—industrial": "VNQ",
    "reit—residential": "REZ",
    "reit—retail": "VNQ",
    "reit—healthcare": "VNQ",
    "utilities—regulated electric": "XLU",
    "telecom services": "VOX",
    "entertainment": "XLC",
    "restaurants": "PEJ",
    "discount stores": "XRT",
    "specialty retail": "XRT",
    "household & personal products": "XLP",
    "tobacco": "XLP",
    "beverages—non-alcoholic": "XLP",
    "beverages—alcoholic": "XLP",
}


# industry (lowercase substring) → 同行 ticker 列表
# 关键字优先匹配，能命中具体 industry 用具体的，不行再 fallback 到 sector
INDUSTRY_PEERS = {
    "semiconductor equipment": ["AMAT", "LRCX", "KLAC", "ASML"],
    "semiconductors": ["NVDA", "AMD", "AVGO", "QCOM"],
    "software": ["MSFT", "ORCL", "CRM", "ADBE"],
    "software—application": ["MSFT", "CRM", "ADBE"],
    "software—infrastructure": ["MSFT", "ORCL", "VMW"],
    "internet content": ["GOOGL", "META", "NFLX"],
    "internet retail": ["AMZN", "EBAY", "SHOP"],
    "consumer electronics": ["AAPL", "SONY", "HPQ"],
    "communication equipment": ["CSCO", "JNPR", "MSI"],
    "electronic components": ["APH", "GLW", "FLEX"],
    "electrical equipment & parts": ["EMR", "ETN", "ROK"],
    "scientific & technical instruments": ["TMO", "DHR", "WAT"],
    "information technology services": ["IBM", "ACN", "INFY"],
    "specialty industrial machinery": ["ITW", "EMR", "ROK"],
    "aerospace": ["BA", "LMT", "RTX", "GD"],
    "defense": ["LMT", "RTX", "GD", "NOC"],
    "oil & gas": ["XOM", "CVX", "COP"],
    "oil & gas e&p": ["EOG", "PXD", "DVN", "FANG"],
    "oil & gas integrated": ["XOM", "CVX", "COP", "BP"],
    "oil & gas equipment": ["SLB", "HAL", "BKR"],
    "oil & gas refining": ["VLO", "MPC", "PSX"],
    "oil & gas midstream": ["KMI", "ENB", "WMB"],
    "drug manufacturers": ["JNJ", "PFE", "MRK", "LLY"],
    "biotechnology": ["AMGN", "GILD", "REGN", "VRTX"],
    "medical devices": ["MDT", "BSX", "SYK", "ABT"],
    "medical instruments": ["TMO", "DHR", "ISRG"],
    "healthcare plans": ["UNH", "ELV", "CI", "HUM"],
    "banks": ["JPM", "BAC", "WFC", "C"],
    "banks—diversified": ["JPM", "BAC", "WFC"],
    "banks—regional": ["USB", "PNC", "TFC"],
    "insurance": ["BRK-B", "PGR", "TRV", "ALL"],
    "asset management": ["BLK", "BX", "KKR"],
    "credit services": ["V", "MA", "AXP"],
    "capital markets": ["GS", "MS", "SCHW"],
    "auto manufacturers": ["TSLA", "F", "GM", "TM"],
    "auto parts": ["APTV", "BWA", "LEA"],
    "restaurants": ["MCD", "SBUX", "CMG", "YUM"],
    "specialty retail": ["HD", "LOW", "TJX"],
    "discount stores": ["WMT", "COST", "TGT"],
    "household & personal products": ["PG", "CL", "KMB"],
    "beverages—non-alcoholic": ["KO", "PEP", "MNST"],
    "beverages—alcoholic": ["DEO", "BUD", "STZ"],
    "tobacco": ["MO", "PM", "BTI"],
    "utilities—regulated electric": ["NEE", "DUK", "SO"],
    "reit": ["AMT", "PLD", "EQIX"],
    "reit—industrial": ["PLD", "DRE", "STAG"],
    "reit—residential": ["AVB", "EQR", "INVH"],
    "reit—retail": ["O", "SPG", "REG"],
    "reit—healthcare": ["WELL", "VTR", "PEAK"],
    "specialty chemicals": ["LIN", "APD", "ECL"],
    "chemicals": ["DOW", "DD", "LYB"],
    "steel": ["NUE", "STLD", "X"],
    "copper": ["FCX", "SCCO", "TECK"],
    "gold": ["NEM", "GOLD", "AEM"],
    "airlines": ["DAL", "UAL", "AAL", "LUV"],
    "trucking": ["ODFL", "JBHT", "KNX"],
    "railroads": ["UNP", "CSX", "NSC"],
    "telecom services": ["T", "VZ", "TMUS"],
    "entertainment": ["DIS", "NFLX", "CMCSA"],
}


# 特殊 ticker → 同行覆盖（用于工具按 industry 自动匹配会选错同行的票）
# 优先级最高：在 get_peers 第一步检查
TICKER_PEERS_OVERRIDE = {
    # OEM 发动机（LSE / ADR / 美本土）—— 同行 = GE Aerospace, Safran (SAF.PA), Heico
    "RR.L": ["GE", "SAF.PA", "HEI"],
    "RYCEY": ["GE", "SAF.PA", "HEI"],

    # OSAT 半导体封测 —— 同行 = Amkor (AMKR)，台 Powertech (PTI 不易拉)
    "ASX": ["AMKR"],

    # AI 数据中心电力 / 核电 IPP —— 同行 = CEG, NRG, TLN
    "VST": ["CEG", "NRG", "TLN"],
    "CEG": ["VST", "NRG", "TLN"],
    "TLN": ["VST", "CEG", "NRG"],

    # 直连卫星通信 —— 同行 = Iridium (IRDM), Globalstar (GSAT)
    "ASTS": ["IRDM", "GSAT"],

    # 国防无人机 / counter-UAS —— 同行 = Kratos (KTOS), Northrop (NOC)
    "AVAV": ["KTOS", "NOC", "LMT"],

    # 移动发电 / 数据中心电力主题 —— 同行 = Generac (GNRC), CMI
    "SOI": ["GNRC", "CMI"],

    # 工业连接器（vs 半导体 IC 设计）—— 同行 = APH, GLW, FLEX
    "TEL": ["APH", "GLW", "FLEX"],

    # 电网/AI 电力/超导（vs 大盘工业巨头）—— 同行 = GEV, VRT, POWL
    "AMSC": ["GEV", "VRT", "POWL"],
    "POWL": ["AMSC", "GEV", "VRT"],

    # 数据中心电力/冷却 —— 同行 = AMSC, GEV, ETN
    "VRT": ["AMSC", "GEV", "ETN"],

    # 半导体材料/化学品（vs fab equipment 巨头）—— 同行 = MKSI, ASMI, KLAC
    "ENTG": ["MKSI", "ASMI", "KLAC"],
    "MKSI": ["ENTG", "ASMI", "KLAC"],

    # OSAT 半导体封测 —— 已在上面（ASX → AMKR）
}


def get_sector_etf(sector, industry=None):
    """
    返回最匹配的对标 ETF ticker。优先级：
      1. industry 子串命中（最长匹配）→ 细分行业 ETF（如半导体设备 → SMH）
      2. sector 命中 → 板块 ETF（如 Technology → XLK）
      3. fallback → SPY
    """
    if industry:
        ind_lower = industry.lower()
        matches = [(k, v) for k, v in INDUSTRY_ETF.items() if k in ind_lower]
        if matches:
            matches.sort(key=lambda x: -len(x[0]))
            return matches[0][1]
    if sector:
        return SECTOR_ETF.get(sector, "SPY")
    return "SPY"


def get_peers(sector, industry, exclude_ticker=None):
    """
    根据 sector / industry 返回 2-3 家主要竞争对手 ticker.
    优先级：
      1. TICKER_PEERS_OVERRIDE （特殊票，绕过 industry 自动匹配错误）
      2. INDUSTRY_PEERS 子串匹配（最长优先）
      3. 空列表（valuation 模块降级处理）
    exclude_ticker: 自动排除自己。
    """
    # 0. 特殊覆盖
    if exclude_ticker:
        override = TICKER_PEERS_OVERRIDE.get(exclude_ticker.upper())
        if override:
            return [p for p in override if p.upper() != exclude_ticker.upper()][:3]

    peers = []
    if industry:
        ind_lower = industry.lower()
        matches = [(k, v) for k, v in INDUSTRY_PEERS.items() if k in ind_lower]
        if matches:
            matches.sort(key=lambda x: -len(x[0]))
            peers = list(matches[0][1])

    if not peers:
        return []

    if exclude_ticker:
        peers = [p for p in peers if p.upper() != exclude_ticker.upper()]

    return peers[:3]
