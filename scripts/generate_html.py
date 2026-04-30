"""
generate_html.py
生成每日 HTML dashboard，发布到 GitHub Pages。
包含：今日 scorecard + 指标指南 + 历史趋势链接。
"""
import json
import os
from datetime import datetime
from typing import Dict, Any


INDICATOR_GUIDE_HTML = """
<section class="guide">
<h2>📚 指标指南</h2>
<p class="guide-intro">本评分系统由 <strong>7 个维度</strong>加权而成（共 100% 权重）。每个维度由多个底层指标组成。综合评分 0-100：<strong>0 = 极度超卖（恐慌底）</strong>，<strong>100 = 极度超买（顶部）</strong>。</p>

<div class="guide-grid">

<div class="guide-card">
<h3>1. 波动率 <span class="weight-badge">18%</span></h3>
<p class="dim-desc">市场恐慌的最直接测量。期权定价反映 30 天后市场预期波动。</p>
<dl>
<dt>VIX</dt><dd>S&amp;P 500 隐含波动率。&lt;15 极度安逸，&gt;30 恐慌，&gt;40 严重恐慌（抄底窗口）。过去 5 年峰值：2020/3 = 82.7，2025/4 = 60.1。</dd>
<dt>VXN</dt><dd>Nasdaq 100 隐含波动率，比 VIX 高 3-5 点。捕捉 Tech 股权专门的风险溢价。</dd>
<dt>MOVE</dt><dd>美债隐含波动率。利率市场的恐慌指标，对股市超卖底部有 leading 作用。</dd>
</dl>
</div>

<div class="guide-card">
<h3>2. 情绪调查 <span class="weight-badge">14%</span></h3>
<p class="dim-desc">散户和机构的"主观调查"读数，是反向指标——越极端越可靠。</p>
<dl>
<dt>CNN F&amp;G Index</dt><dd>0-100 综合恐贪指数。&lt;20 极度恐慌（历史可靠抄底信号），&gt;75 极度贪婪。单数字读数（&lt;10）一年最多 1-2 次，是 high-conviction 信号。</dd>
<dt>AAII Bull-Bear Spread</dt><dd>散户调查（每周四发布）。Spread = 牛 % − 熊 %。历史均值 +6.5%。&lt;-30% 是绝佳逆向信号。</dd>
<dt>NAAIM Exposure</dt><dd>机构投资经理仓位调查（每周三发布）。0-200 范围。&lt;30 = 机构防御，&gt;90 = 满仓。</dd>
</dl>
</div>

<div class="guide-card">
<h3>3. SPX 广度 <span class="weight-badge">12%</span></h3>
<p class="dim-desc">市场参与度。指数涨跌不能反映"多少股票真在涨"，广度才能。</p>
<dl>
<dt>SPX vs 200MA</dt><dd>S&amp;P 500 距离 200 日均线的偏离百分比。+5% 以上偏热，−5% 以下偏冷。极端 +10% / −10%。</dd>
<dt>SPX vs 50MA</dt><dd>短期动能。比 200MA 更敏感，作为 confirmation。</dd>
<dt>RSP/SPY 比值</dt><dd>等权指数 vs 市值加权。下降 = 大盘股带涨，广度差；上升 = 普涨健康。</dd>
</dl>
</div>

<div class="guide-card">
<h3>4. 信用利差 <span class="weight-badge">14%</span></h3>
<p class="dim-desc">"聪明钱"信号——信用市场比股票更早反应真实经济风险。</p>
<dl>
<dt>HY OAS</dt><dd>高收益债（垃圾债）相对国债的利差。历史均值 350-500bps。&lt;300bps 极致紧（顶部信号），&gt;700bps 严重恐慌（抄底信号）。</dd>
<dt>IG OAS</dt><dd>投资级债券利差。历史均值 100-130bps。&gt;180bps 警戒。</dd>
<dt>关键 divergence</dt><dd>股票暴跌但 HY OAS 不动 = 过度反应（如 2025/4、2026/3），可买。</dd>
</dl>
</div>

<div class="guide-card">
<h3>5. NDX 专项 <span class="weight-badge">12%</span></h3>
<p class="dim-desc">纳指比 SPX 更敏感，是风险偏好的高频指标。AI 行情的主战场。</p>
<dl>
<dt>NDX vs 200MA</dt><dd>纳指距 200MA 偏离。比 SPX 容易触及极端（±12% 都常见）。</dd>
<dt>NDX RSI14</dt><dd>14 日相对强弱指数。&lt;25 极度超卖，&gt;80 极度超买。</dd>
<dt>NDX 连涨/连跌天数</dt><dd>+10 天以上连涨是过度热度信号（2026/4 创了 1992 年以来 13 天纪录，BofA 称 "upside crash"）。</dd>
<dt>QQQ vs SPY 动量</dt><dd>风险偏好温度计。QQQ 显著跑赢 = 风险偏好极高。</dd>
</dl>
</div>

<div class="guide-card">
<h3>6. CTA / 量化 <span class="weight-badge">14%</span></h3>
<p class="dim-desc">机械化系统流。CTA 穿越 trigger level 必然行动，与基本面无关——是底部和顶部的"加速器"。</p>
<dl>
<dt>CTA 仓位百分位（代理）</dt><dd>基于 SPX 相对 50/100/200MA 位置 + 实际波动率估算。&gt;85 百分位 = 机械下行风险高，&lt;20 百分位 = 反向买入信号。<em>真实 GS/UBS 数据闭源，本系统用公开 trend 逻辑做代理。</em></dd>
<dt>Put/Call Ratio</dt><dd>21 日均值。&lt;0.7 极度贪婪 call buying（顶部），&gt;1.2 极度恐慌 put buying（底部）。</dd>
</dl>
</div>

<div class="guide-card">
<h3>7. 价格动量 <span class="weight-badge">16%</span></h3>
<p class="dim-desc">最直接的"过热/过冷"测量，但易反转，给中等权重。</p>
<dl>
<dt>SPX RSI14</dt><dd>S&amp;P 500 14 日 RSI。&lt;30 超卖，&gt;70 超买。极端 &lt;25 / &gt;75。</dd>
<dt>SPX 连涨/连跌天数</dt><dd>方向性动能。+8 天以上 / −7 天以上是 stretched 信号。</dd>
<dt>SPX 距 200MA 偏离</dt><dd>趋势 vs 均值回归张力。</dd>
<dt>30 日实际波动率</dt><dd>价格本身的实际变动幅度。配合 IV 看 risk premium。</dd>
</dl>
</div>

</div>

<h2>🎯 评分区间含义</h2>
<table class="zone-table">
<thead><tr><th>分数</th><th>状态</th><th>历史对应</th><th>建议动作</th></tr></thead>
<tbody>
<tr class="zone-extreme-os"><td>0-15</td><td>极度超卖 / 恐慌底</td><td>2020/3, 2008/10</td><td><strong>全力建仓</strong>，杠杆/期权抄底</td></tr>
<tr class="zone-severe-os"><td>15-30</td><td>严重超卖</td><td>2022/10, 2025/4, 2024/8</td><td><strong>大幅加仓</strong>，主动买入</td></tr>
<tr class="zone-mod-os"><td>30-45</td><td>偏超卖</td><td>2026/3, 2023/3, 2023/10</td><td><strong>加仓</strong>，逢低布局</td></tr>
<tr class="zone-neutral"><td>45-55</td><td>中性</td><td>大部分时间</td><td><strong>持仓不动</strong></td></tr>
<tr class="zone-mod-ob"><td>55-70</td><td>偏超买</td><td>大部分上涨期</td><td><strong>正常持仓</strong>，停止加仓</td></tr>
<tr class="zone-severe-ob"><td>70-85</td><td>严重超买</td><td>2026/4, 2024 上半年</td><td><strong>部分减仓 (10-25%)</strong>，对冲</td></tr>
<tr class="zone-extreme-ob"><td>85-100</td><td>极度超买 / 顶部</td><td>2000/1, 2007/10, 2021/12</td><td><strong>大幅减仓 (30-50%)</strong>，买保护</td></tr>
</tbody>
</table>

<h2>⚠️ 实操陷阱</h2>
<ol class="caveats">
<li><strong>超卖中能继续超卖。</strong>单纯靠 RSI&lt;30 抄底是赌博，必须组合信号。</li>
<li><strong>VIX 40+ 的伪信号。</strong>纯流动性事件（如 2024/8 carry 平仓）VIX 暴冲但反弹快——要看 cause。</li>
<li><strong>信用利差是分水岭。</strong>HY&lt;500bps 时股票恐慌大概率过度反应；HY&gt;700bps 警惕真衰退。</li>
<li><strong>催化剂消除是触发。</strong>组合信号到位后还需要"催化剂消失"作为最终确认（如 2025/4 关税暂缓、2026/4 伊朗停火）。</li>
<li><strong>严重超买不必急着抛。</strong>牛市中超买是常态，要等组合信号 + 趋势破位再减仓。</li>
</ol>

<h2>📊 数据源</h2>
<ul class="sources">
<li><strong>FRED</strong>（federal reserve）: VIX, VXN, HY OAS, IG OAS — 免费 API，T+1 延迟</li>
<li><strong>Yahoo Finance</strong>: SPX, NDX, RUT 价格 / RSI / MA — 实时</li>
<li><strong>CNN</strong>: Fear &amp; Greed Index — 实时（盘中更新）</li>
<li><strong>AAII</strong>: 散户情绪 — 周更（每周四发布）</li>
<li><strong>NAAIM</strong>: 机构仓位 — 周更（每周三发布）</li>
<li><strong>CBOE</strong>: Put/Call Ratio — 日更（T+1）</li>
<li><strong>CTA 仓位</strong>: 用公开 trend 逻辑代理（GS/UBS 真实数据闭源）</li>
</ul>

</section>
"""


