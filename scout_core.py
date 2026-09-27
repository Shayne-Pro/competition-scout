"""Validated data boundary shared by the Agent, date refresh and page builder."""
import copy
import datetime as dt
import hashlib
import json
import os
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

BEIJING = ZoneInfo('Asia/Shanghai')
STATUSES = {'open', 'submission', 'unclear', 'upcoming', 'practice', 'closed', 'excluded'}
TEXT_FIELDS = ('title', 'platform', 'venue', 'task', 'requirements', 'award', 'warning')


def now():
    if os.getenv('BUILD_NOW'):
        value = parse_instant(os.environ['BUILD_NOW'])
        return value.astimezone(BEIJING)
    if os.getenv('BUILD_TODAY'):
        return dt.datetime.combine(dt.date.fromisoformat(os.environ['BUILD_TODAY']), dt.time(8, 20), BEIJING)
    return dt.datetime.now(BEIJING)


def read_json(path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else copy.deepcopy(default)


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def valid_url(value):
    if not isinstance(value, str) or re.search(r'[\s<>"\x00-\x1f]', value):
        raise ValueError('URL must be a plain HTTP(S) URL')
    u = urlsplit(value)
    if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password:
        raise ValueError('URL must be a plain HTTP(S) URL')
    return value


def source_urls(event):
    return list(dict.fromkeys(valid_url(u['url'] if isinstance(u, dict) else u)
                              for u in event.get('sources', []) if u))


def event_key(url):
    """Preserve platform event IDs, including Xfyun's identifying query string."""
    u = urlsplit(valid_url(url))
    host = u.netloc.lower().removeprefix('www.')
    path = u.path.rstrip('/')
    if host.endswith('.grand-challenge.org'):
        path = ''
    if host == 'tianchi.aliyun.com':
        match = re.match(r'(/competition/entrance/\d+)', path)
        if match:
            path = match.group(1)
    query = [(k, v) for k, v in parse_qsl(u.query) if not k.lower().startswith('utm_') and k not in ('ref', 'source')]
    return urlunsplit(('https', host, path, urlencode(sorted(query)), ''))


def stable_id(url):
    return 'event-' + hashlib.sha256(event_key(url).encode()).hexdigest()[:16]


def parse_instant(value):
    instant = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if instant.tzinfo is None:
        raise ValueError('instant must include a timezone')
    return instant


def timezone(name):
    return dt.timezone(dt.timedelta(hours=-12)) if name == 'AoE' else ZoneInfo(name)


def validate_node(node):
    if not isinstance(node, dict) or set(node) != {'text', 'day', 'instant', 'kind', 'timezone'}:
        raise ValueError('date node requires text, day, instant, kind, timezone')
    if not isinstance(node['text'], str) or node['kind'] not in ('deadline', 'opening', 'unknown'):
        raise ValueError('invalid date description or kind')
    day, instant = node['day'], node['instant']
    if day is not None:
        if not isinstance(day, str) or dt.date.fromisoformat(day).isoformat() != day:
            raise ValueError('invalid calendar date')
    if instant is not None:
        parsed = parse_instant(instant)
        if day != parsed.astimezone(BEIJING).date().isoformat():
            raise ValueError('day must equal the Beijing date of instant')
    if node['kind'] == 'unknown' and (day is not None or instant is not None):
        raise ValueError('unknown date must clear day and instant')
    if node['kind'] != 'unknown' and day is None:
        raise ValueError('known date kind requires day')
    if node['timezone'] != 'unknown':
        timezone(node['timezone'])


def cutoff(node):
    """Only explicit deadlines participate; legacy/unknown/opening dates do not."""
    if not node or node.get('kind') != 'deadline':
        return None
    if node.get('instant'):
        return parse_instant(node['instant'])
    if node.get('day') and node.get('timezone', 'unknown') != 'unknown':
        # Date-only nodes retain the source calendar date; expire after its whole day.
        return dt.datetime.combine(dt.date.fromisoformat(node['day']), dt.time.max, timezone(node['timezone']))
    return None


def refresh_status(event, at):
    if event.get('eligibility') == 'student_only':
        event['status'] = 'excluded'
        return
    if event.get('verification', {}).get('state') != 'verified':
        return  # old or partially checked data cannot establish new state transitions
    st = event['status']
    if st in ('unclear', 'practice', 'excluded', 'closed'):
        return
    end, entry = cutoff(event.get('submit')), cutoff(event.get('entry'))
    if end and end < at:
        event['status'] = 'closed'
    elif entry and entry < at:
        event['status'] = 'submission' if end and end >= at else 'unclear'
    elif st == 'upcoming':
        opening = event.get('entry', {})
        if opening.get('kind') == 'opening':
            start = parse_instant(opening['instant']) if opening.get('instant') else None
            if not start and opening.get('day') and opening.get('timezone') != 'unknown':
                start = dt.datetime.combine(dt.date.fromisoformat(opening['day']), dt.time.min, timezone(opening['timezone']))
            if start and start <= at:
                event['status'] = 'open'


def days_left(event, at):
    ends = [cutoff(event.get(key)) for key in ('entry', 'submit')]
    future = [value for value in ends if value and value >= at]
    return min((v.astimezone(BEIJING).date() - at.date()).days for v in future) if future else -1


def validate_events(events):
    if not isinstance(events, list):
        raise ValueError('events must be an array')
    ids = set()
    for e in events:
        if not isinstance(e.get('id'), str) or not e['id'] or e['id'] in ids:
            raise ValueError('missing or duplicate event id')
        ids.add(e['id'])
        if e.get('status') not in STATUSES:
            raise ValueError('unknown event status: ' + str(e.get('status')))
        for field in TEXT_FIELDS:
            if not isinstance(e.get(field, ''), str):
                raise ValueError('invalid text field: ' + field)
        valid_url(e['url'])
        source_urls(e)
        if not isinstance(e.get('tags'), list) or any(not isinstance(t, str) for t in e['tags']):
            raise ValueError('tags must be a string array')
        if type(e.get('priority')) is not int or not 1 <= e['priority'] <= 5:
            raise ValueError('priority must be 1..5')
        for field in ('entry', 'submit'):
            node = e[field]
            if 'kind' in node:
                validate_node(node)
            else:  # historical schema: valid dates, never silently promoted to new verification
                if node.get('day'):
                    dt.date.fromisoformat(node['day'])
                if node.get('instant'):
                    parse_instant(node['instant'])
        if e.get('verifiedAt'):
            dt.date.fromisoformat(e['verifiedAt'])


def choose_targets(events, at, limit=20):
    def score(e):
        v = e.get('verification', {})
        pending = e['status'] in ('unclear', 'upcoming') or v.get('state') != 'verified'
        urgent = 0 <= days_left(e, at) <= 14
        # Oldest attempt first prevents inaccessible high-priority entries monopolizing the queue.
        return (v.get('attemptedAt', ''), not pending, not urgent, e.get('priority', 5), e['id'])
    eligible = []
    for e in events:
        if e['status'] in ('excluded', 'practice'):
            continue
        verified = e.get('verification', {}).get('verifiedAt')
        stale = not verified or (at.date() - dt.date.fromisoformat(verified)).days >= 7
        if stale or e['status'] in ('unclear', 'upcoming') or 0 <= days_left(e, at) <= 14:
            eligible.append(e)
    return [e['id'] for e in sorted(eligible, key=score)[:limit]]
