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

    prompt = f"""You are a personal finance advisor reviewing monthly spending.

Historical spending by period and category (USD):
{summary_json}

Individual transactions this period ({current_period}):
{recent_lines}

Write a concise spending analysis (under 350 words) with these sections:

OVERSPENDING ALERTS
List any categories where this period's spend is notably above the personal historical average. Include the current amount, average amount, and percentage difference.

UNUSUAL MERCHANTS
Flag any one-off, unfamiliar, or suspicious charges that don't fit normal spending patterns.

SUBSCRIPTION CREEP
Identify new recurring charges or subscriptions that increased compared to previous periods.

POSITIVE CALLOUTS
Highlight categories where spending is notably below average — good financial discipline.

Be specific with dollar amounts. Use plain text with section headers in ALL CAPS. Skip any section where there's nothing notable to report."""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text
