"""
模块0：大势判断（板块ETF）。
模块6：技术面位置（52周高低 / 200日均线）。
"""

from deep_analysis.data_fetcher import fetch_etf
from deep_analysis.peers import get_sector_etf


def _ytd_return(history):
    """history: yfinance DataFrame, index 是 datetime."""
    if history is None or history.empty:
        return None
    try:
        idx = history.index
        if hasattr(idx, "tz") and idx.tz is not None:
            history = history.copy()
            history.index = idx.tz_localize(None)
            idx = history.index
        last_year = idx[-1].year
        start_of_year = history[history.index.year == last_year]
        if start_of_year.empty:
            return None
        first = start_of_year["Close"].iloc[0]
        last = start_of_year["Close"].iloc[-1]
        if first == 0:
            return None
        return (last - first) / first * 100
    except Exception:
        return None


def _3m_return(history):
    if history is None or history.empty:
        return None
    try:
        if len(history) < 60:
            return None
        recent = history["Close"]
        first = recent.iloc[max(0, len(recent) - 63)]
        last = recent.iloc[-1]
        if first == 0:
            return None
        return (last - first) / first * 100
    except Exception:
        return None


def _pct_from_high(history):
    if history is None or history.empty:
        return None
    try:
        high = history["High"].max()
        last = history["Close"].iloc[-1]
        if high == 0:
            return None
        return (high - last) / high * 100
    except Exception:
        return None


def assess_market(data):
    """模块0：大势判断."""
    info = data.get("info") or {}
    sector = info.get("sector")
    industry = info.get("industry")
    etf_ticker = get_sector_etf(sector, industry)
    etf_data = fetch_etf(etf_ticker)
    if etf_data is None:
        return {
            "etf": etf_ticker,
            "ytd": None,
            "ret_3m": None,
            "near_high": None,
            "judgment": "中性",
            "tolerance": "估值容忍度：历史均值不变",
            "note": f"无法拉取 {etf_ticker} 数据，按中性处理",
        }
    hist = etf_data["history"]
    ytd = _ytd_return(hist)
    ret_3m = _3m_return(hist)
    pct_from_high = _pct_from_high(hist)
    near_high = pct_from_high is not None and pct_from_high < 5

    # 判断逻辑
    if ytd is not None and ret_3m is not None:
        if ytd > 10 and ret_3m > 3:
            judgment = "顺风"
            tolerance = "估值容忍度：历史均值上浮 10%"
        elif ytd < -5 and ret_3m < -3:
            judgment = "逆风"
            tolerance = "估值容忍度：历史均值下调 15%"
        else:
            judgment = "中性"
            tolerance = "估值容忍度：历史均值不变"
    else:
        judgment = "中性"
        tolerance = "估值容忍度：历史均值不变（数据缺失）"

    return {
        "etf": etf_ticker,
        "ytd": ytd,
        "ret_3m": ret_3m,
        "near_high": near_high,
        "pct_from_high": pct_from_high,
        "judgment": judgment,
        "tolerance": tolerance,
        "note": "",
    }


def assess_position(data):
    """模块6：个股技术面位置."""
    info = data.get("info") or {}
    history = data.get("history_1y")
    high_52 = info.get("fiftyTwoWeekHigh")
    low_52 = info.get("fiftyTwoWeekLow")
    price = info.get("currentPrice") or info.get("regularMarketPrice")

    pct_from_high = None
    if high_52 and price:
        pct_from_high = (high_52 - price) / high_52 * 100

    # 200 日均线
    ma200 = None
    pct_vs_ma200 = None
    if history is not None and not history.empty and len(history) >= 100:
        try:
            ma200 = history["Close"].tail(200).mean()
            if ma200 and ma200 > 0 and price:
                pct_vs_ma200 = (price - ma200) / ma200 * 100
        except Exception:
            ma200 = None

    # 位置判断
    if pct_from_high is not None and pct_from_high > 30 and pct_vs_ma200 is not None and pct_vs_ma200 < 0:
        position = "🟢 低位"
    elif pct_from_high is not None and pct_from_high < 5:
        position = "🔴 高位"
    else:
        position = "🟡 中间"

    return {
        "high_52": high_52,
        "low_52": low_52,
        "price": price,
        "pct_from_high": pct_from_high,
        "ma200": ma200,
        "pct_vs_ma200": pct_vs_ma200,
        "position": position,
    }