def get_zone_class(zone: str) -> str:
    return f"zone-{zone.replace('_', '-')}"


def render_html(score: Dict, indicators: Dict, analysis: Dict, history: list = None) -> str:
    """生成完整 HTML"""
    today = score.get("as_of", indicators.get("as_of_date", datetime.utcnow().strftime("%Y-%m-%d")))
    composite = score["composite_score"]
    status_label = score["status_label"]
    status_zone = score["status_zone"]
    zone_class = get_zone_class(status_zone)

    analysis_data = analysis.get("analysis", {})
    headline = analysis_data.get("headline", f"综合评分 {composite}")
    main_drivers = analysis_data.get("main_drivers", [])
    key_changes = analysis_data.get("key_changes", "")
    dim_highlights = analysis_data.get("dimension_highlights", {})
    inv_advice = analysis_data.get("investment_advice", {})
    next_watch = analysis_data.get("next_to_watch", [])
    verdict = analysis_data.get("verdict", "")

    # 各维度卡片
    dim_cards_html = ""
    dim_name_zh = {
        "volatility": "1. 波动率",
        "sentiment": "2. 情绪调查",
        "spx_breadth": "3. SPX 广度",
        "credit": "4. 信用利差",
        "ndx": "5. NDX 专项",
        "cta": "6. CTA / 量化",
        "momentum": "7. 价格动量",
    }
    for k, v in score["dimensions"].items():
        sub_score = v["score"]
        weight_pct = round(v["weight"] * 100)
        details = v.get("details", {}).get("components", {})
        details_html = "".join(
            f'<li><span class="ind-name">{name}:</span> <span class="ind-val">{val}</span></li>'
            for name, val in details.items()
        )
        sub_color = (
            "danger" if sub_score >= 80 else
            "warning" if sub_score >= 65 else
            "info" if sub_score >= 35 else
            "success"
        )
        highlight = dim_highlights.get(dim_name_zh[k].split(". ")[1], "")
        dim_cards_html += f"""
        <div class="dim-card">
          <div class="dim-header">
            <h3>{dim_name_zh[k]}</h3>
            <span class="dim-weight">权重 {weight_pct}%</span>
          </div>
          <div class="dim-score score-{sub_color}">{sub_score:.0f}</div>
          <div class="dim-bar"><div class="dim-bar-fill bar-{sub_color}" style="width:{sub_score}%"></div></div>
          <ul class="dim-details">{details_html}</ul>
          {f'<p class="dim-highlight">💡 {highlight}</p>' if highlight else ''}
        </div>
        """

    drivers_html = "".join(f"<li>{d}</li>" for d in main_drivers)
    next_watch_html = "".join(f"<li>{w}</li>" for w in next_watch)

    # 历史趋势 mini-chart (如果有数据)
    history_html = ""
    if history and len(history) > 1:
        recent = history[-30:]
        scores_data = [(h.get("as_of", ""), h.get("composite_score", 50)) for h in recent]
        # 简单 SVG 折线图
        if len(scores_data) >= 2:
            width = 600
            height = 80
            xs = [i * width / (len(scores_data) - 1) for i in range(len(scores_data))]
            ys = [height - (s / 100) * height for _, s in scores_data]
            points = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
            history_html = f"""
            <div class="history-chart">
              <h3>最近 30 个交易日评分趋势</h3>
              <svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" style="width:100%;height:80px;">
                <line x1="0" y1="{height - 50/100*height}" x2="{width}" y2="{height - 50/100*height}" stroke="#ccc" stroke-dasharray="2,2"/>
                <polyline points="{points}" fill="none" stroke="#333" stroke-width="1.5"/>
              </svg>
              <div class="history-axis">
                <span>{scores_data[0][0]}</span>
                <span>{scores_data[-1][0]}</span>
              </div>
            </div>
            """

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>美股市场情绪评分 — {today}</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<div class="container">

