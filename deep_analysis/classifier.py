"""
模块1：股票分类。
分类决定后续估值工具选择。
优先级：投机 > 困境反转 > 周期 > 快速增长 > 稳定增长
"""

import statistics

from deep_analysis._common import quarterly_revenue_yoy_growths as _quarterly_revenue_yoy_growths  # noqa: F401


CYCLICAL_SECTORS = {"Energy", "Basic Materials", "Materials", "Industrials"}


def _quarterly_profit_margin_std(quarterly_income, n=4):
    """
    最近 n 个季度营业利润率（Operating Margin）的标准差（百分点）。

    旧版用净利润率（Net Margin），但容易被**非经营性一次性事项**扭曲：
      - valuation allowance 逆转（如 AMSC Q3 一次性 +$80M 税收收益）
      - 资产减值 / 重组费用
      - 投资收益 / 衍生品 mark-to-market
    这些会让净利率标准差爆炸（AMSC 76pp）误触发"周期股"分类。
    新版用 Operating Margin（剔除税收 + 一次性项），更准确反映经营周期性。
    """
    if quarterly_income is None or quarterly_income.empty:
        return None
    if "Total Revenue" not in quarterly_income.index:
        return None

    # 优先用 Operating Income，其次 EBIT，都没有再 fallback 到 Net Income
    op_key = None
    for k in ("Operating Income", "EBIT", "Net Income"):
        if k in quarterly_income.index:
            op_key = k
            break
    if op_key is None:
        return None

    rev = quarterly_income.loc["Total Revenue"].astype(float).sort_index(ascending=True)
    op = quarterly_income.loc[op_key].astype(float).sort_index(ascending=True)
    margins = []
    for date in rev.index[-n:]:
        if date in op.index and rev[date] and rev[date] > 0:
            margins.append(op[date] / rev[date] * 100)
    if len(margins) < 2:
        return None
    return statistics.stdev(margins)


def _had_material_loss_quarter(quarterly_income, n=4, material_pct_of_revenue=5.0):
    """
    最近 n 季度是否有过 **重大** 亏损季度（亏损 > 营收 X%）。

    旧版"任一季度净利润 < 0"过于敏感，会把 VST 这种利润被
    商品对冲合约 mark-to-market 短期压成 -78% YoY 的股票错归"困境反转"。
    新版要求亏损金额 > 营收 5% 才算 material，过滤会计噪音。

    返回 (had_loss: bool, latest_ni: float) 或 None.
    """
    if quarterly_income is None or quarterly_income.empty:
        return None
    if "Net Income" not in quarterly_income.index:
        return None
    ni = quarterly_income.loc["Net Income"].dropna().astype(float).sort_index(ascending=True)
    if len(ni) < 1:
        return None
    recent = ni.tail(n)
    if recent.empty:
        return None

    rev_row = quarterly_income.loc["Total Revenue"] if "Total Revenue" in quarterly_income.index else None
    had_material = False
    for date, ni_val in recent.items():
        if ni_val >= 0:
            continue
        if rev_row is None or date not in rev_row.index:
            had_material = True  # 没营收数据时回退到原逻辑
            break
        rev = rev_row.get(date)
        if rev is None or rev <= 0:
            continue
        if abs(ni_val) / rev * 100 > material_pct_of_revenue:
            had_material = True
            break
    return had_material, float(recent.iloc[-1])


def _eps_growth_pct(info):
    """
    earningsGrowth 在 info 里是小数 (0.25 = 25%).
    基期效应清洗：>500% 或 <-95% 是会计噪音，返回 None。
    """
    eg = info.get("earningsGrowth")
    if eg is None:
        return None
    try:
        v = float(eg) * 100
        if -95 < v < 500:
            return v
        return None
    except (TypeError, ValueError):
        return None


CATEGORY_META = {
    "speculative":  ("🎰 投机股",         "Speculative"),
    "turnaround":   ("🏚️ 困境反转",       "Turnaround"),
    "cyclical":     ("🔄 周期股",         "Cyclical"),
    "inflection":   ("⚡ 拐点反转",        "Inflection"),
    "fast_grower":  ("🚀 快速增长股",     "Fast Grower"),
    "stalwart":     ("🏛️ 稳定增长股",     "Stalwart"),
    "unclassified": ("❓ 未分类",          "Unclassified"),
}


