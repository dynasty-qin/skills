# 个人基金组合投研 Skill

这是一个基于 **OpenClaw + Markdown + Python** 的个人基金组合投研 Skill。它用于辅助你进行基金持仓监控、每日估值、仓位再平衡、候选基金池评分、基金观察/淘汰建议和操作复盘。

> 重要边界：本 Skill 不自动交易，不构成投资建议，不保证收益。所有估值均为参考估算，不等于基金公司正式净值。

## 适合解决的问题

- 查看当前基金组合结构、总投入、预估市值、盈亏贡献。
- 每个交易日下午生成基金组合日报。
- 每周复盘仓位是否偏离目标配置。
- 每月在同类别基金池中进行基金质量评分，筛选更优候选。
- 对当前持有基金执行“继续持有 / 进入观察 / 建议替换候选”的规则判断。
- 防止因短期涨跌、近期排名或单一新闻做出冲动操作。

## 快速开始

### 1. 安装依赖

```bash
cd fund-investment-skill
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> `akshare` 和 `efinance` 是可选数据源。如果安装失败，Skill 仍可通过手动行情快照运行。

### 2. 配置个人信息（两种方式）

**方式 A：使用 Obsidian（推荐，数据不进 Git）**

1. 在你的 Obsidian vault 中创建 `基金投研/` 文件夹
2. 将 `config/obsidian_path.example.yaml` 复制为 `config/obsidian_path.yaml`，填入 vault 路径
3. 将 `config/*.example.yaml` 复制为对应的 `*.yaml`，放入 Obsidian 的 `基金投研/config/` 并填入真实数据
4. 脚本会自动读取 Obsidian 中的配置，报告也输出到 Obsidian

**方式 B：使用 Skill 本地配置（不需要 Obsidian）**

1. 将 `config/*.example.yaml` 复制为对应的 `*.yaml`（去掉 `.example`），填入真实数据
2. 不创建 `config/obsidian_path.yaml`（或设为空路径）
3. 脚本使用本地配置，报告输出到 skill 本地 `reports/`

> ⚠️ 方式 B 的配置文件已在 `.gitignore` 中排除，不会上传到 Git。但如果你需要 fork 或分享，请确保不要手动提交这些文件。

### 3. 生成日报

```bash
python scripts/run_fund_skill.py --mode daily
```

如果没有安装数据源或获取失败，它会使用 `config/market_snapshot.yaml` 中的手动行情快照生成报告，并降低数据质量等级。

### 4. 生成周报/月报/季报

```bash
python scripts/run_fund_skill.py --mode weekly
python scripts/run_fund_skill.py --mode monthly
python scripts/run_fund_skill.py --mode quarterly
```

报告会自动输出到正确位置（Obsidian 或本地 `reports/`）。

## 推荐 OpenClaw 定时任务

### 交易日日报

```cron
30 14 * * 1-5
```

执行命令：

```bash
python scripts/run_fund_skill.py --mode daily
```

### 每周复盘

```cron
0 20 * * 5
```

执行命令：

```bash
python scripts/run_fund_skill.py --mode weekly
```

### 每月基金优选

建议每月最后一个交易日晚上执行。OpenClaw 可以先判断当日是否接近月末：

```bash
python scripts/run_fund_skill.py --mode monthly
```

## 核心文件说明

| 文件 | 作用 | Git |
|---|---|---|
| `SKILL.md` | 给 OpenClaw 的主指令文件 | ✅ 公开 |
| `config/*.example.yaml` | 配置模板（示例数据） | ✅ 公开 |
| `config/obsidian_path.example.yaml` | Obsidian vault 路径模板 | ✅ 公开 |
| `config/obsidian_path.yaml` | 你的 Obsidian vault 路径 | ❌ gitignore |
| `config/*.yaml`（非 example） | 你的真实配置 | ❌ gitignore |
| `data/fund_metrics.template.csv` | 基金指标模板 | ✅ 公开 |
| `data/operation_log.csv` | 操作日志 | ❌ gitignore |
| `rules/*.md` | 操作规则、评分规则、模板 | ✅ 公开 |
| `scripts/run_fund_skill.py` | 主运行入口 | ✅ 公开 |
| `scripts/fund_skill_core.py` | 计算、评分、报告核心逻辑 | ✅ 公开 |
| `scripts/fetch_fund_data.py` | 可选数据抓取脚本 | ✅ 公开 |
| `reports/` | 报告输出目录 | ❌ gitignore |

## 设计原则

1. 先看资产配置，再看基金选择。
2. 同类基金之间比较，不跨类别比较。
3. 近期表现只能作为观察指标，不能作为换基唯一依据。
4. 指数基金看跟踪、规模和费率；主动基金看基金经理、风格和回撤；债基看稳健性和信用风险。
5. 每日只判断是否触发操作规则；每月才做基金优选；季度才考虑调整策略。
6. 数据缺失时，不输出强买卖建议。

## 免责声明

本 Skill 仅用于个人学习、记录、分析和投资纪律辅助。它不是基金销售工具，也不构成任何投资建议。基金有风险，投资需谨慎。你应自行判断并承担投资决策结果。
