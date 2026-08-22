"""
Local tools for the support-triage demo (Flow 1, zero-rewrite).

All tools are local/synthetic — no external systems. Poison behavior is
keyed by ticket_id prefix and reproduces a realistic downstream failure
mode; the LLM calls that consume these results are real.
"""

import time

from langchain_core.tools import tool


@tool
def check_billing_history(ticket_id: str) -> str:
    """Look up the billing history associated with a support ticket."""
    if ticket_id.startswith("DELEGATION-CYCLE"):
        # Deterministic poison: no billing record exists, so the billing
        # specialist (correctly) concludes this is not a billing issue.
        return ("NO_BILLING_HISTORY: no invoices or charges are associated "
                "with this account — this is very likely NOT a billing issue.")
    return ("BILLING_OK: 2 invoices on file, most recent paid in full "
            "(invoice #INV-77413, $49.00). One proration of $12.40 applied "
            "on the last cycle.")


@tool
def run_diagnostic(ticket_id: str) -> str:
    """Run a workspace diagnostic for a support ticket."""
    if ticket_id.startswith("DELEGATION-CYCLE"):
        # Deterministic poison: diagnostic is clean, so the technical
        # specialist (correctly) concludes this is not a technical issue.
        return ("DIAG_CLEAN: all workspace subsystems nominal, no errors in "
                "server logs — no technical defect reproduced.")
    if ticket_id.startswith("TIMEOUT"):
        # Deterministic poison: a hung downstream diagnostic job. The sleep
        # exceeds the 30s timeout ceiling (rule threshold) for this ticket
        # only.
        time.sleep(31)
        return "DIAG_TIMEOUT_PATH: diagnostic eventually completed after a long hang."
    return ("DIAG_OK: workspace healthy; a stale sync lock was found and "
            "cleared. Sync should resume within 5 minutes.")


@tool
def lookup_account(ticket_id: str) -> str:
    """Fetch the account record associated with a support ticket."""
    if ticket_id.startswith("FAIL-LOOP"):
        # Deterministic poison: the account store returns an incomplete
        # record every time — the same class of flaky downstream dependency
        # that causes retry loops in production.
        return "AMBIGUOUS: account record incomplete (fields missing). Retry advised."
    return "ACCOUNT_OK: plan=Pro, status=active, mfa=enabled, region=us-east."


TOOLS = [check_billing_history, run_diagnostic, lookup_account]
