#!/usr/bin/env python3
"""Refresh explicit verified deadlines; log reminder candidates without claiming delivery."""
from pathlib import Path
from scout_core import cutoff, now, read_json, refresh_status, validate_events, write_json

BASE = Path(__file__).resolve().parent


def main():
    at = now()
    events = read_json(BASE / 'events.json')
    validate_events(events)
    notified = read_json(BASE / 'notified.json', {'reminded': []})
    reminded = {tuple(item) for item in notified.get('reminded', [])}
    due = []
    for event in events:
        refresh_status(event, at)
        if event['status'] not in ('open', 'submission'):
            continue
        for key in ('entry', 'submit'):
            end = cutoff(event.get(key))
            if end and at <= end and (end - at).total_seconds() <= 7 * 86400:
                tag = (event['id'], key, end.isoformat())
                if tag not in reminded:
                    due.append({'eventId': event['id'], 'field': key, 'deadline': end.isoformat()})
                    reminded.add(tag)
    notified.update(reminded=[list(t) for t in sorted(reminded)], lastRun=at.isoformat())
    write_json(BASE / 'events.json', events)
    write_json(BASE / 'notified.json', notified)
    # Append rather than erasing same-day Agent evidence. No external notification is sent.
    from scout import append_log
    append_log(BASE, {'type': 'date_refresh', 'date': at.date().isoformat(), 'at': at.isoformat(), 'reminderCandidates': due})
    print('Date refresh complete: %d reminder candidates (not delivered).' % len(due))


if __name__ == '__main__':
    main()
