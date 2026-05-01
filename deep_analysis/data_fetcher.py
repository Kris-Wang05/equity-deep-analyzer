"""
deep_analysis 专用 yfinance 抓取层。
返回一个包含原始 dataframe 与衍生指标的 dict，下游各模块按需取用。
"""

import math
from datetime import datetime

import yfinance as yf


def _safe(v):
    if v is None:
        return None
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _round(v, n=2):
    f = _safe(v)
    return round(f, n) if f is not None else None


def fetch_all(ticker):
    """
    一站式抓取：返回 dict 包含 info / 多张报表 / 价格历史 / 内部人交易 / 财报日期。
    任何字段失败返回 None，调用方做缺失检查。
    """
    t = yf.Ticker(ticker)
    out = {"ticker": ticker.upper(), "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M")}

    try:
        info = t.info or {}
    except Exception:
        info = {}
    out["info"] = info

    # 报表
    for attr in ("financials", "quarterly_financials", "balance_sheet",
                 "quarterly_balance_sheet", "cashflow", "quarterly_cashflow",
                 "income_stmt", "quarterly_income_stmt"):
        try:
            df = getattr(t, attr)
            out[attr] = df if df is not None and not df.empty else None
        except Exception:
            out[attr] = None

    # 价格历史
    try:
        out["history_1y"] = t.history(period="1y")
    except Exception:
        out["history_1y"] = None
    try:
        out["history_5y"] = t.history(period="5y")
    except Exception:
        out["history_5y"] = None

    # 内部人 / 推荐 / 财报日期
    try:
        out["insider_transactions"] = t.insider_transactions
    except Exception:
        out["insider_transactions"] = None
    try:
        out["recommendations"] = t.recommendations
    except Exception:
        out["recommendations"] = None
    try:
        out["earnings_dates"] = t.earnings_dates
    except Exception:
        out["earnings_dates"] = None

    # 把 yfinance ticker 对象本身留着，供 history 拉 ETF 时复用（无需重复创建实例）
    out["_yf_ticker"] = t

    # ---- 币种识别 + FX 汇率（修复 LSE / ADR / TYO 等非美股币种 bug）----
    # currency = 价格币种（影响股价 / 52w 高低 / 目标价 / 入场价）
    # financialCurrency = 财务报表币种（影响营收 / OCF / FCF / netIncome）
    # 两者可能不同：ASX (USD ADR + TWD 财报)、RYCEY (USD ADR + GBP 财报)
    price_ccy = info.get("currency")
    fin_ccy = info.get("financialCurrency")
    out["price_currency"] = price_ccy
    out["financial_currency"] = fin_ccy
    out["fx_price_to_usd"] = _fetch_fx_to_usd(price_ccy)
    out["fx_fin_to_usd"] = _fetch_fx_to_usd(fin_ccy) if fin_ccy != price_ccy else out["fx_price_to_usd"]

    # ---- 前瞻信号：用来对抗 TTM 滞后 ----
    qf_for_fwd = out.get("quarterly_income_stmt")
    if qf_for_fwd is None:
        qf_for_fwd = out.get("quarterly_financials")
    out["forward_signals"] = _compute_forward_signals(info, qf_for_fwd)

    # M&A 整合期识别：流通股 +30% YoY 且营收 +50%+ 几乎一定是大并购合并跳变
    out["ma_signal"] = _detect_ma_integration(t, out["forward_signals"])
    return out


def _detect_recent_split(stock_obj, lookback_days=400):
    """
    检测最近 lookback_days 内是否有 stock split。
    返回 (cumulative_split_ratio, split_date_str) 或 (None, None)。
    例：5:1 split → 返回 (5.0, '2025-12-18')；多次 split 累积相乘。
    """
    try:
        splits = stock_obj.splits
        if splits is None or len(splits) == 0:
            return None, None
        # yfinance 不同版本可能返回 Series 或 DataFrame，统一转成 Series
        import pandas as pd
        if isinstance(splits, pd.DataFrame):
            splits = splits.iloc[:, 0]
        from datetime import timedelta
        cutoff = datetime.today() - timedelta(days=lookback_days)
        idx = splits.index
        # 处理 tz-aware：tz-aware index 不能直接 tz_localize(None) (会 raise)
        try:
            if hasattr(idx, "tz") and idx.tz is not None:
                splits = splits.copy()
                splits.index = idx.tz_convert(None)
        except Exception:
            pass
        recent = splits[splits.index >= cutoff]
        if len(recent) == 0:
            return None, None
        cum_ratio = float(recent.prod())
        last_date = recent.index[-1].strftime("%Y-%m-%d")
        return cum_ratio, last_date
    except Exception:
        return None, None


