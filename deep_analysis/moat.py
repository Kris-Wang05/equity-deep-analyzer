"""
模块2：护城河四维度评估。
转换成本 / 品牌定价权 / 成本规模优势 / 监管牌照壁垒。
"""


REGULATED_SECTORS = {"Utilities", "Healthcare", "Health Care"}
REGULATED_INDUSTRY_KEYWORDS = ("defense", "aerospace & defense", "tobacco",
                              "drug manufacturers", "biotechnology", "banks",
                              "insurance")


def _gross_margin_history(income_stmt):
    """
    返回最近 4 年（或可用年度）gross margin 列表 (%) ，时间升序。
    """
    if income_stmt is None or income_stmt.empty:
        return None
    if "Total Revenue" not in income_stmt.index:
        return None
    rev = income_stmt.loc["Total Revenue"].astype(float).sort_index(ascending=True)
    gp_key = None
    for k in ("Gross Profit",):
        if k in income_stmt.index:
            gp_key = k
            break
    if gp_key is None:
        return None
    gp = income_stmt.loc[gp_key].astype(float).sort_index(ascending=True)
    margins = []
    for date in rev.index:
        if date in gp.index and rev[date] and rev[date] > 0:
            margins.append(gp[date] / rev[date] * 100)
    return margins[-4:] if margins else None


def _operating_margin_history(income_stmt):
    if income_stmt is None or income_stmt.empty:
        return None
    if "Total Revenue" not in income_stmt.index:
        return None
    rev = income_stmt.loc["Total Revenue"].astype(float).sort_index(ascending=True)
    op_key = None
    for k in ("Operating Income", "EBIT"):
        if k in income_stmt.index:
            op_key = k
            break
    if op_key is None:
        return None
    op = income_stmt.loc[op_key].astype(float).sort_index(ascending=True)
    margins = []
    for date in rev.index:
        if date in op.index and rev[date] and rev[date] > 0:
            margins.append(op[date] / rev[date] * 100)
    return margins[-4:] if margins else None


def _trend_arrow(values):
    """返回 '↑' / '↓' / '→'，比较前后两段均值."""
    if not values or len(values) < 2:
        return "→"
    half = len(values) // 2
    if half == 0:
        return "→"
    early = sum(values[:half]) / half
    late = sum(values[half:]) / (len(values) - half)
    diff = late - early
    if diff > 1:
        return "↑"
    if diff < -1:
        return "↓"
    return "→"


def assess(data):
    info = data.get("info") or {}
    income = data.get("income_stmt")
    if income is None:
        income = data.get("financials")
    sector = info.get("sector") or ""
    industry = (info.get("industry") or "").lower()
    market_cap = info.get("marketCap") or 0

    gm_hist = _gross_margin_history(income)
    om_hist = _operating_margin_history(income)
    gm_latest = gm_hist[-1] if gm_hist else None
    om_latest = om_hist[-1] if om_hist else None
    gm_trend = _trend_arrow(gm_hist)
    om_trend = _trend_arrow(om_hist)

    items = []

    # 1. 转换成本（高毛利率代理）
    if gm_latest is None:
        items.append(("转换成本", "❓", "毛利率数据缺失"))
    elif gm_latest > 50:
        items.append(("转换成本", "✅", f"毛利率 {gm_latest:.1f}% (>50%)，定价权强"))
    elif gm_latest > 35:
        items.append(("转换成本", "⚠️", f"毛利率 {gm_latest:.1f}%，中等"))
    else:
        items.append(("转换成本", "❌", f"毛利率仅 {gm_latest:.1f}%，缺乏锁定能力"))

    # 2. 品牌/定价权（毛利率 + 营业利润率趋势）
    if gm_trend == "↑" and om_trend in ("↑", "→") and gm_latest and gm_latest > 30:
        items.append(("品牌/定价权", "✅", f"毛利率趋势 {gm_trend}，营业利润率 {om_trend}"))
    elif gm_trend == "↓" or om_trend == "↓":
        items.append(("品牌/定价权", "❌", f"毛利率 {gm_trend}，营业利润率 {om_trend}，被压价"))
    else:
        items.append(("品牌/定价权", "⚠️", f"毛利率 {gm_trend}，营业利润率 {om_trend}，平稳"))

    # 3. 成本/规模优势（市值是不是行业前列）
    if market_cap >= 5e10:
        items.append(("成本/规模优势", "✅", f"市值 ${market_cap/1e9:.0f}B，规模型企业"))
    elif market_cap >= 1e10:
        items.append(("成本/规模优势", "⚠️", f"市值 ${market_cap/1e9:.0f}B，中盘规模一般"))
    else:
        items.append(("成本/规模优势", "❌", f"市值 ${market_cap/1e9:.1f}B，规模偏小"))

    # 4. 监管/牌照壁垒
    if sector in REGULATED_SECTORS or any(k in industry for k in REGULATED_INDUSTRY_KEYWORDS):
        items.append(("监管/牌照壁垒", "✅", f"sector={sector or '?'} / industry 含监管特征"))
    else:
        items.append(("监管/牌照壁垒", "❌", f"sector={sector or '?'}，无明显牌照壁垒"))

    # 总评
    yes_count = sum(1 for _, sign, _ in items if sign == "✅")
    if yes_count >= 3:
        stars = "⭐⭐⭐⭐"
        verdict = "宽护城河"
    elif yes_count >= 1:
        stars = "⭐⭐⭐☆"
        verdict = "窄护城河"
    else:
        stars = "⭐☆☆☆"
        verdict = "无明显壁垒"

    return {
        "items": items,
        "stars": stars,
        "verdict": verdict,
        "yes_count": yes_count,
        "gross_margin_latest": gm_latest,
        "gross_margin_trend": gm_trend,
        "operating_margin_latest": om_latest,
        "operating_margin_trend": om_trend,
    }
