"""
knowledge_base.py
------------------
All the "facts" the agent relies on live here, in plain Python data
structures, so you can review, correct, and extend them without touching
any agent logic.

*** IMPORTANT BEFORE YOU SUBMIT / DEMO ***
Germany is the fully fleshed-out reference country (spot-checked against
2026 sources). Italy, France, Japan, and South Korea are starter entries
marked "VERIFY" — approximate, not confirmed against a current official
source. Work/visa rules change often and vary by exact visa subtype, so:
    1. Before any real use, re-verify every VERIFY entry against the
       relevant country's immigration authority.
    2. Never let the agent state a VERIFY number as if it were confirmed —
       tools.py is written to always flag this explicitly.
    This matters here as much as in a medical or legal tool: a wrong work-
    hour or document rule can put a real student's visa status at risk.
"""

# ---------------------------------------------------------------------------
# Work-hour rules by country. Germany is verified against 2026 sources;
# everything else is an illustrative VERIFY placeholder.
# ---------------------------------------------------------------------------
WORK_HOUR_RULES = {
    "germany": {
        "verified": True,
        "eu_eea_citizens": "No restriction beyond normal labor law — same rights as German/EU citizens.",
        "non_eu_annual_limit": "140 full days or 280 half days per calendar year (raised from 120/240 in March 2024).",
        "half_day_definition": "A shift of 4 hours or less counts as a half day.",
        "full_day_definition": "Any shift longer than 4 hours counts as one full day, regardless of length (a 9-hour shift still only counts as 1 full day).",
        "weekly_guideline": "In practice this works out to roughly 20 hours/week averaged across the year during term time; full-time is generally fine during semester breaks but still draws down the annual quota.",
        "tracking_period": "Calendar year (Jan 1 - Dec 31), NOT the academic year.",
        "exempt_categories": [
            "Mandatory curricular internship (Pflichtpraktikum) that is a required part of the degree program.",
            "Some academic student-assistant (HiWi) roles may be treated differently depending on the state (Bundesland) — VERIFY with your university's International Office.",
        ],
        "requires_approval_if_exceeded": "Working beyond the quota requires prior approval from the Ausländerbehörde (Foreigners' Office) before you exceed it, not after.",
        "source_hint": "Search 'Bundesagentur für Arbeit 140 Tage internationale Studierende' or ask your university's International Office for the current figure.",
    },
    "italy": {
        "verified": False,
        "note": "VERIFY — general guidance is that non-EU students with a permesso di soggiorno per studio may work part-time, commonly cited around 20 hours/week (approx. 1,040 hours/year), but this must be confirmed with the local Questura before relying on it.",
    },
    "france": {
        "verified": False,
        "note": "VERIFY — non-EU students typically may work up to roughly 964 hours per year (about 60% of the French legal full-time annual hours), averaging near 20 hours/week. Confirm the current figure with Campus France or your préfecture.",
    },
    "japan": {
        "verified": False,
        "note": "VERIFY — student ('ryugaku') visa holders generally need a 'permission to engage in activity other than that permitted' (shikakugai katsudo kyoka) from Immigration, commonly capped around 28 hours/week during term and up to full-time during long school breaks. Confirm current limits with the Immigration Services Agency.",
    },
    "south korea": {
        "verified": False,
        "note": "VERIFY — D-2 (degree-seeking) student visa holders generally need work-permission approval from immigration, with weekly hour caps that vary by semester standing and TOPIK level (commonly cited in the 20-30 hour/week range); D-4 language-track visas tend to be more restrictive. Confirm current limits with the Korea Immigration Service (Hi Korea).",
    },
}

# ---------------------------------------------------------------------------
# Categories of work that are restricted or disallowed regardless of hour
# quota. Germany verified; others VERIFY.
# ---------------------------------------------------------------------------
FORBIDDEN_WORK_CATEGORIES = {
    "germany": {
        "verified": True,
        "restricted": [
            "Self-employment and freelance work generally require separate approval from the Ausländerbehörde.",
            "Work must not conflict with your registered course schedule/exam obligations in a way that jeopardizes enrollment status.",
        ],
    },
    "italy": {"verified": False, "note": "VERIFY — self-employment and freelance work typically require separate authorization."},
    "france": {"verified": False, "note": "VERIFY — some regulated professions and self-employment may be restricted or require extra permits."},
    "japan": {"verified": False, "note": "VERIFY — work in the 'adult entertainment' / fuzoku industry sectors is explicitly prohibited under all activity permissions."},
    "south korea": {"verified": False, "note": "VERIFY — work permission is generally job/employer-specific and must be re-approved if you change jobs."},
}

