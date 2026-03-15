# src/sheets_writer.py
import os
import base64
import json
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Set

import gspread
from google.oauth2.service_account import Credentials

from src.categorizer import CATEGORIES as CATEGORIES_LIST

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

TRANSACTION_HEADERS = [
    'transaction_id', 'date', 'merchant', 'amount',
    'plaid_category', 'claude_category', 'claude_reasoning', 'period',
]


def get_sheets_client():
    creds_json = base64.b64decode(os.environ['GOOGLE_SERVICE_ACCOUNT_JSON']).decode()
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


def _get_or_create_worksheet(spreadsheet, name: str):
    try:
        return spreadsheet.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=name, rows=5000, cols=20)


def _get_existing_ids(worksheet) -> Set[str]:
    try:
        records = worksheet.get_all_records()
        return {str(r.get('transaction_id', '')) for r in records if r.get('transaction_id')}
    except Exception:
        return set()


def append_transactions(transactions: List[Dict], spreadsheet_id: str) -> int:
    client = get_sheets_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    ws = _get_or_create_worksheet(spreadsheet, 'Transactions')

    if ws.row_count == 0 or not ws.cell(1, 1).value:
        ws.update('A1', [TRANSACTION_HEADERS])

    existing_ids = _get_existing_ids(ws)
    new_txns = [t for t in transactions if t['transaction_id'] not in existing_ids]

    if not new_txns:
        return 0

    rows = [[t.get(h, '') for h in TRANSACTION_HEADERS] for t in new_txns]
    ws.append_rows(rows, value_input_option='USER_ENTERED')
    return len(new_txns)


def clear_transactions(spreadsheet_id: str) -> None:
    """Wipe the Transactions tab (headers + all rows) for a clean backfill."""
    client = get_sheets_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    ws = _get_or_create_worksheet(spreadsheet, 'Transactions')
    ws.clear()
    ws.update('A1', [TRANSACTION_HEADERS])


def read_all_transactions(spreadsheet_id: str) -> List[Dict]:
    """Read all transactions from the Transactions tab for full historical context."""
    client = get_sheets_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    ws = _get_or_create_worksheet(spreadsheet, 'Transactions')
    return ws.get_all_records()


