# -*- coding: utf-8 -*-
"""从采集 Excel 生成模拟器验证数据（2024/2025 逐赛事）→ if-simulator/scripts/verify-data.json"""
import os
import json
import glob
from collections import defaultdict
import openpyxl

BASE = os.path.dirname(os.path.abspath(__file__))
YEARS = [2024, 2025]
OUT = os.path.join(BASE, "if-simulator", "scripts", "verify-data.json")


def load_sheet(wb, name):
    rows = list(wb[name].iter_rows(min_row=2, values_only=True))
    header = rows[0]
    return [dict(zip(header, r)) for r in rows[1:] if r and any(v is not None for v in r)]


def classify_event(name):
    n = name or ""
    if "Major" in n:
        return "Major"
    if ("卡托维兹" in n) or ("科隆" in n):
        return "超级精英赛"
    if ("全球总决赛" in n) or ("世界总决赛" in n) or ("ESL Pro League" in n) or ("EPL" in n):
        return "精英赛"
    if ("IEM" in n) or ("BLAST" in n) or ("电竞世界杯" in n):
        return "大型赛事"
    return "中型赛事"


def map_placement(text):
    t = (text or "").strip()
    if ("冠军" in t) or ("1-2名" in t):
        return "冠军"
    if "亚军" in t:
        return "亚军"
    if ("季军" in t) or ("四强" in t) or ("3-4" in t) or ("4名" in t) \
            or ("1-3名" in t) or ("2-3名" in t) or ("1-4名" in t):
        return "四强"
    if ("八强" in t) or ("5-8" in t) or ("6-8" in t) or ("5-6" in t) or ("7-8" in t):
        return "八强"
    return None


def main():
    xlsx = sorted(glob.glob(os.path.join(BASE, "data", "CS2选手排名数据_*.xlsx")))[-1]
    wb = openpyxl.load_workbook(xlsx, read_only=True)

    # 5E 逐年统计 → (pid, year) -> rating/adr/kpr
    stats = {}
    for r in load_sheet(wb, "5E逐年统计"):
        y = int(r["年份"])
        if y in YEARS and isinstance(r.get("地图数"), (int, float)) and r["地图数"] > 0:
            stats[(int(r["选手ID"]), y)] = dict(
                rating=float(r.get("Rating") or 0),
                adr=float(r.get("ADR") or 0),
                kpr=float(r.get("KPR") or 0),
            )

    # career → 按 (year, event) 聚合选手记录
    ev_mvp = {}       # (year, event) -> pid
    ev_evp = defaultdict(list)   # (year, event) -> [pid]
    ev_place = {}     # (year, event, pid) -> placement
    names = {}
    for r in load_sheet(wb, "历年生涯荣誉"):
        pid = int(r["选手ID"])
        names[pid] = r.get("选手") or str(pid)
        date = str(r.get("日期") or "")
        y = int(date[:4]) if date[:4].isdigit() else 0
        if y not in YEARS:
            continue
        ev = (r.get("赛事名") or "").strip()
        if not ev:
            continue
        t = r.get("类型")
        if t == 1:
            ev_mvp[(y, ev)] = pid
        elif t == 5:
            ev_evp[(y, ev)].append(pid)
        elif t == 4:
            p = map_placement(r.get("名次"))
            if p:
                ev_place[(y, ev, pid)] = p

    # 官方 Top20 baseline
    baselines = defaultdict(list)
    for r in load_sheet(wb, "历年HLTV_Top20"):
        y = int(r["年份"])
        if y in YEARS:
            baselines[y].append(dict(rank=int(r["官方名次"]), playerId=str(int(r["选手ID"])),
                                     name=r.get("选手") or ""))

    # 仅保留有 MVP/EVP 记录的赛事（type4 名次记录含大量预选赛/地区赛灌水；
    # MVP/EVP 仅 HLTV 覆盖的正式赛事才有）
    players, events, results = {}, {}, []
    ev_keys = sorted(set(list(ev_mvp) + list(ev_evp)))
    for (y, ev) in ev_keys:
        level = classify_event(ev)
        eid = f"{y}::{ev}"
        events[eid] = dict(id=eid, name=ev, year=y, level=level)
        # 该赛事有记录的选手集合
        pids = set()
        if (y, ev) in ev_mvp:
            pids.add(ev_mvp[(y, ev)])
        pids.update(ev_evp.get((y, ev), []))
        pids.update(pid for (yy, ee, pid) in ev_place if yy == y and ee == ev)
        # EVP 顺位：按当年 5E rating 降序，取前3（模拟器仅支持3个EVP槽位）
        evps = sorted(ev_evp.get((y, ev), []),
                      key=lambda p: stats.get((p, y), {}).get("rating", 0), reverse=True)[:3]
        for pid in pids:
            players[pid] = dict(id=str(pid), name=names.get(pid, str(pid)), team="", year=y)
            st = stats.get((pid, y), dict(rating=0, adr=0, kpr=0))
            if ev_mvp.get((y, ev)) == pid:
                honor, hrank = "MVP", 1
            elif pid in evps:
                honor, hrank = "EVP", evps.index(pid) + 1
            else:
                honor, hrank = "无", 0
            results.append(dict(
                eventId=eid, playerId=str(pid),
                teamPlacement=ev_place.get((y, ev, pid), "小组淘汰"),
                honor=honor, honorRank=hrank,
                rating=st["rating"], adr=st["adr"], kpr=st["kpr"],
            ))

    out = dict(
        players=list(players.values()),
        events=list(events.values()),
        results=results,
        baselines={str(y): baselines[y] for y in YEARS},
    )
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"players={len(players)} events={len(events)} results={len(results)}")
    for y in YEARS:
        evs = [e for e in events.values() if e["year"] == y]
        lv = defaultdict(int)
        for e in evs:
            lv[e["level"]] += 1
        print(f"{y}: {len(evs)} 赛事 {dict(lv)}, baseline={len(baselines[y])} 人")


if __name__ == "__main__":
    main()
