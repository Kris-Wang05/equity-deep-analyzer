"""
拼装 Markdown 报告。
"""

from datetime import datetime


def _f(v, fmt="{:.2f}", default="N/A"):
    if v is None:
        return default
    try:
        return fmt.format(v)
    except (TypeError, ValueError):
        return default


def _ccy_symbol(ccy):
    """币种代码 → 货币符号。GBp/ZAc 等"分单位"显示符号本身。"""
    if not ccy:
        return "$"
    return {
        "USD": "$", "GBP": "£", "EUR": "€", "JPY": "¥", "CNY": "¥",
        "HKD": "HK$", "TWD": "NT$", "KRW": "₩", "INR": "₹",
        "CAD": "C$", "AUD": "A$", "CHF": "CHF",
        "GBp": "p", "ZAc": "c",
    }.get(ccy, ccy + " ")


def _money_b(v, default="N/A", ccy="USD", fx=1.0):
    """Big money in original currency, with USD equiv if non-USD."""
    if v is None:
        return default
    try:
        sym = _ccy_symbol(ccy)
        native = f"{sym}{v/1e9:.2f}B"
        if ccy and ccy != "USD" and fx and fx > 0:
            usd = v * fx / 1e9
            return f"{native} (≈${usd:.1f}B)"
        return native
    except Exception:
        return default


def _money_m(v, default="N/A", ccy="USD", fx=1.0):
    if v is None:
        return default
    try:
        sym = _ccy_symbol(ccy)
        native = f"{sym}{v/1e6:.0f}M"
        if ccy and ccy != "USD" and fx and fx > 0:
            usd = v * fx / 1e6
            return f"{native} (≈${usd:.0f}M)"
        return native
    except Exception:
        return default


def _price(v, default="N/A", ccy="USD", fx=1.0):
    """股价 / 入场价 / 止损价等。原币种带单位 + USD 等价（非 USD 时）。"""
    if v is None:
        return default
    try:
        sym = _ccy_symbol(ccy)
        if ccy == "GBp":
            native = f"{v:.2f} GBp"
        elif ccy == "USD" or not ccy:
            native = f"${v:.2f}"
        else:
            native = f"{sym}{v:.2f}"
        if ccy and ccy not in ("USD",) and fx and fx > 0:
            usd = v * fx
            return f"{native} (≈${usd:.2f})"
        return native
    except Exception:
        return default


def _signed(v, default="N/A"):
    if v is None:
        return default
    return f"{v:+.1f}%"


def _signal_strength(category, valuation, moat, fundamentals, fwd, market_judgment="中性"):
    """1-5 星信号强度."""
    score = 0
    cat_key = category["key"]
    info_metrics = {m["name"]: m["current"] for m in valuation["metrics"]}

    peg = info_metrics.get("PEG")
    if peg is not None and peg < 1:
        score += 1
    elif peg is not None and peg < 1.5 and cat_key == "inflection":
        # 拐点期 PEG 1.0-1.5 也算合理便宜
        score += 1
    if "🟢" in valuation["verdict"]:
        score += 1
    if moat["yes_count"] >= 2:
        score += 1
    revs = fundamentals.get("revenues") or []
    if len(revs) >= 2:
        last_yoy = revs[-1][2]
        prev_yoy = revs[-2][2]
        if last_yoy is not None and prev_yoy is not None and last_yoy > prev_yoy:
            score += 1
    if fundamentals.get("upside_pct") is not None and fundamentals["upside_pct"] > 20:
        score += 1
    # 拐点 bonus：前瞻信号强 + 估值未到🔴 → +1
    if cat_key == "inflection" and "🔴" not in valuation["verdict"]:
        score += 1

    # 封顶
    if cat_key == "speculative":
        score = min(score, 2)
    if "🔴" in valuation["verdict"]:
        score = min(score, 2)
    # 大势封顶（修复 BSX 案例：板块逆风时不该给 4-5 星）
    if market_judgment == "逆风":
        score = min(score, 3)

    score = max(1, min(score, 5))
    return score, "⭐" * score + "☆" * (5 - score)


def _entry_prices(price, signal_score):
    """双档入场价."""
    if price is None:
        return None, None, None
    if signal_score >= 4:
        aggressive = price * 0.97
    else:
        aggressive = price * 0.87
    conservative = aggressive * 0.85
    stoploss = conservative * 0.85
    return aggressive, conservative, stoploss


