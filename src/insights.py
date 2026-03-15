# src/insights.py
import json
from collections import defaultdict
from typing import List, Dict
from anthropic import Anthropic


def generate_insights(all_transactions: List[Dict]) -> str:
    if not all_transactions:
        return "No transaction data available for analysis."

    client = Anthropic()

    # Build spending summary by period and category
    by_period_category: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for t in all_transactions:
        by_period_category[t['period']][t['claude_category']] += float(t['amount'])

    summary_json = json.dumps(
        {period: dict(cats) for period, cats in sorted(by_period_category.items())},
        indent=2
    )

    # Get recent transactions for merchant-level detail
    current_period = max(t['period'] for t in all_transactions)
    recent = [t for t in all_transactions if t['period'] == current_period]
    recent_lines = "\n".join(
        f"  - {t['merchant']}: ${float(t['amount']):.2f} ({t['claude_category']})"
        for t in sorted(recent, key=lambda x: float(x['amount']), reverse=True)
    )

    # All-time top merchants for subscription/pattern detection
    all_merchant_totals: Dict[str, float] = defaultdict(float)
    all_merchant_count: Dict[str, int] = defaultdict(int)
    for t in all_transactions:
        all_merchant_totals[t['merchant']] += float(t['amount'])
        all_merchant_count[t['merchant']] += 1
    top_merchants = sorted(all_merchant_totals.items(), key=lambda x: x[1], reverse=True)[:15]
    top_merchants_lines = "\n".join(
        f"  - {m}: ${amt:.2f} total ({all_merchant_count[m]} transactions)"
        for m, amt in top_merchants
    )

    prompt = f"""You are a personal finance advisor reviewing spending data across {len(set(t['period'] for t in all_transactions))} months.

Historical spending by period and category (USD):
{summary_json}

Individual transactions this period ({current_period}):
{recent_lines}

Top merchants all time:
{top_merchants_lines}

Write a spending analysis with these 5 sections. Be specific with dollar amounts. Use section headers in ALL CAPS. Skip any section where there is genuinely nothing notable.

OVERSPENDING ALERTS
Categories where this period's spend is notably above the personal average. Include: current amount, average, % difference.

UNUSUAL MERCHANTS
One-off, unfamiliar, or suspicious charges that don't fit normal patterns.

SUBSCRIPTION CREEP
New recurring charges or subscriptions that increased. Flag anything that looks like a trial that converted.

POSITIVE CALLOUTS
Categories where spending is notably below average — good financial discipline worth continuing.

SAVINGS OPPORTUNITIES
Based on the full spending history, give 3–5 specific, actionable suggestions to reduce monthly expenses. Reference actual merchants and amounts. For example: identify subscriptions that could be cancelled, dining frequency that could be reduced, or patterns like frequent small purchases that add up. Be direct and practical — no generic advice."""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text
