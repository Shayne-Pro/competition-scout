#!/usr/bin/env python3
"""Prepare a bounded Agent task and atomically validate its proposed data updates."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import uuid

from scout_core import (TEXT_FIELDS, choose_targets, event_key, now, read_json, refresh_status,
                        source_urls, stable_id, valid_url, validate_events, validate_node, write_json)

BASE = Path(__file__).resolve().parent
FIELDS = set(TEXT_FIELDS) | {'url', 'tags', 'entry', 'submit', 'status', 'priority'}


def data_hash(events):
    return hashlib.sha256(json.dumps(events, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def prepare(base=BASE, limit=20):
    if not 1 <= limit <= 20:
        raise ValueError('target limit must be between 1 and 20')
    at = now()
    events = read_json(base / 'events.json')
    validate_events(events)
    sources = read_json(base / 'sources.json')['sources']
    state = read_json(base / 'source-state.json', {})
    due_by_url = {}
    for source in sources:
        if source['tier'] == 'discovery':
            continue
        last = state.get(source['url'], {}).get('lastSuccess')
        if source['tier'] != 'watch' or not last or (at.date() - __import__('datetime').date.fromisoformat(last)).days >= 7:
            url = valid_url(source['url'])
            if url not in due_by_url:
                due_by_url[url] = copy.deepcopy(source)
            else:
                # The registry can describe one page under multiple discovery categories.
                # Scan it once, retaining both policies for the model.
                due_by_url[url].setdefault('relatedEntries', []).append(copy.deepcopy(source))
    due = list(due_by_url.values())
    target_ids = choose_targets(events, at, limit)
    task = {'runId': os.getenv('GITHUB_RUN_ID', str(uuid.uuid4())) + '-' + os.getenv('GITHUB_RUN_ATTEMPT', '1'),
            'date': at.date().isoformat(), 'startedAt': at.isoformat(), 'baseHash': data_hash(events),
            'targets': target_ids, 'sources': due}
    write_json(base / '.scout/task.json', task)
    write_json(base / '.scout/events.json', events)
    write_json(base / '.scout/targets.json', [e for e in events if e['id'] in target_ids])
    write_json(base / '.scout/evidence.json', {'pages': {}, 'sources': {}})
    # A previously created proposal must never be reused for a new invocation.
    (base / '.scout/proposal.json').unlink(missing_ok=True)
    return task


def validate_proposal(proposal, task, events):
    if not isinstance(proposal, dict) or set(proposal) != {'runId', 'date', 'sources', 'updates', 'failed'}:
        raise ValueError('proposal requires runId, date, sources, updates, failed')
    if proposal['runId'] != task['runId'] or proposal['date'] != task['date']:
        raise ValueError('stale proposal or wrong run identity')
    if data_hash(events) != task['baseHash']:
        raise ValueError('events changed after task preparation; rerun instead of overwriting')
    for key in ('sources', 'updates', 'failed'):
        if not isinstance(proposal[key], list):
            raise ValueError(key + ' must be an array')
    if len(proposal['updates']) > 60:
        raise ValueError('update limit exceeded')
    expected_sources = {s['url'] for s in task['sources']}
    seen_sources = set()
    for source in proposal['sources']:
        if set(source) != {'url', 'status', 'note'} or source['url'] not in expected_sources or source['url'] in seen_sources:
            raise ValueError('unexpected or duplicate source result')
        if source['status'] not in ('ok', 'failed', 'deferred') or not isinstance(source['note'], str) or not source['note'].strip():
            raise ValueError('source status and note are required')
        seen_sources.add(source['url'])
    if seen_sources != expected_sources:
        raise ValueError('every due source needs an explicit result, including failures')
    existing = {e['id']: e for e in events}
    handled, identities = set(), set()
    for update in proposal['updates']:
        if set(update) != {'eventId', 'event', 'verification', 'eligibility', 'evidence'}:
            raise ValueError('invalid update fields')
        eid, event = update['eventId'], update['event']
        if eid is not None and (eid not in existing or eid in handled):
            raise ValueError('unknown or repeated eventId')
        if eid:
            handled.add(eid)
        if not isinstance(event, dict) or set(event) != FIELDS:
            raise ValueError('event must contain exactly the documented fields')
        for key in TEXT_FIELDS:
            if not isinstance(event[key], str) or len(event[key]) > 3000:
                raise ValueError('invalid text: ' + key)
        if not event['title'].strip():
            raise ValueError('empty title')
        identity = event_key(event['url'])
        if identity in identities:
            raise ValueError('duplicate event identities in proposal')
        identities.add(identity)
        if update['verification'] not in ('verified', 'partial') or update['eligibility'] not in ('open', 'student_only', 'unclear'):
            raise ValueError('invalid verification or eligibility')
        if not isinstance(update['evidence'], list) or not 1 <= len(update['evidence']) <= 10:
            raise ValueError('an update requires official evidence')
        for ev in update['evidence']:
            if set(ev) != {'url', 'quote'} or not isinstance(ev['quote'], str) or not 8 <= len(ev['quote']) <= 600:
                raise ValueError('evidence requires URL and a short supporting excerpt')
            valid_url(ev['url'])
        for key in ('entry', 'submit'):
            validate_node(event[key])
        if update['verification'] == 'verified' and update['eligibility'] == 'unclear':
            raise ValueError('unknown eligibility must remain partial')
        if update['verification'] == 'partial' and event['status'] != 'unclear':
            raise ValueError('partially verified entries must remain unclear')
        validate_events([dict(event, id=eid or stable_id(event['url']), sources=[ev['url'] for ev in update['evidence']])])
        if eid is None:
            if any(event_key(old['url']) == identity for old in events):
                raise ValueError('event already exists; use its existing eventId')
            # A list URL cannot identify a newly discovered competition.
            from urllib.parse import urlsplit
            u = urlsplit(event['url'])
            if u.hostname in ('www.kaggle.com', 'kaggle.com') and u.path.rstrip('/') == '/competitions':
                raise ValueError('Kaggle candidate needs its detail URL')
            if u.hostname == 'tianchi.aliyun.com' and '/entrance/' not in u.path:
                raise ValueError('Tianchi candidate needs its detail URL')
            if u.hostname == 'challenge.xfyun.cn' and 'type=' not in u.query:
                raise ValueError('Xfyun candidate needs its detail URL')
    for failure in proposal['failed']:
        if set(failure) != {'eventId', 'reason'} or failure['eventId'] not in existing or failure['eventId'] in handled:
            raise ValueError('invalid or duplicate failed target')
        if not isinstance(failure['reason'], str) or not failure['reason'].strip():
            raise ValueError('failed target requires a reason')
        handled.add(failure['eventId'])
    if not set(task['targets']) <= handled:
        raise ValueError('every selected event needs an update or an explicit failure')


def append_log(base, status):
    with (base / 'runs-log.jsonl').open('a', encoding='utf-8') as out:
        out.write(json.dumps(status, ensure_ascii=False) + '\n')


def validate_evidence(proposal, evidence):
    import re
    def normalized(text):
        return re.sub(r'\s+', ' ', text).strip()
    pages = evidence.get('pages', {})
    for source in proposal['sources']:
        if source['status'] == 'ok' and evidence.get('sources', {}).get(source['url']) not in pages:
            raise ValueError('successful source has no captured page evidence')
    for update in proposal['updates']:
        for citation in update['evidence']:
            page = pages.get(citation['url'])
            if not page or normalized(citation['quote']) not in normalized(page['text']):
                raise ValueError('evidence quote is absent from pages fetched in this run')


def apply(base=BASE):
    at = now()
    task = read_json(base / '.scout/task.json')
    proposal = read_json(base / '.scout/proposal.json')
    events = read_json(base / 'events.json')
    validate_proposal(proposal, task, events)
    validate_evidence(proposal, read_json(base / '.scout/evidence.json', {}))
    # All validation happens before any published file is changed.
    result = copy.deepcopy(events)
    by_id = {e['id']: e for e in result}
    by_url = {event_key(e['url']): e for e in result}
    changed_ids = set()
    for item in proposal['updates']:
        payload = copy.deepcopy(item['event'])
        record = by_id.get(item['eventId']) if item['eventId'] else by_url.get(event_key(payload['url']))
        if record is None:
            record = {'id': stable_id(payload['url'])}
            result.append(record)
            by_id[record['id']] = record
        if record['id'] in changed_ids:
            raise ValueError('same stored event addressed more than once')
        changed_ids.add(record['id'])
        old_verified = record.get('verification', {}).get('verifiedAt')
        record.update(payload)
        record.update(eligibility=item['eligibility'], sources=[ev['url'] for ev in item['evidence']], verifiedBy='agent')
        verification = {'state': item['verification'], 'attemptedAt': at.isoformat(), 'evidence': item['evidence'],
                        'runId': task['runId'], 'verifiedAt': task['date'] if item['verification'] == 'verified' else old_verified}
        record['verification'] = verification
        if item['verification'] == 'verified':
            record['verifiedAt'] = task['date']
        if item['eligibility'] == 'student_only':
            record['status'] = 'excluded'
        refresh_status(record, at)
        by_url[event_key(record['url'])] = record
    for failure in proposal['failed']:
        record = by_id[failure['eventId']]
        v = record.setdefault('verification', {'state': 'legacy', 'verifiedAt': None})
        v.update(attemptedAt=at.isoformat(), lastError=failure['reason'])
    validate_events(result)
    state = read_json(base / 'source-state.json', {})
    for source in proposal['sources']:
        previous = state.get(source['url'], {})
        state[source['url']] = {**previous, **source, 'lastAttempt': task['date']}
        if source['status'] == 'ok':
            state[source['url']]['lastSuccess'] = task['date']
    sources_ok = sum(s['status'] == 'ok' for s in proposal['sources'])
    verified = sum(u['verification'] == 'verified' for u in proposal['updates'])
    partial = bool(proposal['failed']) or sources_ok < len(proposal['sources']) or any(u['verification'] != 'verified' for u in proposal['updates'])
    state_name = ('partial' if partial else 'ok') if sources_ok or verified else 'failed'
    status = {'runId': task['runId'], 'date': task['date'], 'finishedAt': at.isoformat(), 'state': state_name,
              'sourcesOk': sources_ok, 'sourcesTotal': len(proposal['sources']), 'verified': verified,
              'updated': len(proposal['updates']), 'failed': proposal['failed'], 'sources': proposal['sources']}
    write_json(base / 'events.json', result)
    write_json(base / 'source-state.json', state)
    write_json(base / 'refresh-status.json', status)
    append_log(base, status)
    return status


def failed(reason, base=BASE):
    task = read_json(base / '.scout/task.json', {})
    status = {'runId': task.get('runId', 'unknown'), 'date': now().date().isoformat(), 'finishedAt': now().isoformat(),
              'state': 'failed', 'reason': reason, 'verified': 0, 'updated': 0,
              'sourcesOk': 0, 'sourcesTotal': len(task.get('sources', []))}
    write_json(base / 'refresh-status.json', status)
    append_log(base, status)
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'apply', 'failed', 'check'])
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--reason', default='Agent did not produce a valid proposal; existing event data retained.')
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(limit=args.limit)
    elif args.command == 'apply':
        result = apply()
    elif args.command == 'failed':
        result = failed(args.reason)
    else:
        validate_events(read_json(BASE / 'events.json'))
        result = {'valid': True}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
