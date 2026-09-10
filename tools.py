"""
tools.py
--------
Each tool is a plain Python function the agent can call when it decides
it's relevant — the docstring is what teaches the agent WHEN to use it.
Same design philosophy as the other two agents this project family shares:
never invent facts, always say so honestly when data is unverified, and
log everything the agent doesn't fully trust for human review instead of
acting on it directly.
"""

import json
import re
from datetime import datetime, date, timezone
from pathlib import Path

import requests
from strands import tool

from knowledge_base import (
    WORK_HOUR_RULES,
    FORBIDDEN_WORK_CATEGORIES,
    BLOCKED_ACCOUNT_MINIMUMS,
    BUDGET_BASELINES,
    LOCAL_RULES,
    INSURANCE_REQUIREMENTS,
    DOCUMENT_CHECKLISTS,
)

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

WORK_LOG_PATH = DATA_DIR / "work_log.jsonl"
DEADLINES_PATH = DATA_DIR / "deadlines.json"
FEEDBACK_LOG_PATH = DATA_DIR / "feedback_log.jsonl"


def _normalize(country: str) -> str:
    return country.strip().lower()


def _verify_note(entry: dict) -> str:
    """Standard trailer appended whenever we're returning unverified data."""
    if entry.get("verified"):
        return ""
    return (
        "\n\n⚠️ This entry is marked VERIFY in our knowledge base — it is an illustrative "
        "approximation, not confirmed against a current official source. Tell the user to "
        "double-check this with the relevant embassy, immigration office, or university "
        "International Office before relying on it."
    )


@tool
def get_work_hour_limit(country: str) -> str:
    """Get the work-hour/day quota rules for international students in a
    given country, including how full/half days are counted, the annual or
    weekly cap, and which activities are exempt.

    Args:
        country: Destination country, e.g. "Germany", "Japan", "South Korea".

    Returns:
        The rule details as plain text, with a clear VERIFY warning
        attached if the entry hasn't been confirmed against a current
        official source. Never state a number from memory if this tool
        returns NOT_COVERED.
    """
    entry = WORK_HOUR_RULES.get(_normalize(country))
    if not entry:
        return (
            f"NOT_COVERED — we don't have work-hour data for '{country}' yet. "
            f"Tell the user to check with their university's International Office "
            f"or the national immigration authority directly."
        )
    if not entry.get("verified"):
        return f"{entry['note']}{_verify_note(entry)}"

    lines = [f"Work-hour rules for {country.title()} (verified):"]
    for key, val in entry.items():
        if key in ("verified",):
            continue
        if isinstance(val, list):
            lines.append(f"- {key}: " + "; ".join(val))
        else:
            lines.append(f"- {key}: {val}")
    return "\n".join(lines)


