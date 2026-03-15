# src/main.py
import os
import sys

from dotenv import load_dotenv

from src.teller_client import fetch_transactions
from src.categorizer import categorize_transactions
from src.sheets_writer import (
    append_transactions,
    get_uncategorized_transactions,
    update_transaction_categories,
    update_dashboard_data,
    read_all_transactions,
    clear_transactions,
)
from src.insights import generate_insights

REQUIRED_ENV_VARS = [
    'TELLER_CERT',
    'TELLER_KEY',
    'TELLER_ACCESS_TOKEN',
    'ANTHROPIC_API_KEY',
    'GOOGLE_SERVICE_ACCOUNT_JSON',
    'GOOGLE_SPREADSHEET_ID',
]


class ConfigError(Exception):
    pass


def validate_env() -> None:
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        raise ConfigError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            f"See .env.example for the full list of required variables."
        )


def run() -> None:
    load_dotenv()
    validate_env()

    spreadsheet_id = os.environ['GOOGLE_SPREADSHEET_ID']

    if os.environ.get('RESET_DATA', 'false').lower() == 'true':
        print("RESET_DATA=true — clearing Transactions tab for clean backfill...")
        clear_transactions(spreadsheet_id)
        print("  Transactions tab cleared.")

    print("Fetching transactions from Teller (2025-01-01 onwards)...")
    transactions = fetch_transactions(start_date='2025-01-01')
    print(f"  Fetched {len(transactions)} transactions.")

    if not transactions:
        print("No new transactions found. Exiting.")
        return

    print("Persisting raw transactions to Google Sheet...")
    new_count = append_transactions(transactions, spreadsheet_id)
    print(f"  Wrote {new_count} new transactions ({len(transactions) - new_count} already existed).")

    print("Categorizing uncategorized transactions with Claude...")
    uncategorized = get_uncategorized_transactions(spreadsheet_id)
    print(f"  Found {len(uncategorized)} uncategorized transactions.")
    if uncategorized:
        row_nums = [r for r, _ in uncategorized]
        txns = [t for _, t in uncategorized]
        categorized = categorize_transactions(txns)
        update_transaction_categories(list(zip(row_nums, categorized)), spreadsheet_id)
        print(f"  Categorized and updated {len(categorized)} transactions.")

    print("Reading full transaction history for insights and dashboard...")
    all_transactions = read_all_transactions(spreadsheet_id)
    print(f"  Loaded {len(all_transactions)} total transactions.")

    print("Generating Claude insights...")
    insights = generate_insights(all_transactions)
    print("  Insights generated.")

    print("Updating Dashboard tab...")
    update_dashboard_data(all_transactions, spreadsheet_id, insights_text=insights)
    print("  Dashboard updated.")

    print(f"\nDone. {new_count} new transactions added, dashboard refreshed.")


if __name__ == '__main__':
    try:
        run()
    except ConfigError as e:
        print(f"Configuration error:\n{e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        raise
