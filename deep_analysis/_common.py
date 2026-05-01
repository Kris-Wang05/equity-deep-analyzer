"""
deep_analysis 内部共用工具函数。
避免在 classifier / valuation / fundamentals 多处重复实现。
"""


def quarterly_revenue_yoy_growths(quarterly_income, n=4):
    """
    返回最近 n 个季度的 YoY 营收增速列表 (%)，升序时间。
    需要至少 n+4 季度数据；不够时回退到 QoQ（带季节性噪音，调用方需感知）。
    全部失败 → None。

    用途：
      - classifier.py 检测拐点 / 季度营收减速
      - valuation.py 模块4 cheap_reason 归类
    """
    if quarterly_income is None or quarterly_income.empty:
        return None
    if "Total Revenue" not in quarterly_income.index:
        return None
    rev = quarterly_income.loc["Total Revenue"].dropna().astype(float).sort_index(ascending=True)
    # 数据足够算 YoY
    if len(rev) >= n + 4:
        growths = []
        for i in range(len(rev) - n, len(rev)):
            prev = rev.iloc[i - 4]
            if prev > 0:
                growths.append((rev.iloc[i] - prev) / prev * 100)
        return growths or None
    # QoQ 回退
    if len(rev) >= n + 1:
        growths = []
        for i in range(len(rev) - n, len(rev)):
            prev = rev.iloc[i - 1]
            if prev > 0:
                growths.append((rev.iloc[i] - prev) / prev * 100)
        return growths or None
    return None
