"""
main.py
-------
Run with: python main.py

Before running:
    export AWS_PROFILE=bedrock
    export AWS_REGION=us-west-2   (match your enabled Bedrock region)
"""

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

model = BedrockModel(
    model_id="global.anthropic.claude-sonnet-4-6",
    region_name="us-west-2",
    temperature=0.2,  # low temperature: careful, consistent answers on visa/compliance topics
)

# ---------------------------------------------------------------------------
# SYSTEM PROMPT — this agent touches visa compliance, so treat honesty about
# what's verified vs. unverified as a hard requirement, not a nicety.
# ---------------------------------------------------------------------------
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

agent = Agent(
    model=model,
    system_prompt=SYSTEM_PROMPT,
    tools=[
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
    ],
)


def main():
    print("Scholaris — your international student copilot")
    print("⚠️  This is a demo/hackathon project — always confirm compliance details with your university's International Office or the relevant immigration authority.")
    print("Type your question, or 'exit' to quit.\n")

    while True:
        user_input = input("You: ")
        if user_input.strip().lower() in ("exit", "quit"):
            print("Good luck out there!")
            break
        response = agent(user_input)
        print(f"\nScholaris: {response}\n")


if __name__ == "__main__":
    main()
