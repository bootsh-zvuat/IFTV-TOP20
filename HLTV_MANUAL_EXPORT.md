# HLTV 对手强度数据 — 手动导出与解析指南

> 目的：补齐 HLTV 官方中段排序依赖的**对手质量拆分**（vs Top-N Rating）。
> 这是唯一能真正突破中段信息上界的路径（前 10 轮自动化尝试已全部失败，
> 见 `REPORT.md` / `FINDINGS-2.md` / `FINDINGS-3.md` / `FINDINGS-4.md`）。

---

## 为什么必须手动

实测（2026-10-13）：

| 层级 | 结果 |
|---|---|
| DNS / TCP 443 | ✅ 正常 |
| TLS 握手 | ⚠️ 裸 socket 超时；`requests` 有时能过（20-56s） |
| HTTP | ❌ **403 `Just a moment... Enable JavaScript and cookies to continue`** |
| 走 CF 节点 | `cf-ray: ...-LHR`（伦敦） |

hltv.org 由 Cloudflare 保护，返回的是 **JS Challenge**，纯 HTTP 客户端拿不到内容。
真实浏览器可以正常打开 —— 所以由人工导出、脚本本地解析，完全绕开反爬机制。

**这也符合合规**：只解析你浏览器正常访问到的页面，不绕过任何保护措施。

---

## 使用步骤

### 1. 准备目录

```
data/hltv_html/2025/     ← 放 2025 年的 HTML
data/hltv_html/2024/     ← 放 2024 年的 HTML
```

### 2. 浏览器导出选手页

打开 HLTV 选手页，**加上日期范围让页面只统计该年**：

```
https://www.hltv.org/stats/players/11893/ZywOo?startDate=2025-01-01&endDate=2025-12-31
```

> 选手 ID 可以从 `data/if_sim_2025_baseline.xlsx` 的「选手ID」列取，
> 或用 `crawler.py` 的 `/player/top20` 接口拿（那套 id 与 HLTV URL 一致）。

页面加载完成后按 **Ctrl+S**：

- 保存类型选 **「网页，仅 HTML」**（Webpage, HTML Only）
- 文件名随意，但**建议保留选手名**，便于核对
- 存到对应年份目录

**注意**：一定要等页面完全加载（vs Top-N 区块出现）再保存。
若保存时区块未渲染，脚本会报「未识别到任何 vs Top-N 值」——
重存一次即可。

约 20 人/年，熟练后 10 分钟左右。

### 3. 解析

```powershell
.venv\Scripts\python.exe parse_hltv_html.py `
  --html-dir data\hltv_html\2025 `
  --year 2025 `
  --out data\hltv_opponent_2025.xlsx
```

**若某些文件解析失败**，加 `--dump` 打印实际可见文本：

```powershell
.venv\Scripts\python.exe parse_hltv_html.py `
  --html-dir data\hltv_html\2025 --year 2025 `
  --out data\hltv_opponent_2025.xlsx --dump --dump-lines 120
```

把 dump 出的文本发我，我据此调整提取规则。

---

## 输出格式

| 列 | 说明 |
|---|---|
| 年份 | 由 `--year` 指定 |
| 选手 | 选手名（用于与赛事数据 join） |
| 地图数 | 该年出场图数 |
| Rating | 整体 Rating |
| KD差 | K-D Diff（带符号） |
| KD比值 | K/D Ratio |
| vsTop5 / vsTop10 / vsTop20 / vsTop30 / vsTop50 | 对阵 top-N **战队**时的 Rating |
| 来源文件 | 便于回溯 |

---

## 已验证的鲁棒性

解析器**不依赖固定 CSS class**（HLTV 改版会失效），而是用「可见文本 + 标签锚定 + 数值模式」。

已用 5 种布局变体的仿真 HTML 测试（`.analysis/hltv_fixtures/`）：

| 变体 | 场景 | 结果 |
|---|---|---|
| A | 标签与值分行（最常见） | ✅ 全部字段正确 |
| B | 标签与值同行 | ✅ |
| C | 值被拆到下一行 + 广告噪音 | ✅ |
| D | 缺 vs 区块（页面未完整加载） | ✅ 正确报错并给出排查提示 |
| E | 值带「(18 maps)」括号 | ✅ 数值仍正确提取 |

边界测试（K-D Diff 提取器）：

| 输入 | 输出 | 说明 |
|---|---|---|
| `['K-D Diff', '-45']` | −45 | 负数分行 |
| `['K-D Diff -120']` | −120 | 负数同行 |
| `['+9999 coins bonus', 'K-D Diff', '+560']` | **560** | ✅ 锚定标签，未被广告数字干扰 |
| `['+1234']`（无标签） | None | 不猜测 |

**关键设计**：K-D Diff 必须锚定标签后再取值。
早期版本直接搜"第一个带符号整数"，会把广告里的 `+9999` 误当成 KD 差 —— 已修复。

---

## 拿到数据后怎么用

1. 把 `hltv_opponent_YYYY.xlsx` 的 vsTopN 列**按选手名 join** 到
   `if_sim_YYYY_events.xlsx`（注意是选手名，不是选手ID ——
   两个数据源的 ID 命名空间不同，见 `gen_if_data_2025.py` 的注释）。
2. 在 `score.ts` 增加对手强度通道，用 2024/2025 两年做**跨年验证**。
   **必须两年都改善才可采纳** —— 这是前 10 轮反复踩到的坑：
   单年调优极易过拟合（中段仅 14 人/年）。
3. 参照 `FINDINGS-3.md` 的跨年判决方法（在一年选参、另一年测试）。

---

## 环境说明

- 解析器优先用 BeautifulSoup，未安装时**自动降级为正则路径**（当前环境即此路径，已验证可用）。
- 如需更稳的解析，可安装：`.venv\Scripts\python.exe -m pip install beautifulsoup4`
- 输出 xlsx 需要 openpyxl（项目已有）。
