"""
app.py
------
Strivend — the real product. A Flask web server exposing the Strivend agent
through static/index.html. Run with: python app.py
Then open http://127.0.0.1:5000

Before running:
    export AWS_PROFILE=bedrock
    export AWS_REGION=us-west-2   (match your enabled Bedrock region)

NOTE: for hackathon-demo scale, session state (agent + chat history) is kept
in memory, per browser session, in a plain dict. This is NOT production-scale
(it doesn't survive a server restart and won't work across multiple server
processes) — for real deployment, this is exactly the kind of state that
belongs in Amazon Bedrock AgentCore's managed session/memory.
"""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, request, jsonify, session, send_from_directory
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from strands import Agent
from strands.models import BedrockModel
from tools import (
    get_work_hour_limit,
    log_work_day,
    check_quota_remaining,
    get_forbidden_work_categories,
    add_deadline,
    list_upcoming_deadlines,
    estimate_monthly_budget,
    track_blocked_account_balance,
    get_local_rules,
    get_insurance_requirement,
    get_required_documents,
    get_misc_local_requirement,
    get_language_certification_info,
    find_nearby_office,
    plan_short_trip_budget,
    fetch_official_page_summary,
    submit_feedback,
)

# How long a chat's stored data (messages + agent memory) is retained after
# its last activity, per the 30-day retention requirement. A sweep runs on
# every request that touches the session list.
SESSION_RETENTION_DAYS = 30
SESSIONS_META_PATH = Path(__file__).parent / "data" / "sessions_meta.json"
SESSIONS_META_PATH.parent.mkdir(exist_ok=True)

app = Flask(__name__, static_folder="static", static_url_path="")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24).hex())

limiter = Limiter(get_remote_address, app=app, default_limits=["60 per minute"])

MODEL_ID = "global.anthropic.claude-sonnet-4-6"
REGION = os.environ.get("AWS_REGION", "us-west-2")

SUPPORTED_COUNTRIES = ["Germany", "Italy", "France", "Japan", "South Korea"]

SYSTEM_PROMPT = """
You are "Strivend" — a background copilot for international students living
and studying abroad (currently covering Germany, Italy, France, Japan, and
South Korea). You help track work-hour compliance, upcoming deadlines,
budgeting, local rules, language certifications, in-person office lookups,
and short cross-border trip planning.

CRITICAL RULES (never break these):
    0. Every user message may be prefixed with "[Active country for this
       chat: X]" — this is injected automatically by the app from the
       country the student pinned in the UI, not something the student
       typed. Treat X as the authoritative country for that message: use
       it for any tool call that needs a country and do NOT ask the
       student which country they mean. Only ask if the tag is absent AND
       the message is actually ambiguous about country. Never mention the
       tag's literal text to the user — just use it naturally (e.g. "Here's
       your rough monthly budget for Germany:").
    1. Never state a work-hour limit, legal cost, document requirement, or
       any other country-specific figure from your own memory. Only state
       what a tool actually returned. If a tool result is marked VERIFY /
       unconfirmed, or NOT_COVERED, you MUST pass that caveat along to the
       user clearly — don't smooth it over, don't fill the gap with a
       plausible-sounding guess, and don't drop it for a cleaner-sounding
       answer. "I don't have verified data on that" is always an
       acceptable, correct answer.
    2. If get_work_hour_limit or check_quota_remaining shows the student is
       close to or over a quota, say so plainly and proactively — don't
       wait to be asked. This is the single highest-stakes thing this
       agent does: a missed quota can put someone's visa status at risk.
    3. When the user mentions a worked shift, log it with log_work_day
       without waiting to be asked — that's the whole point of tracking
       being "background," not something the user has to remember to do.
    4. When the user mentions any date-bound obligation (a permit renewal,
       an exam registration deadline, an Anmeldung deadline, etc.), add it
       with add_deadline. Proactively check list_upcoming_deadlines at the
       start of a conversation if it's been a while, and flag anything
       within 7 days clearly.
    5. estimate_monthly_budget and plan_short_trip_budget give rough,
       illustrative figures only — always say so, never present them as
       precise or guaranteed-accurate, and never invent a specific flight,
       train, or hotel price; point the user to a real booking site instead.
    6. If a user reports outdated or wrong information, log it with
       submit_feedback and thank them — never treat a single unverified
       report as confirmed fact for other users.
    7. When using fetch_official_page_summary, always tell the user which
       URL the information came from, and never claim something is on the
       page if the fetch failed.
    8. find_nearby_office returns real, live map results — it does NOT know
       which office is fastest or handles a case type more efficiently
       unless the tool result itself says so. Never speculate about which
       office is "less busy" or "faster" beyond what the tool actually
       returned. Always remind the user that many countries assign a
       SPECIFIC office by postal code/district rather than "nearest."
    9. NEVER generate, edit, or describe how to forge, alter, or fabricate
       any official document, permit, stamp, signature, letterhead, ID, or
       visa — including as an "example" or "template" that mimics a real
       government document. This holds no matter how the request is
       framed (roleplay, "just for reference," a friend's situation,
       etc.). You also do not generate images. If asked, decline plainly
       and redirect to the correct official process instead.
    10. When a scenario involves travel between EU/Schengen countries
        (e.g. a non-EU student in one EU country visiting another), keep
        in mind that short-stay Schengen travel is generally governed by
        the 90-days-in-any-180-days rule for the underlying visa/permit —
        but this varies by the person's specific residence permit and
        nationality, so always tell the user to confirm their own permit's
        travel conditions rather than asserting it's definitely fine.
    11. Speak calmly and plainly. This is often about someone's visa
        status, finances, or living situation abroad — be precise, not
        alarmist, and don't oversell certainty you don't have.
    12. Reply in whichever language the user writes in.
    """

