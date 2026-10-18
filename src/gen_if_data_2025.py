# -*- coding: utf-8 -*-
"""
采集 2025 年赛事数据，生成 If 线模拟器可直接导入的 Excel。

管线（完美世界 API）：
  1. 扫描 eventId 区间 → getEventDetail 发现 2025 年赛事（prizeList 非空、排除预选赛）
  2. getMatchList(eventId) → 全部比赛 → getMatchPlayerStats(namiMatchId) 逐图选手数据
  3. 聚合：每选手每赛事 Rating/ADR/KPR（按回合数加权）、队伍、出场图数
  4. 队伍名次：prizeList rank → 冠军/亚军/四强/八强/小组淘汰
  5. MVP/EVP：从采集 Excel 的 career 荣誉按赛事名模糊匹配；EVP 顺位按赛事 Rating 降序
  6. 另输出 HLTV 2025 官方 Top20 基准文件

输出：
  data/if_sim_2025_events.xlsx    （模拟器"导入赛事数据"）
  data/if_sim_2025_baseline.xlsx  （模拟器"导入 HLTV 原版 Top20"）

运行：.venv\\Scripts\\python.exe src\\gen_if_data_2025.py [--year 2024]
"""
import argparse
import datetime
import glob
import os
import re
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crawler import wm_get, fetch_wm_top20, log

try:
    import openpyxl
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
except ImportError:
    print("缺少 openpyxl"); sys.exit(1)

_ap = argparse.ArgumentParser()
_ap.add_argument("--year", type=int, default=2025)
YEAR = _ap.parse_known_args()[0].year

# 项目根 = src/ 的上一级（data/ 与采集 Excel 都在根目录下）
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 各年份 eventId 扫描区间（KNOWN_EVENT_IDS 为空时才扫描）
ID_RANGES = {
    2024: range(6000, 7905),
    2025: range(7500, 9100),
}
ID_RANGE = ID_RANGES.get(YEAR, range(6000, 9100))
SLEEP = 0.35
MIN_PLAYERS = 20                  # 赛事最少有统计的选手数，否则丢弃
MIN_PRIZE_USD = 200000            # 最低奖金（美元），过滤小型赛事

# 已知赛事（2026-10-13 扫描结果），非空则跳过扫描直接采集
KNOWN_BY_YEAR = {
    2025: [
        7909, 8034, 8043, 7904, 7911, 8044, 8062, 8036, 7905, 8435,
        8045, 8037, 7902, 8063, 8038, 7910, 8039, 7912, 8064, 8539,
        8040, 8027, 8067, 8046, 8041, 7908, 8068, 8042,
    ],
}
KNOWN_EVENT_IDS = KNOWN_BY_YEAR.get(YEAR, [])

# 排除的赛事名关键词（预选赛/地区赛/阶段赛）
EXCLUDE_KW = ["qualifier", "regional", "席位", "stage 1", "stage 2", "stage 3",
              "play-in", "open qualifier", "closed qualifier", "rmr", "showdown"]

OUT_EVENTS = os.path.join(BASE, "data", f"if_sim_{YEAR}_events.xlsx")
OUT_BASELINE = os.path.join(BASE, "data", f"if_sim_{YEAR}_baseline.xlsx")

HEADER_FILL = PatternFill("solid", fgColor="305496")
HEADER_FONT = Font(bold=True, color="FFFFFF")


# ---------- 赛事分级 ----------
def prize_usd(prize):
    """'$1,250,000' -> 1250000"""
    m = re.sub(r"[^0-9]", "", prize or "")
    return int(m) if m else 0


def classify_level(name):
    n = (name or "").lower()
    if "major" in n:
        return "Major"
    if "katowice" in n or "cologne" in n or "卡托" in n or "科隆" in n:
        return "超级精英赛"
    if "world final" in n or "pro league" in n:
        return "精英赛"
    if ("iem" in n or "blast" in n or "esl" in n or "pgl" in n
            or "esports world cup" in n or "电竞世界杯" in n):
        return "大型赛事"
    return "中型赛事"


