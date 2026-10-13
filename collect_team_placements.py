# -*- coding: utf-8 -*-
"""
战队口径赛事名次采集器（补冠军数据源）

背景：完美 player/career 的 type4 队伍名次存在两个缺陷：
  1. 无"冠军"字样——冠军要么缺失（夺冠选手该赛事无 type4 记录），要么混在"1-2名"里
  2. 因此 fit_ranking 的队伍名次组件无法识别冠军，Wt 权重坍缩
方案：team/career 接口提供 2020+ 明确的"冠军"名次 + 当时5人阵容，
  按"选手 ∈ 阵容"归属名次，重建干净的 (选手, 赛事) → 名次 数据。

流程：
  1. /player/top20 → 历年 Top20 选手集合
  2. /player/career × N → 选手生涯事件（含赛事ID、阵容）用于覆盖率校验
  3. /team/rank（当前 top30）+ /match/fuzzySearch（历史强队按名索 id）→ 候选战队
  4. /team/career × M → (赛事, 名次[含冠军], 阵容)
  5. 覆盖率校验：选手生涯 2021-2025 非预选赛事件，是否被战队数据覆盖
输出：data/team_placements.json

运行：.venv\\Scripts\\python.exe collect_team_placements.py
"""
import os
import re
import sys
import json
import time
import datetime
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crawler import wm_get, ms_to_date, log

OUT_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "data", "team_placements.json")
TEAM_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "data", "team_career_cache.json")
SLEEP = 0.35
SLEEP_TEAM = 0.8          # team/career 限速更敏感，加大间隔


def fetch_team_career(tid, retries=4):
    """带指数退避的 team/career 获取（该接口易触发限速）"""
    for attempt in range(retries):
        try:
            time.sleep(SLEEP_TEAM)
            return wm_get("/team/career", {"teamId": tid}) or []
        except Exception:
            if attempt == retries - 1:
                raise
            wait = 3 * (attempt + 1)
            log(f"    team {tid} 第 {attempt + 1} 次失败，{wait}s 后重试")
            time.sleep(wait)

# 历史强队按名检索（当前 team/rank top30 之外的 2020-2025 相关队伍）
# 注意：fuzzySearch 对含空格/特殊字符的全名会报 1004，统一用短特征词
TEAM_SEARCH_NAMES = [
    "Gambit", "Heroic", "Astralis", "Virtus.pro", "FaZe", "Cloud9",
    "G2", "ENCE", "fnatic", "Liquid", "BIG", "Entropiq", "Falcons",
    "3DMAX", "paiN", "FURIA", "Complexity", "MIBR", "Imperial", "Monte",
    "GamerLegion", "SAW", "OG", "Apeks", "9INE", "forZe", "Aurora",
    "TYLOO", "HAVU", "Endpoint",
    # 短词检索（全名搜索会失败）：永恒之火/蒙古/ Lynn Vision / Rare Atom / Outsiders
    "Eternal", "Mongol", "Lynn", "Rare", "Outsiders",
]
# 预选赛/小组赛/Major阶段赛过滤（中英文；HLTV 口径只计正赛）
QUALIFIER_RE = re.compile(
    r"预选|预赛|资格|入围|封闭|海选|揭幕赛|揭幕战|最后机会|挑战者组|传奇组|"
    r"第一阶段|第二阶段|第三阶段|quarterfinal[s]? *qual|qualifier|qualification|"
    r"play[- ]?in|closed|RMR|showdown|小组赛|groups|play-in|open qual|"
    r"challengers stage|opening stage|legends stage|stage ?[123]|conference",
    re.IGNORECASE)
# 表演/慈善赛过滤（HLTV 不计入）
EXHIBITION_RE = re.compile(
    r"charity|born to be brave|kinguin legends|the draft|"
    r"steelseries invitational cs2 legends", re.IGNORECASE)

