# -*- coding: utf-8 -*-
"""
HLTV Top20 排名逻辑参数拟合（可解释、可复现）

从 data/CS2选手排名数据_*.xlsx 读取采集数据，构建"选手×年份"特征表，
用差分进化算法拟合评分公式参数（目标：预测排名与官方名次的 Pearson 相关最大），
并用留一年法（leave-one-year-out）验证泛化能力。

评分公式（每年独立 z-score 归一化，Score 为加权和，组件权重和为 1）：
  Score = Wp*Perf + Wh*HonorZ + Wt*TeamZ + Ws*Sec
  Perf  = wr*z_rating + wk*z_kast + wa*z_adr + wi*z_impact + wwr*z_winrate   （5E 口径）
  HonorZ= z( ΣMVP mult(等级) + evp_ratio*ΣEVP mult(等级) )   2020+ 逐赛事（完美 career）
          z( 当年MVP数 )                                       2016-2019 回退（MVP年度统计）
  TeamZ = z( Σ名次分 )   冠军/亚军/四强/八强 各为独立拟合参数
  Sec   = w1*z(首杀/图) + w2*z(多杀/图) + w3*z(残局/图)
  mult(等级): Major=m_major, IEM卡托/科隆=m_super, 其他=1.0

运行：.venv\\Scripts\\python.exe src\\fit_ranking.py
输出：控制台结果 + fitted_params.json（拟合参数与验证指标）
"""
import os
import sys
import glob
import json
import datetime
from collections import defaultdict

try:
    import numpy as np
    from scipy.optimize import differential_evolution
    from scipy.stats import rankdata
except ImportError:
    print("缺少依赖 numpy/scipy，请先执行：.venv\\Scripts\\python.exe -m pip install numpy scipy")
    sys.exit(1)
try:
    import openpyxl
except ImportError:
    print("缺少依赖 openpyxl，请先执行：.venv\\Scripts\\python.exe -m pip install openpyxl")
    sys.exit(1)

# ---------- 配置 ----------
# 项目根 = src/ 的上一级（fitted_params.json 输出到根目录，data/ 也在根目录下）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_MAPS = 10                    # 纳入归一化池的最低地图数
EVP_YEAR_START = 2020            # 完美 career 的逐赛事 MVP/EVP 仅 2020+ 有数据
TEAM_PLACE_YEAR_START = 2021     # 战队口径名次数据（含冠军）从此年起生效
SEED = 42
OUT_JSON = os.path.join(BASE_DIR, "fitted_params.json")
TEAM_PLACE_JSON = os.path.join(BASE_DIR, "data", "team_placements.json")

# 战队口径名次文本 → 分级（1-2名/1-3名/1-4名/2-3名 为阶段赛产物，一律弃用）
TEAM_TIER_MAP = {
    "冠军": "champ", "亚军": "runner",
    "季军": "semi", "3-4名": "semi", "4名": "semi",
    "5-8名": "quarter", "6-8名": "quarter", "5-6名": "quarter",
    "7-8名": "quarter", "八强": "quarter",
}
# 选手生涯回退时可信的名次文本（亚军/3-4名 等为明确文本；1-2名 不可信）
CAREER_RELIABLE_TIER_MAP = {
    "亚军": "runner",
    "季军": "semi", "3-4名": "semi", "4名": "semi",
    "5-8名": "quarter", "6-8名": "quarter", "5-6名": "quarter",
    "7-8名": "quarter", "八强": "quarter",
}


def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------- Excel 读取 ----------
def load_sheet(wb, name):
    """读取带说明行的 sheet：第1行=说明，第2行=表头，第3行起=数据"""
    ws = wb[name]
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    header = rows[0]
    out = []
    for r in rows[1:]:
        if r is None or all(v is None for v in r):
            continue
        out.append(dict(zip(header, r)))
    return out


def num(v):
    return float(v) if isinstance(v, (int, float)) else 0.0


