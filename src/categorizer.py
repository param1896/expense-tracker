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


BATCH_SIZE = 50  # ~1500 tokens output per batch, well within limits


def _categorize_batch(client: Anthropic, batch: List[Dict], offset: int) -> List[Dict]:
    """Categorize a single batch of transactions. Returns the batch with categories filled in."""
    txn_list = "\n".join([
        f"{offset + i + 1}. {t['merchant']} — ${float(t['amount']):.2f} on {t['date']} (hint: {t['plaid_category']})"
        for i, t in enumerate(batch)
    ])

    prompt = f"""You are a personal finance categorizer. Assign each transaction to exactly one category.

Category definitions:
{CATEGORY_DEFINITIONS}

For each transaction, identify the merchant type and assign the best-fit category.

Transactions:
{txn_list}

Respond with a JSON array. Each element:
- "index": transaction number shown above (starts at {offset + 1})
- "category": exactly one of: {', '.join(CATEGORIES)}
- "reasoning": one sentence

Return ONLY valid JSON, no other text."""

    last_error = None
    for attempt in range(2):
        try:
            response = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            # Strip markdown code fences if Claude wraps the JSON
            if raw.startswith("```"):
                raw = raw.split("```", 2)[1]  # drop opening fence
                if raw.startswith("json"):
                    raw = raw[4:]             # drop "json" language tag
                raw = raw.rsplit("```", 1)[0] # drop closing fence
                raw = raw.strip()
            try:
                results = json.loads(raw)
            except json.JSONDecodeError as je:
                print(f"    [batch {offset+1}] JSON parse error: {je}. Raw response[:200]: {raw[:200]}")
                raise
            results_by_index = {r["index"]: r for r in results}
            return [
                {
                    **t,
                    "claude_category": results_by_index.get(offset + i + 1, {}).get("category", "Uncategorized"),
                    "claude_reasoning": results_by_index.get(offset + i + 1, {}).get("reasoning", ""),
                }
                for i, t in enumerate(batch)
            ]
        except Exception as e:
            last_error = e
            print(f"    [batch {offset+1}-{offset+len(batch)} attempt {attempt+1}] ERROR: {type(e).__name__}: {e}")
            continue

    # Both attempts failed for this batch
    print(f"    [batch {offset+1}-{offset+len(batch)}] FAILED after 2 attempts: {last_error}")
    return [
        {
            **t,
            "claude_category": "Uncategorized",
            "claude_reasoning": f"Batch error: {last_error}",
        }
        for t in batch
    ]


def categorize_transactions(transactions: List[Dict]) -> List[Dict]:
    if not transactions:
        return []

    client = Anthropic()
    results = []
    total = len(transactions)

    for start in range(0, total, BATCH_SIZE):
        batch = transactions[start:start + BATCH_SIZE]
        end = min(start + BATCH_SIZE, total)
        print(f"    Categorizing transactions {start + 1}–{end} of {total}...")
        results.extend(_categorize_batch(client, batch, offset=start))

    # Report category distribution so we can catch silent failures
    from collections import Counter
    dist = Counter(r['claude_category'] for r in results)
    print(f"    Category distribution: {dict(dist.most_common(5))}")
    return results
