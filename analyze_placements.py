# -*- coding: utf-8 -*-
"""分析：重新按正确口径校验覆盖率 + 冠军清单 + 疑点核查"""
import json
import re
from collections import defaultdict

D = json.load(open(r"d:\demo\iftv\data\team_placements.json", encoding="utf-8"))
QUALIFIER_RE = re.compile(
    r"预选|资格|入围|封闭|海选|quarterfinal[s]? *qual|qualifier|qualification|"
    r"play[- ]?in|closed|RMR|showdown|小组赛|groups|play-in|open qual",
    re.IGNORECASE)

placements = D["placements"]
player_events = D["player_events"]
by_event = defaultdict(list)
for p in placements:
    by_event[p["eventId"]].append(p)

# 1. 疑点核查：G2@5608、Vitality@7524
print("=== 疑点核查 ===")
for eid, note in ((5608, "BLAST世界总决赛2021"), (7524, "上海Major2024"), (6809, "IEM卡托2023")):
    ps = by_event.get(eid, [])
    print(f"event {eid} ({note}): {len(ps)} 队有记录")
    for p in ps:
        print(f"   {p['teamName']} rank={p['rank']} roster={p['playerNames']}")

# 2. type4 口径覆盖率（选手生涯声称有名次的事件，战队数据必须覆盖）
print("\n=== type4 口径覆盖率（2021-2025 非预选） ===")
covered, uncovered = 0, []
for ev in player_events:
    if ev["type"] != 4:
        continue
    if not (ev["date"][:4].isdigit() and 2021 <= int(ev["date"][:4]) <= 2025):
        continue
    if QUALIFIER_RE.search(ev["eventName"] or ""):
        continue
    if any(ev["playerId"] in p["playerIds"] for p in by_event.get(ev["eventId"], [])):
        covered += 1
    else:
        uncovered.append(ev)
total = covered + len(uncovered)
print(f"覆盖: {covered}/{total} = {covered/total*100:.1f}%")
unc_by_year = defaultdict(int)
for ev in uncovered:
    unc_by_year[ev["date"][:4]] += 1
print(f"未覆盖按年: {dict(sorted(unc_by_year.items()))}")
for ev in uncovered[:25]:
    print(f"  未覆盖: {ev['date']} {ev['playerName']} @ {ev['eventName']} "
          f"(event={ev['eventId']}, rank={ev['rank']})")

# 3. 冠军清单（2021-2025 非预选）
print("\n=== 冠军清单（2021-2025 非预选） ===")
champs = [p for p in placements if p["rank"] == "冠军"
          and p["date"][:4].isdigit() and 2021 <= int(p["date"][:4]) <= 2025
          and not QUALIFIER_RE.search(p["eventName"] or "")]
by_year = defaultdict(list)
for p in champs:
    by_year[p["date"][:4]].append(p)
for y in sorted(by_year):
    print(f"{y}: {len(by_year[y])} 个冠军记录")
    for p in sorted(by_year[y], key=lambda x: x["date"]):
        print(f"   {p['date']} {p['teamName']} @ {p['eventName']}")
