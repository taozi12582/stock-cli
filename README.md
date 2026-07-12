# stock-cli

A股股票数据CLI工具，从MySQL获取**行情数据**（stock_info表，21列）和**基本面数据**（fundamental_info表，3维度），生成可供LLM/子代理分析的压缩上下文。

## 数据来源

| 表 | 列数 | 内容 | 覆盖 |
|---|---|---|---|
| `stock_info` | 21 | OHLCV + 筹码分布(cost_5/15/50/85/95pct) + 获利比例 + 历史高低 + 集中度 | 5,936只股票 × 601天 = 3.24M行 |
| `fundamental_info` | 8 | 质押状态 + 盈余管理级别(修正Jones模型) + 四大审计 | 5,530只股票 × 601天 = 3.33M行 |

## 安装

```bash
cd stock-cli
pip install -r requirements.txt
pip install -e .
```

或直接用 `python3 -m stock_cli` 运行。

## 命令

### context — 完整分析上下文（基本面+行情+prompt）

```bash
# 单只股票，默认120天摘要模式
python3 -m stock_cli context 000001.SZ

# 完整120天表格（所有21列）
python3 -m stock_cli context 000001.SZ --mode full

# 多只股票，写入文件
python3 -m stock_cli context 000001.SZ 600519.SH 000858.SZ --output analysis.txt

# 不附加分析prompt（只要数据）
python3 -m stock_cli context 000001.SZ --no-prompt
```

### fundamental — 只看基本面

```bash
python3 -m stock_cli fundamental 000001.SZ
```

### price — 只看行情

```bash
# 摘要模式（区间统计 + 周线 + 最近10天明细 + 筹码分布）
python3 -m stock_cli price 000001.SZ

# 完整120天表格
python3 -m stock_cli price 000001.SZ --mode full
```

### risk — 快速风险检查

```bash
# 文本格式
python3 -m stock_cli risk 000001.SZ 600519.SH 000858.SZ

# JSON格式（方便程序解析）
python3 -m stock_cli risk 000001.SZ --format json
```

### screen — 按基本面风险筛选股票

```bash
# 排除红色警报股（高比例质押/刚解押/高盈余管理+非四大）
python3 -m stock_cli screen --exclude-red --limit 100

# 只显示绿色安全股（未质押+低盈余管理+四大审计）
python3 -m stock_cli screen --green-only --limit 50
```

## 选股流程

```
1. 技术面筛选（auto-stock-selector等工具）
   → 候选股列表（如10只）
        ↓
2. 基本面排雷
   python3 -m stock_cli risk 000001.SZ 600519.SH ...
   → 排除红色警报股
        ↓
3. 生成分析上下文
   python3 -m stock_cli context 000001.SZ --mode full
   → 基本面前缀 + 120天行情 + 分析prompt
        ↓
4. 喂给子代理/LLM分析
   → 趋势判断 + 操作建议
```

## 三个基本面维度

| 维度 | 来源论文 | 预测什么 |
|---|---|---|
| 质押状态 | 谢德仁 2016《管理世界》 | 质押期维稳→解押后暴跌 |
| 盈余管理 | 潘越 2011 + 辛清泉 2014 | 不透明度↑→暴跌风险↑ |
| 四大审计 | 辛清泉 2014 | 非四大→信息质量弱→波动性高 |

这三个维度是**排雷指标**（预测暴跌），不是选牛指标（预测上涨）。正确用法：技术面选方向，基本面确保不踩雷。

## 配置

MySQL连接配置默认内置，也可通过环境变量覆盖：

```bash
export MYSQL_HOST=your_host
export MYSQL_USER=your_user
export MYSQL_PASSWORD=your_password
export MYSQL_DATABASE=your_db
```

## 行情数据字段（stock_info表21列）

| 字段 | 含义 |
|---|---|
| open / high / low / close | 开高低收 |
| pre_close / change / pct_chg | 前收 / 涨跌额 / 涨跌幅 |
| vol / amount | 成交量 / 成交额 |
| cost_5pct / cost_15pct / cost_50pct / cost_85pct / cost_95pct | 筹码分布5/15/50/85/95分位 |
| weight_avg | 加权平均价 |
| winner_rate | 获利比例 |
| his_low / his_high | 历史最低 / 最高 |
| cost_concentration_90pct | 90%筹码集中度 |