# ---------------------------------------------------------------------------
# Blocked/proof-of-funds account minimums. Germany verified; others VERIFY.
# These figures are adjusted periodically by each country's authorities.
# ---------------------------------------------------------------------------
BLOCKED_ACCOUNT_MINIMUMS = {
    "germany": {
        "verified": True,
        "amount_eur_per_year": 11904,
        "note": "Sperrkonto (blocked account) annual minimum, current as of the 2024/2025 adjustment. This is reviewed periodically — VERIFY the exact current figure before relying on it for a visa application.",
    },
    "italy": {"verified": False, "note": "VERIFY — proof-of-funds requirement (attestazione di disponibilità economica) varies and is not a fixed blocked-account figure like Germany's."},
    "france": {"verified": False, "note": "VERIFY — typically shown via a Campus France financial guarantee (approx. historically cited near EUR 7,380-11,400/year depending on funding source); confirm current figure."},
    "japan": {"verified": False, "note": "VERIFY — no single fixed blocked-account figure; proof of funds requirement varies by school/sponsor and is assessed case by case."},
    "south korea": {"verified": False, "note": "VERIFY — proof-of-funds (bank balance certificate) requirement is commonly cited around USD 20,000 equivalent, but this varies by visa subtype and changes periodically."},
}

# ---------------------------------------------------------------------------
# Rough baseline monthly cost-of-living ranges, in local currency. These are
# ILLUSTRATIVE ballparks for budgeting sanity checks, not precise figures —
# actual costs vary heavily by city within each country.
# ---------------------------------------------------------------------------
BUDGET_BASELINES = {
    "germany": {
        "currency": "EUR",
        "rent_range": (400, 900),
        "health_insurance_range": (120, 140),
        "phone_internet_range": (15, 40),
        "food_range": (200, 350),
        "transport_range": (0, 60),
        "note": "Rent varies hugely by city — Munich/Frankfurt trend toward the top of this range, smaller cities toward the bottom. Many universities include a subsidized transit pass (Semesterticket).",
    },
    "italy": {"currency": "EUR", "rent_range": (350, 800), "health_insurance_range": (0, 150), "phone_internet_range": (10, 30), "food_range": (200, 350), "transport_range": (20, 40), "note": "VERIFY — illustrative range only."},
    "france": {"currency": "EUR", "rent_range": (400, 900), "health_insurance_range": (0, 100), "phone_internet_range": (10, 30), "food_range": (200, 350), "transport_range": (30, 75), "note": "VERIFY — illustrative range only; CAF housing subsidy (APL) can reduce effective rent significantly for eligible students."},
    "japan": {"currency": "JPY", "rent_range": (40000, 90000), "health_insurance_range": (2000, 3000), "phone_internet_range": (3000, 6000), "food_range": (30000, 50000), "transport_range": (5000, 10000), "note": "VERIFY — illustrative range only; strongly varies between Tokyo and smaller cities."},
    "south korea": {"currency": "KRW", "rent_range": (300000, 700000), "health_insurance_range": (60000, 100000), "phone_internet_range": (30000, 60000), "food_range": (400000, 600000), "transport_range": (60000, 100000), "note": "VERIFY — illustrative range only; goshiwon/officetel options at the low end skew the rent range significantly."},
}

