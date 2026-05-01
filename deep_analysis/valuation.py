"""
模块3：估值诊断（按分类选工具）。
模块4：便宜/贵的原因归类。
"""

import statistics

from deep_analysis._common import quarterly_revenue_yoy_growths
from deep_analysis.data_fetcher import fetch_peer_snapshot
from deep_analysis.peers import get_peers


# 这些行业 P/B 不适用（资产记账方式让 book value 失真），用 EV/EBITDA 做主估值
# - Utilities/REIT/Energy/Materials：重资产 + mark-to-market 让 book value 失真
# - Consumer Defensive：品牌无形资产远高于账面（KO P/B 11、MNST 8、CELH 7、PG 7），P/B 不反映真实价值
EV_EBITDA_PRIMARY_SECTORS = {
    "Utilities", "Real Estate", "Energy", "Basic Materials", "Materials",
    "Consumer Defensive",
}
EV_EBITDA_PRIMARY_INDUSTRY_KEYWORDS = (
    "independent power", "utilities—regulated", "reit", "oil & gas", "midstream",
    "pipelines", "telecom services", "airlines", "trucking", "railroads",
    # 品牌驱动的消费行业（P/B 长期被低估，应该用 EV/EBITDA + Forward P/E）
    "beverages", "packaged foods", "confectioners", "tobacco",
    "household & personal products", "restaurants",
)


def _use_ev_ebitda_primary(sector, industry):
    if sector in EV_EBITDA_PRIMARY_SECTORS:
        return True
    if industry:
        ind = industry.lower()
        if any(k in ind for k in EV_EBITDA_PRIMARY_INDUSTRY_KEYWORDS):
            return True
    return False