def rank_to_placement(rank_text):
    """prizeList 名次文本 → 名次档，按该档的最好名次归类：
    1st→冠军，2nd→亚军，3rd / 4th / 3-4th→四强，5-6th / 7-8th / 5-8th→八强，其余→小组淘汰。

    旧版只认 "1st / 2nd / 3-4 / 5-8" 四种写法：IEM 等 6 队淘汰赛的 5-6 名、
    有季军赛的 3rd / 4th 都被当成了小组淘汰（−1 分）。
    """
    t = (rank_text or "").strip()
    if "冠军" in t:
        return "冠军"
    if "亚军" in t:
        return "亚军"
    if "季军" in t or "殿军" in t:
        return "四强"
    m = re.match(r"\D*(\d+)", t)
    if not m:
        return "小组淘汰"
    best = int(m.group(1))
    if best == 1:
        return "冠军"
    if best == 2:
        return "亚军"
    if best <= 4:
        return "四强"
    if best <= 8:
        return "八强"
    return "小组淘汰"


def norm_name(s):
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", (s or "").lower())


# ---------- 带封禁等待的请求封装 ----------
def wm_get_safe(path, params, retries=4):
    """wm_get 的 403/临时封禁重试版"""
    for i in range(retries):
        try:
            return wm_get(path, params)
        except Exception as e:
            msg = str(e)
            if "banned" in msg or "403" in msg or "None" in msg:
                wait = 30 * (i + 1)
                log(f"  ! 疑似封禁/限流，等待 {wait}s 后重试 ({i + 1}/{retries})")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError(f"{path} 多次重试仍失败")


# ---------- 1. 扫描发现赛事 ----------
def discover_events():
    if KNOWN_EVENT_IDS:
        log(f"使用已知赛事列表（{len(KNOWN_EVENT_IDS)} 个），拉取详情 ...")
        events = {}
        for i, eid in enumerate(KNOWN_EVENT_IDS, 1):
            try:
                r = wm_get_safe("/event/getEventDetail", {"eventId": eid})
            except Exception as e:
                log(f"  ! id={eid} 详情失败: {e}")
                continue
            ed = r.get("eventDetail") or {}
            events[eid] = ed
            st = ed.get("startTime")
            d = datetime.datetime.fromtimestamp(st / 1000).strftime("%m-%d") if st else "??"
            log(f"  [{i}/{len(KNOWN_EVENT_IDS)}] [{d}] id={eid} {ed.get('name')} prize={ed.get('prize')}")
            time.sleep(SLEEP)
        return events

    log(f"扫描 eventId {ID_RANGE.start}~{ID_RANGE.stop - 1} ...")
    events = {}
    for i, eid in enumerate(ID_RANGE, 1):
        try:
            # 用防封禁版：长扫描遇到 IP 临时封禁时静默跳过会丢赛事
            r = wm_get_safe("/event/getEventDetail", {"eventId": eid})
        except Exception as e:
            # 不存在的 id 会直接报错，照常静默跳过；封禁重试用尽则必须提示，否则会悄悄丢赛事
            if "多次重试仍失败" in str(e):
                log(f"  ! id={eid} 多次重试仍失败，已跳过（该赛事可能丢失）")
            time.sleep(SLEEP)
            continue
        ed = r.get("eventDetail") or {}
        st = ed.get("startTime")
        if not st:
            time.sleep(SLEEP)
            continue
        dt = datetime.datetime.fromtimestamp(st / 1000)
        if dt.year == YEAR:
            name = ed.get("name") or ""
            name_zh = ed.get("nameZh") or ""
            low = (name + " " + name_zh).lower()
            if any(k in low for k in EXCLUDE_KW):
                time.sleep(SLEEP)
                continue
            if not (ed.get("prizeList") or []):
                time.sleep(SLEEP)
                continue
            if prize_usd(ed.get("prize")) < MIN_PRIZE_USD:
                time.sleep(SLEEP)
                continue
            events[eid] = ed
            log(f"  [{dt.strftime('%m-%d')}] id={eid} {name} ({name_zh}) prize={ed.get('prize')}")
        if i % 200 == 0:
            log(f"  扫描进度 {i}/{len(ID_RANGE)}，已发现 {len(events)} 个")
        time.sleep(SLEEP)
    log(f"发现 {YEAR} 年赛事 {len(events)} 个")
    return events