def _detect_ma_integration(stock_obj, fwd_signals):
    """
    检测大并购整合期 vs stock split。返回 dict:
      is_ma_integration: bool
      shares_change_yoy: float | None       — 原始（未调整 split）流通股变化
      shares_change_adj: float | None       — 调整 split 后的流通股变化（真实 M&A 信号）
      split_ratio: float | None             — 近 400 天累积 split 比例
      split_date: str | None
      reason: str
    判断逻辑（修复后）：
      1. 先检测 split。如果有 split，把流通股变化除以 split ratio 得到调整后变化
      2. 调整后变化 +50% 单条件 / +30% AND 季度营收 +50% 双条件 才算 M&A
      3. 如果只有 split 没有真 M&A，输出 split_only 标记
    """
    out = {
        "is_ma_integration": False, "is_stock_split": False,
        "shares_change_yoy": None, "shares_change_adj": None,
        "split_ratio": None, "split_date": None, "reason": "",
    }

    # 1. 检测 split
    split_ratio, split_date = _detect_recent_split(stock_obj)
    if split_ratio and split_ratio > 1.0:
        out["is_stock_split"] = True
        out["split_ratio"] = split_ratio
        out["split_date"] = split_date

    # 2. 拉流通股变化
    try:
        from datetime import timedelta
        end = datetime.today()
        start = end - timedelta(days=400)
        shares = stock_obj.get_shares_full(start=start, end=end)
        if shares is None or len(shares) < 2:
            return out
        oldest = float(shares.iloc[0])
        newest = float(shares.iloc[-1])
        if oldest <= 0:
            return out
        change_pct = (newest - oldest) / oldest * 100
        out["shares_change_yoy"] = change_pct
    except Exception:
        return out

    # 3. 按 split 调整流通股变化
    # split 让流通股变 N 倍 = +(N-1)*100%；剔除 split 后才看真实 M&A 对价
    if split_ratio and split_ratio > 1.0:
        # 调整：(1 + change/100) / split_ratio - 1
        adj = (1 + change_pct / 100) / split_ratio - 1
        out["shares_change_adj"] = adj * 100
    else:
        out["shares_change_adj"] = change_pct

    # 4. 判断 M&A（用调整后值）
    adj_pct = out["shares_change_adj"]
    rev_yoy = fwd_signals.get("revenue_growth_yoy_q") if fwd_signals else None
    if adj_pct is not None and adj_pct > 50:
        out["is_ma_integration"] = True
        out["reason"] = f"流通股 YoY +{adj_pct:.0f}%（已剔除 split 影响）单条件触发，几乎确定为大并购对价支付"
    elif adj_pct is not None and adj_pct > 30 and rev_yoy is not None and rev_yoy > 50:
        out["is_ma_integration"] = True
        out["reason"] = f"流通股 YoY +{adj_pct:.0f}%（已剔除 split）+ 季度营收 YoY +{rev_yoy:.0f}% 双重触发"
    return out