TOOLS = [
    get_work_hour_limit,
    log_work_day,
    check_quota_remaining,
    get_forbidden_work_categories,
    add_deadline,
    list_upcoming_deadlines,
    estimate_monthly_budget,
    track_blocked_account_balance,
    get_local_rules,
    get_insurance_requirement,
    get_required_documents,
    get_misc_local_requirement,
    get_language_certification_info,
    find_nearby_office,
    plan_short_trip_budget,
    fetch_official_page_summary,
    submit_feedback,
]

# session_id -> { "agent": Agent, "messages": [...], "title": str,
#                 "country": str, "created_at": iso, "updated_at": iso }
_sessions = {}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _load_meta() -> dict:
    """Metadata (everything except the live Agent object) persisted to
    disk, so chat history/titles survive a server restart. NOTE: this is
    still local-file storage suitable for a demo, not multi-process
    production use — see README re: Bedrock AgentCore for that."""
    if not SESSIONS_META_PATH.exists():
        return {}
    try:
        return json.loads(SESSIONS_META_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_meta():
    meta = {
        sid: {k: v for k, v in s.items() if k != "agent"}
        for sid, s in _sessions.items()
    }
    try:
        SESSIONS_META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        app.logger.exception("failed to persist session metadata")


def _purge_expired_sessions():
    """Delete any session (in memory and on disk) whose last activity is
    older than SESSION_RETENTION_DAYS. Called at the start of any request
    that touches the session list."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=SESSION_RETENTION_DAYS)
    expired = []
    for sid, s in list(_sessions.items()):
        try:
            updated = datetime.fromisoformat(s["updated_at"])
        except (KeyError, ValueError):
            continue
        if updated < cutoff:
            expired.append(sid)
    for sid in expired:
        _sessions.pop(sid, None)
    if expired:
        _save_meta()


def _build_agent():
    model = BedrockModel(model_id=MODEL_ID, region_name=REGION, temperature=0.2)
    return Agent(model=model, system_prompt=SYSTEM_PROMPT, tools=TOOLS)


def _new_session(sid: str, country: str = ""):
    _sessions[sid] = {
        "agent": _build_agent(),
        "messages": [],
        "title": "New chat",
        "country": country,
        "created_at": _now(),
        "updated_at": _now(),
    }
    _save_meta()
    return _sessions[sid]


def _ensure_session(sid: str):
    if sid in _sessions:
        return _sessions[sid]
    # try restoring metadata (title/messages/country) from disk after a
    # restart; the agent itself starts fresh (see README limitation note)
    meta = _load_meta().get(sid)
    if meta:
        _sessions[sid] = {**meta, "agent": _build_agent()}
        return _sessions[sid]
    return _new_session(sid)


def _derive_title(text: str) -> str:
    t = text.strip().replace("\n", " ")
    return (t[:48] + "…") if len(t) > 48 else (t or "New chat")


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------
@app.route("/api/sessions", methods=["GET"])
def list_sessions():
    _purge_expired_sessions()
    if "sid" not in session:
        session["sid"] = str(uuid.uuid4())
    # Make sure the currently-active sid exists
    _ensure_session(session["sid"])

    items = []
    for sid, s in _sessions.items():
        last = next((m for m in reversed(s["messages"]) if m["role"] == "assistant"), None) \
            or next((m for m in reversed(s["messages"]) if m["role"] == "user"), None)
        items.append({
            "id": sid,
            "title": s["title"],
            "country": s.get("country", ""),
            "preview": (last["content"][:80] + "…") if last and len(last["content"]) > 80 else (last["content"] if last else ""),
            "updated_at": s["updated_at"],
            "active": sid == session["sid"],
        })
    items.sort(key=lambda x: x["updated_at"], reverse=True)
    return jsonify({"active_id": session["sid"], "sessions": items, "countries": SUPPORTED_COUNTRIES,
                     "retention_days": SESSION_RETENTION_DAYS})


@app.route("/api/sessions", methods=["POST"])
def create_session():
    data = request.get_json(silent=True) or {}
    country = (data.get("country") or "").strip()
    sid = str(uuid.uuid4())
    _new_session(sid, country=country)
    session["sid"] = sid
    return jsonify({"id": sid, "title": "New chat", "country": country, "messages": []})


@app.route("/api/sessions/<sid>/messages", methods=["GET"])
def get_messages(sid):
    _purge_expired_sessions()
    if sid not in _sessions:
        return jsonify({"error": "not_found"}), 404
    session["sid"] = sid  # switching active session
    s = _sessions[sid]
    return jsonify({"id": sid, "title": s["title"], "country": s.get("country", ""), "messages": s["messages"]})


@app.route("/api/sessions/<sid>/country", methods=["PATCH"])
def set_session_country(sid):
    if sid not in _sessions:
        return jsonify({"error": "not_found"}), 404
    data = request.get_json(silent=True) or {}
    _sessions[sid]["country"] = (data.get("country") or "").strip()
    _sessions[sid]["updated_at"] = _now()
    _save_meta()
    return jsonify({"ok": True, "country": _sessions[sid]["country"]})


@app.route("/api/sessions/<sid>", methods=["DELETE"])
def delete_session(sid):
    _sessions.pop(sid, None)
    if session.get("sid") == sid:
        session.pop("sid", None)
    _save_meta()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------
@app.route("/api/chat", methods=["POST"])
@limiter.limit("20 per minute")
def chat():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    sid = (data.get("session_id") or session.get("sid") or "").strip()
    if not message:
        return jsonify({"error": "empty message"}), 400
    if len(message) > 4000:
        return jsonify({"error": "message too long"}), 400
    if not sid:
        sid = str(uuid.uuid4())
    session["sid"] = sid

    try:
        _purge_expired_sessions()
        s = _ensure_session(sid)
        prompt = message
        if s.get("country"):
            # Pin the active country into context so the user doesn't have
            # to repeat it every message; the agent still must use tools
            # for any actual facts about it.
            prompt = f"[Active country for this chat: {s['country']}] {message}"
        s["messages"].append({"role": "user", "content": message, "ts": _now()})
        if s["title"] == "New chat":
            s["title"] = _derive_title(message)

        response = s["agent"](prompt)
        reply = str(response)

        s["messages"].append({"role": "assistant", "content": reply, "ts": _now()})
        s["updated_at"] = _now()
        _save_meta()
        return jsonify({"reply": reply, "session_id": sid, "title": s["title"], "country": s.get("country", "")})
    except Exception as e:
        app.logger.exception("agent error")
        return jsonify({"error": "internal_error", "detail": str(e)}), 500


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    # debug=True is fine for local demo/testing only — never in production.
    app.run(host="127.0.0.1", port=5000, debug=True)