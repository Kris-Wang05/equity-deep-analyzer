"""
模块5：基本面与风险快检。
营收 / 利润率趋势 / 现金流 / 负债 / 回购稀释 / 内部人 / 分析师 / 下次财报。
"""

from datetime import datetime

import pandas as pd


def _last_n_quarter_revenues(qf, n=4):
    """返回 [(date_str, rev, yoy_growth_pct or None), ...]，时间升序."""
    if qf is None or qf.empty or "Total Revenue" not in qf.index:
        return None
    rev = qf.loc["Total Revenue"].dropna().astype(float).sort_index(ascending=True)
    if rev.empty:
        return None
    items = []
    for i in range(max(0, len(rev) - n), len(rev)):
        date = rev.index[i]
        val = rev.iloc[i]
        yoy = None
        if i >= 4:
            prev = rev.iloc[i - 4]
            if prev > 0:
                yoy = (val - prev) / prev * 100
        items.append((date, val, yoy))
    return items


def _quarterly_margins(qf, n=4):
    """返回最近 n 季度的 (gross_margin, op_margin) 列表，升序."""
    if qf is None or qf.empty or "Total Revenue" not in qf.index:
        return None
    rev = qf.loc["Total Revenue"].astype(float).sort_index(ascending=True)
    gp = qf.loc["Gross Profit"].astype(float).sort_index(ascending=True) if "Gross Profit" in qf.index else None
    op = None
    for k in ("Operating Income", "EBIT"):
        if k in qf.index:
            op = qf.loc[k].astype(float).sort_index(ascending=True)
            break
    items = []
    for date in rev.index[-n:]:
        r = rev.get(date)
        if not r or r <= 0:
            continue
        g = (gp.get(date) / r * 100) if gp is not None and date in gp.index and gp.get(date) is not None else None
        o = (op.get(date) / r * 100) if op is not None and date in op.index and op.get(date) is not None else None
        items.append({"date": date, "gross_margin": g, "operating_margin": o})
    return items


def _trend(values):
    if not values or len(values) < 2:
        return "→"
    delta = values[-1] - values[0]
    if delta > 1:
        return "↑"
    if delta < -1:
        return "↓"
    return "→"


def _ttm_cashflow(cashflow_df):
    """从年度 cashflow 取最近 1 期 OCF & FCF."""
    if cashflow_df is None or cashflow_df.empty:
        return None, None
    latest = cashflow_df.columns[0]  # yfinance 通常最新在第一列
    ocf_keys = ("Operating Cash Flow", "Cash Flow From Continuing Operating Activities",
                "Total Cash From Operating Activities")
    capex_keys = ("Capital Expenditure", "Capital Expenditures")
    ocf = None
    capex = None
    for k in ocf_keys:
        if k in cashflow_df.index:
            try:
                ocf = float(cashflow_df.loc[k, latest])
                break
            except Exception:
                pass
    for k in capex_keys:
        if k in cashflow_df.index:
            try:
                capex = float(cashflow_df.loc[k, latest])
                break
            except Exception:
                pass
    fcf = None
    if ocf is not None and capex is not None:
        # capex 通常已为负
        fcf = ocf + capex if capex < 0 else ocf - capex
    return ocf, fcf


def _quarterly_ttm_cashflow(qcashflow):
    """季度数据 TTM (最近 4 季度求和)."""
    if qcashflow is None or qcashflow.empty:
        return None, None
    ocf_keys = ("Operating Cash Flow", "Cash Flow From Continuing Operating Activities",
                "Total Cash From Operating Activities")
    capex_keys = ("Capital Expenditure", "Capital Expenditures")
    ocf = None
    capex = None
    for k in ocf_keys:
        if k in qcashflow.index:
            try:
                vals = qcashflow.loc[k].dropna().astype(float).sort_index(ascending=True).tail(4)
                if not vals.empty:
                    ocf = float(vals.sum())
                break
            except Exception:
                pass
    for k in capex_keys:
        if k in qcashflow.index:
            try:
                vals = qcashflow.loc[k].dropna().astype(float).sort_index(ascending=True).tail(4)
                if not vals.empty:
                    capex = float(vals.sum())
                break
            except Exception:
                pass
    fcf = None
    if ocf is not None and capex is not None:
        fcf = ocf + capex if capex < 0 else ocf - capex
    return ocf, fcf


