"""
Ticket fixtures for the support-triage demo.

Happy-path tickets route and resolve normally — they are the false-positive
check (none of the four poison rules may fire on them).

Poison tickets are deterministic at the TOOL layer only: the LLM calls are
real; the synthetic tool data keyed by ticket_id reproduces the kind of
downstream condition (flaky tool, slow diagnostic, bloated context) that
causes the corresponding anomaly in production.
"""

TICKETS = {
    # ── Happy path ────────────────────────────────────────────────────
    "HAPPY-BILLING-001": {
        "subject": "Double charge on last invoice",
        "body": "I was charged twice for my July subscription. Please refund "
                "the duplicate charge on my card.",
        "history": "",
    },
    "HAPPY-TECH-002": {
        "subject": "Export button does nothing",
        "body": "When I click Export in the reports tab, nothing downloads. "
                "This started after the last update. Browser: Chrome.",
        "history": "",
    },
    "HAPPY-ACCOUNT-003": {
        "subject": "Update my email address",
        "body": "I need to change the email address on my account to my new "
                "work address. Please confirm once updated.",
        "history": "",
    },
    "HAPPY-BILLING-004": {
        "subject": "Question about plan pricing tiers",
        "body": "Can you confirm what the Pro plan includes compared to Team, "
                "and whether I can switch mid-cycle?",
        "history": "",
    },

    # ── Poison tickets (deterministic tool-layer conditions) ──────────
    "DELEGATION-CYCLE-001": {
        "subject": "Being charged for a feature that crashes",
        "body": "I'm billed for the advanced analytics add-on, but every time "
                "I open the analytics dashboard the page crashes. Is this a "
                "billing problem or a technical problem? Nobody on either "
                "team has been able to tell me.",
        "history": "",
        # check_billing_history -> NO history (not a billing issue)
        # run_diagnostic      -> NO defect found (not a technical issue)
        # -> each specialist refers to the other; routing bounces back to a
        #    previously visited agent before completing.
    },
    "FAIL-LOOP-002": {
        "subject": "Cannot log in after password reset",
        "body": "I reset my password but still can't log in. My account might "
                "be stuck in a weird state — can you check my account "
                "settings?",
        "history": "",
        # lookup_account returns AMBIGUOUS every time -> the account agent
        # retries the identical call 5x (>= the 4-in-60s failure-loop rule).
    },
    "TIMEOUT-003": {
        "subject": "Slow dashboard and stuck data sync",
        "body": "My dashboard has been stuck syncing for two days. Can you "
                "run a diagnostic on my workspace?",
        "history": "",
        # run_diagnostic sleeps 31s for this ticket only (> 30s ceiling).
    },
    "TOKEN-SPIKE-004": {
        "subject": "Dispute charges across all historical invoices",
        "body": "I believe I've been overcharged repeatedly this year and "
                "want every invoice reviewed. Full context attached.",
        # `history` below is ~100 KB of synthetic ticket history; the composer
        # includes it, pushing a single LLM call past the 8k-token threshold.
        "history": ("PREVIOUS INTERACTION LOG (excerpt):\n"
                    + ("Customer opened ticket about invoice discrepancies, "
                       "support responded with partial refund, customer "
                       "escalated, billing reviewed, plan adjusted, customer "
                       "confirmed, follow-up opened, resolved, reopened.\n" * 1100)),
    },
}

HAPPY_PATH = [t for t in TICKETS if t.startswith("HAPPY")]
POISON = [t for t in TICKETS if not t.startswith("HAPPY")]
