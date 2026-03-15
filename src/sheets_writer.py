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


def read_all_transactions(spreadsheet_id: str) -> List[Dict]:
    """Read all transactions from the Transactions tab for full historical context."""
    client = get_sheets_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    ws = _get_or_create_worksheet(spreadsheet, 'Transactions')
    return ws.get_all_records()


def update_dashboard_data(all_transactions: List[Dict], spreadsheet_id: str, insights_text: str = "") -> None:
    """Rebuilds the Dashboard tab with summary pivot tables and Claude insights."""
    client = get_sheets_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    ws = _get_or_create_worksheet(spreadsheet, 'Dashboard')
    ws.clear()

    periods = sorted({t['period'] for t in all_transactions})
    categories = CATEGORIES_LIST

    pivot: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for t in all_transactions:
        pivot[t['period']][t['claude_category']] += float(t['amount'])

    # Section 1: Category x Period pivot table
    header_row = ['Category'] + periods
    pivot_rows = [header_row]
    for cat in categories:
        row = [cat] + [round(pivot[p][cat], 2) for p in periods]
        pivot_rows.append(row)

    ws.update('A1', [['MONTHLY SPEND BY CATEGORY']])
    ws.update('A2', pivot_rows)

    # Section 2: Monthly totals
    totals_start_row = len(pivot_rows) + 4
    totals_header = [['MONTHLY TOTALS'], ['Period', 'Total']]
    totals_rows = [[p, round(sum(pivot[p].values()), 2)] for p in periods]
    ws.update(f'A{totals_start_row}', totals_header + totals_rows)

    # Section 3: Current month breakdown
    current_period = max(periods) if periods else ''
    pie_start_row = totals_start_row + len(totals_rows) + 4
    pie_header = [[f'CURRENT PERIOD BREAKDOWN ({current_period})'], ['Category', 'Amount']]
    pie_rows = [
        [cat, round(pivot[current_period][cat], 2)]
        for cat in categories
        if pivot[current_period][cat] > 0
    ]
    ws.update(f'A{pie_start_row}', pie_header + pie_rows)

    # Section 4: Top 10 merchants
    current_txns = [t for t in all_transactions if t['period'] == current_period]
    merchant_totals: Dict[str, float] = defaultdict(float)
    for t in current_txns:
        merchant_totals[t['merchant']] += float(t['amount'])
    top10 = sorted(merchant_totals.items(), key=lambda x: x[1], reverse=True)[:10]

    top10_start_row = pie_start_row + len(pie_rows) + 4
    top10_header = [[f'TOP 10 MERCHANTS ({current_period})'], ['Merchant', 'Total Spend']]
    top10_rows = [[m, round(amt, 2)] for m, amt in top10]
    ws.update(f'A{top10_start_row}', top10_header + top10_rows)

    # Section 5: Claude Insights
    if insights_text:
        insights_start_row = top10_start_row + len(top10_rows) + 4
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M UTC')
        ws.update(f'A{insights_start_row}', [
            ['CLAUDE INSIGHTS'],
            [f'Last updated: {timestamp}'],
            [insights_text],
        ])