def _trend_text(t):
    return {"↑": "上行", "↓": "下行", "→": "持平"}.get(t, "—")


def generate(data, category, moat_res, valuation_res, fundamentals_res,
             market_res, position_res):
    info = data.get("info") or {}
    ticker = data.get("ticker")
    company = info.get("longName") or info.get("shortName") or ticker
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    market_cap = info.get("marketCap")
    today = datetime.today().strftime("%Y-%m-%d")
    sector = info.get("sector") or "—"
    industry = info.get("industry") or "—"

    fwd = data.get("forward_signals") or {}
    market_judgment = data.get("market_judgment", "中性")
    sig_score, sig_stars = _signal_strength(category, valuation_res, moat_res, fundamentals_res, fwd, market_judgment)

    # 币种 / FX (用于本币 + USD 等价显示)
    price_ccy = data.get("price_currency") or "USD"
    fin_ccy = data.get("financial_currency") or "USD"
    fx_price = data.get("fx_price_to_usd") or 1.0
    fx_fin = data.get("fx_fin_to_usd") or 1.0
    is_non_usd = price_ccy not in ("USD", None) or fin_ccy not in ("USD", None)
    aggressive, conservative, stoploss = _entry_prices(price, sig_score)
    target = fundamentals_res.get("target_mean")

    lines = []
    a = lines.append

    a(f"# 📊 {ticker} 诊断报告")
    a(f"**公司**：{company}")
    # 市值用 financialCurrency 表达（marketCap 在 yfinance 里大多是 financial currency 单位的本位货币）
    # 但实际上 marketCap 单位 = currency（除了 GBp 应转为 GBP）
    mcap_ccy = "GBP" if price_ccy == "GBp" else price_ccy
    mcap_fx = fx_price * 100 if price_ccy == "GBp" else fx_price
    a(f"**日期**：{today}　｜　**股价**：{_price(price, ccy=price_ccy, fx=fx_price)}　｜　**市值**：{_money_b(market_cap, ccy=mcap_ccy, fx=mcap_fx)}")
    a(f"**Sector / Industry**：{sector} / {industry}")
    if is_non_usd:
        a(f"**币种**：股价 `{price_ccy}`（FX：1 {price_ccy} ≈ ${fx_price:.4f}）　｜　财报 `{fin_ccy}`（FX：1 {fin_ccy} ≈ ${fx_fin:.4f}）")
        a(f"> ⚠️ **非美股币种警告**：所有数字保留原币种 + USD 等价。请勿将便士 (GBp) 或新台币 (TWD) 误读为美元。")
    a(f"**数据拉取时间**：{data.get('fetched_at')}")
    a("")
    a("---")
    a("")

    # 模块0
    a(f"## 🌊 大势：`{market_res['judgment']}`")
    a("")
    a(f"- 对标 ETF：**{market_res['etf']}**（按 industry={industry} 自动选择，半导体/软件等子行业不再用 XLK 粗代理）")
    a(f"- {market_res['etf']} YTD {_signed(market_res['ytd'])}，3M {_signed(market_res['ret_3m'])}")
    a(f"- 距 ETF 52 周高点：{_f(market_res.get('pct_from_high'), '{:.1f}%')}　｜　近高点：{'是' if market_res.get('near_high') else '否'}")
    a(f"- 大势判断：{market_res['judgment']}")
    a(f"- → {market_res['tolerance']}")
    if market_res.get("note"):
        a(f"- 注：{market_res['note']}")
    a("")
    a("---")
    a("")

    # 模块1
    a(f"## 🏷️ 分类：`{category['label']}`")
    a("")
    a(f"- 理由：{category['reason']}")
    a(f"- 适配子系统：{category['sub_system']}")
    a("")

    # 前瞻 vs 滞后对比（识别拐点 / 防止 TTM 错杀）
    a("**📈 前瞻 vs 滞后增速对比：**")
    a("")
    a("| 维度 | 数值 | 说明 |")
    a("|------|------|------|")
    a(f"| TTM 营收增速 | {_f(fwd.get('revenue_growth_ttm'), '{:+.1f}%')} | 滞后指标 |")
    a(f"| 最新季度 YoY 增速 | {_f(fwd.get('revenue_growth_yoy_q'), '{:+.1f}%')} | 单季同比 |")
    a(f"| 最新季度 QoQ 增速 | {_f(fwd.get('revenue_growth_qoq'), '{:+.1f}%')} | 环比，捕捉拐点 |")
    a(f"| YoY 加速度 (近 2 季差) | {_f(fwd.get('revenue_yoy_acceleration'), '{:+.1f}pp')} | >+5pp = 加速 |")
    eg_q = fwd.get("earnings_growth_q")
    eg_q_raw = fwd.get("earnings_growth_q_raw_noisy")
    if eg_q is None and eg_q_raw is not None:
        eg_q_display = f"⚠️ 噪音 ({eg_q_raw:+.0f}%，已忽略)"
    else:
        eg_q_display = _f(eg_q, "{:+.1f}%")
    a(f"| 最新季度净利润 YoY | {eg_q_display} | yfinance earningsQuarterlyGrowth (>500% 视为基期噪音) |")
    a(f"| EPS 隐含增速 (Forward vs TTM) | {_f(fwd.get('eps_implied_growth'), '{:+.1f}%')} | 卖方共识 vs 实际 EPS |")
    if fwd.get("is_inflection"):
        a("")
        a("> ⚡ **检测到拐点信号**：TTM 增速平淡，但前瞻数据显示加速。建议结合下次财报 + guidance 验证后再做仓位决定。")
    ma = data.get("ma_signal") or {}
    if ma.get("is_stock_split") and not ma.get("is_ma_integration"):
        a("")
        a(f"> 🔀 **Stock Split 提醒**：近 1 年发生 {ma['split_ratio']:.0f}:1 拆股（{ma.get('split_date')}）。流通股 YoY +{ma.get('shares_change_yoy', 0):.0f}% **不是并购对价**而是 split 造成的；调整后真实流通股变化 {ma.get('shares_change_adj', 0):+.1f}%。所有 split 前价格除以 {ma['split_ratio']:.0f} 才能与当前价对比。")
    elif ma.get("is_ma_integration"):
        a("")
        split_note = f"（已剔除 {ma['split_ratio']:.0f}:1 split 影响）" if ma.get("is_stock_split") else ""
        a(f"> 🔀 **M&A 整合期警告**{split_note}：{ma['reason']}。**前瞻表中的营收 YoY 增速大概率含并购合并跳变**，不代表内生增长。务必查询公司公告获取 pro forma / organic revenue 数据再做判断。")
    a("")
    a("---")
    a("")

    # 模块2
    a(f"## 🏰 护城河：{moat_res['stars']} ({moat_res['verdict']})")
    a("")
    a("| 维度 | 评判 | 理由 |")
    a("|------|------|------|")
    for name, sign, reason in moat_res["items"]:
        a(f"| {name} | {sign} | {reason} |")
    a("")
    a(f"_毛利率最新值：{_f(moat_res['gross_margin_latest'], '{:.1f}%')}（趋势 {_trend_text(moat_res['gross_margin_trend'])}）"
      f"，营业利润率最新值：{_f(moat_res['operating_margin_latest'], '{:.1f}%')}（趋势 {_trend_text(moat_res['operating_margin_trend'])}）_")
    a("")
    a("---")
    a("")

    # 模块3
    a(f"## 💰 估值（{valuation_res['tools']}）：`{valuation_res['verdict']}`")
    a("")
    if valuation_res.get("cycle_warning"):
        a("> ⚠️ **P/E 陷阱警告**：本股被分类为周期股。低 P/E 通常出现在周期顶部（盈利创高），是**卖出**信号；高 P/E 反而出现在周期底部（盈利触底），是**买入**信号。请以 P/B + P/S 为主判断依据。")
        a("")
    # 估值表（删掉 5 年均值列：信息和历史百分位重复，且大部分 metric 没历史均值显示 N/A 是噪音）
    a("| 指标 | 当前值 | 同行均值 | 历史百分位 |")
    a("|------|--------|----------|------------|")
    for m in valuation_res["metrics"]:
        cur = _f(m["current"], "{:.2f}")
        peer = _f(m.get("peer"), "{:.2f}")
        pct = _f(m.get("percentile"), "{:.0f}%")
        a(f"| {m['name']} | {cur} | {peer} | {pct} |")
    hpe = valuation_res.get("historical_pe") or {}
    if hpe.get("pe_basis"):
        a("")
        a(f"_百分位口径：{hpe['pe_basis']}（样本 n={hpe.get('samples_n', '?')}，月度采样 + Winsorize）_")
    if valuation_res.get("peg_is_implied"):
        a("")
        a("_PEG 为工具自算（forward P/E ÷ 增速），yfinance 未提供 trailingPegRatio_")
    a("")

    # 同行折价/溢价（显式锚）
    pr = valuation_res.get("peer_relative") or []
    if pr:
        a("**📐 vs 同行相对估值：**")
        a("")
        a("| 指标 | 本股 | 同行均值 | 相对位置 |")
        a("|------|------|----------|----------|")
        for r in pr:
            a(f"| {r['metric']} | {_f(r['self'])} | {_f(r['peer_avg'])} | {r['label']} |")
        a("")

    # 同行对标表
    if valuation_res.get("peers"):
        a("**同行对标：**")
        a("")
        a("| 公司 | Forward P/E | PEG | P/S | 营收增速 |")
        a("|------|-------------|-----|-----|----------|")
        # 自己也加进去做对比
        own_pe = info.get("forwardPE")
        own_peg = info.get("trailingPegRatio") or info.get("pegRatio")
        own_ps = info.get("priceToSalesTrailing12Months")
        own_rg = info.get("revenueGrowth")
        own_rg_pct = own_rg * 100 if own_rg is not None else None
        a(f"| **{ticker}** (本股) | {_f(own_pe)} | {_f(own_peg)} | {_f(own_ps)} | {_f(own_rg_pct, '{:.1f}%')} |")
        for p in valuation_res["peers"]:
            a(f"| {p['ticker']} | {_f(p['forward_PE'])} | {_f(p['PEG'])} | {_f(p['P_S'])} | {_f(p['revenue_growth'], '{:.1f}%')} |")
        a("")
    a("---")
    a("")

    # 模块4
    cr = valuation_res["cheap_reason"]
    a(f"## ❓ 为什么便宜/贵：`{cr['class']} 类 — {cr['label']}`")
    a("")
    a(f"- 原因：{cr['reason']}")
    a(f"- 关键证据：{cr['evidence']}")
    a("")
    a("---")
    a("")

    # 模块5
    a("## 🔍 基本面快检")
    a("")
    a("| 指标 | 数据 |")
    a("|------|------|")
    revs = fundamentals_res.get("revenues") or []
    if revs:
        last = revs[-1]
        date_str = last[0].strftime("%Y-%m-%d") if hasattr(last[0], "strftime") else str(last[0])[:10]
        a(f"| 营收（最新季度） | {_money_m(last[1], ccy=fin_ccy, fx=fx_fin)}，YoY {_signed(last[2])} ({date_str}) |")
    else:
        a("| 营收（最新季度） | 数据缺失 |")
    a(f"| 毛利率 | {_f(fundamentals_res.get('gm_latest'), '{:.1f}%')}（趋势：{_trend_text(fundamentals_res.get('gm_trend'))}） |")
    a(f"| 营业利润率 | {_f(fundamentals_res.get('om_latest'), '{:.1f}%')}（趋势：{_trend_text(fundamentals_res.get('om_trend'))}） |")
    a(f"| OCF（TTM） | {_money_m(fundamentals_res.get('ocf_ttm'), ccy=fin_ccy, fx=fx_fin)} |")
    a(f"| FCF（TTM） | {_money_m(fundamentals_res.get('fcf_ttm'), ccy=fin_ccy, fx=fx_fin)} |")
    a(f"| D/E | {_f(fundamentals_res.get('debt_to_equity'))} |")
    a(f"| 流动比率 | {_f(fundamentals_res.get('current_ratio'))} |")
    sc = fundamentals_res.get("shares_change_1y")
    # 如果发生 split，显示调整后的真实变化（剔除 split 影响）
    if ma.get("is_stock_split") and ma.get("shares_change_adj") is not None:
        sc_adj = ma["shares_change_adj"]
        sc_label = ("回购" if sc_adj < 0 else ("稀释" if sc_adj > 0 else "持平"))
        a(f"| 流通股变化（YoY） | 原始 {_signed(sc)}（含 {ma['split_ratio']:.0f}:1 split），**调整后 {sc_adj:+.1f}%**（{sc_label}） |")
    else:
        sc_label = ("回购" if sc and sc < 0 else ("稀释" if sc and sc > 0 else "—"))
        a(f"| 流通股变化（YoY） | {_signed(sc)}（{sc_label}） |")
    insider_stats = fundamentals_res.get("insider_stats")
    if insider_stats is None:
        insider_text = "数据缺失"
    elif insider_stats["total_count"] == 0:
        insider_text = "近 6 个月无交易"
    else:
        net_om = insider_stats["net_open_market"]
        buy = insider_stats["open_market_buy_usd"]
        sell = insider_stats["open_market_sell_usd"]
        grant = insider_stats["grant_usd"]
        ceo_buy = insider_stats.get("ceo_buy_usd", 0)
        ceo_sell = insider_stats.get("ceo_sell_usd", 0)
        ceo_net = insider_stats.get("ceo_net", 0)

        bits = []
        if buy > 0:
            bits.append(f"开盘买 {_money_m(buy)} ({insider_stats['buy_count']}笔)")
        if sell > 0:
            bits.append(f"开盘卖 {_money_m(sell)} ({insider_stats['sell_count']}笔)")
        if not bits and insider_stats["grant_count"] > 0:
            bits.append(f"仅激励/行权（{insider_stats['grant_count']}笔，中性）")
        net_label = ""
        if buy > 0 or sell > 0:
            net_label = f"，**净{'买' if net_om > 0 else '卖'} {_money_m(abs(net_om))}**"
        # CEO 单独拆分（修复 SOFI 案例：CEO 行为可能与其他高管反向）
        if ceo_buy > 0 or ceo_sell > 0:
            if ceo_buy > 0 and ceo_sell == 0:
                ceo_label = f"_CEO 净买 {_money_m(ceo_buy)}（强多头信号）_"
            elif ceo_sell > 0 and ceo_buy == 0:
                ceo_label = f"_CEO 净卖 {_money_m(ceo_sell)}_"
            else:
                ceo_label = f"_CEO 净{'买' if ceo_net > 0 else '卖'} {_money_m(abs(ceo_net))}_"
            bits.append(ceo_label)
        if grant > 0:
            bits.append(f"激励/行权 {_money_m(grant)}（中性）")
        insider_text = "；".join(bits) + net_label
    a(f"| 内部人（6 个月） | {insider_text} |")
    a(f"| 分析师共识 | {fundamentals_res.get('analyst_rating') or '—'}（{fundamentals_res.get('analyst_count') or 0} 人）"
      f"，目标价 {_price(fundamentals_res.get('target_mean'), ccy=price_ccy, fx=fx_price)}（上行 {_signed(fundamentals_res.get('upside_pct'))}） |")
    a(f"| 下次财报 | {fundamentals_res.get('next_earnings') or '—'} |")
    a("")
    a("---")
    a("")

    # 模块6
    a(f"## 📍 位置：`{position_res['position']}`")
    a("")
    a(f"- 52 周：高 {_price(position_res.get('high_52'), ccy=price_ccy, fx=fx_price)} / 低 {_price(position_res.get('low_52'), ccy=price_ccy, fx=fx_price)}　｜　距高点 {_f(position_res.get('pct_from_high'), '{:.1f}%')}")
    pma = position_res.get("pct_vs_ma200")
    above_below = "上方" if pma is not None and pma > 0 else "下方"
    a(f"- 200 日均线：{_price(position_res.get('ma200'), ccy=price_ccy, fx=fx_price)}　｜　当前价在均线{above_below} {_f(abs(pma) if pma is not None else None, '{:.1f}%')}")
    a("")
    a("---")
    a("")

    # 结论
    a("## 🎯 结论")
    a("")
    a(f"**信号强度**：{sig_stars} ({sig_score}/5)")
    a("")
    summary = _build_summary(category, valuation_res, moat_res, fundamentals_res, position_res, sig_score)
    a(f"**一句话**：{summary}")
    a("")
    if sig_score >= 4:
        action = "🟢 BUY — 可以分批建仓"
    elif sig_score == 3:
        action = "🟡 WATCH — 加入观察名单，等更好的入场点或财报验证"
    else:
        action = "🔴 AVOID — 当前不建议入场"
    a(f"**操作建议**：{action}")
    a("")
    a("| | 价格 | 折扣 | 仓位建议 |")
    a("|---|---|---|---|")
    if aggressive and conservative:
        agg_disc = (aggressive / price - 1) * 100 if price else 0
        cons_disc = (conservative / price - 1) * 100 if price else 0
        a(f"| 🟢 激进入场 | {_price(aggressive, ccy=price_ccy, fx=fx_price)} | {agg_disc:+.1f}% | 1/3 仓位先手 |")
        a(f"| 🔵 保守入场 | {_price(conservative, ccy=price_ccy, fx=fx_price)} | {cons_disc:+.1f}% | 剩余 2/3 加仓 |")
    a("")
    a(f"**止损**：{_price(stoploss, ccy=price_ccy, fx=fx_price)}　｜　**目标价（分析师共识）**：{_price(target, ccy=price_ccy, fx=fx_price)}")
    a("")
    a("---")
    a("")

    # 风险
    a("## ⚠️ 风险提示")
    a("")
    # 把 market_judgment 临时塞进 info（_collect_risks 需要它精准触发 guide 提示）
    info_for_risks = dict(info)
    info_for_risks["_market_judgment_"] = market_judgment
    risks = _collect_risks(category, valuation_res, fundamentals_res, position_res, info_for_risks, ma)
    for r in risks:
        a(f"- {r}")
    a("")
    a("---")
    a("")
    a("_本报告由 deep_analysis 自动生成，仅供研究参考，不构成投资建议。_")
    a(f"_数据源：yfinance；拉取时间 {data.get('fetched_at')}_")

    return "\n".join(lines)


