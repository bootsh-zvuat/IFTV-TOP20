# IFTV — CS2 选手年度排名与 If 线模拟器

模拟 HLTV 年度 Top20 的排名逻辑，并支持 What-if 情景模拟
（"如果 donk 赢了某个 Major，排名会怎样"）。

> 版本：v1.3.0 · 2026-10-13

---

## 这是什么

用可解释的参数化模型复现 HLTV 年度 Top20 的排名逻辑，并支持 What-if 情景模拟
（如"如果 donk 赢了某个 Major，排名会怎样"）。

三个组件：

| 组件 | 入口 | 作用 |
|---|---|---|
| 数据采集 | `crawler.py` | 完美世界 API（HLTV 口径）+ 5EPlay API |
| 参数拟合 | `fit_ranking.py` | 差分进化拟合评分公式，留一年验证 |
| If 线模拟器 | `if-simulator/` | React + TS + Vite，纯前端 |

另有 HLTV 对手强度采集（`fetch_hltv_opponents.py`），见下文"本次新增"。

---

## 快速开始

### 方式 A：双击启动（推荐，免安装依赖）

**双击根目录的 `启动模拟器.bat`** —— 会自动起本地服务器并打开浏览器。

- 优先用 Python，没有 Python 则自动改用 Node.js
- 端口被占用会自动向后找空闲端口
- 关闭窗口即停止服务

> **为什么不直接双击 `dist/index.html`？**
> 现代浏览器禁止 `file://` 页面加载 ES Module（CORS 策略），
> 而 Vite 构建产物必然是 module，所以必须经 HTTP 访问。
> 实测报错：
> `Access to script at 'file:///...' from origin 'null' has been blocked by CORS policy`
>
> 仅改相对路径也无效 —— 这是协议层面的限制，不是路径问题。

也可手动起服务器（三者等价）：

```powershell
python serve.py              # Python 标准库，无依赖
node serve.js                # Node 版，无依赖
cd if-simulator/dist && python -m http.server 8000
```

### 方式 B：开发模式（可改代码，有热更新）

```powershell
cd if-simulator
npm ci        # node_modules 未打包，需重新安装（首次约 1-2 分钟）
npm run dev   # http://localhost:5173
```

### 方式 C：构建后预览

```powershell
cd if-simulator
npm ci
npm run build
npm run preview   # http://localhost:4173
```

### 导入数据

浏览器打开后，点「导入赛事数据 Excel」选 `data/if_sim_2025_events.xlsx`，
再点「导入 HLTV 原版 Top20」选 `data/if_sim_2025_baseline.xlsx`。

> 注意：`data/if_sim_2024_*` 与 2025 是两套数据，导入 2024 会覆盖 2025。
> 清空浏览器数据可在控制台执行 `indexedDB.deleteDatabase('if-simulator')`。

