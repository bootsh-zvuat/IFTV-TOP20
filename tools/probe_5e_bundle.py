# -*- coding: utf-8 -*-
"""探查5：5E bundle 中的 mfilter/数据 API 路径 + tt_series 选项来源"""
import re
import os
import sys

# 让 tools/ 下的脚本能导入 ../src/ 的模块（相对本文件，跨机器可用）
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from crawler import request_get, HEADERS_5E, log

js = request_get("https://event.5eplay.com/static/js/index.bundle.126be0c21629a196e62f.js",
                 headers=HEADERS_5E).text

# 含 mfilter / list / stats 等关键词的路径片段（引号内）
frags = sorted(set(re.findall(r'["\']([a-zA-Z0-9_/.-]*(?:mfilter|dimension|stats|series|season|grade|filter)[a-zA-Z0-9_/.-]*)["\']', js)))
for f in frags:
    log(f)

log("\n=== tt_series/tt_ids 上下文 ===")
for m in list(re.finditer(r'.{80}tt_series.{120}', js))[:6]:
    log(m.group(0))
    log("---")