<header>
  <h1>美股市场情绪评分</h1>
  <p class="meta">{today} · 北京时间每日早 10 点更新</p>
</header>

<section class="hero {zone_class}">
  <div class="composite-row">
    <div class="composite-score">{composite}</div>
    <div class="composite-info">
      <div class="composite-label">{status_label}</div>
      <div class="composite-headline">{headline}</div>
    </div>
  </div>
  <div class="composite-bar">
    <div class="bar-zone bar-zone-1" style="width:15%"></div>
    <div class="bar-zone bar-zone-2" style="width:15%"></div>
    <div class="bar-zone bar-zone-3" style="width:15%"></div>
    <div class="bar-zone bar-zone-4" style="width:10%"></div>
    <div class="bar-zone bar-zone-5" style="width:15%"></div>
    <div class="bar-zone bar-zone-6" style="width:15%"></div>
    <div class="bar-zone bar-zone-7" style="width:15%"></div>
    <div class="bar-marker" style="left:{composite}%"></div>
  </div>
  <div class="composite-axis">
    <span>0 极度超卖</span>
    <span>50 中性</span>
    <span>100 极度超买</span>
  </div>
</section>

<section class="key-changes">
  <h2>🔑 关键驱动 &amp; 变化</h2>
  <ul class="drivers">{drivers_html}</ul>
  {f'<p class="changes-text"><strong>vs 上期变化：</strong>{key_changes}</p>' if key_changes and key_changes != "N/A" else ''}
