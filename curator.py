"""
curator.py
----------
Standalone "self-auditing" agent — NOT the chat agent, and not triggered by
a user message. Run this on its own (locally, in CI, or on a schedule) to
have an agent walk every VERIFY entry in knowledge_base.py, try to confirm
it against a real official source, and write a report for a human to
review. Nothing here overwrites knowledge_base.py automatically — same
"log for human review, don't auto-trust a single pass" discipline as
submit_feedback.

This is the clearest demonstration of genuinely agentic behavior in this
project: the system notices what it doesn't know and goes and tries to fix
that on its own, without a user in the loop at all.

Requires the same AWS_PROFILE/AWS_REGION as app.py, plus GOOGLE_SEARCH_API_KEY
and GOOGLE_SEARCH_CX for find_official_source to actually work (otherwise
every entry comes back INCONCLUSIVE, which is still an honest result).

Run with: python curator.py
Writes:   data/curation_report.md
"""

import os
from datetime import datetime, timezone
from pathlib import Path

from strands import Agent
from strands.models import BedrockModel

from tools import find_official_source, fetch_official_page_summary
from knowledge_base import (
    WORK_HOUR_RULES,
    FORBIDDEN_WORK_CATEGORIES,
    BLOCKED_ACCOUNT_MINIMUMS,
    INSURANCE_REQUIREMENTS,
    MISC_REQUIREMENTS,
)

REGION = os.environ.get("AWS_REGION", "us-west-2")
REPORT_PATH = Path(__file__).parent / "data" / "curation_report.md"
REPORT_PATH.parent.mkdir(exist_ok=True)

CURATOR_SYSTEM_PROMPT = """
You are a fact-checking research assistant for a student-visa knowledge
base. You will be given a country, a topic, and the CURRENT unverified
note on file. Your job:

1. Use find_official_source to search for the real official page.
2. Use fetch_official_page_summary to actually read the most official-
   looking result (.gov / .go.<cc> / embassy / national immigration
   authority domain — never a blog, forum, or aggregator).
3. Compare what the page actually says to the current note.
4. Reply with EXACTLY one of these verdicts as your first line, then 2-4
   sentences of explanation:
   - CONFIRMED — matches our note closely enough to trust
   - OUTDATED — the page contradicts or updates our note
   - INCONCLUSIVE — couldn't find or read a sufficiently official source

Never state a number or rule as fact unless you actually read it on a
fetched official page in this session. If find_official_source comes back
NOT_CONFIGURED, say INCONCLUSIVE and say why — do not fall back on your
own training-data memory to fill the gap.
"""


def _collect_unverified():
    """Yield (source, country, topic, current_note) for every unverified
    entry we know how to read. Covers the 'flat' shape (verified: bool +
    note: str) plus MISC_REQUIREMENTS' one-level-nested shape.
    DOCUMENT_CHECKLISTS / LOCAL_RULES / BUDGET_BASELINES use a slightly
    different internal shape and aren't wired in here yet — the same
    pattern extends to them if you want full coverage; left out to keep
    this script's first pass small and readable."""
    flat_sources = {
        "WORK_HOUR_RULES": WORK_HOUR_RULES,
        "FORBIDDEN_WORK_CATEGORIES": FORBIDDEN_WORK_CATEGORIES,
        "BLOCKED_ACCOUNT_MINIMUMS": BLOCKED_ACCOUNT_MINIMUMS,
        "INSURANCE_REQUIREMENTS": INSURANCE_REQUIREMENTS,
    }
    for source_name, table in flat_sources.items():
        for country, entry in table.items():
            if not entry.get("verified", False):
                topic = source_name.replace("_", " ").title()
                yield source_name, country, topic, entry.get("note", "(no note on file)")

    for country, topics in MISC_REQUIREMENTS.items():
        for topic, entry in topics.items():
            if not entry.get("verified", False):
                yield "MISC_REQUIREMENTS", country, topic.replace("_", " "), entry.get("note", "(no note on file)")


def run_curator(verbose: bool = True) -> str:
    """Run the curator over every unverified entry and return the full
    report as text (also written to REPORT_PATH). Importable so app.py's
    "Run knowledge check" button can trigger the same real research run —
    this is not a canned response, it makes live tool calls."""
    model = BedrockModel(model_id="global.anthropic.claude-sonnet-4-6", region_name=REGION, temperature=0.1)
    agent = Agent(model=model, system_prompt=CURATOR_SYSTEM_PROMPT, tools=[find_official_source, fetch_official_page_summary])

    targets = list(_collect_unverified())
    if verbose:
        print(f"Curator: found {len(targets)} unverified entries to check.\n")

    lines = ["# Knowledge base curation report", f"Run at {datetime.now(timezone.utc).isoformat()}", ""]
    for source_name, country, topic, current_note in targets:
        if verbose:
            print(f"Checking {country.title()} — {topic} ...")
        prompt = (
            f"Country: {country.title()}\nTopic: {topic}\n"
            f"Current note on file: {current_note}\n\n"
            f"Research this and give your verdict."
        )
        try:
            result = str(agent(prompt))
        except Exception as e:
            result = f"INCONCLUSIVE — curator run failed: {e}"

        verdict = result.strip().splitlines()[0] if result.strip() else "INCONCLUSIVE — empty response"
        if verbose:
            print(f"  -> {verdict}\n")

        lines.append(f"## {country.title()} — {topic} ({source_name})")
        lines.append(f"**Current note:** {current_note}")
        lines.append("")
        lines.append(f"**Curator finding:**\n{result}")
        lines.append("")

    report = "\n".join(lines)
    REPORT_PATH.write_text(report, encoding="utf-8")
    if verbose:
        print(f"Done. Report written to {REPORT_PATH}")
    return report


if __name__ == "__main__":
    run_curator()