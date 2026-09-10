# Scholaris — International Student Copilot

An AI agent built with the [Strands Agents SDK](https://strandsagents.com) that
runs quietly in the background for international students — tracking
work-hour compliance, deadlines, budgeting, and the local rules that are
easy to miss — currently covering Germany, Italy, France, Japan, and South
Korea.

**Built with:** Strands Agents SDK, Amazon Bedrock, Claude, Python, Flask.
**Hackathon track:** Everyday Agents ("Agents for Humans Hackathon")

**Problem:** Existing tools either help you get *into* a country (visa
application assistants) or track one narrow thing in one country (a work-day
counter for Germany). Nothing tracks the whole picture — quota usage,
renewal deadlines, budget sanity, and local norms — continuously, in the
background, the way the student actually experiences it: as one ongoing
situation, not five separate lookups.

**Who it's for:** International students already living abroad (or about
to move), who need one place that remembers their situation instead of
five bookmarked government pages.

---

## Design philosophy

Same discipline as the rest of this project family:

- **Germany is the fully verified reference country.** Italy, France,
  Japan, and South Korea are starter entries explicitly marked `VERIFY` in
  `knowledge_base.py` — the agent is instructed to always pass that caveat
  to the user rather than presenting an unconfirmed number as fact.
- **It never invents a compliance figure.** If a tool returns `NOT_COVERED`
  or a `VERIFY` note, the agent says so honestly instead of guessing.
- **It logs, it doesn't overwrite.** `submit_feedback` saves corrections
  for a human to review — a single user report never silently changes what
  every other user is told.

---

## Running it locally

```bash
python -m venv .venv
source .venv/Scripts/activate      # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt

export AWS_PROFILE=bedrock
export AWS_REGION=us-west-2        # match your enabled Bedrock region

python app.py                      # web UI — recommended
# python main.py                   # terminal version, useful for quick testing
```

Open **http://127.0.0.1:5000**. Try:

- "I worked 6 hours today in Germany"
- "How many work days do I have left this year?"
- "Add a deadline: residence permit renewal on 2026-11-15"
- "What deadlines do I have coming up?"
- "Give me a rough monthly budget for Germany"
- "What local rules should I know about in Germany?"

---

## File structure

| File                | What it does                                                                              |
| ------------------- | ------------------------------------------------------------------------------------------- |
| `knowledge_base.py` | Work-hour rules, forbidden categories, blocked-account minimums, budgets, local rules, insurance, document checklists — by country. **Edit this to add/verify countries.** |
| `tools.py`          | 13 tools: work-hour quota tracking, deadlines, budgeting, insurance, documents, a live page-fetch tool, and a feedback logger. |
| `main.py`           | Terminal/CLI agent entry point.                                                             |
| `app.py`            | Flask web server exposing the agent via `/api/chat`, with per-session agent instances and rate limiting. |
| `static/index.html` | The chat UI — boarding-pass-themed, with country chips and one-tap quick actions.            |
| `data/`             | Auto-created at runtime: `work_log.jsonl`, `deadlines.json`, `feedback_log.jsonl`. Not committed to git. |

---

## Path to production: Bedrock AgentCore

`app.py` currently keeps one `Agent` instance per browser session in a
plain Python dictionary — this is fine for a local demo, but it doesn't
survive a server restart and won't work across multiple server processes.
That in-memory state is exactly what **Amazon Bedrock AgentCore's** managed
runtime and session/memory services are built to replace once you're ready
to deploy for real, rather than just running locally.

---

## Where to improve next

1. Fully verify Italy, France, Japan, and South Korea data (replace every `VERIFY` entry).
2. Move `data/*.jsonl` state into a real per-user database instead of local files.
3. Deploy to Bedrock AgentCore for persistent, multi-user hosting.
4. Add push notifications (email/SMS) for deadlines instead of requiring the user to ask.
5. Expand country coverage beyond the initial five.

---

## License

MIT.
