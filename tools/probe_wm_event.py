# -*- coding: utf-8 -*-
"""探查24：match 里的队伍信息字段 + career 名次覆盖"""
import json
import os
import sys

# 让 tools/ 下的脚本能导入 ../src/ 的模块（相对本文件，跨机器可用）
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from crawler import wm_get, log

r = wm_get("/event/getMatchList", {"eventId": 7902})
matches = r["matchResponse"]["dtoList"]
m = matches[0]
for k in ("team1Id", "team1DTO", "team2Id", "team2DTO", "winnerTeamId", "score1", "score2"):
    v = m.get(k)
    s = json.dumps(v, ensure_ascii=False)
    log(f"{k}: {s[:200]}")
