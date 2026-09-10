"""
app.py
------
The real product — a Flask web server exposing the Scholaris agent through
static/index.html. Run with: python app.py
Then open http://127.0.0.1:5000

Before running:
    export AWS_PROFILE=bedrock
    export AWS_REGION=us-west-2   (match your enabled Bedrock region)

NOTE: for hackathon-demo scale, one Agent instance is kept in memory per
browser session (via a signed cookie), in a plain dict. This is NOT
production-scale (it doesn't survive a server restart and won't work
across multiple server processes) — for real deployment, this is exactly
the kind of state that belongs in Amazon Bedrock AgentCore's managed
session/memory instead of a local dict.
"""

import os
import uuid

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
    fetch_official_page_summary,
    submit_feedback,
)

app = Flask(__name__, static_folder="static", static_url_path="")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24).hex())

limiter = Limiter(get_remote_address, app=app, default_limits=["60 per minute"])

MODEL_ID = "global.anthropic.claude-sonnet-4-6"
REGION = os.environ.get("AWS_REGION", "us-west-2")

SYSTEM_PROMPT = """
You are "Scholaris" — a background copilot for international students living
and studying abroad (currently covering Germany, Italy, France, Japan, and
South Korea). You help track work-hour compliance, upcoming deadlines,
budgeting, and local rules that are easy to miss.

CRITICAL RULES (never break these):
    1. Never state a work-hour limit, legal cost, document requirement, or
       any other country-specific figure from your own memory. Only state
       what a tool actually returned. If a tool result is marked VERIFY /
       unconfirmed, you MUST pass that caveat along to the user clearly —
       don't smooth it over or drop it for a cleaner-sounding answer.
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
    5. estimate_monthly_budget and track_blocked_account_balance give
       rough, illustrative figures — always say so, never present them as
       precise or guaranteed-accurate.
    6. If a user reports outdated or wrong information, log it with
       submit_feedback and thank them — never treat a single unverified
       report as confirmed fact for other users.
    7. When using fetch_official_page_summary, always tell the user which
       URL the information came from, and never claim something is on the
       page if the fetch failed.
    8. Speak calmly and plainly. This is often about someone's visa status,
       finances, or living situation abroad — be precise, not alarmist, and
       don't oversell certainty you don't have.
    9. Reply in whichever language the user writes in.
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
    fetch_official_page_summary,
    submit_feedback,
]

# session_id -> Agent instance. In-memory only — see the module docstring.
_agents = {}


def _get_agent_for_session() -> Agent:
    if "sid" not in session:
        session["sid"] = str(uuid.uuid4())
    sid = session["sid"]
    if sid not in _agents:
        model = BedrockModel(model_id=MODEL_ID, region_name=REGION, temperature=0.2)
        _agents[sid] = Agent(model=model, system_prompt=SYSTEM_PROMPT, tools=TOOLS)
    return _agents[sid]


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/chat", methods=["POST"])
@limiter.limit("20 per minute")
def chat():
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "empty message"}), 400
    if len(message) > 4000:
        return jsonify({"error": "message too long"}), 400

    try:
        agent = _get_agent_for_session()
        response = agent(message)
        return jsonify({"reply": str(response)})
    except Exception as e:
        app.logger.exception("agent error")
        return jsonify({"error": "internal_error", "detail": str(e)}), 500


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    # debug=True is fine for local demo/testing only — never in production.
    app.run(host="127.0.0.1", port=5000, debug=True)
