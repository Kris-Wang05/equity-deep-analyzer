# CHANGELOG

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-05-01

Initial public release.

### Added — 6 模块诊断流程

- 模块 0：大势判断（按 industry 自动选 sector ETF，逆风时收紧估值阈值 + 信号强度封顶）
- 模块 1：分类系统（投机 / 困境反转 / 周期 / 拐点反转 / 快速增长 / 稳定增长 / 未分类）
- 模块 2：护城河 4 维度评估（转换成本 / 品牌定价权 / 规模 / 监管壁垒）
- 模块 3：估值（按分类切换工具：PEG+P/S / EV/EBITDA / P/B+净现金 / Forward P/E）
- 模块 4：cheap_reason 归类（A/B/C/D/E/?）
- 模块 5：基本面快检（含 CEO 单独 insider 信号）
- 模块 6：技术面位置（52 周 + 200 日均线）

### Added — 边缘 case 处理

- **币种统一**：识别 GBp / TWD / JPY / GBP 等本币，标注 + USD 等价
- **Stock Split 检测**：流通股 +N00% 自动识别 N:1 split，避免误报"M&A 整合期"
- **M&A 整合期识别**：流通股 +30% YoY + 营收 +50% YoY 触发警告
- **GAAP 一次性事项过滤**：用 Operating Margin 而非 Net Income 判周期股
- **CEO 单独 insider 信号**：拆分 CEO 行为 vs 其他高管 RSU vesting 噪音
- **earningsGrowth 大数清洗**：>500% 视为基期效应噪音
- **拐点反转触发**：单一极强信号（EPS 隐含增速 >100%）即可触发
- **行业自适应估值**：utility / IPP / Consumer Defensive 用 EV/EBITDA 替代 P/B
- **TICKER_PEERS_OVERRIDE**：12+ 票特殊同行映射
- **PEG fallback**：yfinance 不给 trailingPegRatio 时自算
- **大势动态阈值**：顺风/中性/逆风时调整 verdict 阈值 + 信号封顶

### Added — 报告质量改进

- 财报前 14 天文字提醒（不扣分，仅提示）
- 管理层 guide 历史被动提示（精准触发：非顺风 + 距财报 ≤60 天）
- 同行折价/溢价显式表
- 历史 P/E 百分位（月度采样 + Winsorize 离群值）
- 多币种 + ADR 自动识别 + USD 等价显示

### Known Limitations

- 半年报制度公司（英欧大部分）quarterly 数据缺失，可能落到"未分类"
- ADR 公司 P/S 失真（USD 市值 / 本币营收，yfinance 上游 bug）
- 管理层 guide 历史无法自动检测（yfinance 拿不到 8-K）
- ADR / 海外公司通常无 Form 4 数据
- 银行业 OCF/FCF/D/E 用通用逻辑读，未做行业特殊处理
- 历史 P/E 在 turnaround 期（2020-2022 年大额亏损）样本不足

详见 README.md 的"已知限制"章节。
