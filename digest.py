"""
digest.py
---------
Standalone proactive "weekly digest" job — NOT the chat agent, and doesn't
call Bedrock at all. It just reads the same on-disk state app.py already
writes (data/sessions_meta.json, data/work_log.jsonl, data/deadlines.json)
and produces a "here's what needs your attention" digest per chat, with no
user asking for it. Run this on a schedule (cron, or Bedrock AgentCore's
scheduled invocation in production) to prove Strivend is actually a
background agent and not just a chatbot that waits to be spoken to.

In a real deployment this is where you'd push the digest out (email/SMS/
push notification) instead of just writing a file — see README "Where to
improve next".

Run with: python digest.py
Writes:   data/digest_<session_id>.md (and prints to stdout)
"""

import json
from datetime import date, datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
SESSIONS_META_PATH = DATA_DIR / "sessions_meta.json"
WORK_LOG_PATH = DATA_DIR / "work_log.jsonl"
DEADLINES_PATH = DATA_DIR / "deadlines.json"
DEADLINE_LOOKAHEAD_DAYS = 14


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _quota_summary(country: str) -> str:
    norm = country.strip().lower()
    if not norm:
        return "No country pinned for this chat — nothing to check."
    current_year = str(date.today().year)
    full_days = half_days = total_hours = 0
    if WORK_LOG_PATH.exists():
        with open(WORK_LOG_PATH, encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("country") != norm or not entry.get("date", "").startswith(current_year):
                    continue
                hours = entry.get("hours", 0)
                total_hours += hours
                if norm == "germany":
                    full_days += 1 if hours > 4 else 0
                    half_days += 1 if hours <= 4 else 0

    if norm == "germany" and (full_days or half_days):
        used = full_days + half_days / 2
        flag = " ⚠️ approaching the 140 full-day limit — review soon." if used >= 112 else ""
        return f"{full_days} full day(s) + {half_days} half day(s) logged this year ({used:.1f} full-day-equivalents of 140).{flag}"
    if total_hours:
        return f"{total_hours:.1f} hours logged this year (no verified quota rule for {country.title()} yet — raw hours only)."
    return f"No work days logged yet for {country.title()} this year."


def _upcoming_deadlines(country: str):
    deadlines = _load_json(DEADLINES_PATH, [])
    today = date.today()
    norm = country.strip().lower()
    upcoming = []
    for d in deadlines:
        try:
            due = datetime.strptime(d["date"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        if d.get("done"):
            continue
        # Deadlines aren't currently tagged per-session — show ones matching
        # this chat's country, plus any untagged ones, so nothing is missed.
        if d.get("country") and d["country"].strip().lower() != norm:
            continue
        delta = (due - today).days
        if 0 <= delta <= DEADLINE_LOOKAHEAD_DAYS:
            upcoming.append((delta, d))
    upcoming.sort(key=lambda x: x[0])
    return upcoming


def _digest_report(country: str, title: str) -> str:
    lines = [f"# Weekly digest — {title}" + (f" ({country})" if country else ""), ""]
    lines.append(f"**Work-hour quota:** {_quota_summary(country)}")
    lines.append("")

    upcoming = _upcoming_deadlines(country)
    if upcoming:
        lines.append(f"**Deadlines in the next {DEADLINE_LOOKAHEAD_DAYS} days:**")
        for delta, d in upcoming:
            urgency = " 🔴 URGENT" if delta <= 3 else ""
            lines.append(f"- {d.get('event', 'Untitled')} — {d.get('date')} ({delta} day(s) away){urgency}")
    else:
        lines.append(f"**Deadlines in the next {DEADLINE_LOOKAHEAD_DAYS} days:** none.")

    return "\n".join(lines)


def build_digest_for_session(sid: str, country: str = "", title: str = "chat") -> str:
    """On-demand digest for a single, already-known session — what
    app.py's "Check my status" button calls. Doesn't touch Bedrock at all,
    just reads the on-disk logs, so it's fast enough to run synchronously
    in a request."""
    report = _digest_report(country, title)
    (DATA_DIR / f"digest_{sid}.md").write_text(report, encoding="utf-8")
    return report


def build_digest():
    """CLI/scheduled sweep across every session on disk — reads
    sessions_meta.json directly rather than needing a live app.py process."""
    sessions = _load_json(SESSIONS_META_PATH, {})
    if not sessions:
        print("No sessions found — nothing to digest yet.")
        return

    for sid, s in sessions.items():
        country = (s.get("country") or "").strip()
        title = s.get("title", "chat")
        report = build_digest_for_session(sid, country, title)
        print(report)
        print("\n" + "=" * 60 + "\n")

    print(f"Digest files written to {DATA_DIR}/digest_<session_id>.md")


if __name__ == "__main__":
    build_digest()