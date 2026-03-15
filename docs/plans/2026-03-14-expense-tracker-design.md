# Expense Tracker Design
**Date:** 2026-03-14
**Status:** Approved

## Overview

A Python-based expense tracker that pulls Amex transactions via Plaid twice a month, categorizes them using Claude AI, and writes results to a Google Sheet with charts and a Claude-powered insights section. Runs automatically via GitHub Actions on the 1st and 15th of each month.

---

## Architecture

### Project Structure

```
expense-tracker/
├── .github/
│   └── workflows/
│       └── tracker.yml          # Runs on 1st and 15th of each month
├── src/
│   ├── plaid_client.py          # Fetches transactions from Amex via Plaid
│   ├── categorizer.py           # Sends transactions to Claude, returns categories
│   ├── sheets_writer.py         # Appends rows, deduplicates, updates Dashboard
│   └── main.py                  # Orchestrator: calls all three in sequence
├── requirements.txt
└── .env.example                 # Template for secrets (never committed)
```

### Data Flow

```
GitHub Actions (cron: 1st & 15th)
    → main.py
        → plaid_client.py   → fetches last 16 days of Amex transactions
        → categorizer.py    → sends all transactions to Claude in one batch
        → sheets_writer.py  → appends new rows to "Transactions" sheet
                            → skips rows whose transaction_id already exists
                            → rebuilds "Dashboard" tab with charts & summaries
                            → writes Claude Insights section to Dashboard
```

### Secrets

Stored in GitHub Actions repo secrets, never in code:

- `PLAID_CLIENT_ID`
- `PLAID_SECRET`
- `PLAID_ACCESS_TOKEN`
- `ANTHROPIC_API_KEY`
- `GOOGLE_SERVICE_ACCOUNT_JSON` (base64-encoded service account credentials)

---

## Google Sheet Structure

### "Transactions" Tab

Append-only rolling log. Columns:

| transaction_id | date | merchant | amount | plaid_category | claude_category | claude_reasoning | period |
|---|---|---|---|---|---|---|---|

- `transaction_id` — Plaid's unique ID, used for deduplication on every run
- `claude_reasoning` — short explanation of why Claude chose that category
- `period` — `YYYY-MM` format for chart grouping

### Default Categories

- Dining & Restaurants
- Groceries
- Travel & Transport
- Shopping
- Subscriptions & Software
- Health & Fitness
- Entertainment
- Utilities & Bills
- Other

### "Dashboard" Tab

Rebuilt fresh on every run:

1. **Monthly spend by category** — stacked bar chart (months on X axis, category stacks on Y)
2. **Monthly total spend** — line chart showing trend over time
3. **Current month breakdown** — pie chart of category split
4. **Top 10 merchants this month** — table

5. **Claude Insights section** — written analysis rebuilt every run, covering:
   - **Overspending alerts** — categories notably above personal average (with % comparison)
   - **Unusual merchants** — one-off or suspicious charges outside normal patterns
   - **Subscription creep** — new or increased recurring charges
   - **Positive callouts** — categories where spend is below average
   - Includes timestamp of last analysis

---

## Error Handling

| Failure | Behavior |
|---|---|
| Plaid API down / token expired | Exit early, GitHub Actions marks run failed, sends email |
| `ITEM_LOGIN_REQUIRED` (Amex re-auth needed) | Log clear message in Actions output |
| Claude API failure | Retry once; on second failure, write `Uncategorized` with note in reasoning — transaction data is never lost |
| Google Sheets write failure | Idempotent — re-running skips existing `transaction_id`s, writes only missing rows |
| Missing secrets | Validate all env vars on startup, exit immediately with helpful message |

---

## Scheduling

- **Platform:** GitHub Actions
- **Schedule:** `cron: '0 9 1,15 * *'` — runs at 9am UTC on the 1st and 15th of every month
- **Fetch window:** Last 16 days of transactions (ensures no gaps between runs)
- **Deduplication:** Transaction IDs checked against existing Sheet rows before writing

---

## Key Design Decisions

- **Batch Claude calls** — all transactions sent in a single API call per run (not one per transaction) for efficiency and cost
- **Google Sheet as source of truth** — no local state files; idempotent design means re-runs are always safe
- **Claude Insights uses full history** — the insights analysis receives the complete transaction history, not just the current batch, to enable meaningful trend comparisons