# ---------- 参数定义 ----------
# 参数向量顺序（19 维）：
#   0-3   组件权重 Wp/Wh/Wt/Ws（归一化后和为1）
#   4-8   表现分子权重 rating/kast/adr/impact/winrate（归一化后和为1）
#   9-11  次级子权重 首杀/多杀/残局（归一化后和为1）
#   12    evp_ratio（EVP 基础分 = MVP 基础分 × 该比例）
#   13-16 队伍名次分 冠军/亚军/四强/八强
#   17-18 MVP 赛事等级乘数 Major / IEM卡托科隆（其他=1）
PARAM_NAMES = [
    "Wp", "Wh", "Wt", "Ws",
    "wr", "wk", "wa", "wi", "wwr",
    "w1", "w2", "w3",
    "evp_ratio",
    "v_champ", "v_runner", "v_semi", "v_quarter",
    "m_major", "m_super",
]
BOUNDS = [
    (0.05, 1), (0.05, 1), (0.02, 1), (0.0, 1),
    (0.05, 1), (0, 1), (0, 1), (0, 1), (0, 1),
    (0, 1), (0, 1), (0, 1),
    (0, 1),
    (1, 10), (0, 8), (0, 6), (0, 4),
    (0.8, 2.0), (0.8, 1.6),
]


def decode(vec):
    """参数向量 → 结构化字典（各类权重归一化）"""
    v = {k: float(x) for k, x in zip(PARAM_NAMES, vec)}
    for keys in [("Wp", "Wh", "Wt", "Ws"),
                 ("wr", "wk", "wa", "wi", "wwr"),
                 ("w1", "w2", "w3")]:
        s = sum(v[k] for k in keys)
        for k in keys:
            v[k] = v[k] / s if s > 0 else 1.0 / len(keys)
    return v


def event_tier(name):
    """赛事等级（按名称关键词）：Major > IEM卡托/科隆 > 其他"""
    n = name or ""
    if "Major" in n:
        return "major"
    if ("卡托维兹" in n) or ("科隆" in n):
        return "super"
    return "other"


def placement_tier(text):
    """队伍名次文本 → 分级。career 实测名次文本：
    1-2名/亚军/季军/4名/3-4名/1-3名/2-3名/1-4名（无'冠军'字样，冠军记为1-2名）"""
    t = (text or "").strip()
    if not t:
        return None
    if ("冠军" in t) or ("1-2名" in t):
        return "champ"
    if "亚军" in t:
        return "runner"
    if ("季军" in t) or ("四强" in t) or ("3-4" in t) or ("4名" in t) \
            or ("1-3名" in t) or ("2-3名" in t) or ("1-4名" in t):
        return "semi"
    if ("八强" in t) or ("5-8" in t) or ("6-8" in t) or ("5-6" in t) or ("7-8" in t):
        return "quarter"
    return None


def rank_value(text, p):
    """队伍名次文本 → 名次分（参数化）"""
    tier = placement_tier(text)
    if tier == "champ":
        return p["v_champ"]
    if tier == "runner":
        return p["v_runner"]
    if tier == "semi":
        return p["v_semi"]
    if tier == "quarter":
        return p["v_quarter"]
    return 0.0


def zscore(a):
    a = np.asarray(a, dtype=float)
    sd = a.std()
    if sd < 1e-9:
        return np.zeros_like(a)
    return (a - a.mean()) / sd


