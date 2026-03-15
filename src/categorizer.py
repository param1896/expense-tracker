# src/categorizer.py
import json
from typing import List, Dict
from anthropic import Anthropic

CATEGORIES = [
    "Dining & Restaurants",
    "Groceries",
    "Travel & Transport",
    "Shopping",
    "Subscriptions & Software",
    "Health & Fitness",
    "Entertainment",
    "Utilities & Bills",
    "Other",
]


def categorize_transactions(transactions: List[Dict]) -> List[Dict]:
    if not transactions:
        return []

    client = Anthropic()

    txn_list = "\n".join([
        f"{i + 1}. {t['merchant']} — ${t['amount']:.2f} on {t['date']} (Plaid: {t['plaid_category']})"
        for i, t in enumerate(transactions)
    ])

    categories_str = "\n".join(f"- {c}" for c in CATEGORIES)

    prompt = f"""You are a personal finance categorizer. Analyze each transaction carefully and assign it to exactly one category.

Available categories:
{categories_str}

For each transaction, examine:
- The merchant name (look up what kind of business it is)
- The amount (helps distinguish business type)
- The date and Plaid category as additional context

Provide detailed reasoning that demonstrates you've analyzed the specific merchant, not just matched keywords.

Transactions:
{txn_list}

Respond with a JSON array. Each element must have:
- "index": transaction number (1-based)
- "category": exactly one category from the list above
- "reasoning": 1-2 sentences explaining your analysis of this specific merchant and why this category fits

Return ONLY valid JSON, no other text."""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    results = json.loads(response.content[0].text)
    results_by_index = {r["index"]: r for r in results}

    return [
        {
            **t,
            "claude_category": results_by_index[i + 1]["category"],
            "claude_reasoning": results_by_index[i + 1]["reasoning"],
            "period": t["date"][:7],
        }
        for i, t in enumerate(transactions)
    ]