# 手工冠军补丁：战队生涯被平台清洗（Gambit）或档案独立（Outsiders）的知名赛事
# 收录规则：该赛事有 MVP/EVP 记录（HLTV 认定为重要赛事）或为 Major
# 阵容 id 已从选手生涯 roster 字段验证（probe10）
MANUAL_CHAMPION_PATCHES = [
    # Gambit 2021（阵容：sh1ro/Ax1Le/HObbit/interz/nafany）
    dict(eventId=5552, eventName="IEM卡托维兹2021", date="2021-02-28", teamName="Gambit"),
    dict(eventId=5219, eventName="IEM 第十六季 夏季赛", date="2021-06-13", teamName="Gambit"),
    dict(eventId=5901, eventName="EPIC联赛 独联体2021", date="2021-06-01", teamName="Gambit"),
    dict(eventId=5604, eventName="BLAST Premier春季决赛-2021", date="2021-06-20", teamName="Gambit"),
    dict(eventId=6070, eventName="IEM秋季赛独联体区", date="2021-10-03", teamName="Gambit"),
    dict(eventId=6018, eventName="V4 Future Sports Festival 2021 Finals", date="2021-11-21", teamName="Gambit"),
    dict(eventId=6334, eventName="2021 Funspark 终极决赛", date="2022-01-24", teamName="Gambit"),
    # Outsiders 里约 Major 2022
    dict(eventId=6586, eventName="IEM里约热内卢Major-2022", date="2022-11-13", teamName="Outsiders"),
]
PATCH_ROSTERS = {
    "Gambit": ([16920, 16555, 8528, 15071, 16921],
               ["sh1ro", "Ax1Le", "HObbit", "interz", "nafany"]),
    "Outsiders": ([13776, 12732, 13239, 16612, 20101],
                  ["Jame", "FL1T", "Qikert", "n0rb3r7", "fame"]),
}
# 搜索失效档案的手工指定 id（fuzzySearch 命中的是同名旧档案，0 记录）
TEAMS_BY_ID = {
    6248: "The MongolZ",   # fuzzySearch "Mongol" 命中的 11482 为失效旧档案
}

COVER_YEAR_START, COVER_YEAR_END = 2021, 2025


def fetch_json(path, params):
    time.sleep(SLEEP)
    return wm_get(path, params)