# ---------- 2. 单赛事：比赛与选手统计 ----------
def fetch_event_matches(eid):
    r = wm_get_safe("/event/getMatchList", {"eventId": eid})
    return (r.get("matchResponse") or {}).get("dtoList") or []


def aggregate_player_stats(matches):
    """逐 match 调 getMatchPlayerStats，聚合 (playerId -> 加权统计)。

    返回 stats: {playerId: {kills, rounds, adr_w, rating_w, kast_w,
                            adr_rounds, rating_rounds, kast_rounds, maps,
                            name, teams:{teamId:maps},
                            series:[(date_ms, rating, rounds), ...]}}
    *_w 为按回合加权的和，*_rounds 为对应指标有值的回合数（缺失的图不进分母）。

    series 保留**逐图时间序列**（比赛 startTime + 图序号），用于构造"稳定性"信号。
    中段（官方 7-20 名）复现的主要瓶颈是缺少"全年聚合稳定性"维度，
    而逐图 rating 的波动正是该维度的直接代理 —— 聚合时若丢弃时间维度就无法恢复。
    """
    stats = defaultdict(lambda: dict(kills=0, rounds=0, adr_w=0.0, rating_w=0.0,
                                     kast_w=0.0, adr_rounds=0, rating_rounds=0,
                                     kast_rounds=0, maps=0, name="", teams=defaultdict(int),
                                     series=[]))
    # 三套战队 ID 命名空间：
    #   stats 里的 p.teamId（nami 内部 id）≠ match 的 team1Id/team2Id（HLTV id）
    #   ＝ prizeList 的 teamId（HLTV id）
    # 已验证：homePlayerStats ↔ team1Id，awayPlayerStats ↔ team2Id（Austin Major 决赛）
    # teams 直接按 HLTV id 记录，与 prizeList/teamDTO 对齐
    n_calls = 0
    for m in matches:
        nami = m.get("namiMatchId")
        if not nami:
            continue
        # 已完成比赛才有数据（比分非空）
        if m.get("score1") is None or m.get("score2") is None:
            continue
        try:
            maps = wm_get_safe("/match/getMatchPlayerStats", {"namiId": nami}) or []
        except Exception as e:
            log(f"  ! 比赛 namiId={nami} 取数失败，已跳过: {e}")
            time.sleep(SLEEP)
            continue
        n_calls += 1
        t1, t2 = m.get("team1Id"), m.get("team2Id")
        # 比赛开始时间（毫秒）作为该场所有图的时间锚点；缺失则记为 None
        match_ts = m.get("startTime")
        for entry in maps:
            hs, as_ = entry.get("homeScore"), entry.get("awayScore")
            if not isinstance(hs, int) or not isinstance(as_, int):
                continue
            rounds = hs + as_
            if rounds <= 0:
                continue
            # 图序号：boxNum 为该图在 BO 中的次序（1 起），缺失则退化为列表序号
            box = entry.get("boxNum")
            if not isinstance(box, int):
                box = maps.index(entry) + 1
            for side, hltv_tid in (("homePlayerStats", t1), ("awayPlayerStats", t2)):
                for p in entry.get(side) or []:
                    pid = p.get("playerId")
                    if not pid:
                        continue
                    s = stats[pid]
                    s["name"] = p.get("name") or s["name"]
                    s["kills"] += p.get("kill") or 0
                    s["rounds"] += rounds
                    s["maps"] += 1
                    r = p.get("rating")
                    # 缺失的指标不进该指标的分母，否则没有 rating 的图会把平均值往 0 拉
                    for key, v in (("adr", p.get("adr")), ("rating", r), ("kast", p.get("kast"))):
                        if v is not None:
                            s[f"{key}_w"] += float(v) * rounds
                            s[f"{key}_rounds"] += rounds
                    # 逐图时间序列：保留 (时间锚点, 图序, rating, 回合数)
                    if r is not None:
                        s["series"].append((match_ts, box, float(r), rounds))
                    if hltv_tid:
                        s["teams"][hltv_tid] += 1
        time.sleep(SLEEP)
    return stats, n_calls