</section>

<section class="dimensions">
  <h2>七维度评分明细</h2>
  <div class="dim-grid">{dim_cards_html}</div>
</section>

<section class="advice">
  <h2>💡 投资建议</h2>
  <table class="advice-table">
    <tr><td class="advice-key">仓位</td><td>{inv_advice.get('position', 'N/A')}</td></tr>
    <tr><td class="advice-key">对冲</td><td>{inv_advice.get('hedge', 'N/A')}</td></tr>
    <tr><td class="advice-key">不要做</td><td>{inv_advice.get('do_not', 'N/A')}</td></tr>
    <tr><td class="advice-key">触发立场转换</td><td>{inv_advice.get('trigger_to_act', 'N/A')}</td></tr>
  </table>
</section>

<section class="watch">
  <h2>👀 未来 3-7 天观察</h2>
  <ul class="watch-list">{next_watch_html}</ul>
</section>

<section class="verdict-section">
  <div class="verdict-box">
    <h2>最终决断</h2>
    <p class="verdict-text">{verdict}</p>
  </div>
</section>

{history_html}

{INDICATOR_GUIDE_HTML}

<footer>
  <p>评分系统由 Aaron 设计，Claude Opus 4.7 生成分析</p>
  <p>数据更新时间：{indicators.get('timestamp_utc', 'N/A')}</p>
  <p>本报告仅供参考，不构成投资建议</p>
  <p><a href="archive/">📁 查看历史快照</a></p>