@tool
def log_work_day(country: str, work_date: str, hours_worked: float) -> str:
    """Record a day the student worked, so their quota usage can be tracked
    over time. Call this whenever the user tells you they worked a shift.

    Args:
        country: The country this work counts toward, e.g. "Germany".
        work_date: The date worked, in YYYY-MM-DD format.
        hours_worked: Number of hours worked that day.

    Returns:
        A confirmation message, including whether this counts as a full or
        half day under that country's rule (Germany only — other countries
        are logged but not yet auto-classified).
    """
    try:
        datetime.strptime(work_date, "%Y-%m-%d")
    except ValueError:
        return "INVALID_DATE — please provide the date in YYYY-MM-DD format."

    entry = {
        "country": _normalize(country),
        "date": work_date,
        "hours": hours_worked,
        "logged_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(WORK_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    classification = ""
    if _normalize(country) == "germany":
        classification = " → counts as a FULL day (Germany: any shift over 4 hours is 1 full day)." \
            if hours_worked > 4 else " → counts as a HALF day (Germany: 4 hours or less)."

    return f"Logged {hours_worked}h on {work_date} for {country.title()}.{classification} Use check_quota_remaining to see the running total."


@tool
def check_quota_remaining(country: str) -> str:
    """Check how much of the student's annual work-day/hour quota has been
    used so far this calendar year, based on days logged with log_work_day.

    Args:
        country: The country to check, e.g. "Germany".

    Returns:
        A summary of days/hours used and remaining, or a message that no
        work has been logged yet. For countries other than Germany, this
        only reports total hours logged, since the exact quota-counting
        rule for that country isn't in our verified data yet.
    """
    norm = _normalize(country)
    current_year = str(date.today().year)
    full_days = 0
    half_days = 0
    total_hours = 0.0
    entries_found = 0

    if WORK_LOG_PATH.exists():
        with open(WORK_LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("country") != norm or not entry.get("date", "").startswith(current_year):
                    continue
                entries_found += 1
                hours = entry.get("hours", 0)
                total_hours += hours
                if norm == "germany":
                    if hours > 4:
                        full_days += 1
                    else:
                        half_days += 1

    if entries_found == 0:
        return f"No work days logged yet for {country.title()} in {current_year}. Use log_work_day to start tracking."

    if norm == "germany":
        rule = WORK_HOUR_RULES.get("germany", {})
        limit_text = rule.get("non_eu_annual_limit", "140 full days or 280 half days per calendar year")
        used_full_equivalent = full_days + (half_days / 2)
        return (
            f"{current_year} so far for Germany: {full_days} full day(s) + {half_days} half day(s) logged "
            f"({total_hours:.1f} total hours). That's approximately {used_full_equivalent:.1f} full-day-equivalents "
            f"against the limit of {limit_text} This is based only on what's been logged in this tool — "
            f"if the student has worked days they haven't logged here, the real total will be higher."
        )

    return (
        f"{current_year} so far for {country.title()}: {total_hours:.1f} total hours logged across "
        f"{entries_found} entries. We don't have a verified day/hour quota rule for this country yet "
        f"(see get_work_hour_limit), so this is a raw hours log only — not a quota comparison."
    )


@tool
def get_forbidden_work_categories(country: str) -> str:
    """Get categories of work that are restricted or disallowed for
    international students in a given country, regardless of their
    remaining hour/day quota.

    Args:
        country: Destination country, e.g. "Germany".

    Returns:
        The restricted categories, with a VERIFY warning if unconfirmed.
    """
    entry = FORBIDDEN_WORK_CATEGORIES.get(_normalize(country))
    if not entry:
        return f"NOT_COVERED — no data for '{country}' yet. Recommend checking with the university's International Office."
    if not entry.get("verified"):
        return f"{entry['note']}{_verify_note(entry)}"
    return "Restricted/disallowed without separate approval:\n" + "\n".join(f"- {r}" for r in entry["restricted"])


@tool
def add_deadline(event_name: str, deadline_date: str, country: str = "") -> str:
    """Add a deadline to the student's tracked calendar — a visa renewal
    appointment, a document submission date, an exam registration cutoff,
    an Anmeldung deadline, etc.

    Args:
        event_name: Short description of what's due, e.g. "Residence permit renewal appointment".
        deadline_date: The date, in YYYY-MM-DD format.
        country: Optional — which country this relates to.

    Returns:
        A confirmation message.
    """
    try:
        datetime.strptime(deadline_date, "%Y-%m-%d")
    except ValueError:
        return "INVALID_DATE — please provide the date in YYYY-MM-DD format."

    deadlines = []
    if DEADLINES_PATH.exists():
        try:
            deadlines = json.loads(DEADLINES_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            deadlines = []

    deadlines.append({
        "event": event_name,
        "date": deadline_date,
        "country": country,
        "added_at": datetime.now(timezone.utc).isoformat(),
        "done": False,
    })
    DEADLINES_PATH.write_text(json.dumps(deadlines, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"Added: '{event_name}' on {deadline_date}{f' ({country})' if country else ''}."


@tool
def list_upcoming_deadlines(days_ahead: int = 30) -> str:
    """List deadlines coming up within a given number of days, soonest first.

    Args:
        days_ahead: How many days into the future to look. Defaults to 30.

    Returns:
        A list of upcoming deadlines, or a message that nothing is coming up.
    """
    if not DEADLINES_PATH.exists():
        return "No deadlines have been added yet. Use add_deadline to start tracking them."

    try:
        deadlines = json.loads(DEADLINES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "No deadlines have been added yet."

    today = date.today()
    upcoming = []
    for d in deadlines:
        if d.get("done"):
            continue
        try:
            d_date = datetime.strptime(d["date"], "%Y-%m-%d").date()
        except (ValueError, KeyError):
            continue
        delta = (d_date - today).days
        if 0 <= delta <= days_ahead:
            upcoming.append((delta, d))

    if not upcoming:
        return f"No deadlines in the next {days_ahead} days."

    upcoming.sort(key=lambda x: x[0])
    lines = [f"Upcoming deadlines (next {days_ahead} days):"]
    for delta, d in upcoming:
        urgency = " ⚠️ SOON" if delta <= 7 else ""
        country_tag = f" [{d.get('country')}]" if d.get("country") else ""
        lines.append(f"- {d['date']} ({delta} day(s) away): {d['event']}{country_tag}{urgency}")
    return "\n".join(lines)


@tool
def estimate_monthly_budget(country: str) -> str:
    """Get a rough baseline monthly cost-of-living breakdown for a
    destination country, to help a student sanity-check their budget.
    These are illustrative ranges, not precise figures — actual costs vary
    significantly by city.

    Args:
        country: Destination country, e.g. "France".

    Returns:
        A cost breakdown by category with an explicit range, in local
        currency, plus a caveat about city-level variation.
    """
    entry = BUDGET_BASELINES.get(_normalize(country))
    if not entry:
        return f"NOT_COVERED — no budget baseline for '{country}' yet."

    currency = entry["currency"]
    lines = [f"Rough monthly cost baseline for {country.title()} (in {currency}, illustrative ranges only):"]
    for label, key in [("Rent", "rent_range"), ("Health insurance", "health_insurance_range"),
                        ("Phone/internet", "phone_internet_range"), ("Food", "food_range"),
                        ("Transport", "transport_range")]:
        low, high = entry[key]
        lines.append(f"- {label}: {low:,} - {high:,} {currency}")
    low_total = sum(entry[k][0] for k in ["rent_range", "health_insurance_range", "phone_internet_range", "food_range", "transport_range"])
    high_total = sum(entry[k][1] for k in ["rent_range", "health_insurance_range", "phone_internet_range", "food_range", "transport_range"])
    lines.append(f"- Rough total range: {low_total:,} - {high_total:,} {currency}/month")
    lines.append(f"\nNote: {entry['note']}")
    return "\n".join(lines)


@tool
def track_blocked_account_balance(country: str, current_balance: float) -> str:
    """Compare a student's current blocked-account / proof-of-funds balance
    against the required minimum for their destination country.

    Args:
        country: Destination country, e.g. "Germany".
        current_balance: The student's current balance in that country's
        required currency (e.g. EUR for Germany).

    Returns:
        Whether the balance meets the requirement, with the gap if not,
        and a VERIFY warning if the country's figure isn't confirmed.
    """
    entry = BLOCKED_ACCOUNT_MINIMUMS.get(_normalize(country))
    if not entry:
        return f"NOT_COVERED — no blocked-account/proof-of-funds figure for '{country}' yet."

    if not entry.get("verified"):
        return f"{entry['note']}{_verify_note(entry)}"

    required = entry["amount_eur_per_year"]
    if current_balance >= required:
        return f"Meets the requirement: {current_balance:,.2f} is at or above the required {required:,} minimum. {entry['note']}"
    gap = required - current_balance
    return f"Below the requirement: {current_balance:,.2f} is short by {gap:,.2f} of the required {required:,} minimum. {entry['note']}"


@tool
def get_local_rules(country: str, category: str = "") -> str:
    """Get local rules or etiquette norms that commonly catch new
    international students off guard — quiet hours, shop closing days,
    recycling/waste sorting, mandatory address registration deadlines, etc.

    Args:
        country: Destination country, e.g. "Germany".
        category: Optional filter, e.g. "quiet_hours", "recycling". Leave
        empty to get all known rules for that country.

    Returns:
        The matching rule(s), with a VERIFY warning if the country's
        section hasn't been confirmed yet.
    """
    entry = LOCAL_RULES.get(_normalize(country))
    if not entry:
        return f"NOT_COVERED — no local rules recorded for '{country}' yet."

    rules = entry["rules"]
    if category:
        rules = [r for r in rules if category.lower() in r["category"].lower()]
        if not rules:
            return f"No rule found for category '{category}' in {country.title()}."

    lines = [f"{r['category']}: {r['en']}" for r in rules]
    return "\n".join(lines) + _verify_note(entry)


@tool
def get_insurance_requirement(country: str) -> str:
    """Get the health/student insurance requirement for a destination
    country.

    Args:
        country: Destination country, e.g. "Japan".

    Returns:
        The insurance requirement note, with a VERIFY warning if unconfirmed.
    """
    entry = INSURANCE_REQUIREMENTS.get(_normalize(country))
    if not entry:
        return f"NOT_COVERED — no insurance data for '{country}' yet."
    return f"{entry['note']}{_verify_note(entry)}"


@tool
def get_required_documents(country: str, purpose: str = "arrival") -> str:
    """Get the checklist of documents needed for a specific stage of the
    student's stay.

    Args:
        country: Destination country, e.g. "Germany".
        purpose: One of "arrival" or "renewal". Defaults to "arrival".

    Returns:
        The document checklist, with a VERIFY warning if unconfirmed.
    """
    entry = DOCUMENT_CHECKLISTS.get(_normalize(country))
    if not entry:
        return f"NOT_COVERED — no document checklist for '{country}' yet."

    checklist = entry.get(purpose)
    if not checklist:
        return f"NOT_COVERED — no '{purpose}' checklist for '{country}' yet. Try 'arrival' or 'renewal'."

    lines = [f"{purpose.title()} document checklist for {country.title()}:"]
    lines.extend(f"- {item}" for item in checklist)
    return "\n".join(lines) + _verify_note(entry)


@tool
def fetch_official_page_summary(url: str) -> str:
    """Fetch the raw text of an official government/university web page so
    you can explain its contents or walk the user through a form. Use this
    when the user gives you a specific URL (e.g. an Ausländerbehörde
    appointment page or a visa application form page) and wants help
    understanding or filling it out.

    Args:
        url: The full URL of the page to fetch, including https://.

    Returns:
        A cleaned, truncated plain-text extract of the page, or an error
        message if it couldn't be fetched. Always tell the user which URL
        this came from, and never claim information came from this page if
        the fetch failed — fall back to saying you don't have it.
    """
    if not url.lower().startswith(("http://", "https://")):
        return "INVALID_URL — please provide a full URL starting with http:// or https://."

    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Scholaris-Hackathon-Agent/1.0"},
            timeout=10,
        )
        response.raise_for_status()
    except Exception as e:
        return f"FETCH_FAILED — couldn't retrieve {url} ({e}). Tell the user to open the link directly instead."

    text = response.text
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    truncated = text[:4000]
    suffix = "... [truncated]" if len(text) > 4000 else ""
    return f"Content fetched from {url}:\n\n{truncated}{suffix}"


@tool
def submit_feedback(category: str, details: str) -> str:
    """Log a correction or real-world information a user offers — e.g. an
    outdated work-hour figure, a document requirement that changed, or a
    general suggestion. This does NOT change the agent's knowledge
    immediately — it saves the info for a human to review before it's
    added to the reference data.

    Args:
        category: Short label, e.g. "work_hour_update", "wrong_document_info".
        details: The actual information or suggestion the user provided.

    Returns:
        A confirmation message to show the user.
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "category": category,
        "details": details,
    }
    try:
        with open(FEEDBACK_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return "Thank you — logged for review before being added to the official reference data."
    except Exception as e:
        return f"Couldn't save this right now ({e}), but thank you for sharing it."