def stability_metrics(series):
    """由逐图时间序列算"稳定性"特征。

    返回 dict：
      maps         参与统计的图数
      mean_r       逐图 rating 均值（未加权）
      std_r        逐图 rating 标准差（越小越稳定）
      cv           变异系数 std/mean
      first_half   前半程平均 rating（按时间序）
      second_half  后半程平均 rating
      trend        后半程 − 前半程（正值=越打越好）
      n_halves     是否够长可分段
    """
    vals = [(ts if ts else 0, box, r) for ts, box, r, _ in series]
    if not vals:
        return None
    # 按 (时间, 图序) 排序，还原比赛顺序
    vals.sort(key=lambda x: (x[0], x[1]))
    rs = [r for _, _, r in vals]
    n = len(rs)
    mean_r = sum(rs) / n
    if n >= 2:
        var = sum((x - mean_r) ** 2 for x in rs) / n
        std_r = var ** 0.5
    else:
        std_r = 0.0
    half = n // 2
    first = sum(rs[:half]) / half if half else mean_r
    second = sum(rs[half:]) / (n - half) if (n - half) else mean_r
    return dict(
        maps=n,
        mean_r=round(mean_r, 4),
        std_r=round(std_r, 4),
        cv=round(std_r / mean_r, 4) if mean_r else 0.0,
        first_half=round(first, 4),
        second_half=round(second, 4),
        trend=round(second - first, 4),
        n_halves=1 if n >= 2 else 0,
    )


# ---------- 3. career 荣誉（MVP/EVP） ----------
def load_career_honors():
    """从最新采集 Excel 读历年生涯荣誉，返回 {规范赛事名: {"mvp": pid, "evp": [pid...]}}（仅 YEAR）"""
    xlsx_list = sorted(glob.glob(os.path.join(BASE, "data", "CS2选手排名数据_*.xlsx")))
    if not xlsx_list:
        log("! 未找到采集 Excel，荣誉将为空")
        return {}
    wb = openpyxl.load_workbook(xlsx_list[-1], read_only=True)
    if "历年生涯荣誉" not in wb.sheetnames:
        wb.close()
        return {}
    ws = wb["历年生涯荣誉"]
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    wb.close()
    header = rows[0]
    honors = defaultdict(lambda: {"mvp": None, "evp": []})
    for r in rows[1:]:
        d = dict(zip(header, r))
        date = str(d.get("日期") or "")
        if not date.startswith(str(YEAR)):
            continue
        # str()：采集 Excel 可能把纯数字的名字存成数字（如选手 "910"）
        ev = str(d.get("赛事名") or "").strip()
        if not ev:
            continue
        key = norm_name(ev)
        pid = d.get("选手ID")
        name = str(d.get("选手") or "").strip()
        t = d.get("类型")
        if t == 1:
            honors[key]["mvp"] = (pid, name)
        elif t == 5:
            honors[key]["evp"].append((pid, name))
    log(f"career 荣誉：{YEAR} 年共 {len(honors)} 个赛事有 MVP/EVP 记录")
    return honors


def match_honor(honors, event_name, event_name_zh):
    """按名称模糊匹配 career 荣誉"""
    k1 = norm_name(event_name)
    k2 = norm_name(event_name_zh)
    for key, h in honors.items():
        if not key:
            continue
        # k1 / k2 为空时不能参与比较：空串是任何字符串的子串，会匹配到任意赛事
        if (k1 and (key in k1 or k1 in key)) or (k2 and (key in k2 or k2 in key)):
            return h
    return None


# ---------- 4. 基准 ----------
def fetch_baseline():
    top20 = fetch_wm_top20()
    out = []
    for p in top20.get("allHltvTop20Players") or []:
        name = p.get("playerName") or p.get("name")
        pid = p.get("playerId")
        for h in p.get("honorList") or []:
            if h.get("id") == YEAR:
                out.append((int(h.get("rank")), name, pid))
    out.sort()
    return out


# ---------- Excel 输出 ----------
def write_xlsx(path, header, rows, note=None):
    wb = Workbook()
    ws = wb.active
    ws.title = "data"
    start = 1
    if note:
        ws.cell(row=1, column=1, value=note).font = Font(italic=True, color="808080")
        start = 2
    for c, h in enumerate(header, 1):
        cell = ws.cell(row=start, column=c, value=h)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
    for i, row in enumerate(rows, start + 1):
        for c, v in enumerate(row, 1):
            ws.cell(row=i, column=c, value=v)
    wb.save(path)