def _build_summary(category, valuation, moat, fundamentals, position, sig_score):
    parts = []
    parts.append(category["label"])
    parts.append(valuation["verdict"])
    parts.append(f"护城河 {moat['stars']}")
    if "🟢" in position["position"]:
        parts.append("位置低")
    elif "🔴" in position["position"]:
        parts.append("位置高")
    return "，".join(parts) + f"，综合信号 {sig_score}/5。"


def _earnings_proximity_note(fundamentals):
    """
    距下次财报 ≤ 14 天 → 返回提醒字符串。仅提醒不扣分（用户决策）。
    """
    next_earn = fundamentals.get("next_earnings")
    if not next_earn:
        return None
    try:
        from datetime import datetime
        d = datetime.strptime(next_earn, "%Y-%m-%d")
        days = (d - datetime.today()).days
        if 0 <= days <= 14:
            return f"**📅 财报前 {days} 天**（{next_earn}）：财报是双向 catalyst，新建仓不对称风险偏负向。可考虑等财报后再决定仓位（仅提醒，不影响信号强度）。"
    except Exception:
        pass
    return None


def _collect_risks(category, valuation, fundamentals, position, info, ma=None):
    risks = []
    if category["key"] == "speculative":
        risks.append("**投机股**：市值/营收/盈利不达成熟公司门槛，波动性极大，仓位严格控制。")
    if category["key"] == "cyclical":
        risks.append("**周期股 P/E 陷阱**：低 P/E 不一定便宜，警惕周期顶部信号。")
    if category["key"] == "turnaround":
        risks.append("**困境反转**：盈利反弹的可持续性需要 2-3 个季度验证。")
    if category["key"] == "inflection":
        next_earn = fundamentals.get("next_earnings")
        when = f"（下次财报：{next_earn}）" if next_earn else ""
        risks.append(f"**拐点未验证**：分类基于前瞻信号（QoQ 加速 / EPS 隐含增速），核心风险是 guidance 未兑现 → 估值瞬间从 🟢 切到 🔴{when}。")
    # 200 日均线偏离过大（无论位置如何，技术面 stretch 是独立风险）
    pct_vs_ma = position.get("pct_vs_ma200")
    if pct_vs_ma is not None and pct_vs_ma > 40:
        risks.append(f"**技术面拉伸**：当前价高出 200 日均线 +{pct_vs_ma:.0f}%，均值回归压力显著。")
    if "🔴" in valuation["verdict"]:
        risks.append("**估值偏贵**：当前价格未提供安全边际，等待回调或财报验证。")
    if position["position"].startswith("🔴"):
        risks.append("**位置偏高**：距 52 周高点不足 5%，技术面缺少缓冲。")
    # 风险判断用调整后流通股变化（避免 split 触发假稀释告警）
    sc_for_risk = (ma or {}).get("shares_change_adj")
    if sc_for_risk is None:
        sc_for_risk = fundamentals.get("shares_change_1y")
    if sc_for_risk is not None and sc_for_risk > 5:
        suffix = "（剔除 split 后）" if (ma or {}).get("is_stock_split") else ""
        risks.append(f"**股本稀释**：流通股 1 年内{suffix}增加 {sc_for_risk:+.1f}%，对每股价值不利。")
    de = fundamentals.get("debt_to_equity")
    if de is not None and de > 2:
        risks.append(f"**高杠杆**：D/E={de:.2f}，利率上行环境下风险放大。")
    cr = fundamentals.get("current_ratio")
    if cr is not None and cr < 1:
        risks.append(f"**短期偿债压力**：流动比率 {cr:.2f} (<1)，关注现金流。")
    stats = fundamentals.get("insider_stats")
    if stats:
        net_om = stats.get("net_open_market", 0)
        ceo_buy = stats.get("ceo_buy_usd", 0)
        ceo_sell = stats.get("ceo_sell_usd", 0)
        ceo_net = stats.get("ceo_net", 0)
        # 强信号优先级：
        # 1. CEO 净买入 → 多头信号（即使其他 insider 在卖也覆盖）
        # 2. CEO 净卖 + 0 买 → 信心 yellow flag
        # 3. 整体单边卖（无 CEO 买盘对冲）
        if ceo_buy > 0 and ceo_sell == 0 and ceo_buy > 5e5:
            # CEO 仅买无卖（如 SOFI Noto 案例）
            risks.append(f"**✅ CEO 净买入 ${ceo_buy/1e6:.1f}M（0 笔卖）**：管理层强多头信号，即使其他高管在卖也不构成 yellow flag。")
        elif ceo_sell > 5e6 and ceo_buy == 0:
            risks.append(f"**CEO 单边卖出**：近 6 个月开盘卖出 ${ceo_sell/1e6:.1f}M，0 笔买入 — 管理层信心 yellow flag。")
        elif net_om < -5e6 and stats.get("buy_count", 0) == 0:
            risks.append(f"**内部人单边卖出**：近 6 个月开盘市场净卖出 ${abs(net_om)/1e6:.1f}M，**0 笔买入** — 管理层信心 yellow flag。")
        elif net_om < -1e6 and ceo_buy == 0:
            risks.append(f"**内部人净卖出**：开盘市场净卖出 ${abs(net_om)/1e6:.1f}M（{stats['sell_count']}笔卖 vs {stats['buy_count']}笔买，CEO 未参与买盘）。")
    short_pct = info.get("shortPercentOfFloat")
    if short_pct and short_pct > 0.15:
        risks.append(f"**做空压力**：流通股做空比例 {short_pct*100:.1f}% (>15%)，市场存在显著看空力量。")
    # 财报前 2 周提醒（仅提醒不扣分）
    earn_note = _earnings_proximity_note(fundamentals)
    if earn_note:
        risks.append(earn_note)

    # 管理层 guide 历史被动提示（精准触发：大势非顺风 + 距财报 ≤60 天 + 盈利型公司）
    # 顺风期 guide 风险低；远离财报时此提示意义有限。
    cat_key = category.get("key")
    sector = info.get("sector") or ""
    market_judgment = (info.get("_market_judgment_") or "中性")  # 由 generate() 传入
    next_earn = fundamentals.get("next_earnings")
    days_to_earn = None
    if next_earn:
        try:
            from datetime import datetime
            d = datetime.strptime(next_earn, "%Y-%m-%d")
            days_to_earn = (d - datetime.today()).days
        except Exception:
            pass

    needs_guide_hint = (
        cat_key in ("stalwart", "fast_grower", "inflection", "unclassified")
        and sector in ("Healthcare", "Industrials", "Consumer Cyclical",
                       "Consumer Defensive", "Technology", "Financial Services")
        and market_judgment != "顺风"
        and (days_to_earn is None or days_to_earn <= 60)
    )
    if needs_guide_hint:
        risks.append("**📋 管理层 guide 历史**（建议手动核查）：板块非顺风期 + 临近财报，guide 下调风险升高。建议查询过去 4-8 季度 guidance 调整记录（参考 BSX 4/22 砍 4pp 案例）。yfinance 无此数据，需手动核对 8-K / earnings call transcript。")

    if not risks:
        risks.append("当前未识别到突出风险因子（不代表无风险）。")
    return risks
