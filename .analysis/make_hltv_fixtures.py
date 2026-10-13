# -*- coding: utf-8 -*-
"""生成 HLTV 选手页的仿真 HTML 用于测试解析器。

重要说明：我无法联网核对 HLTV 当前真实 DOM（Cloudflare 403），
因此这些 fixture 是按**已知的页面语义**构造的，覆盖几种常见布局变体：
  变体 A：标签与值分行（最常见）
  变体 B：标签与值同行
  变体 C：值被 <span> 拆碎
  变体 D：缺少部分区块（页面未加载完整）
  变体 E：含噪音（导航/广告文本）确保不误取

目的是验证解析器的**鲁棒性**，而非声称匹配真实 DOM。
真实页面的最终校准由 --dump 完成。
"""
import os
import sys

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hltv_fixtures")


def wrap(title, body):
    return f"""<!DOCTYPE html>
<html><head><title>{title}</title></head>
<body>
<div class="header">
  <a href="/">HLTV.org</a> <a href="/news">News</a> <a href="/matches">Matches</a>
  <a href="/results">Results</a> <a href="/stats">Stats</a> <a href="/betting">Betting</a>
</div>
<div class="contentCol">
{body}
</div>
<div class="footer">
  <p>HLTV.org - The home of competitive Counter-Strike</p>
</div>
</body></html>
"""


A = wrap("ZywOo | HLTV.org", """
<div class="playerPage">
  <h1>ZywOo</h1>
  <div class="playerTeam">Team Vitality</div>
  <div class="summaryBreakdownContainer">
    <div class="summaryStatBreakdown">
      <div class="summaryStatBreakdownSubHeader">Rating</div>
      <div class="summaryStatBreakdownDataValue">1.29</div>
    </div>
    <div class="summaryStatBreakdown">
      <div class="summaryStatBreakdownSubHeader">K/D Ratio</div>
      <div class="summaryStatBreakdownDataValue">1.38</div>
    </div>
    <div class="summaryStatBreakdown">
      <div class="summaryStatBreakdownSubHeader">K-D Diff</div>
      <div class="summaryStatBreakdownDataValue">+1234</div>
    </div>
  </div>
  <div class="stats-detailed-stats">
    <div class="stats-section">
      <div class="stats-section-title">Featured ratings</div>
      <div class="stats-row"><span class="desc">vs top 5 opponents</span><span class="value">1.28</span></div>
      <div class="stats-row"><span class="desc">vs top 10 opponents</span><span class="value">1.27</span></div>
      <div class="stats-row"><span class="desc">vs top 20 opponents</span><span class="value">1.30</span></div>
      <div class="stats-row"><span class="desc">vs top 30 opponents</span><span class="value">1.31</span></div>
      <div class="stats-row"><span class="desc">vs top 50 opponents</span><span class="value">1.32</span></div>
    </div>
    <div class="stats-section">
      <div class="stats-section-title">Total</div>
      <div class="stats-row"><span class="desc">Total maps</span><span class="value">168</span></div>
      <div class="stats-row"><span class="desc">Total rounds</span><span class="value">3456</span></div>
    </div>
  </div>
</div>
""")

# 变体 B：标签与值同行；地图数写法不同
B = wrap("donk | HLTV.org", """
<div class="playerPage">
  <h1>donk</h1>
  <div class="stats-detailed-stats">
    <div class="stats-row">Maps played <span>128</span></div>
    <div class="stats-row">Rating <span>1.42</span></div>
    <div class="stats-row">K/D Ratio <span>1.55</span></div>
    <div class="stats-row">K-D Diff <span>+1500</span></div>
    <div class="stats-row">vs top 5 opponents <span>1.38</span></div>
    <div class="stats-row">vs top 10 opponents <span>1.40</span></div>
    <div class="stats-row">vs top 20 opponents <span>1.41</span></div>
    <div class="stats-row">vs top 30 opponents <span>1.42</span></div>
    <div class="stats-row">vs top 50 opponents <span>1.43</span></div>
  </div>
</div>
""")

# 变体 C：值被 span 拆碎 / 分行；含干扰数字
C = wrap("m0NESY | HLTV.org", """
<div class="playerPage">
  <h1>m0NESY</h1>
  <div class="stats-detailed-stats">
    <div class="stats-section-title">Featured ratings</div>
    <div class="stats-row"><span class="desc">vs top 5 opponents</span></div>
    <div class="stats-row"><span class="value">1.33</span></div>
    <div class="stats-row"><span class="desc">vs top 10 opponents</span></div>
    <div class="stats-row"><span class="value">1.34</span></div>
    <div class="stats-row"><span class="desc">vs top 20 opponents</span></div>
    <div class="stats-row"><span class="value">1.35</span></div>
    <div class="stats-row"><span class="desc">Total maps</span></div>
    <div class="stats-row"><span class="value">152</span></div>
    <div class="stats-row"><span class="desc">Rating</span></div>
    <div class="stats-row"><span class="value">1.31</span></div>
    <div class="stats-row"><span class="desc">K-D Diff</span></div>
    <div class="stats-row"><span class="value">+980</span></div>
  </div>
  <div class="advertisement">Win 5000 coins play now 2 4 6</div>
</div>
""")

# 变体 D：缺少 vs 区块（模拟页面未完整加载）
D = wrap("ropz | HLTV.org", """
<div class="playerPage">
  <h1>ropz</h1>
  <div class="stats-detailed-stats">
    <div class="stats-row">Total maps 166</div>
    <div class="stats-row">Rating 1.18</div>
    <div class="stats-row">K/D Ratio 1.24</div>
    <div class="stats-row">K-D Diff +560</div>
  </div>
</div>
""")

# 变体 E：值带多余字符（百分号/括号）
E = wrap("sh1ro | HLTV.org", """
<div class="playerPage">
  <h1>sh1ro</h1>
  <div class="stats-detailed-stats">
    <div class="stats-row"><span>Total maps</span><span>128 maps</span></div>
    <div class="stats-row"><span>Rating</span><span>1.26</span></div>
    <div class="stats-row"><span>K-D Diff</span><span>+812</span></div>
    <div class="stats-row"><span>vs top 5 opponents</span><span>1.22 (18 maps)</span></div>
    <div class="stats-row"><span>vs top 10 opponents</span><span>1.24 (38 maps)</span></div>
    <div class="stats-row"><span>vs top 20 opponents</span><span>1.25 (47 maps)</span></div>
    <div class="stats-row"><span>vs top 30 opponents</span><span>1.25 (47 maps)</span></div>
    <div class="stats-row"><span>vs top 50 opponents</span><span>1.26 (56 maps)</span></div>
  </div>
</div>
""")


def main():
    os.makedirs(OUT, exist_ok=True)
    cases = [
        ("A_zywoo.html", A, "标签值分行"),
        ("B_donk.html", B, "标签值同行"),
        ("C_m0nesy.html", C, "值被拆到下一行 + 广告噪音"),
        ("D_ropz.html", D, "缺 vs 区块（预期部分失败）"),
        ("E_sh1ro.html", E, "值带括号地图数"),
    ]
    for name, html, desc in cases:
        p = os.path.join(OUT, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  写出 {name:<18} ({desc})")
    print(f"\n共 {len(cases)} 个 fixture → {OUT}")
    print("\n预期：")
    print("  A/B/C/E 应全部解析成功")
    print("  D 应报「未识别到任何 vs Top-N 值」（验证诊断能发现问题）")


if __name__ == "__main__":
    main()