def _shares_change_yoy(stock_obj):
    """返回 1 年流通股变化百分比."""
    if stock_obj is None:
        return None
    try:
        from datetime import timedelta
        end = datetime.today()
        start = end - timedelta(days=400)
        shares = stock_obj.get_shares_full(start=start, end=end)
        if shares is None or len(shares) < 2:
            return None
        oldest = float(shares.iloc[0])
        newest = float(shares.iloc[-1])
        if oldest == 0:
            return None
        return (newest - oldest) / oldest * 100
    except Exception:
        return None


def _classify_insider_text(text):
    """
    从 yfinance insider_transactions 的 Text 字段判断交易性质。
    yfinance 的 Transaction 列实际为空，真实信息在 Text 里：
      - "Sale at price ... per share."                            → sell（开盘市场卖出，强信号）
      - "Purchase at price ... per share."                        → buy（开盘市场买入，强信号）
      - "Stock Award(Grant) at price 0.00 per share."             → grant（股权激励授予，中性）
      - "Stock Award(Grant) at price X per share." (X>0)          → grant（带价激励，仍属授予非现金买入）
      - "Conversion of Exercise of derivative security at ..."    → exercise（期权行权，中性，常配对卖出）
      - "Disposition (Non Open Market) ..."                       → dispose（非开盘处置，通常税务 withholding，中性）
      - "Acquisition (Non Open Market) ..."                       → acquire（非开盘获取，中性）
    返回: "buy" / "sell" / "grant" / "exercise" / "other"
    """
    if not text or pd.isna(text):
        return "other"
    t = str(text).lower()
    if t.startswith("sale at price") or "sale at price" in t:
        return "sell"
    if t.startswith("purchase at price") or "open market purchase" in t:
        return "buy"
    if "stock award" in t or "grant at price" in t:
        return "grant"
    if "conversion" in t or "exercise" in t:
        return "exercise"
    if "non open market" in t or "non-open market" in t:
        return "dispose"
    return "other"


def _is_ceo_position(position_str):
    """判断 Position 字段是否为 CEO（含 Chief Executive Officer / President & CEO 等）。"""
    if not position_str or pd.isna(position_str):
        return False
    p = str(position_str).lower()
    # 排除 CFO / CTO / COO 等非 CEO 角色
    if "chief financial" in p or "chief technology" in p or "chief operating" in p:
        return False
    if "chief executive" in p:
        return True
    # 较短形式 "CEO" 单独出现（避免匹配 "CFO" 等）
    if p == "ceo" or p.startswith("ceo ") or p.endswith(" ceo") or " ceo " in p:
        return True
    if "president" in p and ("chief" in p or "ceo" in p):
        return True
    return False


def _insider_net_6m(insider_df):
    """
    返回最近 6 个月内部人交易统计（按 CEO vs 其他高管拆分）。
    返回 dict:
      # 全部 insider 合计
      open_market_buy_usd / open_market_sell_usd / net_open_market / grant_usd
      buy_count / sell_count / grant_count / total_count
      # CEO 单独拆分（修复 SOFI 案例：CEO 5 年 0 卖只买，但被其他高管净卖拖累）
      ceo_buy_usd / ceo_sell_usd / ceo_net / ceo_buy_count / ceo_sell_count
      # 其他 insider（CEO 之外）
      other_buy_usd / other_sell_usd / other_net
    """
    blank = {
        "open_market_buy_usd": 0.0, "open_market_sell_usd": 0.0,
        "net_open_market": 0.0, "grant_usd": 0.0,
        "buy_count": 0, "sell_count": 0, "grant_count": 0, "total_count": 0,
        "ceo_buy_usd": 0.0, "ceo_sell_usd": 0.0, "ceo_net": 0.0,
        "ceo_buy_count": 0, "ceo_sell_count": 0,
        "other_buy_usd": 0.0, "other_sell_usd": 0.0, "other_net": 0.0,
    }
    if insider_df is None or insider_df.empty:
        return None
    df = insider_df.copy()
    date_col = next((c for c in df.columns if "date" in c.lower()), None)
    if date_col is None:
        return None
    try:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    except Exception:
        return None
    cutoff = pd.Timestamp(datetime.today()) - pd.Timedelta(days=180)
    try:
        recent = df[df[date_col] >= cutoff]
    except Exception:
        return None
    if recent.empty:
        return blank
    val_col = next((c for c in recent.columns if "value" in c.lower()), None)
    text_col = next((c for c in recent.columns if c.lower() == "text"), None)
    pos_col = next((c for c in recent.columns if c.lower() == "position"), None)
    if val_col is None or text_col is None:
        return None

    out = dict(blank)
    out["total_count"] = len(recent)
    for _, row in recent.iterrows():
        v = row.get(val_col)
        if v is None or pd.isna(v):
            continue
        try:
            v = abs(float(v))
        except Exception:
            continue
        kind = _classify_insider_text(row.get(text_col))
        is_ceo = _is_ceo_position(row.get(pos_col)) if pos_col else False

        if kind == "buy":
            out["open_market_buy_usd"] += v
            out["buy_count"] += 1
            if is_ceo:
                out["ceo_buy_usd"] += v
                out["ceo_buy_count"] += 1
            else:
                out["other_buy_usd"] += v
        elif kind == "sell":
            out["open_market_sell_usd"] += v
            out["sell_count"] += 1
            if is_ceo:
                out["ceo_sell_usd"] += v
                out["ceo_sell_count"] += 1
            else:
                out["other_sell_usd"] += v
        elif kind == "grant" or kind == "exercise":
            out["grant_usd"] += v
            out["grant_count"] += 1
        # dispose / other 不计入

    out["net_open_market"] = out["open_market_buy_usd"] - out["open_market_sell_usd"]
    out["ceo_net"] = out["ceo_buy_usd"] - out["ceo_sell_usd"]
    out["other_net"] = out["other_buy_usd"] - out["other_sell_usd"]
    return out


