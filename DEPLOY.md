# 部署指南

按下面步骤走一遍，10 分钟搞定。**关键：所有 unzip 和 git 操作都用 terminal**，不要用 Mac Finder 拖拽（会丢 `.github` 隐藏文件夹）。

---

## ⚠️ Step 0：安全 — 先做这件事

**你刚才在 chat 里发的那个 GitHub PAT 现在在对话历史里。**
**部署完成后立刻去 https://github.com/settings/tokens 把它 revoke 掉。**

---

## Step 1：在 GitHub 网页创建一个新的空 repo（30 秒）

1. 打开 https://github.com/new
2. Repository name：**`market-sentiment-scorecard`**（必须叫这个名字，因为 GitHub Pages URL 是基于 repo name 生成的，skill 里硬编码了 `https://yizez529.github.io/market-sentiment-scorecard/`）
3. Visibility：**Private**（推荐）
4. **不要勾选** "Add a README file" / "Add .gitignore" / "Choose a license"（保持完全空 repo）
5. 点 "Create repository"

如果你的 GitHub 用户名不是 `yizez529`，先告诉我，我会更新 skill 文件里的 URL。

---

## Step 2：本地用 terminal 解压并 push（5 分钟）

**⚠️ 关键：用 terminal 的 `unzip` 命令，不要双击 zip 文件让 Mac Finder 解压**——Finder 会隐藏 `.github` 这种 dot 开头的文件夹。

把下面整段贴进 terminal，**注意把 `<你的GitHub用户名>` 替换成你自己的用户名**：

```bash
# 1. 进入下载目录
cd ~/Downloads

# 2. 用 terminal unzip（保留隐藏文件夹）
unzip -o market-sentiment-scorecard.zip

# 3. 进入项目目录
cd market-sentiment-scorecard

# 4. 验证 .github 文件夹存在（必须看到）
ls -la
# 应该看到 .github 这一行：
#   drwxr-xr-x  3 user  staff   96 ... .github
# 如果没看到 .github 行，说明 zip 没解压完全，停下来告诉我

# 5. 验证 workflow 文件存在
ls -la .github/workflows/
# 应该看到 daily_sentiment.yml

# 6. 配置 git（如果之前没配过）
git config --global user.email "你的邮箱"
git config --global user.name "你的名字"

# 7. 初始化并 commit
git init
git add .
git commit -m "initial deploy: market sentiment scorecard"

# 8. 设置远程并 push
git branch -M main
git remote add origin https://github.com/<你的GitHub用户名>/market-sentiment-scorecard.git
git push -u origin main
```

第 8 步 push 时会让你输入 username 和 password。

- **Username**: 你的 GitHub 用户名
- **Password**: 粘贴你那个 GitHub PAT（**不是 GitHub 网页登录密码**）

push 成功后会看到类似 `Branch 'main' set up to track 'origin/main'`。

---

## Step 3：添加 Secrets（GitHub 网页操作）

打开 repo → **Settings** → 左侧 **Secrets and variables** → **Actions** → 右上 **New repository secret**

添加 **3 个** secret：

| Name | Value | 在哪里拿 |
|------|-------|---------|
| `ANTHROPIC_API_KEY` | `sk-ant-xxxx...` | https://console.anthropic.com/settings/keys |
| `FEISHU_WEBHOOK` | `https://open.feishu.cn/open-apis/bot/v2/hook/23517c05-1423-4f82-a381-6238f86aec3a` | （已有） |
| `FRED_API_KEY` | `xxxxxxxx` | 免费注册 https://fred.stlouisfed.org/docs/api/api_key.html （5 分钟） |

### ⚠️ Anthropic API 重要提醒（血泪教训）

- **Anthropic API credits ≠ Claude.ai Pro 订阅**，是两个独立的钱包
- 这个 skill 用 Opus 4.7，每次调用约 $0.05-0.06
- 月跑 26 次（一到六）≈ **$1.5-2/月**
- 去 https://console.anthropic.com/settings/billing 充至少 **$5**（够跑 80+ 次）
- **创建 API key 和充值要在同一个 workspace**——console 左上角下拉框，建议都用 `Default` workspace

---

## Step 4：开启 GitHub Pages

repo → **Settings** → 左侧 **Pages**

- Build and deployment → Source: **GitHub Actions**（**不是** "Deploy from a branch"）
- 不需要点保存，选完就生效

第一次跑完后，dashboard 会出现在：
**`https://<你的GitHub用户名>.github.io/market-sentiment-scorecard/`**

---

## Step 5：第一次手动跑 smoke-test（验证部署）

repo → **Actions** 标签 → 左侧选 **"Daily Market Sentiment Scorecard"** → 右上 **"Run workflow"**