# ---------- 数据加载与特征表构建 ----------
class Dataset:
    """一次性把 Excel 数据解析为按年份缓存的 numpy 特征矩阵"""

    def __init__(self, xlsx_path, train_years, mvp_fallback="all"):
        self.train_years = train_years
        self.mvp_fallback = mvp_fallback  # "all"=全部赛事 / "big"=仅大赛（2016-2019 回退口径）
        wb = openpyxl.load_workbook(xlsx_path, read_only=True)
        log(f"读取 {os.path.basename(xlsx_path)} ...")

        # 1. Ground truth：历年 Top20 官方名次
        self.gt = defaultdict(dict)   # year -> {pid: rank}
        for r in load_sheet(wb, "历年HLTV_Top20"):
            y, pid, rk = int(r["年份"]), int(r["选手ID"]), int(r["官方名次"])
            self.gt[y][pid] = rk

        # 2. 5E 逐年统计 → 表现特征（地图数过滤）
        self.perf = {}                # (pid, year) -> dict
        for r in load_sheet(wb, "5E逐年统计"):
            maps = num(r.get("地图数"))
            if maps < MIN_MAPS:
                continue
            pid, y = int(r["选手ID"]), int(r["年份"])
            self.perf[(pid, y)] = dict(
                rating=num(r.get("Rating")), kast=num(r.get("KAST")),
                adr=num(r.get("ADR")), impact=num(r.get("Impact")),
                winrate=num(r.get("胜率")),
                fb_pm=num(r.get("首杀")) / maps,
                mk_pm=(num(r.get("四杀")) + num(r.get("五杀"))) / maps,
                cl_pm=(num(r.get("1v4")) + num(r.get("1v5"))) / maps,
            )

        # 3. 完美 career → 逐赛事 MVP/EVP/队伍名次（按日期定年，规避 API 年份错位）
        self.mvp_events = defaultdict(list)
        self.evp_events = defaultdict(list)
        self.places = defaultdict(list)
        rank_texts = set()
        type1_yearly = defaultdict(int)
        for r in load_sheet(wb, "历年生涯荣誉"):
            pid = int(r["选手ID"])
            date = str(r.get("日期") or "")
            if date[:4].isdigit():
                y = int(date[:4])
            elif r.get("年份"):
                y = int(r["年份"])
            else:
                continue
            t = r.get("类型")
            if t == 1:
                self.mvp_events[(pid, y)].append(r.get("赛事名") or "")
                type1_yearly[y] += 1
            elif t == 5:
                self.evp_events[(pid, y)].append(r.get("赛事名") or "")
            elif t == 4:
                txt = (r.get("名次") or "").strip()
                self.places[(pid, y)].append(txt)
                rank_texts.add(txt)
        log(f"career 名次文本: {sorted(rank_texts)}")
        log(f"career type=1(按日期定年) 逐年计数: {dict(sorted(type1_yearly.items()))}")

        # 3b. 战队口径名次（TEAM_PLACE_YEAR_START 起）：team/career 冠军显式 + 阵容归属，
        #     未被战队记录覆盖的用选手生涯 type4 明确文本回退（Gambit 非冠军年份等）
        self.places_team = defaultdict(list)   # (pid, year) -> [tier, ...]
        self.team_data_years = set()
        if os.path.exists(TEAM_PLACE_JSON):
            with open(TEAM_PLACE_JSON, encoding="utf-8") as f:
                tp = json.load(f)
            covered = set()                    # (pid, eventId) 已被战队记录覆盖
            n_skip_tier = 0
            for p in tp.get("placements", []):
                if p.get("qualifier") or p.get("exhibition"):
                    continue
                tier = TEAM_TIER_MAP.get((p.get("rank") or "").strip())
                date = str(p.get("date") or "")
                if not tier:
                    n_skip_tier += 1
                    continue
                if not date[:4].isdigit():
                    continue
                y = int(date[:4])
                for pid in p.get("playerIds") or []:
                    self.places_team[(pid, y)].append(tier)
                    covered.add((pid, p.get("eventId")))
                self.team_data_years.add(y)
            n_fallback = 0
            for ev in tp.get("player_events", []):
                if ev.get("type") != 4 or ev.get("qualifier") or ev.get("exhibition"):
                    continue
                if (ev.get("playerId"), ev.get("eventId")) in covered:
                    continue
                tier = CAREER_RELIABLE_TIER_MAP.get((ev.get("rank") or "").strip())
                date = str(ev.get("date") or "")
                if not tier or not date[:4].isdigit():
                    continue
                self.places_team[(ev["playerId"], int(date[:4]))].append(tier)
                n_fallback += 1
            champ_by_year = defaultdict(int)
            for (pid, y), tiers in self.places_team.items():
                champ_by_year[y] += sum(1 for t in tiers if t == "champ")
            log(f"战队口径名次: {sum(len(v) for v in self.places_team.values())} 条 "
                f"(含回退 {n_fallback} 条；弃用阶段赛文本 {n_skip_tier} 条)")
            log(f"  冠军归属人次按年: {dict(sorted(champ_by_year.items()))}")
        else:
            log("! 未找到 team_placements.json，队伍名次沿用选手生涯口径")

        # 4. MVP 年度统计 → 2016-2019 回退口径（全部赛事 / 仅大赛）
        fallback_label = "全部赛事" if mvp_fallback == "all" else "仅大赛"
        self.mvp_count = defaultdict(int)   # (pid, year) -> count
        for r in load_sheet(wb, "MVP年度统计"):
            if (r.get("口径") or "").strip() != fallback_label:
                continue
            pid = int(r["选手ID"])
            for y in range(2012, 2027):
                v = r.get(str(y))
                if isinstance(v, (int, float)) and v > 0:
                    self.mvp_count[(pid, y)] = int(v)

        # 5. career type=1 与 MVP 年度统计交叉验证（2020-2025）
        log("career type=1 与 MVP年度统计 交叉验证（2020-2025 逐年总数）:")
        for y in range(2020, 2026):
            career_n = type1_yearly.get(y, 0)
            sheet_n = sum(c for (pp, yy), c in self.mvp_count.items() if yy == y)
            log(f"  {y}: career_type1={career_n}  MVP表={sheet_n}")

        # 6. 按年缓存特征矩阵
        self.year_cache = {}
        for y in train_years:
            self._build_year(y)

        wb.close()
        log("数据加载完成\n")

    def _build_year(self, year):
        """构建单年特征矩阵并缓存（z-score 归一化与参数无关，可预计算）"""
        pool = sorted({pp for (pp, y) in self.perf if y == year})
        if not pool:
            self.year_cache[year] = None
            return
        P = [self.perf[(pid, year)] for pid in pool]
        n = len(pool)

        cMaj = np.zeros(n); cSup = np.zeros(n); cOth = np.zeros(n)
        eMaj = np.zeros(n); eSup = np.zeros(n); eOth = np.zeros(n)
        mvp_fb = np.zeros(n)
        pChamp = np.zeros(n); pRunner = np.zeros(n)
        pSemi = np.zeros(n); pQuarter = np.zeros(n)

        for i, pid in enumerate(pool):
            # 逐赛事 MVP/EVP（2020+）
            if year >= EVP_YEAR_START:
                for e in self.mvp_events.get((pid, year), []):
                    t = event_tier(e)
                    if t == "major":
                        cMaj[i] += 1
                    elif t == "super":
                        cSup[i] += 1
                    else:
                        cOth[i] += 1
                for e in self.evp_events.get((pid, year), []):
                    t = event_tier(e)
                    if t == "major":
                        eMaj[i] += 1
                    elif t == "super":
                        eSup[i] += 1
                    else:
                        eOth[i] += 1
            else:
                mvp_fb[i] = self.mvp_count.get((pid, year), 0)
            # 队伍名次（按分级计数）：TEAM_PLACE_YEAR_START 起用战队口径，此前沿用选手生涯
            if year >= TEAM_PLACE_YEAR_START and year in self.team_data_years:
                for tier in self.places_team.get((pid, year), []):
                    if tier == "champ":
                        pChamp[i] += 1
                    elif tier == "runner":
                        pRunner[i] += 1
                    elif tier == "semi":
                        pSemi[i] += 1
                    elif tier == "quarter":
                        pQuarter[i] += 1
            else:
                for txt in self.places.get((pid, year), []):
                    tier = placement_tier(txt)
                    if tier == "champ":
                        pChamp[i] += 1
                    elif tier == "runner":
                        pRunner[i] += 1
                    elif tier == "semi":
                        pSemi[i] += 1
                    elif tier == "quarter":
                        pQuarter[i] += 1

        self.year_cache[year] = dict(
            pids=np.array(pool),
            zr=zscore([x["rating"] for x in P]),
            zk=zscore([x["kast"] for x in P]),
            za=zscore([x["adr"] for x in P]),
            zi=zscore([x["impact"] for x in P]),
            zw=zscore([x["winrate"] for x in P]),
            zfb=zscore([x["fb_pm"] for x in P]),
            zmk=zscore([x["mk_pm"] for x in P]),
            zcl=zscore([x["cl_pm"] for x in P]),
            cMaj=cMaj, cSup=cSup, cOth=cOth,
            eMaj=eMaj, eSup=eSup, eOth=eOth, mvp_fb=mvp_fb,
            pChamp=pChamp, pRunner=pRunner, pSemi=pSemi, pQuarter=pQuarter,
            pool_index={pid: i for i, pid in enumerate(pool)},
        )

    # ---------- 评分与评估 ----------
    def year_scores(self, year, p):
        """返回 {pid: score}；池外选手（无 5E 数据）不在其中"""
        c = self.year_cache.get(year)
        if c is None:
            return {}
        perf = (p["wr"] * c["zr"] + p["wk"] * c["zk"] + p["wa"] * c["za"]
                + p["wi"] * c["zi"] + p["wwr"] * c["zw"])
        if year >= EVP_YEAR_START:
            honor_raw = (c["cMaj"] * p["m_major"] + c["cSup"] * p["m_super"] + c["cOth"]
                         + p["evp_ratio"] * (c["eMaj"] * p["m_major"]
                                             + c["eSup"] * p["m_super"] + c["eOth"]))
        else:
            honor_raw = c["mvp_fb"].copy()
        team_raw = (c["pChamp"] * p["v_champ"] + c["pRunner"] * p["v_runner"]
                    + c["pSemi"] * p["v_semi"] + c["pQuarter"] * p["v_quarter"])
        sec = p["w1"] * c["zfb"] + p["w2"] * c["zmk"] + p["w3"] * c["zcl"]
        score = (p["Wp"] * perf + p["Wh"] * zscore(honor_raw)
                 + p["Wt"] * zscore(team_raw) + p["Ws"] * sec)
        return dict(zip(c["pids"].tolist(), score.tolist()))

    def eval_years(self, p, years, detail=False):
        """评估若干年：返回 (Spearman均值, MAE均值)；detail=True 时返回逐年明细"""
        sp_list, mae_list, details = [], [], []
        for y in years:
            scores = self.year_scores(y, p)
            officials = self.gt.get(y, {})
            if not scores or not officials:
                continue
            pool_min = min(scores.values()) if scores else 0.0
            all_pids = list(scores.keys()) + [pid for pid in officials if pid not in scores]
            all_scores = list(scores.values()) + [pool_min - 1.0] * len(
                [pid for pid in officials if pid not in scores])
            # 预测名次（分高=名次1）
            order = np.argsort([-s for s in all_scores], kind="stable")
            pred_rank = np.empty(len(all_scores))
            pred_rank[order] = np.arange(1, len(all_scores) + 1)
            rank_map = dict(zip(all_pids, pred_rank.tolist()))

            o_ranks = np.array([officials[pid] for pid in officials])
            p_ranks = np.array([rank_map[pid] for pid in officials])
            n_data = sum(1 for pid in officials if pid in scores)
            # Spearman：官方名次 vs 预测名次（都为1=最好，正相关越高越好）
            d = o_ranks - p_ranks
            sp = 1 - 6 * (d ** 2).sum() / (len(d) * (len(d) ** 2 - 1))
            mae = np.abs(d).mean()
            sp_list.append(sp)
            mae_list.append(mae)
            if detail:
                # Top5 重叠
                off_top5 = {pid for pid, rk in officials.items() if rk <= 5}
                pred_top5 = set(all_pids[i] for i in order[:5])
                details.append(dict(
                    year=y, n_officials=len(officials), n_with_data=n_data,
                    spearman=round(float(sp), 3), mae=round(float(mae), 2),
                    top5_overlap=len(off_top5 & pred_top5),
                ))
        if detail:
            return float(np.mean(sp_list)), float(np.mean(mae_list)), details
        return float(np.mean(sp_list)), float(np.mean(mae_list))


