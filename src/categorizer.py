# src/categorizer.py
import json
from typing import List, Dict
from anthropic import Anthropic

CATEGORIES = [
    "Dining Out",
    "Groceries",
    "Travel",
    "Transportation",
    "Shopping",
    "Subscriptions & Streaming",
    "Health & Medical",
    "Entertainment",
    "Home & Utilities",
    "Personal Care",
    "Miscellaneous",
]

CATEGORY_DEFINITIONS = """
- Dining Out: restaurants, cafes, bars, coffee shops, food delivery (DoorDash, UberEats, Grubhub, Caviar)
- Groceries: supermarkets, grocery stores (Whole Foods, Trader Joe's, Safeway, Costco food runs)
- Travel: flights, hotels, Airbnb, vacation rentals, travel agencies, international spending
- Transportation: Uber, Lyft, taxis, parking, gas/fuel, transit passes, car maintenance, tolls
- Shopping: Amazon, retail stores, clothing, electronics, department stores, online shopping
- Subscriptions & Streaming: Netflix, Spotify, Hulu, Apple/Google services, news sites, SaaS tools, any recurring monthly/annual charge
- Health & Medical: doctors, dentists, pharmacies, hospitals, gym memberships, fitness classes, health apps
- Entertainment: concerts, movies, theaters, sporting events, amusement parks, games
- Home & Utilities: electric/gas/water bills, phone bills, internet, rent, furniture, home improvement, cleaning services
- Personal Care: salon, haircut, spa, massage, beauty products, grooming
- Miscellaneous: anything that genuinely doesn't fit the above categories
"""


def categorize_transactions(transactions: List[Dict]) -> List[Dict]:
    if not transactions:
        return []

    client = Anthropic()

    txn_list = "\n".join([
        f"{i + 1}. {t['merchant']} — ${t['amount']:.2f} on {t['date']} (hint: {t['plaid_category']})"
        for i, t in enumerate(transactions)
    ])

    categories_str = "\n".join(f"- {c}" for c in CATEGORIES)

    prompt = f"""You are a personal finance categorizer. Assign each transaction to exactly one category.

Category definitions — use these to decide:
{CATEGORY_DEFINITIONS}

For each transaction:
- Identify what kind of business the merchant is (e.g. Sweetgreen = salad restaurant = Dining Out)
- Use the amount as a signal if the merchant name is ambiguous
- Use the hint category as a tiebreaker only

Transactions:
{txn_list}

Respond with a JSON array. Each element must have:
- "index": transaction number (1-based)
- "category": exactly one category from: {', '.join(CATEGORIES)}
- "reasoning": one sentence identifying the merchant type and why this category fits

Return ONLY valid JSON, no other text."""

    last_error = None
    for attempt in range(2):
        try:
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
                    "claude_category": results_by_index.get(i + 1, {}).get("category", "Uncategorized"),
                    "claude_reasoning": results_by_index.get(i + 1, {}).get("reasoning", "Missing from Claude response"),
                    "period": t["date"][:7],
                }
                for i, t in enumerate(transactions)
            ]
        except Exception as e:
            last_error = e
            continue

    # Both attempts failed — return transactions as Uncategorized
    return [
        {
            **t,
            "claude_category": "Uncategorized",
            "claude_reasoning": f"API error after 2 attempts: {last_error}",
            "period": t["date"][:7],
        }
        for t in transactions
    ]
