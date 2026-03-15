# src/sheets_writer.py
import os
import base64
import json
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Set, Tuple

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from src.categorizer import CATEGORIES as CATEGORIES_LIST

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

TRANSACTION_HEADERS = [
    'transaction_id', 'date', 'merchant', 'amount',
    'plaid_category', 'claude_category', 'claude_reasoning', 'period',
]


def _get_creds():
    creds_json = base64.b64decode(os.environ['GOOGLE_SERVICE_ACCOUNT_JSON']).decode()
    creds_dict = json.loads(creds_json)
    return Credentials.from_service_account_info(creds_dict, scopes=SCOPES)


def get_sheets_client():
    return gspread.authorize(_get_creds())


def get_sheets_service():
    return build('sheets', 'v4', credentials=_get_creds())


def _get_or_create_worksheet(spreadsheet, name: str):
    try:
        return spreadsheet.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=name, rows=5000, cols=50)


def _get_existing_ids(worksheet) -> Set[str]:
    try:
        records = worksheet.get_all_records()
        return {str(r.get('transaction_id', '')) for r in records if r.get('transaction_id')}
    except Exception:
        return set()


def clear_transactions(spreadsheet_id: str) -> None:
    """Wipe the Transactions tab (headers + all rows) for a clean backfill."""
    client = get_sheets_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    ws = _get_or_create_worksheet(spreadsheet, 'Transactions')
    ws.clear()
    ws.update('A1', [TRANSACTION_HEADERS])


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


def _delete_existing_charts(service, spreadsheet_id: str, meta: dict, sheet_id: int) -> None:
    """Delete all charts currently on the given sheet."""
    requests = []
    for sheet in meta['sheets']:
        if sheet['properties']['sheetId'] == sheet_id:
            for chart in sheet.get('charts', []):
                requests.append({'deleteEmbeddedObject': {'objectId': chart['chartId']}})
    if requests:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={'requests': requests},
        ).execute()


def _build_chart_requests(
    data_sheet_id: int,    # Dashboard tab — where data lives
    charts_sheet_id: int,  # Charts tab — where charts are anchored
    pie_data_rows: Tuple[int, int],    # (start_row_idx, end_row_idx) data only, no header
    bar_section_rows: Tuple[int, int], # (header_row_idx, end_row_idx) includes header
    num_categories: int,
) -> list:
    """
    Build batchUpdate requests for two charts on the Charts tab:
    1. Pie chart — This Month's Breakdown, labels show dollar values
    2. Stacked column bar chart — Monthly spending by category over time
    Data sourced from Dashboard tab; charts anchored on Charts tab.
    """

    def data_rng(start_row, end_row, start_col, end_col):
        """Range pointing at the Dashboard data tab."""
        return {
            'sheetId': data_sheet_id,
            'startRowIndex': start_row,
            'endRowIndex': end_row,
            'startColumnIndex': start_col,
            'endColumnIndex': end_col,
        }

    def anchor(row, col):
        """Position anchor on the Charts tab."""
        return {'sheetId': charts_sheet_id, 'rowIndex': row, 'columnIndex': col}

    pie_start, pie_end = pie_data_rows
    bar_header, bar_end = bar_section_rows

    # ── Pie chart ──────────────────────────────────────────────────────────
    # Anchored at top-left of Charts tab (row 0, col 0)
    # Domain: Dashboard col A = "Category ($amount)" labels
    # Series: Dashboard col B = amounts
    pie_chart = {
        'addChart': {
            'chart': {
                'spec': {
                    'title': "This Month's Spending by Category",
                    'pieChart': {
                        'legendPosition': 'LABELED_LEGEND',
                        'pieHole': 0,
                        'domain': {
                            'sourceRange': {'sources': [data_rng(pie_start, pie_end, 0, 1)]}
                        },
                        'series': {
                            'sourceRange': {'sources': [data_rng(pie_start, pie_end, 1, 2)]}
                        },
                    },
                },
                'position': {
                    'overlayPosition': {
                        'anchorCell': anchor(0, 0),
                        'widthPixels': 680,
                        'heightPixels': 460,
                    }
                },
            }
        }
    }

    # ── Stacked column bar chart ───────────────────────────────────────────
    # Anchored below the pie chart on the Charts tab (row 28, col 0)
    # bar_header row on Dashboard: "Month | Cat1 | Cat2 | ..."
    # Domain: Month column; Series: one per active category
    bar_series = [
        {
            'series': {
                'sourceRange': {'sources': [data_rng(bar_header, bar_end, col, col + 1)]}
            },
            'targetAxis': 'LEFT_AXIS',
        }
        for col in range(1, num_categories + 1)
    ]

    bar_chart = {
        'addChart': {
            'chart': {
                'spec': {
                    'title': 'Monthly Spending by Category',
                    'basicChart': {
                        'chartType': 'COLUMN',
                        'stackedType': 'STACKED',
                        'legendPosition': 'RIGHT_LEGEND',
                        'axis': [
                            {'position': 'BOTTOM_AXIS', 'title': 'Month'},
                            {'position': 'LEFT_AXIS', 'title': 'Total Spend (USD)'},
                        ],
                        'domains': [{
                            'domain': {
                                'sourceRange': {'sources': [data_rng(bar_header, bar_end, 0, 1)]}
                            }
                        }],
                        'series': bar_series,
                    },
                },
                'position': {
                    'overlayPosition': {
                        'anchorCell': anchor(28, 0),
                        'widthPixels': 900,
                        'heightPixels': 500,
                    }
                },
            }
        }
    }

    return [pie_chart, bar_chart]