def _compute_forward_signals(info, qf):
    """
    把"前瞻 vs 滞后"的差异显式化，让分类器和报告都能看到。

    返回字段：
      revenue_growth_ttm        — TTM YoY 营收增速 (%)
      revenue_growth_yoy_q      — 最新单季 YoY 增速 (%)
      revenue_growth_qoq        — 最新单季 QoQ 增速 (%)
      revenue_yoy_acceleration  — 最近 2 个季度 YoY 增速差（>0=加速）
      earnings_growth_q         — earningsQuarterlyGrowth (info 字段，YoY 净利润，%)
      forward_eps               — 前瞻 EPS
      trailing_eps              — 滞后 EPS
      eps_implied_growth        — (forward_eps - trailing_eps) / |trailing_eps| * 100
      is_inflection             — 拐点信号：TTM 平 / 最新季度环比 + YoY 加速 + EPS 隐含改善
    """
    out = {
        "revenue_growth_ttm": None,
        "revenue_growth_yoy_q": None,
        "revenue_growth_qoq": None,
        "revenue_yoy_acceleration": None,
        "earnings_growth_q": None,
        "forward_eps": None,
        "trailing_eps": None,
        "eps_implied_growth": None,
        "is_inflection": False,
    }

    rg = info.get("revenueGrowth")
    if rg is not None:
        try:
            out["revenue_growth_ttm"] = float(rg) * 100
        except (TypeError, ValueError):
            pass

    eg = info.get("earningsQuarterlyGrowth")
    if eg is not None:
        try:
            eg_pct = float(eg) * 100
            # 基期效应清洗：单季净利润 YoY 增速 >500% 或 <-95% 几乎一定是基期接近 0 / 由负转正 等会计噪音，
            # 不能作为分类信号（曾让 TEL 触发"快速增长股" +7150%、AVAV/VST 误归"投机"）。
            if -95 < eg_pct < 500:
                out["earnings_growth_q"] = eg_pct
            else:
                out["earnings_growth_q"] = None
                out["earnings_growth_q_raw_noisy"] = eg_pct
        except (TypeError, ValueError):
            pass

    fe = info.get("forwardEps")
    te = info.get("trailingEps")
    out["forward_eps"] = _safe(fe)
    out["trailing_eps"] = _safe(te)
    if out["forward_eps"] is not None and out["trailing_eps"] is not None and out["trailing_eps"] != 0:
        out["eps_implied_growth"] = (out["forward_eps"] - out["trailing_eps"]) / abs(out["trailing_eps"]) * 100

    # ---- 季度营收衍生 ----
    if qf is not None and not qf.empty and "Total Revenue" in qf.index:
        try:
            rev = qf.loc["Total Revenue"].dropna().astype(float).sort_index(ascending=True)
            if len(rev) >= 5:
                # YoY 最新季度
                latest = rev.iloc[-1]
                yoy_prev = rev.iloc[-5]
                if yoy_prev > 0:
                    out["revenue_growth_yoy_q"] = (latest - yoy_prev) / yoy_prev * 100
                # YoY 上一季度（用于加速度）
                if len(rev) >= 6:
                    prev_q = rev.iloc[-2]
                    yoy_prev2 = rev.iloc[-6]
                    if yoy_prev2 > 0 and out["revenue_growth_yoy_q"] is not None:
                        prev_yoy = (prev_q - yoy_prev2) / yoy_prev2 * 100
                        out["revenue_yoy_acceleration"] = out["revenue_growth_yoy_q"] - prev_yoy
            if len(rev) >= 2:
                latest = rev.iloc[-1]
                prev = rev.iloc[-2]
                if prev > 0:
                    out["revenue_growth_qoq"] = (latest - prev) / prev * 100
        except Exception:
            pass

    # ---- 拐点判断 ----
    # TTM 增速平淡（|TTM|<10%）下，触发条件：
    #   (1) 任一信号超过"双倍阈值"= 单一极强信号独立触发（修复 ENTG 漏抓案例）
    #   (2) 或者 ≥2 个普通阈值信号同时存在
    ttm = out["revenue_growth_ttm"]
    if ttm is not None and abs(ttm) < 10:
        # 普通阈值信号
        signals = 0
        # 极强单条件（任一触发即拐点）
        strong_single = False
        strong_reason = None

        if out["revenue_yoy_acceleration"] is not None:
            if out["revenue_yoy_acceleration"] > 5:
                signals += 1
            if out["revenue_yoy_acceleration"] > 10:
                strong_single = True
                strong_reason = f"季度 YoY 加速 +{out['revenue_yoy_acceleration']:.1f}pp"
        if out["revenue_growth_qoq"] is not None:
            if out["revenue_growth_qoq"] > 10:
                signals += 1
            if out["revenue_growth_qoq"] > 25:
                strong_single = True
                strong_reason = f"环比 +{out['revenue_growth_qoq']:.1f}%"
        if out["eps_implied_growth"] is not None:
            if out["eps_implied_growth"] > 25:
                signals += 1
            if out["eps_implied_growth"] > 100:
                strong_single = True
                strong_reason = f"前瞻 EPS 隐含增速 +{out['eps_implied_growth']:.1f}%"
        if out["earnings_growth_q"] is not None:
            if out["earnings_growth_q"] > 25:
                signals += 1
            # earnings_growth_q 单条件不触发（基期效应风险高，已在 >500% 过滤但仍偏噪音）

        if signals >= 2 or strong_single:
            out["is_inflection"] = True
            if strong_single:
                out["inflection_strong_single"] = strong_reason

    return out


def _fetch_fx_to_usd(currency_code):
    """
    返回 1 unit currency_code = X USD 的最新汇率。USD 自身返回 1.0，失败返回 None。
    GBp（便士，0.01 GBP）= GBP / 100 特殊处理。
    """
    if not currency_code:
        return None
    if currency_code in ("USD", "usd"):
        return 1.0
    # GBp 是 GBP/100（伦敦交易所大多数股票报价单位）
    if currency_code == "GBp":
        rate_gbp = _fetch_fx_to_usd("GBP")
        return rate_gbp / 100 if rate_gbp else None
    if currency_code == "ZAc":  # 南非 cents
        rate_zar = _fetch_fx_to_usd("ZAR")
        return rate_zar / 100 if rate_zar else None
    try:
        pair_ticker = f"{currency_code}USD=X"
        hist = yf.Ticker(pair_ticker).history(period="5d")
        if hist is None or hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception:
        return None


def fetch_etf(etf_ticker):
    """轻量拉 ETF：只要 1 年历史 + 52 周高/低."""
    try:
        t = yf.Ticker(etf_ticker)
        hist = t.history(period="1y")
        if hist is None or hist.empty:
            return None
        info = {}
        try:
            info = t.info or {}
        except Exception:
            pass
        return {"ticker": etf_ticker, "history": hist, "info": info}
    except Exception:
        return None


def fetch_peer_snapshot(ticker):
    """
    同行对标快照：只取 forwardPE / pegRatio / priceToSales / revenueGrowth.
    失败返回 None.
    """
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        return None
    return {
        "ticker": ticker,
        "forward_PE": _safe(info.get("forwardPE")),
        "PEG": _safe(info.get("trailingPegRatio") or info.get("pegRatio")),
        "P_S": _safe(info.get("priceToSalesTrailing12Months")),
        "revenue_growth": _round(_safe(info.get("revenueGrowth")) and info["revenueGrowth"] * 100, 1),
    }
