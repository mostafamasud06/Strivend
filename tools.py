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
import os
import re
from datetime import datetime, date, timedelta, timezone
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
    MISC_REQUIREMENTS,
    LANGUAGE_RESOURCES,
    ARRIVAL_SEQUENCES,
)

GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")
GOOGLE_SEARCH_API_KEY = os.environ.get("GOOGLE_SEARCH_API_KEY", "")
GOOGLE_SEARCH_CX = os.environ.get("GOOGLE_SEARCH_CX", "")

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
def get_misc_local_requirement(country: str, topic: str) -> str:
    """Get a one-off local administrative requirement that doesn't fall
    under work hours, insurance, or documents — e.g. bicycle registration
    in Japan, dog licensing, bank-account rules, SIM-card registration.

    Args:
        country: Destination country, e.g. "Japan".
        topic: Short topic key, e.g. "bicycle_registration". If unsure of
        the exact key, try a plain-language guess — the tool does a loose
        match — and fall back to NOT_COVERED honestly if nothing matches
        rather than guessing an answer yourself.

    Returns:
        The requirement note with a VERIFY warning if unconfirmed, or
        NOT_COVERED if we have no entry — in which case suggest the user
        check with the local municipal office, or use
        fetch_official_page_summary on an official page if they have one.
    """
    country_entries = MISC_REQUIREMENTS.get(_normalize(country))
    if not country_entries:
        return f"NOT_COVERED — no misc. requirements recorded for '{country}' yet."

    key = topic.strip().lower().replace(" ", "_")
    entry = country_entries.get(key)
    if not entry:
        # loose match as a fallback
        for k, v in country_entries.items():
            if key in k or k in key:
                entry = v
                break
    if not entry:
        return f"NOT_COVERED — no entry for '{topic}' in {country.title()} yet. Suggest checking the local municipal/ward office directly."

    return f"{entry['note']}{_verify_note(entry)}"


@tool
def get_language_certification_info(country: str) -> str:
    """Get the recognized language-proficiency exams for a country, their
    issuing institutions, official info sites, and general job-search
    resources useful for international students/graduates.

    Args:
        country: Destination country, e.g. "France".

    Returns:
        Exam names, official sites, and job-search resource names. Exam
        names/institutions are stable facts, but always tell the user to
        confirm current test dates, fees, and registration windows on the
        official site rather than stating them from memory.
    """
    entry = LANGUAGE_RESOURCES.get(_normalize(country))
    if not entry:
        return f"NOT_COVERED — no language/job-search resource list for '{country}' yet."

    lines = [f"Recognized language exams for {country.title()}:"]
    lines.extend(f"- {e}" for e in entry["exams"])
    lines.append("\nOfficial sites (confirm current dates/fees here, don't state them from memory):")
    lines.extend(f"- {s}" for s in entry["official_sites"])
    lines.append("\nGeneral job-search resources:")
    lines.extend(f"- {j}" for j in entry["job_search"])
    return "\n".join(lines) + _verify_note(entry)


