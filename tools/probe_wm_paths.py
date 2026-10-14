# -*- coding: utf-8 -*-
"""探查6：完美 bundle 全部 API 路径"""
import re
import os
import sys

# 让 tools/ 下的脚本能导入 ../src/ 的模块（相对本文件，跨机器可用）
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from crawler import request_get, HEADERS_WM, log

js = request_get("https://data.wanmei.com/asset/csgo/js/csgo-9ee1dfe5.js", headers=HEADERS_WM).text
log(f"bundle size: {len(js)}")
paths = sorted(set(re.findall(r'["\'](/[a-zA-Z0-9_/]+)["\']', js)))
for p in paths:
    log(p)
