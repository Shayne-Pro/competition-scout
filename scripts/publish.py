#!/usr/bin/env python3
"""Publish only validated catalogue files, refusing concurrent main changes."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from scout_core import read_json, validate_events

FILES = ('events.json', 'notified.json', 'runs-log.jsonl', 'refresh-status.json', 'source-state.json', 'index.html')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('artifact', type=Path)
    args = parser.parse_args()
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=BASE, text=True).strip()
    if head != (args.artifact / 'base-commit.txt').read_text().strip():
        raise SystemExit('main changed during the scan. Refusing to overwrite newer work; rerun refresh.')
    validate_events(read_json(args.artifact / 'events.json'))
    for name in FILES:
        source = args.artifact / name
        if source.is_symlink() or not source.is_file():
            raise SystemExit('Missing or unsafe publish file: ' + name)
    for name in FILES:
        shutil.copy2(args.artifact / name, BASE / name)
    subprocess.run([sys.executable, 'ci_check.py'], cwd=BASE, check=True)
    subprocess.run(['git', 'add', '--', *FILES], cwd=BASE, check=True)
    if subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=BASE).returncode:
        subprocess.run(['git', '-c', 'user.name=github-actions[bot]', '-c',
                        'user.email=41898282+github-actions[bot]@users.noreply.github.com',
                        'commit', '-m', '每日 Agent Skill 刷新：核验赛事、记录来源状态并更新页面'], cwd=BASE, check=True)
        subprocess.run(['git', 'push', 'origin', 'HEAD:main'], cwd=BASE, check=True)
    # Explicitly request the existing branch-based Pages build after a bot-token push.
    repo, token = os.environ['GITHUB_REPOSITORY'], os.environ['GH_TOKEN']
    req = urllib.request.Request('https://api.github.com/repos/' + repo + '/pages/builds', data=b'', method='POST',
          headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json', 'User-Agent': 'competition-scout'})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            print('GitHub Pages build requested:', response.status)
    except urllib.error.HTTPError as exc:
        if exc.code != 409:  # A build may already have been started by the branch push.
            raise
        print('GitHub Pages already has a build in progress.')


if __name__ == '__main__':
    main()