def classify(data):
    """
    返回 dict: {
      'key': 'speculative' | 'turnaround' | 'cyclical' | 'fast_grower' | 'stalwart' | 'unclassified',
      'label': '🎰 投机股',
      'name': 'Speculative',
      'reason': '...',
      'sub_system': '不做深度估值 / P/E + 股息率 / ...'
    }
    """
    info = data.get("info") or {}
    qf = data.get("quarterly_income_stmt")
    if qf is None:
        qf = data.get("quarterly_financials")
    sector = info.get("sector")
    market_cap = info.get("marketCap") or 0
    revenue = info.get("totalRevenue") or 0
    net_income = info.get("netIncomeToCommon")
    div_yield = info.get("dividendYield") or 0
    rev_growth_pct = (info.get("revenueGrowth") or 0) * 100 if info.get("revenueGrowth") is not None else None
    eps_growth_pct = _eps_growth_pct(info)

    # ---- 1. 投机股（多维度门槛，避免把 AVAV 这种 $9B+backlog 公司误归）----
    # 旧版："市值<$2B OR 营收<$100M OR 净利润<0" 任一触发即归投机 → 过敏感
    # 新版：要求 (规模小 AND 营收小) 或 (盈利差 AND 财务弱) 才算投机
    is_unprofitable = net_income is not None and net_income < 0
    cash = info.get("totalCash") or 0
    total_debt = info.get("totalDebt") or 0
    net_cash = cash - total_debt

    is_micro = market_cap < 2e9 and revenue < 1e8       # 双重小：市值小 + 营收小
    is_pre_revenue_unprofitable = (
        is_unprofitable
        and revenue < 5e7                                # 营收 < $50M
        and cash < 2e8                                   # 现金 < $200M（无 runway）
    )
    is_microcap_unprofitable = market_cap < 5e8 and is_unprofitable

    if is_micro or is_pre_revenue_unprofitable or is_microcap_unprofitable:
        reason_parts = []
        if is_micro:
            reason_parts.append(f"市值 ${market_cap/1e9:.2f}B + 营收 ${revenue/1e6:.0f}M 双重小")
        if is_pre_revenue_unprofitable:
            reason_parts.append(f"亏损 + 营收 ${revenue/1e6:.0f}M (<$50M) + 现金 ${cash/1e6:.0f}M (<$200M)")
        if is_microcap_unprofitable:
            reason_parts.append(f"亏损 + 微型市值 ${market_cap/1e9:.2f}B (<$0.5B)")
        return {
            "key": "speculative",
            "label": CATEGORY_META["speculative"][0],
            "name": CATEGORY_META["speculative"][1],
            "reason": "；".join(reason_parts) or "不满足成熟公司财务门槛",
            "sub_system": "不做深度估值（直接标注高风险）",
        }

    # ---- 2. 困境反转（要求亏损是 material 的，过滤会计噪音）----
    # 旧版：任一季度 NI<0 即归 turnaround → VST 因商品对冲 mark-to-market 被错归
    # 新版：亏损金额 > 营收 5% 才算 material；若有 material 亏损 + 最新季度恢复盈利 = 真反转
    loss_info = _had_material_loss_quarter(qf, n=4, material_pct_of_revenue=5.0)
    if loss_info is not None:
        had_loss, latest_ni = loss_info
        if had_loss and latest_ni > 0:
            return {
                "key": "turnaround",
                "label": CATEGORY_META["turnaround"][0],
                "name": CATEGORY_META["turnaround"][1],
                "reason": "过去 4 季度出现重大亏损季度（亏损 > 5% 营收），但最新季度恢复盈利",
                "sub_system": "P/B + 净现金（或 EV/EBITDA，取决于行业）",
            }

    # ---- 3. 周期股 ----
    margin_std = _quarterly_profit_margin_std(qf, n=4)
    if sector in CYCLICAL_SECTORS and margin_std is not None and margin_std > 5:
        return {
            "key": "cyclical",
            "label": CATEGORY_META["cyclical"][0],
            "name": CATEGORY_META["cyclical"][1],
            "reason": f"sector={sector}，4 季度净利率标准差 {margin_std:.1f}pp (>5pp)",
            "sub_system": "P/B + P/S（⚠️ P/E 陷阱：低 P/E=卖出信号）",
        }

    # ---- 3.5 拐点反转 (TTM 平 / 但前瞻信号显示加速) ----
    fwd = data.get("forward_signals") or {}
    if fwd.get("is_inflection"):
        bits = []
        if fwd.get("revenue_yoy_acceleration") is not None and fwd["revenue_yoy_acceleration"] > 5:
            bits.append(f"季度 YoY 加速 +{fwd['revenue_yoy_acceleration']:.1f}pp")
        if fwd.get("revenue_growth_qoq") is not None and fwd["revenue_growth_qoq"] > 10:
            bits.append(f"环比 +{fwd['revenue_growth_qoq']:.1f}%")
        if fwd.get("eps_implied_growth") is not None and fwd["eps_implied_growth"] > 25:
            bits.append(f"EPS 隐含增速 +{fwd['eps_implied_growth']:.1f}%")
        if fwd.get("earnings_growth_q") is not None and fwd["earnings_growth_q"] > 25:
            bits.append(f"最新季净利润 YoY +{fwd['earnings_growth_q']:.1f}%")
        return {
            "key": "inflection",
            "label": CATEGORY_META["inflection"][0],
            "name": CATEGORY_META["inflection"][1],
            "reason": f"TTM 增速 {fwd.get('revenue_growth_ttm', 0):.1f}% 显平，但前瞻信号显示拐点：{'；'.join(bits)}",
            "sub_system": "PEG + P/S（按快速增长股估值，但需财报验证）",
        }

    # ---- 4. 快速增长 ----
    # M&A 整合期：营收增速大概率含合并跳变，必须降权处理（不能简单按 +20% 触发"快速增长"）
    ma = data.get("ma_signal") or {}
    is_ma = ma.get("is_ma_integration", False)

    is_fast = False
    fast_reason = []
    eps_fwd_growth = fwd.get("eps_implied_growth")
    # 营收增速判断：M&A 期需 +40% 才算（去掉合并跳变后仍超快），非 M&A 期 +20%
    rev_threshold = 40 if is_ma else 20
    if rev_growth_pct is not None and rev_growth_pct > rev_threshold:
        is_fast = True
        suffix = "（M&A 期阈值上调到 40%）" if is_ma else ""
        fast_reason.append(f"营收增速 {rev_growth_pct:.1f}% (>{rev_threshold}%){suffix}")
    if eps_growth_pct is not None and eps_growth_pct > 25:
        is_fast = True
        fast_reason.append(f"EPS 增速 {eps_growth_pct:.1f}% (>25%)")
    if eps_fwd_growth is not None and eps_fwd_growth > 25 and rev_growth_pct is not None and rev_growth_pct > 10:
        is_fast = True
        fast_reason.append(f"前瞻 EPS 增速 {eps_fwd_growth:.1f}%")
    if is_fast:
        sub = "PEG + P/S"
        if is_ma:
            sub += "（⚠️ M&A 整合期，营收增速含并购跳变，重点看 pro forma / 内生增速）"
        return {
            "key": "fast_grower",
            "label": CATEGORY_META["fast_grower"][0],
            "name": CATEGORY_META["fast_grower"][1],
            "reason": "；".join(fast_reason),
            "sub_system": sub,
        }

    # ---- 5. 稳定增长 ----
    if (
        rev_growth_pct is not None
        and 5 <= rev_growth_pct <= 15
        and div_yield > 0
        and market_cap > 5e10
    ):
        return {
            "key": "stalwart",
            "label": CATEGORY_META["stalwart"][0],
            "name": CATEGORY_META["stalwart"][1],
            "reason": f"营收增速 {rev_growth_pct:.1f}% ∈ [5,15]，市值 ${market_cap/1e9:.0f}B (>$50B)，有股息",
            "sub_system": "P/E + 股息率",
        }

    return {
        "key": "unclassified",
        "label": CATEGORY_META["unclassified"][0],
        "name": CATEGORY_META["unclassified"][1],
        "reason": "不满足任一明确分类条件，按通用 P/E + P/B 处理",
        "sub_system": "P/E + P/B（通用）",
    }