第一次先选 **`smoke-test-only`** 模式，点绿色 Run 按钮。

**预期结果（30 秒内）：**
- 飞书群收到一条文本消息：`[smoke-test] market-sentiment-scorecard deployment OK`
- GitHub Actions 页面 smoke-test job ✅ 绿色
- scan 和 deploy-pages job 显示 skipped（因为这次只跑 smoke-test）

如果 smoke-test 失败：日志最后几行会**明确告诉你**哪个 secret 没设 / webhook 错误等。把日志贴回来给我。

---

## Step 6：smoke-test 通过后跑完整版

回到 Actions → "Run workflow" → 这次选 **`full`** → Run

**预期结果（约 2-3 分钟内）：**

1. **飞书** 收到完整的市场情绪卡片：
   - 综合评分 + 状态徽章
   - 核心驱动 (3-5 条)
   - 七维度评分（双列 emoji 图标）
   - 投资建议（仓位/对冲/不要做/触发）
   - Verdict
   - 跳转 dashboard 的按钮
2. **GitHub Pages** 上线，点链接看到完整 dashboard：
   - Hero 区大数字 + 状态条
   - 七维度详细卡片（含每个底层指标的值）
   - 投资建议表格
   - **完整的指标指南**（永久附在 dashboard 底部）
   - 历史趋势 mini-chart（首次只有一个点）
3. repo 多了一次 commit：`chore(daily): update scorecard YYYY-MM-DD`
4. `data/history.json` 多了一条记录

---

## Step 7：以后就自动跑了

cron `0 2 * * 1-6` = UTC 02:00 周一到周六 = **北京时间 10:00 周一到周六**

完全无人值守。你的电脑可以关机。

---

## 常见问题

### Q1: 飞书没收到消息？

1. 看 GitHub Actions 日志最后一段，找 `Feishu attempt 1: status=...`
2. 如果 `code != 0`：webhook 配错了
3. 如果 `code == 19021`：飞书机器人开了关键词/签名校验，但 webhook 测试不带这些。去飞书机器人配置里关掉关键词验证

### Q2: Claude 分析失败（评分能跑出来但 headline 是 "Claude 分析失败"）？

GitHub Actions 日志里搜 `[Claude] Raw output length`：

- 没有这行 → API 调用失败。看错误信息是 `credit balance too low` (充钱) 还是 timeout (重跑)
- 有这行但后面有 `All JSON parsing layers failed` → JSON 输出格式问题，把 raw output 那段贴给我

### Q3: HY OAS / IG OAS 显示 N/A？

`FRED_API_KEY` 没设或拿错了。免费注册：https://fred.stlouisfed.org/docs/api/api_key.html（填邮箱即可）

### Q4: AAII / NAAIM 显示 N/A？

这两个是周更（周三/周四发布），平时爬虫跑出来可能拿不到当周最新值，会用上周的。如果连续多周拿不到，说明网页结构变了，告诉我我修。

### Q5: 想改运行时间？

编辑 `.github/workflows/daily_sentiment.yml` 第 6 行：

```yaml
- cron: '0 2 * * 1-6'
```

UTC 时间。例如：
- 北京 8:00 = UTC 0:00 → `0 0 * * 1-6`
- 北京 9:00 = UTC 1:00 → `0 1 * * 1-6`
- 包含周日 → `0 2 * * *`

修完 push 一下就生效。

---

## 维护

正常情况下零维护。如果某天爬虫源失效（如 AAII 改了页面）：

1. 飞书会推送降级告警，但其他 6 个维度照常工作
2. 把告警内容贴给我，让我修对应的 fetch 函数

数据自动累积在 `data/history.json`。1 个月后就有趋势图，1 年后可以做评分时序回测。

---

## 文件清单

部署完后，repo 应该有这些文件：

```
market-sentiment-scorecard/
├── .github/workflows/daily_sentiment.yml    # GitHub Actions 主 workflow
├── scripts/
│   ├── fetch_indicators.py    # 抓取所有指标
│   ├── calculate_score.py     # 7 维度评分计算
│   ├── claude_analysis.py     # 调用 Opus 4.7
│   ├── generate_html.py       # 生成 dashboard
│   ├── feishu_card.py         # 飞书推送
│   └── run_daily.py           # 主流程
├── docs/
│   ├── index.html             # 占位（首次运行后被覆盖）
│   └── archive/               # 历史快照
├── data/
│   └── history.json           # 评分历史记录
├── requirements.txt
├── README.md
├── DEPLOY.md
├── SKILL_market-sentiment.md  # skill 文件（可选，本地存档）
└── .gitignore
```
