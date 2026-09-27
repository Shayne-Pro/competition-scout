#!/usr/bin/env python3
"""Validate catalogue schema and the generated page's identity/date contract."""
from html.parser import HTMLParser
from pathlib import Path
import json
from scout_core import now, validate_events

BASE = Path(__file__).resolve().parent


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.dates, self.status = [], [], False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'tr' and 'data-id' in attrs:
            self.ids.append(attrs['data-id'])
        if 'data-build-date' in attrs:
            self.dates.append(attrs['data-build-date'])
        if attrs.get('id') == 'refresh-status':
            self.status = True


def main():
    events = json.loads((BASE / 'events.json').read_text())
    validate_events(events)
    site = BASE / 'docs'
    for path in site.rglob('*'):
        if path.is_symlink() or (path.is_file() and path.relative_to(site).as_posix() not in {'index.html', '.nojekyll'}):
            raise ValueError('Unexpected file in public Pages directory: ' + str(path.relative_to(site)))
    page = Page()
    page.feed((site / 'index.html').read_text())
    visible = [e['id'] for e in events if e['status'] != 'excluded']
    if len(page.ids) != len(visible) or set(page.ids) != set(visible):
        raise ValueError('rendered event IDs differ from the catalogue')
    if page.dates != [now().date().isoformat()] or not page.status:
        raise ValueError('missing exact build date or refresh-status banner')
    print('PASS: %d visible events; schema, IDs, date and refresh banner verified.' % len(visible))


if __name__ == '__main__':
    main()
