# Stock Deep Analysis · 个股深度分析工具

> ⚠️ **仅供研究参考，不构成任何投资建议。作者不对任何使用本工具造成的损失负责。投资有风险，决策需谨慎。**
>
> *For educational and research purposes only. Not investment advice. Use at your own risk.*

---

## Why this exists

`yfinance` 数据有大量陷阱：币种不一致（ADR / LSE / 日股）、stock split 让流通股看似 +400% 实是 5:1 split、GAAP 一次性税收逆转让净利率方差爆炸误判周期股、insider Form 4 把 RSU vesting 当卖出信号、整合期 GAAP 毛利率系统性失真……

这个工具用一套 6 模块流程把这些噪音过滤后，生成结构化中文诊断报告，帮你快速判断**这只股票现在值不值得关注 / 是不是入场点**。

是冷静的相对估值机器，**不是择时机器**。择时还得靠你自己。

---

## ✨ 核心特色

### 6 模块诊断流程

| 模块 | 功能 |
|---|---|
| 🌊 大势 | 按 industry 自动选 sector ETF（SMH / IGV / IHI / ITA / XBI 等），逆风时收紧估值阈值 + 信号强度封顶 |
| 🏷️ 分类 | 7 类自动归属（投机 / 困境反转 / 周期 / 拐点反转 / 快速增长 / 稳定增长 / 未分类），每类用对应的估值工具 |
| 🏰 护城河 | 4 维度（转换成本 / 品牌定价权 / 规模 / 监管壁垒），趋势分析 |
| 💰 估值 | 按分类切换工具：PEG+P/S / EV/EBITDA / P/B+净现金 / Forward P/E + 历史百分位 + 同行折价/溢价 |
| ❓ 便宜原因 | A 起步 / B 暂时利空 / C 周期底部 / D 结构性问题 / E 假便宜 / ? 待手动调研 |
| 🔍 基本面 | 营收/利润率/现金流/负债/回购+稀释/CEO 单独 insider 信号/分析师/财报日 |
| 📍 位置 | 52 周高低 + 200 日均线 + 距高点 % |

### 已经踩过的坑（已修复）

- ✅ **币种统一**：LSE 用 GBp（便士）、ASX/ADR 财报用 TWD/GBP/JPY，全部标注 + USD 等价
- ✅ **Stock Split 检测**：流通股 +393% 时识别 5:1 split 而非误报"M&A 整合期"
- ✅ **GAAP 一次性事项过滤**：用 Operating Margin 标准差替代 Net Income，过滤 valuation allowance 逆转 / 减值噪音
- ✅ **CEO 单独信号**：拆分 CEO 行为 vs 其他高管 RSU vesting，避免"净卖 $7M"误读 CEO 信号
- ✅ **大势动态阈值**：板块逆风时"明显便宜"门槛收紧 + 信号强度 ≤3⭐
- ✅ **拐点反转识别**：TTM 平淡但 forward EPS 隐含增速 +100%+ 单条件触发
- ✅ **earningsGrowth 大数清洗**：>500% 视为基期效应噪音直接忽略
- ✅ **行业自适应估值**：utility / IPP / Consumer Defensive 用 EV/EBITDA 替代失真的 P/B
- ✅ **同行 ticker 覆盖**：12+ 票特殊映射（ASX → AMKR、RR.L → GE/SAF、AMSC → GEV/VRT 等）
- ✅ **PEG fallback**：yfinance 不给 trailingPegRatio 时，工具自算 forward_pe / 增速

---

## 🚀 快速开始

### 安装

```bash
git clone https://github.com/<your-name>/stock-deep-analysis.git
cd stock-deep-analysis
pip install -r requirements.txt
```

### 单只票分析

```bash
python -m deep_analysis.analyze AAPL
```

报告输出到 `output/deep_analysis/reports/AAPL_report.md`

### 多只票批量

```bash
python -m deep_analysis.analyze AAPL MSFT NVDA TSLA
```

### 支持的市场

| 市场 | Ticker 格式 | 已测试 |
|---|---|---|
| US (NASDAQ/NYSE) | `AAPL` | ✅ |
| LSE (伦敦) | `RR.L` | ✅ |
| TYO (东京) | `7203.T` | ⚠️ 部分支持 |
| ADR | `ASX` / `RYCEY` | ✅ |
| HKEX / SH / SZ | — | ❌ 跳过 |

---

## 📖 报告样例

看 [examples/AAPL_sample_report.md](examples/AAPL_sample_report.md) 了解输出形式。

---

## 🏗️ 架构

```
deep_analysis/
├── __init__.py
├── analyze.py            # 入口
├── _common.py            # 共享工具
├── data_fetcher.py       # yfinance 抓取 + 币种 + split + M&A 检测 + forward signals
├── classifier.py         # 模块1：股票分类
├── moat.py               # 模块2：护城河快检
├── valuation.py          # 模块3+4：估值诊断 + cheap_reason 归类
├── fundamentals.py       # 模块5：基本面 + insider 拆分
├── technicals.py         # 模块0+6：大势 + 位置
├── peers.py              # 同行 + ETF 映射 + ticker override
└── report_generator.py   # Markdown 报告拼装
```

---

## 🚨 已知限制

工具不完美，以下 case 仍需手动判断：

1. **半年报制度公司**（英欧大部分）：quarterly_income_stmt 缺失 → 易触发"未分类"
2. **ADR P/S 失真**：yfinance 用 USD 市值除本币营收，比例可能极小（如 ASX 的 P/S 0.10 假数据）
3. **管理层 guide 历史**：yfinance 拿不到 8-K 数据，工具只能被动文字提醒，需手动核查
4. **Insider Form 4 缺失**：ADR / 海外公司通常无 Form 4，不代表"管理层不动"
5. **银行业 OCF/FCF/D/E**：用通用逻辑读，未做行业特殊处理
6. **历史 P/E turnaround 期**：扭亏期 EPS 巨亏会被 Winsorize 过滤掉，样本不足

详见每只票报告里的"工具盲点"提示。

---

## 🤝 贡献

PR welcome but slow review。如果发现新的工具盲点 / 误判 case，欢迎提 issue 附**具体股票代码 + 报告里哪部分判断错了 + 你认为的真实情况**。

---

## 📜 License

MIT — 见 [LICENSE](LICENSE)

---

## ⚠️ 免责声明（再次强调）

本工具仅用于个人研究和教育目的，**不构成任何形式的投资建议、推荐或要约**。

- 工具的判断基于 `yfinance` 公开数据，可能存在数据延迟、错误、缺失
- 所有分析结论是**算法输出**，不代表作者个人投资观点
- 报告里的"BUY / WATCH / AVOID" 仅是工具的相对估值信号，**不是买卖指令**
- 投资决策需要结合你自己的财务状况、风险承受能力、独立尽职调查
- 作者不对任何因使用本工具产生的盈亏负责

如果你不能接受以上免责，请不要使用本工具。
