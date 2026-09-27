#!/usr/bin/env python3
"""Prepare the small, explicit publication artifact; keep raw Agent evidence separate."""
from pathlib import Path
import shutil
import subprocess
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from scout_core import read_json, write_json
from publish import FILES

output = BASE / '.scout/catalogue'
output.mkdir(parents=True, exist_ok=True)
if not (BASE / 'source-state.json').exists():
    write_json(BASE / 'source-state.json', {})
for name in FILES:
    shutil.copy2(BASE / name, output / name)
(output / 'base-commit.txt').write_text(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=BASE, text=True))
status = read_json(BASE / 'refresh-status.json')
summary = 'Agent state: **%s**; verified: **%s**; sources: **%s/%s**.\n' % (
    status['state'], status.get('verified', 0), status.get('sourcesOk', 0), status.get('sourcesTotal', 0))
print(summary)
import os
if os.getenv('GITHUB_STEP_SUMMARY'):
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as out:
        out.write(summary)
