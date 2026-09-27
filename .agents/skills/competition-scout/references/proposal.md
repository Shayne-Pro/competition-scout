# Update contract

`record_event` accepts one object with exactly `eventId`, `event`, `verification`, `eligibility`, `evidence`.

```json
{
  "eventId": null,
  "verification": "verified",
  "eligibility": "open",
  "evidence": [{"url": "https://official.example/contest/rules", "quote": "Short supporting excerpt actually returned by fetch_page."}],
  "event": {
    "title": "Specific competition and edition",
    "platform": "Kaggle",
    "venue": "",
    "tags": ["CV"],
    "task": "具体赛题",
    "entry": {"text": "未单列报名截止", "day": null, "instant": null, "kind": "unknown", "timezone": "unknown"},
    "submit": {"text": "官网明确写出的截止时刻", "day": "2026-10-23", "instant": "2026-10-22T23:59:00Z", "kind": "deadline", "timezone": "UTC"},
    "requirements": "已确认的参赛资格与提交义务",
    "award": "官方金额和币种；未公布时写未公布",
    "warning": "",
    "url": "https://official.example/contest",
    "status": "open",
    "priority": 3
  }
}
```

Existing events use their original eventId; new events use JSON null and receive a URL-based stable ID. The example is fictional and must not be copied as catalogue data. An update supplies all documented event fields. Evidence needs 1–10 official URLs with excerpts of 8–600 characters; cite text actually fetched in this run. Do not quote entire pages.

verification: `verified|partial`. eligibility: `open|student_only|unclear`. Unknown eligibility requires partial; partial requires status unclear. Source-confirmed student-only records are retained as excluded and omitted from the public list. A failed fetch goes to `record_failure`, not an invented update.

Status: `open`, `submission` (mandatory entry prerequisites have passed), `unclear`, `upcoming`, `practice`, `closed`, `excluded`. An explicitly ended event stays closed unless evidence establishes reopening. Dates and status must reflect participation, not organizer proposal deadlines or debug channels.

Each date node requires exactly `text`, `day`, `instant`, `kind`, `timezone`. kind: `deadline|opening|unknown`. Unknown requires null day and instant. Known kind requires a real ISO YYYY-MM-DD. With an exact instant, include its offset and use its Beijing date for day. With only a date, retain its source calendar date. timezone is an IANA name (`Asia/Shanghai`, `UTC`, `America/Los_Angeles`), `AoE`, or `unknown`. Never invent 23:59. Date-only deadlines expire at the end of their stated source day; unknown zones cannot automatically close a competition.

Common tags: `CV`, `大模型`, `Agent`, `检索 / RAG`, `推荐 / 广告`, `医学`, `3D`, `多模态`, `具身 / 机器人`. priority is an integer 1–5, lower first. Do not fabricate missing descriptions, amounts or dates.

`record_source`: exact task URL, status `ok|failed|deferred`, nonempty note, and evidence_url for successful scans. evidence_url must have been fetched in this run; it may be a usable official alternative to the task URL.

`record_failure`: existing eventId and a specific reason. All selected targets require an update or failure. Record results progressively. Call `finish` when done; remaining sources/targets are explicitly marked deferred rather than silently skipped.

For an interactive run, `.scout/proposal.json` has exactly `runId`, `date`, `sources`, `updates`, `failed`. Copy runId/date from task.json. sources contain only `{url,status,note}`. failed contain `{eventId,reason}`. No deletions; maximum 60 updates. The apply command rejects missing coverage, stale run IDs, invalid dates, duplicate identities and changed baseline data. The Python runner also records fetched evidence in `.scout/evidence.json` for validation.