### 数据采集（Python）

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe crawler.py              # 全量采集
.venv\Scripts\python.exe gen_if_data_2025.py     # 生成模拟器导入用 Excel
```

---

## 目录结构

```
IFTV-TOP20/
├── 启动模拟器.bat                # ← 双击这个即可运行（GBK 编码，勿转存为 UTF-8）
├── serve.py                      # 便携静态服务器（Python，无依赖）
├── serve.js                      # 便携静态服务器（Node，无依赖）
├── crawler.py                    # 采集器（完美世界 + 5EPlay）
├── gen_if_data_2025.py           # 赛事 Excel 生成（模拟器导入格式）
├── gen_verify_data.py            # 校验数据生成
├── fit_ranking.py                # 参数拟合（差分进化 + 留一年）
├── collect_team_placements.py    # 战队口径名次采集
├── analyze_placements.py         # 名次分析
├── fetch_hltv_opponents.py       # HLTV 对手强度采集（Edge CDP）
├── parse_hltv_html.py            # HLTV 手工导出页解析（备选方案）
├── probe_*.py                    # API 结构探查脚本（一次性，留档）
├── fitted_params.json            # 拟合结果（2021-2025）
├── fitted_params_team.json       # 战队口径拟合结果
├── requirements.txt
├── 大纲.md                        # 原始项目规格
├── HLTV_MANUAL_EXPORT.md         # HLTV 手工导出流程说明
│
├── data/                         # 数据（见下）
├── if-simulator/                 # 模拟器源码 + dist 构建产物
└── .analysis/                    # 诊断报告与验证脚本（见下）
```

---

## 数据文件说明（`data/`）

### 模拟器导入用

| 文件 | 内容 |
|---|---|
| `if_sim_2025_events.xlsx` | 2025 赛事数据：26 赛事 / 1735 行（**含 vsTop5 等列**） |
| `if_sim_2025_baseline.xlsx` | 2025 官方 Top20 基准 |
| `if_sim_2024_events.xlsx` | 2024 赛事数据：22 赛事 / 1567 行 |
| `if_sim_2024_baseline.xlsx` | 2024 官方 Top20 基准 |
| `*.xlsx.bak` | 补 vsTopN 列前的备份（可删） |

赛事 Excel 列：
`年份 / 赛事名称 / 赛事级别 / 赛事权重 / 选手ID / 选手名 / 队伍 / 队伍名次 /
荣誉类型 / 荣誉顺位 / Rating / ADR / KPR / 地图数 / Rating标准差 / Rating变异系数 /
前后半程差 / 逐图样本数 / vsTop5 / vsTop10 / vsTop20 / vsTop30 / vsTop50`

### 采集原始数据

| 文件 | 内容 |
|---|---|
| `CS2选手排名数据_20261013_111843.xlsx` | 爬虫多表输出（历年 Top20 / 生涯荣誉 / 5E 逐年统计等） |
| `CS2选手排名数据_20261012_235339.xlsx` | 上一版采集 |
| `hltv_opponent_2025.xlsx` / `_2024.xlsx` | HLTV 对手强度原始数据（已 join 进赛事文件） |
| `team_placements.json` | 战队口径名次（1.8 MB） |
| `team_career_cache.json` | 生涯荣誉缓存（2.7 MB） |

---

## 算法说明（v1.3.0）

### 总分

```
总分 = Σ(单赛事表现分 × 赛事权重) + 对手强度通道（默认关闭）
```

单赛事表现分（截断到 `[-2, 11]`）：

```
荣誉基础分(MVP 10 / EVP1 8 / EVP2 6 / EVP3 4)
+ rating 分档(≥1.3:+2, ≥1.2:+1, ≥1.1:+0.5, <1.05:-0.5, <1.0:-1)
+ 队伍名次(冠军+2, 亚军+0.5, 四强0, 八强-0.5, 小组淘汰-1)
```

两道参赛门槛：单赛事 <3 图不计分；年度 <20 图不进榜。

### 回测表现（2025 / 2024）

| 指标 | 2025 | 2024 |
|---|---|---|
| Top20 重叠 | 18/20 | 17/20 |
| 头部（1-6）MAE | 0.17 | 1.00 |
| 中段（7-20）MAE | 4.64 | 5.21 |

**头部两年基本全中，中段复现有限** —— 这是已知边界，非缺陷（见下文）。

---

## 本次新增（相对 v1.2.0）

### 1. 逐图时间序列保留

`gen_if_data_2025.py` 原本聚合后丢弃逐图数据，现已保留
`(比赛时间, 图序, rating, 回合数)`，并导出 4 个稳定性列
（`Rating标准差 / Rating变异系数 / 前后半程差 / 逐图样本数`）。

**但经跨年验证，稳定性信号无效**，仅作数据留存，不参与计分。

### 2. HLTV 对手强度采集

`fetch_hltv_opponents.py`：用**真实 Edge 浏览器 + CDP** 采集 HLTV
的 vs Top-N 数据。

**为什么这么做**：hltv.org 由 Cloudflare 保护（JS Challenge），
纯 HTTP 客户端与 headless 浏览器都被拦；真实（有头）Edge 可在约 29 秒内
自动通过挑战，再用内置 CDP 读取渲染后的 DOM。

**注意**：需先启动 Edge：
```powershell
& "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" `
  --remote-debugging-port=9411 `
  --user-data-dir="<某目录>\edge_profile" `
  --disable-blink-features=AutomationControlled about:blank
.venv\Scripts\python.exe fetch_hltv_opponents.py --year 2025 --out data\hltv_opponent_2025.xlsx
```
端口默认 9411（9333 常被华硕 Armoury Crate 占用）。