def update_dashboard_data(all_transactions: List[Dict], spreadsheet_id: str, insights_text: str = "") -> None:
    """Rebuilds the Dashboard tab with trend tables, then deletes and recreates charts."""
    gc = get_sheets_client()
    service = get_sheets_service()
    spreadsheet = gc.open_by_key(spreadsheet_id)
    ws = _get_or_create_worksheet(spreadsheet, 'Dashboard')
    ws.clear()

    # Resolve sheet IDs and ensure Charts tab exists
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheet_ids = {s['properties']['title']: s['properties']['sheetId'] for s in meta['sheets']}
    dashboard_sheet_id = sheet_ids['Dashboard']

    if 'Charts' not in sheet_ids:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={'requests': [{'addSheet': {'properties': {'title': 'Charts'}}}]},
        ).execute()
        # Refresh meta to get new Charts sheet ID
        meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheet_ids = {s['properties']['title']: s['properties']['sheetId'] for s in meta['sheets']}
    charts_sheet_id = sheet_ids['Charts']

    if not all_transactions:
        ws.update('A1', [['No transaction data available.']])
        return

    periods = sorted({t['period'] for t in all_transactions})
    categories = CATEGORIES_LIST
    current_period = periods[-1]
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M UTC')

    pivot: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for t in all_transactions:
        pivot[t['period']][t['claude_category']] += float(t['amount'])

    monthly_totals = {p: sum(pivot[p].values()) for p in periods}

    all_rows: List[list] = []
    row = 0  # current 0-based row index, tracks where we are as we build

    def blank(n=1):
        nonlocal row
        for _ in range(n):
            all_rows.append([])
            row += 1

    def heading(text):
        nonlocal row
        all_rows.append([text])
        row += 1

    def data_row(r):
        nonlocal row
        all_rows.append(r)
        row += 1

    # ── Section 1: Monthly Spending Trend ─────────────────────────────────
    heading(f'MONTHLY SPENDING TREND  (last updated: {timestamp})')
    data_row(['Period', 'Total Spent', 'vs Prior Month', 'vs 3-Month Avg'])
    for i, p in enumerate(periods):
        total = monthly_totals[p]
        prior = monthly_totals[periods[i - 1]] if i > 0 else None
        delta_str = ''
        if prior and prior > 0:
            pct = (total - prior) / prior * 100
            delta_str = f'{"+" if pct >= 0 else ""}{pct:.1f}%'
        window = [monthly_totals[periods[j]] for j in range(max(0, i - 3), i)]
        avg3 = sum(window) / len(window) if window else None
        avg3_str = ''
        if avg3 and avg3 > 0:
            pct = (total - avg3) / avg3 * 100
            avg3_str = f'{"+" if pct >= 0 else ""}{pct:.1f}%'
        data_row([p, round(total, 2), delta_str, avg3_str])
    blank(2)

    # ── Section 2: Spending by Category (All Months) ──────────────────────
    heading('SPENDING BY CATEGORY — ALL MONTHS')
    data_row(['Category'] + periods + ['TOTAL', 'MONTHLY AVG'])
    for cat in categories:
        row_vals = [round(pivot[p].get(cat, 0), 2) for p in periods]
        total = sum(row_vals)
        if total > 0:
            data_row([cat] + row_vals + [round(total, 2), round(total / len(periods), 2)])
    blank(2)

    # ── Section 3: 2025 vs 2026 Year Comparison ───────────────────────────
    periods_2025 = [p for p in periods if p.startswith('2025')]
    periods_2026 = [p for p in periods if p.startswith('2026')]
    months_2026 = len(periods_2026)

    heading('2025 vs 2026 — YEAR COMPARISON')
    data_row(['Category', '2025 Total', '2026 YTD', '2026 Monthly Avg', 'Trend'])
    for cat in categories:
        total_2025 = sum(pivot[p].get(cat, 0) for p in periods_2025)
        total_2026 = sum(pivot[p].get(cat, 0) for p in periods_2026)
        if total_2025 == 0 and total_2026 == 0:
            continue
        avg_2025 = total_2025 / len(periods_2025) if periods_2025 else 0
        avg_2026 = total_2026 / months_2026 if months_2026 else 0
        if avg_2025 > 0:
            pct = (avg_2026 - avg_2025) / avg_2025 * 100
            trend = f'{"+" if pct >= 0 else ""}{pct:.0f}% vs 2025 avg'
        else:
            trend = 'New in 2026' if total_2026 > 0 else ''
        data_row([cat, round(total_2025, 2), round(total_2026, 2), round(avg_2026, 2), trend])
    blank(2)

    # ── Section 4: Top 10 Merchants (All Time) ────────────────────────────
    merchant_totals: Dict[str, float] = defaultdict(float)
    merchant_count: Dict[str, int] = defaultdict(int)
    for t in all_transactions:
        merchant_totals[t['merchant']] += float(t['amount'])
        merchant_count[t['merchant']] += 1
    top10 = sorted(merchant_totals.items(), key=lambda x: x[1], reverse=True)[:10]

    heading('TOP 10 MERCHANTS — ALL TIME')
    data_row(['Merchant', 'Total Spent', '# Transactions', 'Avg per Transaction'])
    for m, amt in top10:
        count = merchant_count[m]
        data_row([m, round(amt, 2), count, round(amt / count, 2)])
    blank(2)

    # ── Section 5: This Month's Breakdown — pie chart source ──────────────
    current_month_total = monthly_totals.get(current_period, 0)
    heading(f"THIS MONTH'S BREAKDOWN ({current_period})")
    data_row(['Category', 'Amount', '% of Total'])
    month_rows_sorted = sorted(
        [(cat, round(pivot[current_period].get(cat, 0), 2)) for cat in categories
         if pivot[current_period].get(cat, 0) > 0],
        key=lambda x: x[1], reverse=True,
    )
    pie_data_start = row  # first data row (after heading + header)
    for cat, amt in month_rows_sorted:
        pct = f'{amt / current_month_total * 100:.1f}%' if current_month_total > 0 else ''
        label = f'{cat} (${amt:,.0f})'  # dollar value baked into label for pie chart
        data_row([label, amt, pct])
    pie_data_end = row  # exclusive end
    blank(2)

    # ── Section 6: Monthly Category Breakdown — stacked bar chart source ──
    active_cats = [c for c in categories if any(pivot[p].get(c, 0) > 0 for p in periods)]
    heading('MONTHLY CATEGORY BREAKDOWN')
    bar_header_row = row  # the column-header row for the chart domain
    data_row(['Month'] + active_cats)
    for p in periods:
        data_row([p] + [round(pivot[p].get(c, 0), 2) for c in active_cats])
    bar_data_end = row  # exclusive end
    blank(2)

    # ── Section 7: Claude Insights & Savings Opportunities ────────────────
    if insights_text:
        heading('CLAUDE INSIGHTS & SAVINGS OPPORTUNITIES')
        data_row([insights_text])

    # Write all data in one API call
    ws.update('A1', all_rows)

    # Delete existing charts from Charts tab and redraw with correct row positions
    # Refresh meta after data write so chart IDs are current
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    _delete_existing_charts(service, spreadsheet_id, meta, charts_sheet_id)
    chart_requests = _build_chart_requests(
        data_sheet_id=dashboard_sheet_id,
        charts_sheet_id=charts_sheet_id,
        pie_data_rows=(pie_data_start, pie_data_end),
        bar_section_rows=(bar_header_row, bar_data_end),
        num_categories=len(active_cats),
    )
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={'requests': chart_requests},
    ).execute()