</footer>

</div>
</body>
</html>"""

    return html


CSS = """/* Market Sentiment Scorecard - 简洁专业风格 */
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Helvetica Neue",
               Arial, "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  background: #f6f5f0;
  color: #2c2c2a;
  line-height: 1.7;
  padding: 24px 16px;
}
.container { max-width: 920px; margin: 0 auto; }

header { text-align: center; margin-bottom: 32px; }
header h1 { font-size: 28px; font-weight: 500; margin-bottom: 6px; }
.meta { font-size: 13px; color: #888780; }

h2 { font-size: 18px; font-weight: 500; margin-bottom: 12px; }
h3 { font-size: 16px; font-weight: 500; margin-bottom: 8px; }

/* Hero (composite score) */
.hero {
  background: white;
  border-radius: 16px;
  padding: 28px 24px;
  margin-bottom: 24px;
  border: 0.5px solid rgba(0,0,0,0.08);
}
.composite-row { display: flex; align-items: center; gap: 24px; margin-bottom: 16px; }
.composite-score {
  font-size: 76px;
  font-weight: 500;
  line-height: 1;
  letter-spacing: -2px;
}
.composite-info { flex: 1; }
.composite-label {
  font-size: 18px;
  font-weight: 500;
  padding: 6px 14px;
  border-radius: 18px;
  display: inline-block;
  margin-bottom: 8px;
}
.composite-headline { font-size: 16px; color: #444441; line-height: 1.5; }

/* Zone color: hero box left border */
.zone-extreme-oversold .composite-score { color: #173404; }
.zone-extreme-oversold .composite-label { background: #C0DD97; color: #173404; }
.zone-severe-oversold .composite-score { color: #3B6D11; }
.zone-severe-oversold .composite-label { background: #EAF3DE; color: #3B6D11; }
.zone-moderate-oversold .composite-score { color: #185FA5; }
.zone-moderate-oversold .composite-label { background: #E6F1FB; color: #185FA5; }
.zone-neutral .composite-score { color: #444441; }
.zone-neutral .composite-label { background: #F1EFE8; color: #444441; }
.zone-moderate-overbought .composite-score { color: #BA7517; }
.zone-moderate-overbought .composite-label { background: #FAEEDA; color: #854F0B; }
.zone-severe-overbought .composite-score { color: #993C1D; }
.zone-severe-overbought .composite-label { background: #FAC775; color: #854F0B; }
.zone-extreme-overbought .composite-score { color: #501313; }
.zone-extreme-overbought .composite-label { background: #F7C1C1; color: #791F1F; }

.composite-bar {
  position: relative;
  height: 28px;
  border-radius: 14px;
  overflow: hidden;
  display: flex;
  margin-bottom: 12px;
}
.bar-zone-1 { background: #C0DD97; }
.bar-zone-2 { background: #EAF3DE; }
.bar-zone-3 { background: #E6F1FB; }
.bar-zone-4 { background: #F1EFE8; }
.bar-zone-5 { background: #FAEEDA; }
.bar-zone-6 { background: #FAC775; }
.bar-zone-7 { background: #F7C1C1; }
.bar-marker {
  position: absolute;
  top: -4px; bottom: -4px;
  width: 4px;
  background: #2c2c2a;
  border-radius: 2px;
  transform: translateX(-50%);
}
.composite-axis {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #888780;
}

/* Sections */
section {
  background: white;
  border-radius: 12px;
  padding: 20px 24px;
  margin-bottom: 18px;
  border: 0.5px solid rgba(0,0,0,0.08);
}
section h2 { margin-bottom: 14px; padding-bottom: 8px; border-bottom: 0.5px solid rgba(0,0,0,0.08); }

.drivers { list-style: none; }
.drivers li {
  padding: 10px 14px;
  margin-bottom: 8px;
  background: #faf9f3;
  border-left: 3px solid #BA7517;
  border-radius: 4px;
  font-size: 14px;
}

.changes-text {
  margin-top: 12px;
  padding: 12px 14px;
  background: #f6f5f0;
  border-radius: 8px;
  font-size: 14px;
}

/* Dimensions grid */
.dim-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
}
.dim-card {
  background: #faf9f3;
  border-radius: 8px;
  padding: 14px 16px;
}
.dim-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 8px;
}
.dim-weight { font-size: 11px; color: #888780; }
.dim-score {
  font-size: 28px;
  font-weight: 500;
  line-height: 1;
  margin-bottom: 8px;
}
.score-success { color: #3B6D11; }
.score-info { color: #185FA5; }
.score-warning { color: #BA7517; }
.score-danger { color: #A32D2D; }
.dim-bar {
  height: 4px;
  background: #ece9df;
  border-radius: 2px;
  margin-bottom: 10px;
}
.dim-bar-fill { height: 100%; border-radius: 2px; }
.bar-success { background: #97C459; }
.bar-info { background: #378ADD; }
.bar-warning { background: #EF9F27; }
.bar-danger { background: #E24B4A; }
.dim-details { list-style: none; font-size: 12px; color: #5F5E5A; }
.dim-details li { padding: 2px 0; }
.ind-name { color: #888780; }
.ind-val { font-family: monospace; }
.dim-highlight {
  margin-top: 10px;
  padding: 8px 10px;
  background: white;
  border-radius: 6px;
  font-size: 12px;
  color: #444441;
  line-height: 1.5;
}

/* Advice */
.advice-table { width: 100%; font-size: 14px; border-collapse: collapse; }
.advice-table tr { border-bottom: 0.5px solid rgba(0,0,0,0.08); }
.advice-table tr:last-child { border-bottom: none; }
.advice-table td { padding: 10px 8px; vertical-align: top; }
.advice-key {
  width: 110px;
  color: #888780;
  font-weight: 500;
}

.watch-list { list-style: none; }
.watch-list li {
  padding: 8px 0 8px 20px;
  position: relative;
  font-size: 14px;
}
.watch-list li::before {
  content: "▸";
  position: absolute;
  left: 0;
  color: #888780;
}

/* Verdict box */
.verdict-section { background: transparent; padding: 0; border: none; }
.verdict-box {
  background: linear-gradient(135deg, #2c2c2a 0%, #444441 100%);
  color: white;
  padding: 24px;
  border-radius: 12px;
  text-align: center;
}
.verdict-box h2 {
  color: white;
  border: none;
  margin-bottom: 10px;
  font-size: 14px;
  letter-spacing: 1px;
  text-transform: uppercase;
  opacity: 0.7;
}
.verdict-text { font-size: 18px; line-height: 1.6; font-weight: 500; }

/* History chart */
.history-chart { font-size: 14px; }
.history-axis {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #888780;
  margin-top: 4px;
}

/* Indicator guide */
.guide { background: #faf9f3; }
.guide-intro {
  font-size: 14px;
  margin-bottom: 16px;
  padding: 12px 14px;
  background: white;
  border-radius: 8px;
}
.guide-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}
.guide-card {
  background: white;
  padding: 14px 16px;
  border-radius: 8px;
}
.guide-card h3 {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 6px;
}
.weight-badge {
  font-size: 11px;
  background: #f1efe8;
  color: #5f5e5a;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 400;
}
.dim-desc {
  font-size: 13px;
  color: #5f5e5a;
  margin-bottom: 10px;
  line-height: 1.5;
}
.guide-card dl { font-size: 13px; }
.guide-card dt {
  font-weight: 500;
  margin-top: 8px;
  color: #2c2c2a;
}
.guide-card dd {
  color: #444441;
  line-height: 1.6;
  padding-left: 4px;
}

/* Zone table */
.zone-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  margin-bottom: 24px;
}
.zone-table th, .zone-table td {
  padding: 8px 12px;
  text-align: left;
  border-bottom: 0.5px solid rgba(0,0,0,0.08);
}
.zone-table th {
  background: #f1efe8;
  font-weight: 500;
}
.zone-table tr.zone-extreme-os { background: #C0DD97; }
.zone-table tr.zone-severe-os { background: #EAF3DE; }
.zone-table tr.zone-mod-os { background: #E6F1FB; }
.zone-table tr.zone-neutral { background: #F1EFE8; }
.zone-table tr.zone-mod-ob { background: #FAEEDA; }
.zone-table tr.zone-severe-ob { background: #FAC775; }
.zone-table tr.zone-extreme-ob { background: #F7C1C1; }

.caveats {
  font-size: 13px;
  margin-bottom: 24px;
  padding-left: 24px;
}
.caveats li { margin-bottom: 8px; line-height: 1.6; }

.sources {
  font-size: 13px;
  list-style: none;
  background: white;
  padding: 12px 14px;
  border-radius: 8px;
}
.sources li { padding: 4px 0; }

footer {
  text-align: center;
  font-size: 12px;
  color: #888780;
  padding: 24px 0;
}
footer p { margin-bottom: 4px; }
footer a { color: #185FA5; text-decoration: none; }
footer a:hover { text-decoration: underline; }

/* Mobile */
@media (max-width: 600px) {
  body { padding: 12px 8px; }
  header h1 { font-size: 22px; }
  .composite-score { font-size: 56px; }
  .composite-row { gap: 16px; }
  section { padding: 16px; }
  .dim-grid, .guide-grid { grid-template-columns: 1fr; }
}
"""


if __name__ == "__main__":
    import sys
    indicators_path = os.environ.get("INDICATORS_FILE", "/tmp/indicators.json")
    score_path = os.environ.get("SCORE_FILE", "/tmp/score.json")
    analysis_path = os.environ.get("ANALYSIS_FILE", "/tmp/analysis.json")
    history_path = os.environ.get("HISTORY_FILE", "data/history.json")
    out_dir = os.environ.get("OUT_DIR", "/tmp/out")

    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(os.path.join(out_dir, "archive"), exist_ok=True)

    with open(indicators_path) as f:
        indicators = json.load(f)
    with open(score_path) as f:
        score = json.load(f)
    with open(analysis_path) as f:
        analysis = json.load(f)

    history = []
    if os.path.exists(history_path):
        try:
            with open(history_path) as f:
                history = json.load(f)
        except Exception:
            history = []

    html = render_html(score, indicators, analysis, history)

    # 写主页
    today = indicators.get("as_of_date", datetime.utcnow().strftime("%Y-%m-%d"))
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    # 写归档
    with open(os.path.join(out_dir, "archive", f"{today}.html"), "w", encoding="utf-8") as f:
        f.write(html)
    # 写 CSS
    with open(os.path.join(out_dir, "style.css"), "w", encoding="utf-8") as f:
        f.write(CSS)

    print(f"✅ HTML generated:")
    print(f"  - {out_dir}/index.html")
    print(f"  - {out_dir}/archive/{today}.html")
    print(f"  - {out_dir}/style.css")