def main():
    log("=== 战队口径名次采集开始 ===")

    # 1. Top20 选手集合
    top20 = fetch_json("/player/top20", {}) or {}
    players = []
    seen = set()
    for p in top20.get("allHltvTop20Players") or []:
        pid = p.get("playerId")
        if pid and pid not in seen:
            seen.add(pid)
            players.append((pid, p.get("playerName") or p.get("name") or ""))
    log(f"Top20 选手: {len(players)} 人")

    # 2. 选手生涯事件（含赛事ID/阵容）——覆盖率校验用
    player_events = []
    for i, (pid, pname) in enumerate(players, 1):
        try:
            career = fetch_json("/player/career", {"playerId": pid}) or []
        except Exception as e:
            log(f"  ! career {pname}({pid}) 失败: {e}")
            career = []
        for group in career:
            for h in group.get("csHonorList") or []:
                if not h.get("hasEvent"):
                    continue
                ename = (h.get("name") or "").strip()
                player_events.append(dict(
                    playerId=pid, playerName=pname,
                    eventId=h.get("id"), eventName=ename,
                    date=ms_to_date(h.get("timestamp")),
                    type=h.get("type"), rank=h.get("rank") or "",
                    qualifier=bool(QUALIFIER_RE.search(ename)),
                    exhibition=bool(EXHIBITION_RE.search(ename)),
                    roster=[pl.get("playerId") for pl in h.get("players") or []],
                ))
        if i % 20 == 0:
            log(f"  选手生涯进度 {i}/{len(players)}")
    log(f"选手生涯事件: {len(player_events)} 条")

    # 3. 候选战队：当前 top30 + 按名检索历史强队
    teams = {}  # hltvId -> name
    try:
        for t in fetch_json("/team/rank", {"pageNum": 1, "pageSize": 30, "darkType": 1}) or []:
            if t.get("hltvId"):
                teams[t["hltvId"]] = t.get("teamName") or ""
    except Exception as e:
        log(f"! team/rank 失败: {e}")
    log(f"team/rank: {len(teams)} 队")

    for name in TEAM_SEARCH_NAMES:
        try:
            r = fetch_json("/match/fuzzySearch", {"name": name}) or {}
        except Exception as e:
            log(f"  ! 搜索 {name} 失败: {e}")
            continue
        hits = [t for t in r.get("teams") or [] if t.get("hltvId")]
        # 精确匹配优先，其次名称包含查询词，最多取 3 个
        exact = [t for t in hits if (t.get("name") or "").lower() == name.lower()]
        fuzzy = [t for t in hits if name.lower() in (t.get("name") or "").lower()]
        picked = exact or fuzzy[:3] or hits[:1]
        for t in picked:
            teams.setdefault(t["hltvId"], t.get("name") or name)
        log(f"  搜索 {name}: 命中 {len(hits)}，采纳 {[t.get('name') for t in picked]}")
    teams.update(TEAMS_BY_ID)
    log(f"候选战队合计: {len(teams)} 队")

    # 4. 逐队 career → 名次表（带本地缓存，失败可断点续跑）
    cache = {}
    if os.path.exists(TEAM_CACHE):
        try:
            cache = json.load(open(TEAM_CACHE, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cache = {}
    log(f"本地缓存: {len(cache)} 队")

    placements = []
    team_fail = []
    fetched = 0
    for i, (tid, tname) in enumerate(sorted(teams.items()), 1):
        career = cache.get(str(tid))
        if career is None:
            try:
                career = fetch_team_career(tid)
                cache[str(tid)] = career
                fetched += 1
                # 每成功 5 队落盘一次，防中途失败丢进度
                if fetched % 5 == 0:
                    json.dump(cache, open(TEAM_CACHE, "w", encoding="utf-8"),
                              ensure_ascii=False)
            except Exception as e:
                team_fail.append((tid, tname, str(e)))
                continue
        for group in career:
            for h in group.get("csHonorList") or []:
                if not h.get("hasEvent"):
                    continue
                ename = (h.get("name") or "").strip()
                placements.append(dict(
                    teamId=tid, teamName=tname,
                    eventId=h.get("id"), eventName=ename,
                    date=ms_to_date(h.get("timestamp")),
                    rank=h.get("rank") or "",
                    qualifier=bool(QUALIFIER_RE.search(ename)),
                    playerIds=[pl.get("playerId") for pl in h.get("players") or []],
                    playerNames=[pl.get("name") for pl in h.get("players") or []],
                ))
        if i % 15 == 0:
            log(f"  战队生涯进度 {i}/{len(teams)}（新拉取 {fetched}）")
    json.dump(cache, open(TEAM_CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    if team_fail:
        log(f"! {len(team_fail)} 队失败: {team_fail}")

    # 4b. 应用手工冠军补丁 + 表演赛标记
    for patch in MANUAL_CHAMPION_PATCHES:
        ids, names = PATCH_ROSTERS[patch["teamName"]]
        placements.append(dict(
            teamId=-1, teamName=patch["teamName"] + "(补丁)",
            eventId=patch["eventId"], eventName=patch["eventName"],
            date=patch["date"], rank="冠军", qualifier=False,
            playerIds=list(ids), playerNames=list(names),
        ))
    for p in placements:
        p["exhibition"] = bool(EXHIBITION_RE.search(p["eventName"] or ""))
    n_champ = sum(1 for p in placements if p["rank"] == "冠军")
    log(f"名次记录: {len(placements)} 条（含 {len(MANUAL_CHAMPION_PATCHES)} 条补丁），其中冠军 {n_champ} 条")

    # 5. 覆盖率校验（2021-2025 非预选/非表演赛，选手生涯 type4 事件 vs 战队阵容）
    place_by_event = defaultdict(list)
    for p in placements:
        place_by_event[p["eventId"]].append(p)

    covered, uncovered = 0, []
    for ev in player_events:
        if ev["type"] != 4:
            continue
        if not (ev["date"][:4].isdigit() and
                COVER_YEAR_START <= int(ev["date"][:4]) <= COVER_YEAR_END):
            continue
        if QUALIFIER_RE.search(ev["eventName"] or "") or \
                EXHIBITION_RE.search(ev["eventName"] or ""):
            continue
        hit = any(ev["playerId"] in p["playerIds"]
                  for p in place_by_event.get(ev["eventId"], []))
        if hit:
            covered += 1
        else:
            uncovered.append(ev)

    total = covered + len(uncovered)
    log(f"覆盖率（{COVER_YEAR_START}-{COVER_YEAR_END} 非预选赛）: "
        f"{covered}/{total} = {covered / total * 100:.1f}%" if total else "无校验样本")
    unc_by_year = defaultdict(int)
    for ev in uncovered:
        unc_by_year[ev["date"][:4]] += 1
    log(f"未覆盖按年: {dict(sorted(unc_by_year.items()))}")
    for ev in uncovered[:30]:
        log(f"  未覆盖: {ev['date']} {ev['playerName']} @ {ev['eventName']} "
            f"(event={ev['eventId']}, type={ev['type']}, rank={ev['rank']})")

    # 6. 保存
    out = dict(
        collected_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        teams={str(k): v for k, v in sorted(teams.items())},
        placements=placements,
        player_events=player_events,
        coverage=dict(
            year_range=[COVER_YEAR_START, COVER_YEAR_END],
            covered=covered, uncovered=len(uncovered),
            uncovered_events=[dict(playerId=ev["playerId"], playerName=ev["playerName"],
                                   eventId=ev["eventId"], eventName=ev["eventName"],
                                   date=ev["date"], type=ev["type"], rank=ev["rank"])
                              for ev in uncovered],
        ),
    )
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    log(f"已保存: {OUT_JSON}")


if __name__ == "__main__":
    main()