def update_dashboard_data(all_transactions: List[Dict], spreadsheet_id: str, insights_text: str = "") -> None:
    """Rebuilds the Dashboard tab with trend tables and Claude insights."""
    client = get_sheets_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    ws = _get_or_create_worksheet(spreadsheet, 'Dashboard')
    ws.clear()

    if not all_transactions:
        ws.update('A1', [['No transaction data available.']])
        return

    periods = sorted({t['period'] for t in all_transactions})
    categories = CATEGORIES_LIST
    current_period = periods[-1]
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M UTC')

    # Build pivot: period -> category -> total
    pivot: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for t in all_transactions:
        pivot[t['period']][t['claude_category']] += float(t['amount'])

    monthly_totals = {p: sum(pivot[p].values()) for p in periods}

    # Build all rows in one list, send in a single API call
    all_rows = []

    def blank(n=1):
        for _ in range(n):
            all_rows.append([])

    def heading(text):
        all_rows.append([text])

    # ── Section 1: Monthly Spending Trend ─────────────────────────────────
    heading(f'MONTHLY SPENDING TREND  (last updated: {timestamp})')
    all_rows.append(['Period', 'Total Spent', 'vs Prior Month', 'vs 3-Month Avg'])
    for i, p in enumerate(periods):
        total = monthly_totals[p]
        prior = monthly_totals[periods[i - 1]] if i > 0 else None
        delta_str = ''
        if prior and prior > 0:
            pct = (total - prior) / prior * 100
            sign = '+' if pct >= 0 else ''
            delta_str = f'{sign}{pct:.1f}%'
        window = [monthly_totals[periods[j]] for j in range(max(0, i - 3), i)]
        avg3 = sum(window) / len(window) if window else None
        avg3_str = ''
        if avg3 and avg3 > 0:
            pct = (total - avg3) / avg3 * 100
            sign = '+' if pct >= 0 else ''
            avg3_str = f'{sign}{pct:.1f}%'
        all_rows.append([p, round(total, 2), delta_str, avg3_str])
    blank(2)

    # ── Section 2: Spending by Category (All Months) ──────────────────────
    heading('SPENDING BY CATEGORY — ALL MONTHS')
    cat_header = ['Category'] + periods + ['TOTAL', 'MONTHLY AVG']
    all_rows.append(cat_header)
    for cat in categories:
        row_vals = [round(pivot[p].get(cat, 0), 2) for p in periods]
        total = sum(row_vals)
        avg = total / len(periods) if periods else 0
        if total > 0:
            all_rows.append([cat] + row_vals + [round(total, 2), round(avg, 2)])
    blank(2)

    # ── Section 3: 2025 vs 2026 Year Comparison ───────────────────────────
    periods_2025 = [p for p in periods if p.startswith('2025')]
    periods_2026 = [p for p in periods if p.startswith('2026')]
    months_2026 = len(periods_2026)

    heading('2025 vs 2026 — YEAR COMPARISON')
    all_rows.append(['Category', '2025 Total', '2026 YTD', '2026 Monthly Avg', 'Trend'])
    for cat in categories:
        total_2025 = sum(pivot[p].get(cat, 0) for p in periods_2025)
        total_2026 = sum(pivot[p].get(cat, 0) for p in periods_2026)
        avg_2026 = total_2026 / months_2026 if months_2026 else 0
        if total_2025 == 0 and total_2026 == 0:
            continue
        # Compare 2026 monthly avg vs 2025 monthly avg
        avg_2025 = total_2025 / len(periods_2025) if periods_2025 else 0
        if avg_2025 > 0:
            pct = (avg_2026 - avg_2025) / avg_2025 * 100
            sign = '+' if pct >= 0 else ''
            trend = f'{sign}{pct:.0f}% vs 2025 avg'
        else:
            trend = 'New in 2026' if total_2026 > 0 else ''
        all_rows.append([cat, round(total_2025, 2), round(total_2026, 2), round(avg_2026, 2), trend])
    blank(2)

    # ── Section 4: Top 10 Merchants (All Time) ────────────────────────────
    merchant_totals: Dict[str, float] = defaultdict(float)
    merchant_count: Dict[str, int] = defaultdict(int)
    for t in all_transactions:
        merchant_totals[t['merchant']] += float(t['amount'])
        merchant_count[t['merchant']] += 1
    top10 = sorted(merchant_totals.items(), key=lambda x: x[1], reverse=True)[:10]

    heading('TOP 10 MERCHANTS — ALL TIME')
    all_rows.append(['Merchant', 'Total Spent', '# Transactions', 'Avg per Transaction'])
    for m, amt in top10:
        count = merchant_count[m]
        all_rows.append([m, round(amt, 2), count, round(amt / count, 2)])
    blank(2)

    # ── Section 5: This Month's Breakdown ─────────────────────────────────
    current_month_total = monthly_totals.get(current_period, 0)
    heading(f'THIS MONTH\'S BREAKDOWN ({current_period})')
    all_rows.append(['Category', 'Amount', '% of Total'])
    month_rows = [
        (cat, round(pivot[current_period].get(cat, 0), 2))
        for cat in categories
        if pivot[current_period].get(cat, 0) > 0
    ]
    month_rows.sort(key=lambda x: x[1], reverse=True)
    for cat, amt in month_rows:
        pct = f'{amt / current_month_total * 100:.1f}%' if current_month_total > 0 else ''
        all_rows.append([cat, amt, pct])
    blank(2)

    # ── Section 6: Claude Insights & Savings Opportunities ────────────────
    if insights_text:
        heading('CLAUDE INSIGHTS & SAVINGS OPPORTUNITIES')
        all_rows.append([insights_text])

    ws.update('A1', all_rows)