@tool
def find_nearby_office(office_type: str, city: str, country: str = "") -> str:
    """Find real, nearby government/administrative offices (e.g. a
    residence-permit office, a citizens' registration office, a police
    station for bicycle registration) using live map data — so the
    student doesn't have to guess an address for an analog, in-person
    process.

    Args:
        office_type: What kind of office, e.g. "Ausländerbehörde",
        "residence permit office", "citizen registration office", "police station".
        city: The city to search in, e.g. "Berlin".
        country: Optional country name to disambiguate, e.g. "Germany".

    Returns:
        A short list of real nearby offices with name and address, sorted
        by proximity, sourced live from Google Places — NOT from memory.
        Does not claim to know which office is fastest/least busy unless
        the Places result itself reports that (e.g. via popular-times
        data); if that data isn't available, say so plainly instead of
        guessing which office is more efficient.
    """
    if not GOOGLE_MAPS_API_KEY:
        return (
            "NOT_CONFIGURED — office lookup requires a GOOGLE_MAPS_API_KEY environment "
            "variable (Google Places API) that hasn't been set up in this deployment. "
            "Tell the user you can't do a live location search right now, and suggest "
            "they search '<office type> near <city>' on Google Maps directly, or check "
            "their city's official municipal website for the correct office (many cities "
            "assign a specific office by postal code, e.g. Berlin's Bürgeramt system)."
        )

    query = f"{office_type} near {city}" + (f", {country}" if country else "")
    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/place/textsearch/json",
            params={"query": query, "key": GOOGLE_MAPS_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"LOOKUP_FAILED — couldn't reach the Places API ({e}). Suggest the user search '{query}' on Google Maps directly."

    if data.get("status") != "OK":
        return f"LOOKUP_FAILED — Places API returned '{data.get('status')}'. Suggest the user search '{query}' on Google Maps directly."

    results = data.get("results", [])[:5]
    if not results:
        return f"No results found for '{query}'. Suggest the user check the city's official municipal website — many assign a specific office by postal code/district rather than 'nearest'."

    lines = [f"Nearby results for '{office_type}' in {city}:"]
    for r in results:
        name = r.get("name", "Unknown")
        address = r.get("formatted_address", "address not available")
        rating = r.get("rating")
        rating_txt = f" (rating {rating}/5, {r.get('user_ratings_total', 0)} reviews)" if rating else ""
        lines.append(f"- {name} — {address}{rating_txt}")
    lines.append(
        "\nNote: this is live map data, not an official assignment — many countries "
        "(e.g. Germany's Bürgeramt/Ausländerbehörde system) route you to a SPECIFIC "
        "office based on your postal code or district, not just the nearest one. "
        "Always double-check with the city's official website or booking portal before "
        "showing up, and book an appointment in advance where required."
    )
    return "\n".join(lines)


@tool
def plan_short_trip_budget(destination_country: str, nights: int, travelers: int = 1) -> str:
    """Give a rough illustrative daily/total budget sanity-check for a
    short trip to another country (e.g. a weekend trip from Germany to
    Poland), reusing the same cost-of-living baselines used for monthly
    budgeting, scaled down. This is NOT flight/hotel/ticket pricing — it
    cannot look up real fares or book anything.

    Args:
        destination_country: Country being visited, e.g. "Poland".
        nights: Number of nights for the trip.
        travelers: Number of people splitting/incurring costs. Defaults to 1.

    Returns:
        A rough daily-cost ballpark (food + local transport, NOT flights/
        trains/hotel) with a clear illustrative-only caveat, plus a
        pointer toward real booking tools for actual prices — never state
        a specific flight, train, or hotel price, since this tool has no
        live pricing data.
    """
    entry = BUDGET_BASELINES.get(_normalize(destination_country))
    if not entry:
        return (
            f"NOT_COVERED — no cost baseline for '{destination_country}' yet, so no "
            f"ballpark can be given. For real fares/hotels, point the user to a flight/"
            f"rail aggregator and a hotel-booking site directly — never invent prices."
        )

    currency = entry["currency"]
    daily_food_low, daily_food_high = entry["food_range"][0] / 30, entry["food_range"][1] / 30
    daily_transport_low, daily_transport_high = entry["transport_range"][0] / 30, entry["transport_range"][1] / 30
    daily_low = (daily_food_low + daily_transport_low) * travelers
    daily_high = (daily_food_high + daily_transport_high) * travelers
    total_low, total_high = daily_low * nights, daily_high * nights

    return (
        f"Rough on-the-ground daily cost for {destination_country.title()} "
        f"(food + local transport only, {travelers} traveler(s)): "
        f"{daily_low:,.0f}-{daily_high:,.0f} {currency}/day → "
        f"{total_low:,.0f}-{total_high:,.0f} {currency} for {nights} night(s).\n\n"
        f"This is a rough illustrative ballpark derived from monthly cost-of-living "
        f"baselines, scaled down — it does NOT include flights/trains or hotel cost, "
        f"and this tool has no access to real fares. For actual prices, point the user "
        f"to a flight/rail search (e.g. a general aggregator or the national rail "
        f"operator's own site) and a hotel-booking site, and to book directly rather "
        f"than relying on any number from this tool.\n\n"
        f"If the student's visa/residence permit allows Schengen-area travel, short "
        f"trips within the Schengen area are generally still capped by the standard "
        f"90-days-in-any-180-days short-stay rule for the underlying travel document — "
        f"tell them to confirm this against their own residence permit conditions, since "
        f"it can differ by permit type and nationality."
    )


@tool
def find_official_source(country: str, topic: str) -> str:
    """Search the live web for the likely OFFICIAL page covering a topic
    for a country that isn't in our curated knowledge base yet (i.e. any
    country other than Germany, Italy, France, Japan, or South Korea —
    or a topic even those five don't have an entry for). Use this before
    telling a user "I don't have that" for an uncovered country: find a
    candidate official page, then use fetch_official_page_summary on the
    best result to actually read it before answering.

    Args:
        country: The country to search for, e.g. "Poland", "Brazil", "Vietnam" — any country, not just the five curated ones.
        topic: What you're looking for, e.g. "student work hour limit", "residence permit requirements".

    Returns:
        A short list of candidate result titles/URLs/snippets from a live
        web search, or NOT_CONFIGURED if no search API key is set up. This
        is a list of LEADS, not a verified answer — always fetch the
        chosen URL with fetch_official_page_summary and read it before
        stating anything as fact, and prefer .gov/.go/embassy/official
        university domains over blogs or forums.
    """
    if not (GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_CX):
        return (
            "NOT_CONFIGURED — live web search requires GOOGLE_SEARCH_API_KEY and "
            "GOOGLE_SEARCH_CX environment variables (Google Programmable Search Engine) "
            "that haven't been set up in this deployment. Tell the user this country/topic "
            "isn't in the curated knowledge base and isn't live-searchable right now, and "
            "suggest they check their national immigration authority's website or their "
            "university's International Office directly — never fill the gap from memory."
        )

    query = f"{country} international student {topic} official"
    try:
        resp = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={"key": GOOGLE_SEARCH_API_KEY, "cx": GOOGLE_SEARCH_CX, "q": query, "num": 5},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"SEARCH_FAILED — couldn't reach the search API ({e}). Suggest the user search '{query}' themselves."

    items = data.get("items", [])
    if not items:
        return f"No results found for '{query}'. Suggest the user check the national immigration authority's site or their International Office directly."

    lines = [f"Live search leads for '{topic}' in {country.title()} (NOT verified yet — fetch and read before trusting):"]
    for it in items:
        lines.append(f"- {it.get('title', 'Untitled')} — {it.get('link', '')}\n  {it.get('snippet', '').strip()}")
    lines.append(
        "\nPick the most official-looking result (.gov, .go.<cc>, embassy, or the university's "
        "own domain) and call fetch_official_page_summary on it before answering — don't answer "
        "from these snippets alone, they're too short to be reliable."
    )
    return "\n".join(lines)


@tool
def plan_arrival_countdown(country: str, move_in_date: str) -> str:
    """Build a dependency-ordered arrival checklist for a country, working
    forward from the student's move-in date. Call this proactively as soon
    as a student mentions an upcoming move/arrival date — don't wait to be
    asked. After calling this, use add_deadline for every step that has a
    concrete due_date so the checklist actually gets tracked, not just
    displayed once and forgotten.

    Args:
        country: Destination country, e.g. "Germany".
        move_in_date: The date the student moves into their address, YYYY-MM-DD.

    Returns:
        An ordered list of steps with dependencies, and a concrete
        due_date ONLY where backed by a verified hard deadline (e.g.
        Germany's 14-day Anmeldung rule) — everything else gets a
        dependency note instead of an invented day-count, since we have
        no verified source for exact lead times. NOT_COVERED if this
        country has no sequence defined yet; in that case use
        find_official_source instead of inventing an order yourself.
    """
    try:
        move_in = datetime.strptime(move_in_date, "%Y-%m-%d").date()
    except ValueError:
        return "INVALID_DATE — please provide move_in_date in YYYY-MM-DD format."

    entry = ARRIVAL_SEQUENCES.get(_normalize(country))
    if not entry:
        return (
            f"NOT_COVERED — no arrival sequence defined for '{country}' yet. "
            f"Use find_official_source + fetch_official_page_summary to research the "
            f"real steps and order for this country instead of inventing one."
        )

    lines = [f"Arrival checklist for {country.title()}, moving in {move_in_date}:"]
    for i, step in enumerate(entry["steps"], 1):
        deps = f" (after: {', '.join(step['depends_on'])})" if step["depends_on"] else ""
        if step["hard_deadline_days_after_movein"] is not None:
            due = move_in + timedelta(days=step["hard_deadline_days_after_movein"])
            lines.append(f"{i}. {step['step']}{deps} — DUE BY {due.isoformat()} (hard deadline, verified). {step['note']}")
        else:
            lines.append(f"{i}. {step['step']}{deps} — no fixed calendar deadline; sequence/timing note: {step['note']}")
    lines.append(
        "\nNow call add_deadline for each step above that has a concrete DUE BY date "
        "(don't wait for the student to ask individually). For steps without a fixed "
        "date, tell the student the dependency order plainly instead of guessing a date."
    )
    return "\n".join(lines) + _verify_note(entry)


@tool
def draft_escalation_email(topic: str, details: str, recipient: str = "your university's International Office") -> str:
    """Draft (but do NOT send — this tool has no send capability) a plain,
    factual email the student can copy and send themselves when a
    situation is urgent: near/over a work-hour quota, a deadline within a
    few days, or a document problem. Use this proactively when you detect
    that kind of risk, rather than only describing the risk in prose.

    Args:
        topic: Short subject, e.g. "Upcoming Anmeldung deadline" or "Work-hour quota question".
        details: The specific facts to include — pull these from actual tool
        results (quota numbers, deadline dates), never invent figures here.
        recipient: Who this is addressed to. Defaults to the university's
        International Office; the student may specify their Ausländerbehörde,
        academic advisor, etc. instead.

    Returns:
        A ready-to-copy email draft. Always tell the student to review and
        personalize it before sending, and that this tool did not send
        anything on their behalf.
    """
    subject = topic.strip()
    body = (
        f"Subject: {subject}\n\n"
        f"Dear {recipient},\n\n"
        f"I am writing regarding the following: {details.strip()}\n\n"
        f"Could you please advise on the appropriate next steps, or confirm this "
        f"information is correct? I want to make sure I stay compliant with the "
        f"relevant requirements.\n\n"
        f"Thank you for your time.\n\n"
        f"Best regards,\n[Your name]\n[Your student/matriculation number, if applicable]"
    )
    return (
        f"{body}\n\n"
        f"— This is a draft only; nothing has been sent. Review the details above "
        f"(especially any numbers/dates) before sending, and personalize the closing."
    )


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