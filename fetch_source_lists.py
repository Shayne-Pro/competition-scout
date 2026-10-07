#!/usr/bin/env python3
"""Read official public list APIs; inventory completion is not event verification.

Codabench endpoint: /api/docs/ -> /api/api/schema/ -> competitions/public.
EvalAI endpoints: official /dist/js/controllers.min.js and config.min.js.
Uses no credentials, LLM service, or certificate-validation bypass.
"""
import argparse
import datetime
import json
from pathlib import Path
import urllib.parse
import urllib.error
import urllib.request
import time
from refresh_core import atomic_json, BEIJING

BASE = Path(__file__).resolve().parent
PLANS = {
    "codabench": ("https://www.codabench.org/api/competitions/public/?ordering=recent&page_size=100", {"www.codabench.org", "codabench.org", "codabench-prod.lisn.upsaclay.fr"}),
    **{f"evalai-{phase}": (f"https://eval.ai/api/challenges/challenge/{phase}/approved/public", {"eval.ai"}) for phase in ("present", "future", "past")},
}


def get_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "CompetitionScout/1.0", "Accept": "application/json"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                return json.load(response)
        except urllib.error.URLError as error:
            if attempt or isinstance(error, urllib.error.HTTPError) and error.code not in (429, 500, 502, 503, 504):
                raise
            time.sleep(1)


def allowed_url(url, hosts):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in hosts or parsed.username or parsed.password:
        raise ValueError("pagination URL is outside the official HTTPS API hosts")


def collect(name, output, max_pages=100, fetch=get_json):
    seed, hosts = PLANS[name]
    output.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now(BEIJING).isoformat(timespec="seconds")
    result = {"source": name, "url": seed, "startedAt": now, "finishedAt": None,
              "state": "partial", "coverage": "official public list inventory; rules and eligibility remain unverified",
              "pages": [], "items": [], "count": None, "next": seed, "error": None}
    atomic_json(output, result)  # Never reuse an old successful snapshot after a failed run.
    seen_urls, seen_ids = set(), set()
    try:
        while result["next"] and len(result["pages"]) < max_pages:
            url = result["next"]
            allowed_url(url, hosts)
            if url in seen_urls:
                raise ValueError("pagination loop")
            payload = fetch(url)
            if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                raise ValueError("not a paginated public list response")
            count = payload.get("count")
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise ValueError("missing or invalid list count")
            if result["count"] is not None and result["count"] != count:
                raise ValueError("list count changed during pagination; rescan required")
            result["count"] = count
            batch = payload["results"]
            normalized = []
            for item in batch:
                if not isinstance(item, dict) or item.get("id") is None or not isinstance(item.get("title"), str):
                    raise ValueError("invalid list item")
                key = str(item["id"])
                if key in seen_ids:
                    raise ValueError("duplicate ID across list pages; rescan required")
                seen_ids.add(key)
                detail = (f"https://www.codabench.org/competitions/{key}/" if name == "codabench"
                          else f"https://eval.ai/web/challenges/challenge-page/{key}/overview")
                # Retain useful public list facts, never logo signatures or account metadata.
                normalized.append({"id": item["id"], "title": item["title"], "url": detail,
                                   **{k: item[k] for k in ("description", "short_description", "start_date", "end_date", "created_when", "first_phase_start", "reward") if k in item}})
            seen_urls.add(url)
            result["items"].extend(normalized)
            result["pages"].append({"url": url, "items": len(batch), "returnedNext": payload.get("next")})
            next_url = payload.get("next")
            if next_url is not None and not isinstance(next_url, str):
                raise ValueError("invalid next URL")
            result["next"] = urllib.parse.urljoin(url, next_url) if next_url else None
            if result["next"]:
                allowed_url(result["next"], hosts)
                parsed = urllib.parse.urlsplit(result["next"])
                # The public API advertises an unreachable backend host in next.
                # Its exact path/query also work on the documented public origin.
                if name == "codabench" and parsed.hostname == "codabench-prod.lisn.upsaclay.fr":
                    result["next"] = urllib.parse.urlunsplit(parsed._replace(netloc="www.codabench.org"))
            atomic_json(output, result)  # Partial progress and retry cursor survive an interrupted fetch.
        if result["next"]:
            result["error"] = "page limit reached; next URL retained"
        elif len(result["items"]) != result["count"]:
            raise ValueError("unique item count does not match advertised count")
        else:
            result["state"] = "complete"
    except Exception as exc:
        result["state"] = "partial" if result["items"] else "failed"
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["finishedAt"] = datetime.datetime.now(BEIJING).isoformat(timespec="seconds")
    atomic_json(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=BASE / ".scout" / "source-lists")
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--sources", nargs="+", choices=PLANS, default=list(PLANS))
    args = parser.parse_args()
    if args.max_pages < 1:
        parser.error("--max-pages must be positive")
    results = []
    for name in args.sources:
        result = collect(name, args.output_dir / f"{name}.json", args.max_pages)
        summary = {k: result[k] for k in ("source", "state", "count", "next", "error")}
        summary.update(pages=len(result["pages"]), items=len(result["items"]))
        results.append(summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    atomic_json(args.output_dir / "manifest.json", results)
    return 0 if all(r["state"] == "complete" for r in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