# ---------- 4b. HLTV 对手强度（可选，来自 fetch_hltv_opponents.py） ----------
def load_hltv_opponent(year):
    """读 data/hltv_opponent_<year>.xlsx，返回 {规范名: {vsTop5:..., ...}}。

    该文件由 fetch_hltv_opponents.py 通过 Edge CDP 采集（HLTV 有 CF 保护，
    纯 HTTP 拿不到）。缺失时返回空 dict，导出仍可正常进行。

    重要：必须按**选手名** join。赛事数据里的选手ID 是 nami 比赛接口的口径
    （例如 ZywOo 是 10340），而 HLTV 选手页用的是 HLTV ID（ZywOo 是 11893，
    与完美主站、5E 的 ID 相同），两者直接按 ID join 会错配。
    """
    path = os.path.join(BASE, "data", f"hltv_opponent_{year}.xlsx")
    if not os.path.exists(path):
        log(f"! 未找到 {path}，vsTopN 列将为空"
            f"（可用 fetch_hltv_opponents.py 采集）")
        return {}
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    hdr = [str(h).strip() if h is not None else "" for h in rows[0]]
    keys = ["vsTop5", "vsTop10", "vsTop20", "vsTop30", "vsTop50"]
    out = {}
    for r in rows[1:]:
        if not r or all(v is None for v in r):
            continue
        d = dict(zip(hdr, r))
        nm = norm_name(str(d.get("选手") or ""))
        if not nm:
            continue
        rec = {}
        for k in keys:
            v = d.get(k)
            try:
                rec[k] = float(v) if v is not None and str(v).strip() != "" else None
            except (TypeError, ValueError):
                rec[k] = None
        out[nm] = rec
    log(f"HLTV 对手强度：{year} 年载入 {len(out)} 人")
    return out


