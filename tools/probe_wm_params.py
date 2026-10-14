# -*- coding: utf-8 -*-
"""探查8：bundle 中 getMatchList / calender 的调用参数"""
import re
import os
import sys

# 让 tools/ 下的脚本能导入 ../src/ 的模块（相对本文件，跨机器可用）
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from crawler import request_get, HEADERS_WM, log

js = request_get("https://data.wanmei.com/asset/csgo/js/csgo-9ee1dfe5.js", headers=HEADERS_WM).text
for kw in ["getMatchList", "calender/eventList", "getMatchPlayerStats", "getMatchDetail"]:
    log(f"=== {kw} ===")
    for m in list(re.finditer(r".{200}" + kw.replace("/", r"\/") + r".{300}", js))[:3]:
        log(m.group(0))
        log("---")
