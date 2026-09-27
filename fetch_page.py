#!/usr/bin/env python3
"""Capture the same evidence as the scheduled runner for an interactive Skill run."""
import argparse
import json

from agent_refresh import Fetcher
from scout import BASE
from scout_core import read_json, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('--render', action='store_true')
    parser.add_argument('--source', help='Exact due source URL when using an alternate official entry point')
    args = parser.parse_args()
    task = read_json(BASE / '.scout/task.json')
    if not task:
        raise SystemExit('Run scout.py prepare first.')
    source = args.source or args.url
    due = {item['url'] for item in task['sources']}
    if args.source and source not in due:
        raise SystemExit('--source must be a due source URL from task.json')
    fetcher = Fetcher(BASE)
    try:
        page = fetcher.fetch(args.url, args.render)
        if source in due:
            evidence = read_json(BASE / '.scout/evidence.json')
            evidence['sources'][source] = args.url
            write_json(BASE / '.scout/evidence.json', evidence)
        print(json.dumps(page, ensure_ascii=False, indent=2))
    finally:
        fetcher.close()


if __name__ == '__main__':
    main()