# ---------- 主流程 ----------
def main():
    log(f"=== 采集 {YEAR} 年赛事数据（If 模拟器格式）===")

    # 1. 发现赛事
    events = discover_events()

    # 2. career 荣誉
    honors = load_career_honors()

    # 2b. HLTV 对手强度（可选）
    hltv_opp = load_hltv_opponent(YEAR)

    # 3. 逐赛事采集
    all_rows = []
    event_summary = []
    for idx, (eid, ed) in enumerate(sorted(events.items(), key=lambda x: x[1].get("startTime") or 0), 1):
        name = ed.get("name") or ""
        name_zh = ed.get("nameZh") or ""
        level = classify_level(name)
        log(f"[{idx}/{len(events)}] {name} (id={eid}, {level})")

        try:
            matches = fetch_event_matches(eid)
        except Exception as e:
            log(f"  ! getMatchList 失败: {e}")
            continue
        time.sleep(SLEEP)

        stats, n_calls = aggregate_player_stats(matches)
        log(f"  比赛 {len(matches)} 场（取数 {n_calls}），选手 {len(stats)} 人")
        if len(stats) < MIN_PLAYERS:
            log(f"  ! 选手数不足 {MIN_PLAYERS}，跳过")
            continue

        # 队伍名次
        team_place = {}
        for p in ed.get("prizeList") or []:
            tid = p.get("teamId")
            if tid:
                team_place[tid] = rank_to_placement(p.get("rank"))

        # 队伍名映射（从比赛的 teamDTO）
        team_names = {}
        for m in matches:
            for tk, dk in (("team1Id", "team1DTO"), ("team2Id", "team2DTO")):
                tid = m.get(tk)
                dto = m.get(dk) or {}
                if tid and dto.get("name"):
                    team_names[tid] = dto.get("name")

        # MVP/EVP：career 的选手ID 是完美主站命名空间，与 getMatchPlayerStats
        # 的 nami 命名空间不同（ZywOo: 11893 vs 10340），必须按选手名映射
        by_name = {norm_name(s["name"]): pid for pid, s in stats.items() if s["name"]}
        h = match_honor(honors, name, name_zh) or {"mvp": None, "evp": []}
        mvp_pid = by_name.get(norm_name(h["mvp"][1])) if h["mvp"] else None
        evp_pids = []
        for _cpid, cname in h["evp"]:
            sp = by_name.get(norm_name(cname))
            if sp and sp != mvp_pid and sp not in evp_pids:
                evp_pids.append(sp)
        # EVP 顺位：按本赛事 Rating 降序取前 3
        def ev_rating(pid):
            s = stats.get(pid)
            return (s["rating_w"] / s["rating_rounds"]) if s and s["rating_rounds"] else 0
        evp_pids = sorted(evp_pids, key=ev_rating, reverse=True)[:3]
        if mvp_pid:
            log(f"  MVP={stats[mvp_pid]['name']} EVP={[stats[p]['name'] for p in evp_pids]}")
        else:
            log(f"  ! 未匹配到 MVP 记录（可导入后手动补）")

        rows = []
        for pid, s in stats.items():
            if s["rounds"] <= 0:
                continue
            # 主队伍：出场最多的队
            tid = max(s["teams"].items(), key=lambda x: x[1])[0] if s["teams"] else None
            team = team_names.get(tid, "")
            place = team_place.get(tid, "小组淘汰")
            rating = round(s["rating_w"] / s["rating_rounds"], 2) if s["rating_rounds"] else 0.0
            adr = round(s["adr_w"] / s["adr_rounds"], 1) if s["adr_rounds"] else 0.0
            kpr = round(s["kills"] / s["rounds"], 2)
            if pid == mvp_pid:
                honor, hrank = "MVP", 1
            elif pid in evp_pids:
                honor, hrank = "EVP", evp_pids.index(pid) + 1
            else:
                honor, hrank = "无", 0
            # 稳定性特征（逐图时间序列）
            st = stability_metrics(s.get("series") or []) or {}
            # HLTV 对手强度（按选手名 join；缺则该行留空）
            op = hltv_opp.get(norm_name(s["name"])) or {}
            rows.append([YEAR, name, level, None, pid, s["name"], team,
                         place, honor, hrank, rating, adr, kpr, s["maps"],
                         st.get("std_r"), st.get("cv"),
                         st.get("trend"), st.get("maps"),
                         op.get("vsTop5"), op.get("vsTop10"), op.get("vsTop20"),
                         op.get("vsTop30"), op.get("vsTop50")])
        # 排序：名次 → Rating 降序
        porder = {"冠军": 0, "亚军": 1, "四强": 2, "八强": 3, "小组淘汰": 4}
        rows.sort(key=lambda r: (porder.get(r[7], 9), -r[10]))
        all_rows.extend(rows)
        event_summary.append((name, level, len(rows)))
        log(f"  行数 {len(rows)}")

    if not all_rows:
        log("! 无数据，终止")
        return

    header = ["年份", "赛事名称", "赛事级别", "赛事权重", "选手ID", "选手名", "队伍",
              "队伍名次", "荣誉类型", "荣誉顺位", "Rating", "ADR", "KPR", "地图数",
              "Rating标准差", "Rating变异系数", "前后半程差", "逐图样本数",
              "vsTop5", "vsTop10", "vsTop20", "vsTop30", "vsTop50"]
    # 注意：不能加说明行，模拟器把第 1 行当表头解析
    write_xlsx(OUT_EVENTS, header, all_rows)
    log(f"\n赛事数据已写出: {OUT_EVENTS}（{len(all_rows)} 行，{len(event_summary)} 个赛事）")

    # 4. HLTV 基准
    try:
        baseline = fetch_baseline()
        if baseline:
            # 模拟器基准格式：年份/名次/选手名（选手ID 为附加列，解析时忽略）
            write_xlsx(OUT_BASELINE, ["年份", "名次", "选手名", "选手ID"],
                       [[YEAR, rk, name, pid] for rk, name, pid in baseline])
            log(f"基准已写出: {OUT_BASELINE}（{len(baseline)} 人）")
        else:
            log(f"! {YEAR} 官方 Top20 为空")
    except Exception as e:
        log(f"! 基准获取失败: {e}")

    log("\n=== 赛事汇总 ===")
    for name, level, n in event_summary:
        log(f"  [{level}] {name}: {n} 人")


if __name__ == "__main__":
    main()