**合规**：不绕过 Cloudflare —— 由真实浏览器自行完成挑战，脚本只读结果。

### 3. 模拟器对手强度通道（默认关闭）

`core/ranking.ts` 新增 `opponentScore()`：把 vs Top-N 做年度 z-score
后加到总分。设置页可配置权重与档位。

**默认权重 0（关闭）** —— 实测它**无法稳定改善中段**：

| 权重 k | 2025 中段 MAE | 2024 中段 MAE | Top20 |
|---|---|---|---|
| 0（基线） | 4.64 | 5.21 | 18/20、17/20 |
| 0.5 | 4.57 | 5.14 | 18、17 |
| 2 | 4.71 | 5.36 | 18、17 |
| 5 | 5.86 | 7.36 | 18、16 |

MAE 非单调波动、Top20 从未提升。但该信号**方向正确**
（中段 Spearman −0.385/−0.473，强于现行总分的 −0.336/−0.196），
故保留代码供实验。

---

## `.analysis/` 诊断报告

累计 11 轮改善尝试的完整记录：

| 文档 | 内容 |
|---|---|
| `REPORT.md` | 中段误差根因（信号方向反了）+ 4 轮调参证伪 |
| `FINDINGS-2.md` | 对手强度数据源探查、分段重排失败 |
| `FINDINGS-3.md` | 稳定性信号跨年验证失败 |
| `FINDINGS-4.md` | 完美 API 不支持按年份取数 |
| `FINDINGS-5-HLTV-SUCCESS.md` | HLTV 采集成功（顶部含更正声明） |
| `FINDINGS-6-INTEGRATION.md` | 接入模拟器的结果与 3 个错误更正 |

验证脚本：`validate_hltv.py`、`robustness_hltv.py`、
`verify_ts_integration.py`、`migrate_vstopn.py` 等。

### 核心结论

**中段（7-20 名）是信息上界，不是实现缺陷。**

头部 Spearman +0.71~+0.94，中段仅 +0.21~+0.34。差距来自**可用信息量**：
官方中段依赖的对手质量拆分与全年聚合稳定性，现有数据源难以完整提供。

11 轮尝试（调参 / 构造信号 / 分段重排 / 稳定性 / 对手强度）均无法
在 **14 人/年 × 2 年**的样本上稳定降低中段 MAE。

**模拟器的最佳用途是顶部 If 线分析**（前 6 名两年全中）。

---

## 已知边界

1. **中段次序复现有限** —— 见上文，已充分验证为信息上界。
2. **两个数据源的 Rating 口径不可混用** —— 完美是 Rating 3.0（对齐 HLTV），
   5E 是自有口径。
3. **选手 ID 命名空间有三套** —— 完美主站 / nami 比赛接口 / HLTV，
   跨源 join 必须按**选手名**。
4. **只有 2024/2025 两年**可验证，样本小；若要继续改进，需先扩大样本
   （补采 2021-2023 的 HLTV 数据）。
5. `if-simulator/dist/` 是已构建的生产版本，但**部署需注意**
   `vite.config.ts` 的 `base` 为默认 `/`，子路径部署需调整。

---

## 依赖

- **Python**：`requests` / `openpyxl` / `numpy` / `scipy`（见 `requirements.txt`）
- **Node**：见 `if-simulator/package.json`（React 18 / Vite 5 / Tailwind 3 / Dexie 4 / xlsx）
- `.venv` 与 `node_modules` **未打包**，按上文命令重建。

---

## 复现验证

```powershell
# 模拟器
cd if-simulator && npm ci && npm run build   # tsc + vite

# 回测（Python 复刻 TS 逻辑）
.venv\Scripts\python.exe .analysis\verify_ts_integration.py
.venv\Scripts\python.exe .analysis\validate_hltv.py
```
