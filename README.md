# 美股市场情绪评分 (Market Sentiment Scorecard)

每天北京时间早上 10:00（周一到周六）自动跑一次，把美股 7 维度加权综合评分推送到飞书，并发布到 GitHub Pages。

## 七维度评分框架

| # | 维度 | 权重 | 核心指标 |
|---|------|------|---------|
| 1 | 波动率 | 18% | VIX, VXN, MOVE |
| 2 | 情绪调查 | 14% | F&G, AAII, NAAIM |
| 3 | SPX 广度 | 12% | %>200MA, %>50MA, RSP/SPY |
| 4 | 信用利差 | 14% | HY OAS, IG OAS |
| 5 | NDX 专项 | 12% | NDX RSI, %>200MA, 连涨天数 |
| 6 | CTA / 量化 | 14% | CTA 仓位代理, Put/Call |
| 7 | 价格动量 | 16% | SPX RSI, 连涨天数, MA偏离 |

## 评分区间

| 分数 | 状态 | 动作 |
|------|------|------|
| 0-15 | 极度超卖 | 全力建仓 |
| 15-30 | 严重超卖 | 大幅加仓 |
| 30-45 | 偏超卖 | 加仓 |
| 45-55 | 中性 | 持仓不动 |
| 55-70 | 偏超买 | 停止加仓 |
| 70-85 | 严重超买 | 部分减仓 (10-25%) |
| 85-100 | 极度超买 | 大幅减仓 (30-50%) |

## 架构

```
GitHub Actions (周一到周六 北京 10:00)
    │
    ├─ smoke-test job：检查 imports + 环境变量 + 飞书 webhook
    │
    ├─ scan job (依赖 smoke-test 通过)
    │   ├─ fetch_indicators.py   抓取所有指标（多源 fallback）
    │   ├─ calculate_score.py    计算 7 维度子评分 + 加权综合
    │   ├─ claude_analysis.py    调用 Opus 4.7 生成中文分析（三重 JSON 容错）
    │   ├─ generate_html.py      生成 dashboard HTML（含完整指标指南）
    │   └─ feishu_card.py        推送飞书互动卡片（含跳转链接）
    │
    └─ deploy-pages job：发布 docs/ 到 GitHub Pages
```

## 部署

见 [DEPLOY.md](./DEPLOY.md)

## 运行成本

- **GitHub Actions**: 每月 ~50 分钟，免费额度（2000 分钟）内
- **Claude API (Opus 4.7)**: 每次约 $0.05-0.06（含 prompt caching），月跑 26 次约 $1.5-2
- **数据源**: FRED / Yahoo Finance / CNN F&G / AAII / NAAIM 全部免费

**月成本 ≈ $1.5 美元，年成本 ≈ $20 美元**

## 数据源

| 指标 | 源 | 频率 |
|------|-----|------|
| VIX, VXN, SPX, NDX | yfinance | 实时 |
| HY OAS, IG OAS | FRED API | T+1 |
| Fear & Greed | CNN production endpoint | 实时（盘中） |
| AAII Sentiment | aaii.com 爬虫 | 周更（周四） |
| NAAIM Exposure | naaim.org 爬虫 | 周更（周三） |
| Put/Call Ratio | 多源 fallback | 日更 |
| CTA 仓位 | 公开 trend 逻辑代理 | 实时计算 |

## 维护

- 每天的运行结果会自动 commit 到 `data/history.json`
- 历史快照在 `docs/archive/YYYY-MM-DD.html`
- 任何步骤失败都会推送降级告警到飞书
- 任何 LLM 调用失败都会 dump 完整原始输出到 GitHub Actions 日志

## License

私有，仅供 Aaron 使用。
