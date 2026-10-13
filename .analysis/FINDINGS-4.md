# 完美世界接口能否按年份取 vs-Top-N — 探查结论

> 承接 `FINDINGS-2.md` 的"建议 1"。目标：若完美接口支持年份参数，
> 就能绕开 HLTV 的 Cloudflare，直接补齐对手强度维度。
> **结论：不支持。此路已彻底探尽。**

---

## 一、为什么查这个

`FINDINGS-2.md` 确认：中段（官方 7-20 名）复现的瓶颈是缺"对手质量"维度。
完美世界的 `/player/stat/detail` **确实提供** vs-Top5/10/20/30/50 拆分，
但只覆盖当前赛季（ZywOo 56 图 vs 2025 实际 168 图）。

所以关键问题是：**这个接口有没有年份/赛季参数？** 有则问题解决。

---

## 二、探查结果：参数全部被静默忽略

### 2.1 直接接口 `/player/stat/detail`

基线（无参数）：`maps=56 rounds=1154 vsTop20=1.38`

测试了 **30 种**参数组合，**全部返回与基线逐字节相同**：

| 参数类别 | 测试项 | 结果 |
|---|---|---|
| 年份命名 | `year` / `season` / `yearId` / `seasonId` / `year_id` / `season_id` / `gameYear` / `matchYear` / `statYear` / `dataYear` / `period`（2025 与 "2025" 各一次） | 全部忽略 |
| 时间区间 | `timeValue` / `time_value` / `startDate` / `endDate` / `dateRange` | 全部忽略 |
| 时间戳 | `startTime` / `endTime` | **报错 code 1004**（说明接口确实不认时间维度） |
| 其他维度 | `type` / `darkType` / `eventId` / `eventIds` / `matchType` / `grade` / `level` / `scope` / `range` | 全部忽略 |

**关键判据**：若参数生效，`maps` 应变为 168（2025 实际）。实际恒为 56。

### 2.2 同族接口不存在

```
/player/stat/detail/history   → JSON 解析失败（返回非 JSON，即 404 类响应）
/player/stat/history          → 同上
/player/stat/year             → 同上
/player/stat/season           → 同上
/player/stat/detail/year      → 同上
/player/season/stat           → 同上
```

### 2.3 `/player/career` 不含 rating

这是最后一条希望（它已经是逐赛事结构，`crawler.py` 用它取荣誉）。
实测 145 条 honor 记录的**字段全集**：

```
['hasEvent', 'id', 'logo', 'name', 'players', 'rank', 'timestamp', 'type']
```

**没有任何 rating / ADR / 对手强度字段。** `type` 分布：

| type | 含义 | 条数 |
|---|---|---|
| 1 | MVP | 29 |
| 2 | 年度 Top20 | 7 |
| 4 | 队伍名次 | 72 |
| 5 | EVP | 37 |

### 2.4 榜单接口 `/player/stats` 也不支持年份

| 参数 | 首位选手 | maps |
|---|---|---|
| `{pageNum:1, pageSize:5, darkType:1}` | donk | 63 |
| 上者 + `year=2025` | donk | 63 |
| 上者 + `season=2025` | donk | 63 |

同样被忽略。

---

## 三、结论

**完美世界的对手强度拆分（vs-Top-N）只提供"当前赛季"快照，无法按年份回溯。**

这意味着：

| 路径 | 状态 |
|---|---|
| 完美 API 补 vs-Top-N | ❌ 不支持年份，只能拿当前赛季 |
| 完美 API 其他接口 | ❌ 无同族接口，career 不含 rating |
| HLTV 官方页面 | ❌ Cloudflare JS 挑战 + 国内到 CF 链路不稳定 |
| 自行构造对手强度 | ❌ 已验证 MAE 与重叠同时恶化（FINDINGS-2） |
| 稳定性信号 | ❌ 跨年验证双向失败（FINDINGS-3） |

**因此：中段复现的改进路径在当前可及的数据源下已全部探尽。**
"建议 1"正式作废，与 `FINDINGS-2.md` 的结论合并。

---

## 四、还剩的唯一可能路径（需外部条件）

1. **真实浏览器手动导出** — HLTV 选手页人工打开、另存 HTML、本地解析。
   每年 20 人，量小，完全避开反爬。但每年需人工操作一次。
2. **代理 + 浏览器自动化** — 需先解决链路（走代理），再解决 JS 挑战。
   技术上可行，但成本高、合规风险需自评。
3. **接受现状** — 模拟器定位为顶部 If 线分析工具（本项目已验证的强项）。

前两条都需要**你**决定是否投入，我可以实现技术部分，但无法替你判断合规与成本。

---

## 五、复跑

本次探查脚本为一次性诊断（已清理，避免污染 `.analysis`）。
核心方法可直接复制：用 `crawler.wm_get("/player/stat/detail", {"playerId": 11893, ...})`
逐参数比对 `player_stats_data.maps_played` 是否偏离基线 56。
