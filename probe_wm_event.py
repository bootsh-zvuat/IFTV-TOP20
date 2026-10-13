# -*- coding: utf-8 -*-
"""探查24：match 里的队伍信息字段 + career 名次覆盖"""
import json
import sys

sys.path.insert(0, r"d:\demo\iftv")
from crawler import wm_get, log

r = wm_get("/event/getMatchList", {"eventId": 7902})
matches = r["matchResponse"]["dtoList"]
m = matches[0]
for k in ("team1Id", "team1DTO", "team2Id", "team2DTO", "winnerTeamId", "score1", "score2"):
    v = m.get(k)
    s = json.dumps(v, ensure_ascii=False)
    log(f"{k}: {s[:200]}")
