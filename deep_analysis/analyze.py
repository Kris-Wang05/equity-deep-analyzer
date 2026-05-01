"""
个股深度分析入口。

用法：
    python -m deep_analysis.analyze ONTO
    python -m deep_analysis.analyze ONTO LRCX TXN

输出：
    output/deep_analysis/reports/{TICKER}_report.md
"""

import os
import sys
import time
import traceback

# Windows 控制台默认 GBK，无法输出 emoji。强制 stdout/stderr 用 UTF-8。
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 把项目根目录加入 sys.path，使 `python deep_analysis/analyze.py X` 也能跑
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(THIS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from deep_analysis import classifier, fundamentals, moat, technicals, valuation
from deep_analysis.data_fetcher import fetch_all
from deep_analysis.report_generator import generate


REPORT_DIR = os.path.join(PROJECT_ROOT, "output", "deep_analysis", "reports")


HARD_RULES_SKIP_SUFFIXES = (".SH", ".SZ", ".HK")


def _should_skip(ticker, info):
    """硬规则：跳过 A 股 / 港股 / 微型股."""
    upper = ticker.upper()
    if any(upper.endswith(s) for s in HARD_RULES_SKIP_SUFFIXES):
        return f"{ticker}：跳过中国 / 香港股票（exchange 限制）"
    exchange = (info.get("exchange") or "").upper()
    if exchange in {"SHH", "SHZ", "HKG"}:
        return f"{ticker}：跳过 exchange={exchange}（中国 / 香港）"
    market_cap = info.get("marketCap") or 0
    if market_cap and market_cap < 5e8:
        return f"{ticker}：跳过微型股（市值 ${market_cap/1e6:.0f}M < $500M）"
    if not market_cap:
        return f"{ticker}：无 marketCap 数据，可能 ticker 无效"
    return None


def analyze_one(ticker):
    print(f"\n{'='*60}\n📊 分析 {ticker}\n{'='*60}")
    t0 = time.time()
    print(f"[1/7] 拉取 yfinance 数据...")
    data = fetch_all(ticker)
    info = data.get("info") or {}

    skip_reason = _should_skip(ticker, info)
    if skip_reason:
        print(f"  ⛔ {skip_reason}")
        return None

    print(f"  ✓ {ticker} | {info.get('shortName') or info.get('longName')} | "
          f"sector={info.get('sector')} | mcap=${(info.get('marketCap') or 0)/1e9:.2f}B")

    print(f"[2/7] 模块0：大势判断（拉取 sector ETF）...")
    market_res = technicals.assess_market(data)
    # 把大势写回 data，供 valuation / report_generator 调整阈值与封顶
    data["market_judgment"] = market_res.get("judgment", "中性")

    print(f"[3/7] 模块1：股票分类...")
    category = classifier.classify(data)
    print(f"  ✓ 分类：{category['label']} — {category['reason']}")

    print(f"[4/7] 模块2：护城河快检...")
    moat_res = moat.assess(data)

    print(f"[5/7] 模块3+4：估值诊断 + 原因归类（拉取同行对标）...")
    valuation_res = valuation.diagnose(data, category)
    print(f"  ✓ 估值结论：{valuation_res['verdict']}")

    print(f"[6/7] 模块5：基本面快检...")
    fundamentals_res = fundamentals.assess(data)

    print(f"[6.5/7] 模块6：技术面位置...")
    position_res = technicals.assess_position(data)

    print(f"[7/7] 生成 Markdown 报告...")
    md = generate(data, category, moat_res, valuation_res, fundamentals_res,
                  market_res, position_res)

    os.makedirs(REPORT_DIR, exist_ok=True)
    out_path = os.path.join(REPORT_DIR, f"{ticker.upper()}_report.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)
    elapsed = time.time() - t0
    print(f"  ✓ 报告已保存：{out_path}（耗时 {elapsed:.1f}s）")
    return out_path


def main():
    if len(sys.argv) < 2:
        print("用法：python -m deep_analysis.analyze TICKER [TICKER ...]")
        print("示例：python -m deep_analysis.analyze ONTO LRCX TXN")
        sys.exit(1)

    tickers = [t.upper() for t in sys.argv[1:]]
    print(f"待分析：{', '.join(tickers)}")
    results = []
    for t in tickers:
        try:
            path = analyze_one(t)
            results.append((t, path, None))
        except Exception as e:
            traceback.print_exc()
            results.append((t, None, str(e)))

    print(f"\n{'='*60}\n✅ 完成 {len([r for r in results if r[1]])}/{len(tickers)} 份报告\n{'='*60}")
    for t, path, err in results:
        if path:
            print(f"  ✓ {t}  →  {path}")
        else:
            print(f"  ✗ {t}  ({err or 'skip'})")


if __name__ == "__main__":
    main()