def _historical_pe_percentile(history_5y, eps_history_5y, current_pe):
    """
    估算 5 年 P/E 区间，返回 dict (p25/p50/p75/percentile/samples_n).

    旧版算法：年度中位价 × 年度 EPS（5 个样本）→ 早年业务规模小时 P/E 异常高，
            会把当前 P/E 错误推到 100% 分位。
    新版改进：
      1. **月度采样**（约 60 个数据点）替代年度，分布更稳定
      2. 用 EPS 时间序列做线性插值：每个月的价格配该月对应的"近似 TTM EPS"
      3. **Winsorize**：剔除 P/E < 0 或 > 150 的离群点（业务起步期 / 亏损期）
    """
    if history_5y is None or history_5y.empty or not eps_history_5y or current_pe is None:
        return None
    if len(eps_history_5y) < 2:
        return None

    try:
        prices = history_5y["Close"].copy()
        if hasattr(prices.index, "tz") and prices.index.tz is not None:
            prices.index = prices.index.tz_localize(None)
        # 月度末价格（每月最后一个交易日）
        monthly = prices.resample("ME").last().dropna()
    except Exception:
        return None

    if len(monthly) < 12:
        return None

    # 按月份所属年份取该年 EPS（避免线性插值把早期低 EPS 铺满 60 个月制造虚假高 P/E）
    # eps_history_5y 升序，假设最后一个值对应最近年份。年份从 monthly 的最后日期反推。
    last_year = monthly.index[-1].year
    n_eps = len(eps_history_5y)
    # 年份 → EPS 映射：最近一年 = eps_history_5y[-1]，往前类推
    year_to_eps = {last_year - (n_eps - 1 - i): eps for i, eps in enumerate(eps_history_5y)}

    pes = []
    for ts, price in monthly.items():
        eps = year_to_eps.get(ts.year)
        if eps is None or eps <= 0 or price <= 0:
            continue
        pe = price / eps
        # Winsorize：剔除明显离群的 P/E（早期亏损 / 业务起步期）
        if 0 < pe < 150:
            pes.append(pe)

    if len(pes) < 6:
        return None

    pes_sorted = sorted(pes)
    n = len(pes_sorted)
    p25 = pes_sorted[n // 4]
    p50 = statistics.median(pes_sorted)
    p75 = pes_sorted[min(n - 1, n * 3 // 4)]

    rank = sum(1 for x in pes_sorted if x <= current_pe)
    percentile = rank / n * 100

    return {
        "samples": pes_sorted,
        "samples_n": n,
        "p25": p25,
        "p50": p50,
        "p75": p75,
        "percentile": percentile,
    }


# _quarterly_revenue_growths 已迁移到 _common.quarterly_revenue_yoy_growths
# 保留别名以减少调用处改动
_quarterly_revenue_growths = quarterly_revenue_yoy_growths


def _net_cash_per_share(info):
    cash = info.get("totalCash")
    debt = info.get("totalDebt")
    shares = info.get("sharesOutstanding")
    if cash is None or debt is None or not shares:
        return None
    return (cash - debt) / shares


def diagnose(data, category):
    """
    返回 dict:
      tools: 使用的估值工具描述
      metrics: list of dict {name, current, peer_avg, history_avg, percentile}
      historical_pe: dict or None
      peers: list of peer snapshot dicts
      verdict: '🟢 明显便宜' / '🟡 合理' / '🔴 不便宜'
      cycle_warning: bool（周期股 P/E 陷阱）
      cheap_reason: dict {class, label, reason, evidence}
    """
    info = data.get("info") or {}
    sector = info.get("sector")
    industry = info.get("industry")
    ticker = data.get("ticker")
    cat_key = category["key"]

    # 同行快照
    peer_tickers = get_peers(sector, industry, exclude_ticker=ticker)
    peer_snapshots = []
    for pt in peer_tickers:
        snap = fetch_peer_snapshot(pt)
        if snap:
            peer_snapshots.append(snap)

    # 关键指标
    forward_pe = info.get("forwardPE")
    trailing_pe = info.get("trailingPE")
    peg = info.get("trailingPegRatio") or info.get("pegRatio")
    p_s = info.get("priceToSalesTrailing12Months")
    p_b = info.get("priceToBook")
    ev_ebitda = info.get("enterpriseToEbitda")
    ev_revenue = info.get("enterpriseToRevenue")
    div_yield_raw = info.get("dividendYield")
    div_yield = (div_yield_raw * 100) if div_yield_raw and div_yield_raw < 1 else div_yield_raw

    # PEG fallback：当 yfinance 没给 trailingPegRatio / pegRatio 时，自己用 forward_pe / 增速 算
    # 增速优先级：earningsGrowth (TTM 净利润 YoY) > revenueGrowth > forward EPS 隐含增速
    peg_is_implied = False
    if peg is None and forward_pe is not None and forward_pe > 0:
        eps_grw = info.get("earningsGrowth")
        rev_grw = info.get("revenueGrowth")
        fwd_signals = data.get("forward_signals") or {}
        eps_implied = fwd_signals.get("eps_implied_growth")
        # 选最稳健的增速（按优先级）
        growth_pct = None
        for candidate in (eps_grw, rev_grw):
            if candidate is None:
                continue
            try:
                g = float(candidate) * 100
                if 0 < g < 200:  # 过滤基期效应噪音
                    growth_pct = g
                    break
            except (TypeError, ValueError):
                continue
        # 最后兜底：forward EPS 隐含增速（已经是百分比形式，且已过滤 >500% 噪音）
        if growth_pct is None and eps_implied is not None and 0 < eps_implied < 200:
            growth_pct = eps_implied
        if growth_pct and growth_pct > 0:
            peg = forward_pe / growth_pct
            peg_is_implied = True

    # 行业自适应：utility / IPP / REIT / 能源 / 基础材料 用 EV/EBITDA 替代 P/B 做主估值
    industry = info.get("industry")
    use_ev = _use_ev_ebitda_primary(sector, industry)

    # 历史 P/E 百分位
    # 对 inflection / fast_grower / turnaround 用 forward_pe 做对比 PE：
    #   trailing PE 受最近一两个季度 EPS 波动影响巨大（如 ONTO Q4 净利润 -78%
    #   会把 trailing PE 推到 100x，但分析师 forward 共识是 31x），
    #   trailing PE 不能反映"被市场预期的估值水位"。
    # 对 stalwart / cyclical / unclassified 仍用 trailing_pe（更稳定）。
    historical_pe = None
    cat_key_for_pe = category["key"]
    use_forward = cat_key_for_pe in ("inflection", "fast_grower", "turnaround")
    pe_for_compare = forward_pe if use_forward else trailing_pe
    if pe_for_compare and pe_for_compare > 0:
        income = data.get("income_stmt")
        if income is None:
            income = data.get("financials")
        eps_hist = _safe_eps_history(income)
        historical_pe = _historical_pe_percentile(data.get("history_5y"), eps_hist, pe_for_compare)
        if historical_pe is not None:
            historical_pe["pe_basis"] = "Forward P/E vs 历史 trailing P/E（前瞻视角）" if use_forward else "Trailing P/E vs 历史 trailing P/E"

    # 同行均值
    def _peer_avg(field):
        vals = [p[field] for p in peer_snapshots if p.get(field) is not None]
        return sum(vals) / len(vals) if vals else None

    peer_pe_avg = _peer_avg("forward_PE")
    peer_peg_avg = _peer_avg("PEG")
    peer_ps_avg = _peer_avg("P_S")

    metrics = []
    cycle_warning = False
    tools_desc = category.get("sub_system", "通用")

    if cat_key == "stalwart":
        metrics.append({"name": "Forward P/E", "current": forward_pe,
                        "peer": peer_pe_avg,
                        "history_5y_median": historical_pe["p50"] if historical_pe else None,
                        "percentile": historical_pe["percentile"] if historical_pe else None})
        metrics.append({"name": "股息率 (%)", "current": div_yield,
                        "peer": None, "history_5y_median": None, "percentile": None})
    elif cat_key in ("fast_grower", "inflection"):
        metrics.append({"name": "PEG", "current": peg, "peer": peer_peg_avg,
                        "history_5y_median": None, "percentile": None})
        metrics.append({"name": "P/S (TTM)", "current": p_s, "peer": peer_ps_avg,
                        "history_5y_median": None, "percentile": None})
        metrics.append({"name": "Forward P/E", "current": forward_pe, "peer": peer_pe_avg,
                        "history_5y_median": historical_pe["p50"] if historical_pe else None,
                        "percentile": historical_pe["percentile"] if historical_pe else None})
    elif cat_key == "cyclical":
        cycle_warning = True
        if use_ev:
            metrics.append({"name": "EV/EBITDA", "current": ev_ebitda, "peer": None,
                            "history_5y_median": None, "percentile": None})
        else:
            metrics.append({"name": "P/B", "current": p_b, "peer": None,
                            "history_5y_median": None, "percentile": None})
        metrics.append({"name": "P/S (TTM)", "current": p_s, "peer": peer_ps_avg,
                        "history_5y_median": None, "percentile": None})
        metrics.append({"name": "Forward P/E (⚠️ 仅参考)", "current": forward_pe,
                        "peer": peer_pe_avg, "history_5y_median": None, "percentile": None})
    elif cat_key == "turnaround":
        ncps = _net_cash_per_share(info)
        if use_ev:
            # 像 VST 这种被错归 turnaround 的实际是 utility/IPP，用 EV/EBITDA 而非 P/B
            metrics.append({"name": "EV/EBITDA", "current": ev_ebitda, "peer": None,
                            "history_5y_median": None, "percentile": None})
            metrics.append({"name": "EV/Revenue", "current": ev_revenue, "peer": None,
                            "history_5y_median": None, "percentile": None})
        else:
            metrics.append({"name": "P/B", "current": p_b, "peer": None,
                            "history_5y_median": None, "percentile": None})
            metrics.append({"name": "净现金/股 ($)", "current": ncps,
                            "peer": None, "history_5y_median": None, "percentile": None})
    elif cat_key == "speculative":
        metrics.append({"name": "P/S (TTM)", "current": p_s, "peer": peer_ps_avg,
                        "history_5y_median": None, "percentile": None})
        metrics.append({"name": "Forward P/E", "current": forward_pe, "peer": peer_pe_avg,
                        "history_5y_median": None, "percentile": None})
    else:  # unclassified
        metrics.append({"name": "Forward P/E", "current": forward_pe, "peer": peer_pe_avg,
                        "history_5y_median": historical_pe["p50"] if historical_pe else None,
                        "percentile": historical_pe["percentile"] if historical_pe else None})
        metrics.append({"name": "P/B", "current": p_b, "peer": None,
                        "history_5y_median": None, "percentile": None})

    # ---- 同行折价/溢价（显式化）----
    peer_relative = _peer_relative(forward_pe, peer_pe_avg, p_s, peer_ps_avg, peg, peer_peg_avg)

    # ---- 估值结论（大势动态阈值）----
    market_judgment = data.get("market_judgment", "中性")
    verdict = _verdict(cat_key, info, peg, forward_pe, p_s, peer_pe_avg, peer_peg_avg,
                       peer_ps_avg, historical_pe, p_b, ev_ebitda, use_ev, peer_relative,
                       market_judgment=market_judgment)

    # ---- 模块4：原因归类 ----
    cheap_reason = _classify_reason(data, category, verdict, info)

    return {
        "tools": tools_desc,
        "metrics": metrics,
        "historical_pe": historical_pe,
        "peers": peer_snapshots,
        "peer_relative": peer_relative,
        "verdict": verdict,
        "cycle_warning": cycle_warning,
        "cheap_reason": cheap_reason,
        "peg_is_implied": peg_is_implied,
    }


def _peer_relative(forward_pe, peer_pe_avg, p_s, peer_ps_avg, peg, peer_peg_avg):
    """
    显式计算 vs 同行折价/溢价百分比。
    返回 list of dict {metric, self, peer_avg, vs_peer_pct, label}
    label: "便宜" / "贵" / "持平"
    """
    items = []
    def add(name, self_v, peer_v):
        if self_v is None or peer_v is None or peer_v <= 0:
            return
        diff_pct = (self_v - peer_v) / peer_v * 100
        if diff_pct < -10:
            label = f"vs 同行折价 {abs(diff_pct):.0f}% 🟢"
        elif diff_pct > 15:
            label = f"vs 同行溢价 {diff_pct:.0f}% 🔴"
        else:
            label = f"vs 同行 {diff_pct:+.0f}% 🟡"
        items.append({"metric": name, "self": self_v, "peer_avg": peer_v,
                      "vs_peer_pct": diff_pct, "label": label})
    add("Forward P/E", forward_pe, peer_pe_avg)
    add("PEG", peg, peer_peg_avg)
    add("P/S", p_s, peer_ps_avg)
    return items


def _safe_eps_history(income):
    if income is None or income.empty:
        return None
    for k in ("Diluted EPS", "Basic EPS"):
        if k in income.index:
            try:
                eps = income.loc[k].dropna().astype(float).sort_index(ascending=True)
                return [float(x) for x in eps.tolist()][-5:]
            except Exception:
                return None
    return None


def _market_thresholds(market_judgment):
    """
    根据大势返回 (peg_cheap_threshold, peer_cheap_mult, peer_expensive_mult).
    顺风：放宽 cheap 阈值；逆风：收紧（防止"便宜在板块逆风里"假信号，BSX 案例）。
    """
    if market_judgment == "顺风":
        return 1.2, 0.90, 1.20
    if market_judgment == "逆风":
        return 0.8, 0.75, 1.10
    return 1.0, 0.85, 1.15  # 中性（旧默认值）


def _verdict(cat_key, info, peg, forward_pe, p_s, peer_pe_avg, peer_peg_avg, peer_ps_avg,
             historical_pe, p_b, ev_ebitda=None, use_ev=False, peer_relative=None,
             market_judgment="中性"):
    if cat_key == "speculative":
        return "🔴 投机股不做估值判断"

    # 大势动态阈值（修复 BSX 案例：板块逆风时不该轻易给"明显便宜"）
    peg_cheap, peer_cheap_mult, peer_exp_mult = _market_thresholds(market_judgment)

    cheap_signals = 0
    expensive_signals = 0
    total = 0

    if cat_key in ("fast_grower", "inflection"):
        if peg is not None:
            total += 1
            # inflection 期 PEG 阈值进一步放宽（财报后才能验证）
            cheap_threshold = peg_cheap + 0.3 if cat_key == "inflection" else peg_cheap
            if peg < cheap_threshold:
                cheap_signals += 1
            elif peg > 2:
                expensive_signals += 1
        if p_s is not None and peer_ps_avg is not None:
            total += 1
            if p_s < peer_ps_avg * peer_cheap_mult:
                cheap_signals += 1
            elif p_s > peer_ps_avg * peer_exp_mult:
                expensive_signals += 1
    elif cat_key == "cyclical":
        if p_b is not None:
            total += 1
            if p_b < 1.2:
                cheap_signals += 1
            elif p_b > 3:
                expensive_signals += 1
        if p_s is not None and peer_ps_avg is not None:
            total += 1
            if p_s < peer_ps_avg * 0.85:
                cheap_signals += 1
            elif p_s > peer_ps_avg * 1.15:
                expensive_signals += 1
    elif cat_key == "turnaround":
        if use_ev and ev_ebitda is not None:
            # utility/IPP/REIT/能源 用 EV/EBITDA：<8 = 便宜，>15 = 贵
            total += 1
            if ev_ebitda < 8:
                cheap_signals += 1
            elif ev_ebitda > 15:
                expensive_signals += 1
        elif p_b is not None:
            total += 1
            if p_b < 1:
                cheap_signals += 1
            elif p_b > 2:
                expensive_signals += 1
    else:  # stalwart / unclassified
        if forward_pe is not None and historical_pe is not None:
            total += 1
            pct = historical_pe["percentile"]
            if pct < 25:
                cheap_signals += 1
            elif pct > 75:
                expensive_signals += 1
        if forward_pe is not None and peer_pe_avg is not None:
            total += 1
            if forward_pe < peer_pe_avg * peer_cheap_mult:
                cheap_signals += 1
            elif forward_pe > peer_pe_avg * peer_exp_mult:
                expensive_signals += 1

    # 同行折价/溢价加权（任意主估值指标对同行折价 >25% = 强 cheap signal）
    if peer_relative:
        for pr in peer_relative:
            if pr["vs_peer_pct"] < -25:
                cheap_signals += 1
                total += 1
            elif pr["vs_peer_pct"] > 30:
                expensive_signals += 1
                total += 1

    if total == 0:
        return "🟡 数据不足，按合理估值处理"
    if cheap_signals >= max(1, total - 1) and cheap_signals > expensive_signals:
        return "🟢 明显便宜"
    if expensive_signals >= max(1, total - 1) and expensive_signals > cheap_signals:
        return "🔴 不便宜"
    return "🟡 合理"


def _classify_reason(data, category, verdict, info):
    """
    模块4：归类便宜/贵的原因。
    A 起步阶段 / B 暂时利空 / C 周期底部 / D 结构性问题 / E 假便宜
    """
    qf = data.get("quarterly_income_stmt")
    if qf is None:
        qf = data.get("quarterly_financials")
    cat_key = category["key"]
    analyst_count = info.get("numberOfAnalystOpinions") or 0
    high_52w = info.get("fiftyTwoWeekHigh")
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    p_b = info.get("priceToBook")

    # 季度营收变化
    growths = _quarterly_revenue_growths(qf)

    # E 类：估值=🔴 → 假便宜
    if "🔴" in verdict and "投机" not in verdict:
        return {
            "class": "E",
            "label": "假便宜 / 不便宜",
            "reason": "估值高于历史 75 分位且高于同行均值",
            "evidence": "见模块3估值表",
        }

    # D 类：连续 3+ 季度营收同比下滑
    if growths and len(growths) >= 3:
        last3 = growths[-3:]
        if all(g < 0 for g in last3):
            return {
                "class": "D",
                "label": "结构性问题",
                "reason": "连续 3 个季度 YoY 营收负增长",
                "evidence": f"近 3 季度增速：{', '.join(f'{g:+.1f}%' for g in last3)}",
            }

    # C 类：周期股 + P/B < 历史均值（这里用 1.5 作粗略阈值）
    if cat_key == "cyclical" and p_b is not None and p_b < 1.5:
        return {
            "class": "C",
            "label": "周期底部",
            "reason": "周期股 + P/B 低位",
            "evidence": f"P/B={p_b:.2f}（粗略阈值 1.5）",
        }

    # B 类：距 52w 高跌 >20% + 最新季度营收未下滑
    pct_from_high = None
    if high_52w and price:
        pct_from_high = (high_52w - price) / high_52w * 100
    latest_growth = growths[-1] if growths else None
    if pct_from_high is not None and pct_from_high > 20 and latest_growth is not None and latest_growth >= 0:
        return {
            "class": "B",
            "label": "暂时利空",
            "reason": f"距 52 周高点跌 {pct_from_high:.0f}%，但最新季度 YoY 营收 {latest_growth:+.1f}%",
            "evidence": "股价回调与基本面背离",
        }

    # A 类：营收加速 + 分析师覆盖少
    if growths and len(growths) >= 2 and analyst_count < 10:
        if growths[-1] > growths[-2]:
            return {
                "class": "A",
                "label": "起步阶段",
                "reason": f"营收加速（{growths[-2]:+.1f}% → {growths[-1]:+.1f}%）+ 分析师仅 {analyst_count} 人覆盖",
                "evidence": "尚未被广泛认知",
            }

    # 默认（修复 BSX 案例：估值🟢但不匹配 A/B/C/D 时不该强行归"暂时利空"，
    # 这类 fallback 会让用户错把"市场领先于基本面的卖压"当成"暂时利空"机会）
    if "🟢" in verdict:
        return {
            "class": "?",
            "label": "便宜原因不明（需手动调研）",
            "reason": "估值显示便宜，但未匹配 A/B/C/D 任何明确模式 — 可能是市场领先于基本面 1-2 季度（即将到来的 guidance 下调 / 同业坏消息 / 监管变化）",
            "evidence": "建议手动调研：①最近一次 earnings call 管理层口风；②同业近期 guide 走向；③内部人开盘市场卖出 vs 买入；④sell-side 评级变动",
        }
    return {
        "class": "—",
        "label": "无显著模式",
        "reason": "估值合理，未触发任何便宜/贵的归类条件",
        "evidence": "—",
    }