def make_objective(ds, train_years):
    def objective(vec):
        p = decode(vec)
        sp, _ = ds.eval_years(p, train_years)
        return -sp
    return objective


def fit(ds, train_years, label):
    """差分进化拟合，返回 (解码参数, 训练集Spearman)"""
    obj = make_objective(ds, train_years)
    result = differential_evolution(
        obj, BOUNDS, seed=SEED, maxiter=80, popsize=24,
        tol=1e-8, polish=False, init="sobol",
    )
    p = decode(result.x)
    sp, mae = ds.eval_years(p, train_years)
    log(f"[{label}] 训练集: Spearman={sp:.3f}, MAE={mae:.2f} 名")
    return p, sp, mae


def main():
    import argparse
    ap = argparse.ArgumentParser(description="HLTV Top20 排名逻辑参数拟合")
    ap.add_argument("--year-start", type=int, default=2016, help="训练起始年（默认2016）")
    ap.add_argument("--mvp-fallback", choices=["all", "big"], default="all",
                    help="2016-2019 荣誉回退口径：all=全部赛事 / big=仅大赛")
    ap.add_argument("--tag", default="", help="输出 JSON 文件名后缀")
    args = ap.parse_args()

    train_years = list(range(args.year_start, 2026))
    xlsx_list = sorted(glob.glob(os.path.join(BASE_DIR, "data", "CS2选手排名数据_*.xlsx")))
    if not xlsx_list:
        print("未找到 data/CS2选手排名数据_*.xlsx，请先运行 crawler.py")
        sys.exit(1)
    ds = Dataset(xlsx_list[-1], train_years, mvp_fallback=args.mvp_fallback)

    # 各年 Top20 成员的 5E 数据覆盖率
    log("各年 Top20 成员数据覆盖率:")
    for y in train_years:
        officials = ds.gt.get(y, {})
        n_data = sum(1 for pid in officials if (pid, y) in ds.perf)
        log(f"  {y}: {n_data}/{len(officials)}")

    # 1. 全量拟合
    log("\n=== 全量拟合（训练年: %d-%d）===" % (train_years[0], train_years[-1]))
    p_full, sp_full, mae_full = fit(ds, train_years, "全量")
    sp_d, mae_d, details = ds.eval_years(p_full, train_years, detail=True)
    log("\n全量拟合逐年明细:")
    log("  年份  有数据/总数  Spearman  MAE   Top5重叠")
    for d in details:
        log(f"  {d['year']}  {d['n_with_data']:3d}/{d['n_officials']:3d}     "
            f"{d['spearman']:+.3f}    {d['mae']:5.2f}   {d['top5_overlap']}/5")

    # 2. 留一年验证
    log("\n=== 留一年验证（leave-one-year-out）===")
    loyo = []
    for held in train_years:
        train = [y for y in train_years if y != held]
        p_h, _, _ = fit(ds, train, f"留出{held}")
        sp_h, mae_h = ds.eval_years(p_h, [held])
        loyo.append(dict(year=held, spearman=round(sp_h, 3), mae=round(mae_h, 2)))
        log(f"  留出 {held}: Spearman={sp_h:+.3f}, MAE={mae_h:.2f} 名")
    sp_mean = float(np.mean([x["spearman"] for x in loyo]))
    sp_std = float(np.std([x["spearman"] for x in loyo]))
    mae_mean = float(np.mean([x["mae"] for x in loyo]))
    log(f"留一年汇总: Spearman={sp_mean:.3f}±{sp_std:.3f}, MAE={mae_mean:.2f} 名")

    # 3. 输出参数
    log("\n=== 拟合参数（全量） ===")
    for k in PARAM_NAMES:
        log(f"  {k:12s} = {p_full[k]:.4f}")
    comp = f"Wp(表现)={p_full['Wp']:.2f}  Wh(荣誉)={p_full['Wh']:.2f}  " \
           f"Wt(队伍)={p_full['Wt']:.2f}  Ws(次级)={p_full['Ws']:.2f}"
    log(f"组件权重: {comp}")

    # 4. 保存 JSON
    out = dict(
        fitted_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        xlsx=os.path.basename(xlsx_list[-1]),
        train_years=train_years,
        mvp_fallback=args.mvp_fallback,
        min_maps=MIN_MAPS,
        seed=SEED,
        params={k: round(v, 4) for k, v in p_full.items()},
        component_weights=dict(Wp=round(p_full["Wp"], 3), Wh=round(p_full["Wh"], 3),
                               Wt=round(p_full["Wt"], 3), Ws=round(p_full["Ws"], 3)),
        train_spearman=round(sp_full, 3), train_mae=round(mae_full, 2),
        per_year=details,
        loyo=loyo,
        loyo_spearman_mean=round(sp_mean, 3), loyo_spearman_std=round(sp_std, 3),
        loyo_mae_mean=round(mae_mean, 2),
    )
    tag = f"_{args.tag}" if args.tag else ""
    out_path = os.path.join(BASE_DIR, f"fitted_params{tag}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    log(f"\n结果已保存: {out_path}")


if __name__ == "__main__":
    main()
