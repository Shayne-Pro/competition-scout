import copy
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import agent_refresh
import scout
from scout_core import (BEIJING, choose_targets, cutoff, event_key, refresh_status,
                        source_urls, validate_events, validate_node, write_json)


def node(day=None, instant=None, kind='unknown', timezone='unknown'):
    return dict(text='Official date', day=day, instant=instant, kind=kind, timezone=timezone)


def event(eid='existing'):
    return {'id': eid, 'title': 'Medical Challenge', 'platform': '会议官网', 'venue': '', 'tags': ['医学'],
            'task': 'Segmentation', 'requirements': 'Open to all participants', 'award': 'Not announced',
            'warning': '', 'url': 'https://contest.example/2026', 'entry': node(), 'submit': node(),
            'priority': 2, 'status': 'open', 'sources': []}


def update(eid='existing', verification='verified', eligibility='open'):
    item = event(eid)
    item.pop('id')
    item.pop('sources')
    if verification == 'partial':
        item['status'] = 'unclear'
    return {'eventId': eid, 'event': item, 'verification': verification, 'eligibility': eligibility,
            'evidence': [{'url': 'https://contest.example/rules', 'quote': 'Open to all participants'}]}


class CoreTests(unittest.TestCase):
    def test_platform_identity_preserves_contest_ids(self):
        pairs = [
            ('https://www.kaggle.com/competitions/a', 'https://www.kaggle.com/competitions/b'),
            ('https://tianchi.aliyun.com/competition/entrance/1', 'https://tianchi.aliyun.com/competition/entrance/2'),
            ('https://www.codabench.org/competitions/1', 'https://www.codabench.org/competitions/2'),
            ('https://challenge.xfyun.cn/topic/info?type=one', 'https://challenge.xfyun.cn/topic/info?type=two')]
        for a, b in pairs:
            self.assertNotEqual(event_key(a), event_key(b))
        self.assertEqual(event_key('https://a.grand-challenge.org/timeline/'), event_key('https://a.grand-challenge.org/'))

    def test_pending_and_closed_targets_not_stranded(self):
        events = [dict(event(str(i)), status=status) for i, status in enumerate(['unclear', 'upcoming', 'closed'])]
        self.assertEqual(set(choose_targets(events, dt.datetime(2026, 9, 27, tzinfo=BEIJING))), {'0', '1', '2'})

    def test_unreachable_targets_do_not_starve_never_attempted(self):
        a, b = event('a'), event('b')
        a['verification'] = {'attemptedAt': '2026-09-27T10:00:00+08:00'}
        self.assertEqual(choose_targets([a, b], dt.datetime(2026, 9, 28, tzinfo=BEIJING), 1), ['b'])

    def test_invalid_or_contradictory_dates_are_rejected(self):
        for bad in [node('2026-02-30', kind='deadline'), node('2026-10-11'),
                    node('2026-10-24', '2026-10-25T19:59:00+08:00', 'deadline', 'Asia/Shanghai')]:
            with self.assertRaises(ValueError):
                validate_node(bad)

    def test_entry_expiry_becomes_submission(self):
        e = event()
        e['verification'] = {'state': 'verified'}
        e['entry'] = node('2026-09-27', kind='deadline', timezone='Asia/Shanghai')
        e['submit'] = node('2026-10-01', kind='deadline', timezone='Asia/Shanghai')
        refresh_status(e, dt.datetime(2026, 9, 28, 8, 20, tzinfo=BEIJING))
        self.assertEqual(e['status'], 'submission')

    def test_exact_instant_and_aoe_are_not_closed_early(self):
        e = event()
        e['verification'] = {'state': 'verified'}
        e['submit'] = node('2026-10-25', '2026-10-24T23:59:00-12:00', 'deadline', 'AoE')
        refresh_status(e, dt.datetime(2026, 10, 25, 8, 20, tzinfo=BEIJING))
        self.assertEqual(e['status'], 'open')
        refresh_status(e, dt.datetime(2026, 10, 25, 20, 0, tzinfo=BEIJING))
        self.assertEqual(e['status'], 'closed')
        self.assertEqual(cutoff(node('2026-10-24', kind='deadline', timezone='AoE')).astimezone(BEIJING).day, 25)

    def test_explicitly_closed_event_cannot_reopen_from_dates_alone(self):
        e = event()
        e.update(status='closed', verification={'state': 'verified'})
        e['entry'] = node('2026-09-01', kind='deadline', timezone='UTC')
        e['submit'] = node('2026-10-30', kind='deadline', timezone='UTC')
        refresh_status(e, dt.datetime(2026, 9, 28, tzinfo=BEIJING))
        self.assertEqual(e['status'], 'closed')

    def test_opening_is_not_a_deadline_and_unknown_zone_cannot_expire(self):
        self.assertIsNone(cutoff(node('2026-09-01', kind='opening', timezone='UTC')))
        self.assertIsNone(cutoff(node('2026-09-01', kind='deadline', timezone='unknown')))

    def test_legacy_records_are_not_silently_reverified(self):
        e = event()
        e['submit'] = {'text': 'old date', 'day': '2020-01-01', 'instant': None}
        refresh_status(e, dt.datetime(2026, 9, 27, tzinfo=BEIJING))
        self.assertNotIn('verification', e)

    def test_historical_source_objects(self):
        e = event()
        e['sources'] = [{'label': 'Rules', 'url': 'https://contest.example/rules'}]
        self.assertEqual(source_urls(e), ['https://contest.example/rules'])


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        write_json(self.base / 'events.json', [event()])
        write_json(self.base / 'sources.json', {'rules': {}, 'sources': [
            {'url': 'https://contest.example/list', 'name': 'Official list', 'tier': 'core'}]})
        (self.base / 'runs-log.jsonl').write_text('')
        self.env = patch.dict(os.environ, {'BUILD_NOW': '2026-09-27T08:20:00+08:00'})
        self.env.start()
        self.task = scout.prepare(self.base)
        self.proposal = {'runId': self.task['runId'], 'date': self.task['date'],
                         'sources': [{'url': 'https://contest.example/list', 'status': 'ok', 'note': 'Read official list'}],
                         'updates': [update()], 'failed': []}
        self.evidence = {'pages': {'https://contest.example/rules': {'text': 'Open to all participants. Official event rules.'},
                                   'https://contest.example/list': {'text': 'Official competition list'}},
                         'sources': {'https://contest.example/list': 'https://contest.example/list'}}

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def apply(self):
        write_json(self.base / '.scout/proposal.json', self.proposal)
        write_json(self.base / '.scout/evidence.json', self.evidence)
        return scout.apply(self.base)

    def test_verified_update_clears_unknown_dates_and_updates_eligibility(self):
        existing = event()
        existing['submit'] = node('2026-10-11', kind='deadline', timezone='UTC')
        write_json(self.base / 'events.json', [existing])
        self.task = scout.prepare(self.base)
        self.proposal.update(runId=self.task['runId'], date=self.task['date'])
        self.proposal['updates'][0]['eligibility'] = 'student_only'
        self.apply()
        result = json.loads((self.base / 'events.json').read_text())[0]
        self.assertIsNone(result['submit']['day'])
        self.assertIsNone(result['submit']['instant'])
        self.assertEqual(result['status'], 'excluded')
        self.assertEqual(result['verification']['verifiedAt'], '2026-09-27')

    def test_invalid_proposal_leaves_all_published_data_unchanged(self):
        before = (self.base / 'events.json').read_bytes()
        self.proposal['updates'][0]['event']['submit'] = node('2026-02-30', kind='deadline')
        with self.assertRaises(ValueError):
            self.apply()
        self.assertEqual((self.base / 'events.json').read_bytes(), before)
        self.assertFalse((self.base / 'refresh-status.json').exists())

    def test_fabricated_quote_is_rejected(self):
        self.proposal['updates'][0]['evidence'][0]['quote'] = 'Unseen invented deadline and eligibility'
        with self.assertRaisesRegex(ValueError, 'evidence quote'):
            self.apply()

    def test_missing_source_and_target_coverage_rejected(self):
        for key in ('sources', 'updates'):
            proposal = copy.deepcopy(self.proposal)
            proposal[key] = []
            with self.assertRaises(ValueError):
                scout.validate_proposal(proposal, self.task, [event()])

    def test_real_source_registry_can_stage_a_proposal(self):
        shutil.copy2(ROOT / 'sources.json', self.base / 'sources.json')
        task = scout.prepare(self.base)
        urls = [item['url'] for item in task['sources']]
        self.assertEqual(len(urls), len(set(urls)))
        agent = agent_refresh.Agent(self.base)
        staged = agent.save()
        self.assertEqual(len(staged['sources']), len(urls))
        self.assertTrue(any(s.get('relatedEntries') for s in task['sources']))

    def test_changed_baseline_and_stale_proposal_are_rejected(self):
        other = event()
        other['title'] = 'Concurrent edit'
        with self.assertRaisesRegex(ValueError, 'changed after'):
            scout.validate_proposal(self.proposal, self.task, [other])
        self.proposal['runId'] = 'old-run'
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.apply()

    def test_failures_preserve_data_and_do_not_advance_verification(self):
        self.proposal['updates'] = []
        self.proposal['failed'] = [{'eventId': 'existing', 'reason': 'Official site unavailable'}]
        status = self.apply()
        e = json.loads((self.base / 'events.json').read_text())[0]
        self.assertEqual(status['state'], 'partial')
        self.assertIsNone(e['verification']['verifiedAt'])
        self.assertEqual(e['title'], event()['title'])

    def test_same_day_runs_append_history(self):
        self.apply()
        scout.failed('Second run model unavailable', self.base)
        self.assertEqual(len((self.base / 'runs-log.jsonl').read_text().splitlines()), 2)

    def test_existing_url_cannot_be_added_with_a_new_id(self):
        self.proposal['updates'][0]['eventId'] = None
        self.proposal['failed'] = [{'eventId': 'existing', 'reason': 'Candidate matched by URL'}]
        with self.assertRaisesRegex(ValueError, 'event already exists'):
            self.apply()
        self.assertEqual(len(json.loads((self.base / 'events.json').read_text())), 1)

    def test_agent_tool_loop_roundtrip_without_network(self):
        shutil.copytree(ROOT / '.agents', self.base / '.agents')
        base = self.base
        class FakeFetcher:
            def fetch(self, url, render=False):
                ev = json.loads((base / '.scout/evidence.json').read_text())
                text = 'Open to all participants. Official competition list and rules.'
                ev['pages'][url] = {'text': text}
                write_json(base / '.scout/evidence.json', ev)
                return {'url': url, 'text': text, 'links': []}
            def close(self):
                pass
        calls = [('read_task', {}), ('fetch_page', {'url': 'https://contest.example/list'}),
                 ('record_source', {'url': 'https://contest.example/list', 'status': 'ok', 'note': 'Official listing read'}),
                 ('fetch_page', {'url': 'https://contest.example/rules'}), ('record_event', {'update': update()}), ('finish', {})]
        def completion(messages):
            index = len([m for m in messages if m['role'] == 'assistant'])
            name, args = calls[index]
            if index:
                self.assertTrue(any(m['role'] == 'tool' and m.get('tool_call_id') == str(index - 1) for m in messages))
            return {'role': 'assistant', 'content': None, 'tool_calls': [{'id': str(index), 'type': 'function',
                    'function': {'name': name, 'arguments': json.dumps(args)}}]}, {'total_tokens': 10}
        with patch.object(agent_refresh, 'Fetcher', return_value=FakeFetcher()):
            agent_refresh.run(base, completion=completion, max_steps=10)
        result = scout.apply(base)
        self.assertEqual(result['state'], 'ok')
        self.assertEqual(result['verified'], 1)

    def test_arbitrary_tool_is_not_executable(self):
        agent = agent_refresh.Agent(self.base)
        with self.assertRaisesRegex(ValueError, 'Unknown tool'):
            agent.tool('bash', {'command': 'echo should-not-run'})


if __name__ == '__main__':
    unittest.main()