# ---------------------------------------------------------------------------
# Local rules / etiquette that commonly trip up new arrivals. Germany
# verified; others VERIFY placeholders to extend later.
# ---------------------------------------------------------------------------
LOCAL_RULES = {
    "germany": {
        "verified": True,
        "rules": [
            {"category": "quiet_hours", "en": "Ruhezeit (legally protected quiet hours): typically 22:00-06:00 on weekdays, plus ALL DAY on Sundays and public holidays. No loud music, drilling, vacuuming, or parties during these times in residential buildings."},
            {"category": "sunday_closing", "en": "Sonntagsruhe: almost all shops are closed on Sundays, with limited exceptions (some bakeries for a few morning hours, gas stations, train-station convenience stores)."},
            {"category": "recycling", "en": "Strict waste sorting is expected: Restmüll (residual/black bin), Biomüll (organic/brown bin), Gelber Sack or Wertstoff (recyclables/yellow), Papier (paper/blue), and Glas (glass, sorted by color at public bottle banks). Getting this wrong can result in fines from your building management."},
            {"category": "anmeldung_deadline", "en": "You must register your address (Anmeldung) at the local Bürgeramt within 14 days of moving into a new address — this is a legal requirement, not optional, and is needed for almost everything else (bank account, phone contract, visa appointments)."},
        ],
    },
    "italy": {"verified": False, "rules": [{"category": "general", "en": "VERIFY — add confirmed local rules for Italy before relying on this section."}]},
    "france": {"verified": False, "rules": [{"category": "general", "en": "VERIFY — add confirmed local rules for France before relying on this section."}]},
    "japan": {"verified": False, "rules": [{"category": "general", "en": "VERIFY — add confirmed local rules for Japan (e.g. strict garbage-sorting schedules by day of week, noise norms) before relying on this section."}]},
    "south korea": {"verified": False, "rules": [{"category": "general", "en": "VERIFY — add confirmed local rules for South Korea before relying on this section."}]},
}

# ---------------------------------------------------------------------------
# Health/student insurance requirements by country.
# ---------------------------------------------------------------------------
INSURANCE_REQUIREMENTS = {
    "germany": {
        "verified": True,
        "note": "Proof of health insurance recognized under German law (gesetzlich or an approved private equivalent) is required BEFORE you can enroll (immatrikulieren) at a public university. Most students under 30 use statutory public insurance (gesetzliche Krankenversicherung).",
    },
    "italy": {"verified": False, "note": "VERIFY — non-EU students typically need either the Italian National Health Service (SSN) enrollment or a private policy meeting minimum coverage; requirement varies by region/university."},
    "france": {"verified": False, "note": "VERIFY — students are generally automatically covered under the French national health system (PUMA) after registering, but confirm current enrollment steps with Campus France."},
    "japan": {"verified": False, "note": "VERIFY — enrollment in Japan's National Health Insurance (Kokumin Kenko Hoken) is generally mandatory for residents staying 3+ months, including students."},
    "south korea": {"verified": False, "note": "VERIFY — National Health Insurance Service (NHIS) enrollment became mandatory for most long-term foreign residents, including students; confirm current requirement and premium."},
}

# ---------------------------------------------------------------------------
# Arrival/renewal document checklists.
# ---------------------------------------------------------------------------
DOCUMENT_CHECKLISTS = {
    "germany": {
        "verified": True,
        "arrival": [
            "Valid passport + national entry visa (if required for your nationality)",
            "Anmeldung (address registration) within 14 days of moving in",
            "Enrollment certificate (Immatrikulationsbescheinigung) from your university",
            "Health insurance confirmation letter",
            "Blocked account (Sperrkonto) confirmation or other proof of financial means",
            "Residence permit appointment booked at the local Ausländerbehörde",
        ],
        "renewal": [
            "Updated enrollment certificate showing continued study progress",
            "Updated proof of financial means for the next period",
            "Updated health insurance confirmation",
            "Biometric photo (current requirements vary by Ausländerbehörde — check locally)",
        ],
    },
    "italy": {"verified": False, "arrival": ["VERIFY — build out the confirmed arrival checklist for Italy (permesso di soggiorno application, codice fiscale, etc.)."], "renewal": ["VERIFY"]},
    "france": {"verified": False, "arrival": ["VERIFY — build out the confirmed arrival checklist for France (OFII validation, titre de séjour, CVEC, etc.)."], "renewal": ["VERIFY"]},
    "japan": {"verified": False, "arrival": ["VERIFY — build out the confirmed arrival checklist for Japan (Residence Card, city hall registration, National Health Insurance enrollment, etc.)."], "renewal": ["VERIFY"]},
    "south korea": {"verified": False, "arrival": ["VERIFY — build out the confirmed arrival checklist for South Korea (Alien Registration Card / ARC within 90 days, NHIS enrollment, etc.)."], "renewal": ["VERIFY"]},
}