def _next_earnings_date(earnings_dates_df):
    if earnings_dates_df is None or earnings_dates_df.empty:
        return None
    try:
        idx = earnings_dates_df.index
        if hasattr(idx, "tz") and idx.tz is not None:
            idx = idx.tz_localize(None)
        now = pd.Timestamp(datetime.today())
        future = [d for d in idx if pd.Timestamp(d) >= now]
        if not future:
            return None
        return min(future).strftime("%Y-%m-%d")
    except Exception:
        return None


def assess(data):
    info = data.get("info") or {}
    qf = data.get("quarterly_income_stmt")
    if qf is None:
        qf = data.get("quarterly_financials")
    cashflow = data.get("cashflow")
    qcashflow = data.get("quarterly_cashflow")
    stock_obj = data.get("_yf_ticker")

    revenues = _last_n_quarter_revenues(qf, n=4)
    margins = _quarterly_margins(qf, n=4)

    gm_values = [m["gross_margin"] for m in margins or [] if m["gross_margin"] is not None]
    om_values = [m["operating_margin"] for m in margins or [] if m["operating_margin"] is not None]
    gm_trend = _trend(gm_values)
    om_trend = _trend(om_values)

    ocf, fcf = _quarterly_ttm_cashflow(qcashflow)
    if ocf is None and fcf is None:
        ocf, fcf = _ttm_cashflow(cashflow)

    # 负债
    de = info.get("debtToEquity")
    de_ratio = (de / 100) if de is not None else None
    current_ratio = info.get("currentRatio")

    shares_change = _shares_change_yoy(stock_obj)

    insider_stats = _insider_net_6m(data.get("insider_transactions"))

    rating_key = info.get("recommendationKey")
    rating_text = rating_key.replace("_", " ").title() if rating_key else None
    target_mean = info.get("targetMeanPrice")
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    upside = None
    if target_mean and price and price > 0:
        upside = (target_mean - price) / price * 100

    next_earn = _next_earnings_date(data.get("earnings_dates"))

    return {
        "revenues": revenues,
        "margins": margins,
        "gm_latest": gm_values[-1] if gm_values else None,
        "gm_trend": gm_trend,
        "om_latest": om_values[-1] if om_values else None,
        "om_trend": om_trend,
        "ocf_ttm": ocf,
        "fcf_ttm": fcf,
        "debt_to_equity": de_ratio,
        "current_ratio": current_ratio,
        "shares_change_1y": shares_change,
        "insider_stats": insider_stats,
        "analyst_rating": rating_text,
        "analyst_count": info.get("numberOfAnalystOpinions"),
        "target_mean": target_mean,
        "upside_pct": upside,
        "next_earnings": next_earn,
    }
