#!/usr/bin/env python3
"""
One-time script to add charts to the Google Sheet Dashboard tab.
Run this once after the first successful tracker run.
Charts will auto-update on every subsequent tracker run.

Usage:
    cd /Users/pkulkarni/expense-tracker
    source .venv/bin/activate
    pip install -r requirements.txt
    python scripts/setup_charts.py
"""
import os
import base64
import json

from dotenv import load_dotenv
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']


def get_service():
    creds_json = base64.b64decode(os.environ['GOOGLE_SERVICE_ACCOUNT_JSON']).decode()
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds)


def get_sheet_id(service, spreadsheet_id: str, sheet_name: str) -> int:
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for sheet in meta['sheets']:
        if sheet['properties']['title'] == sheet_name:
            return sheet['properties']['sheetId']
    raise ValueError(f"Sheet '{sheet_name}' not found. Run the tracker first.")


def build_chart_requests(dashboard_sheet_id: int) -> list:
    """
    Build chart requests for the Dashboard tab.

    Dashboard layout (from sheets_writer.py):
    - Row 1: "MONTHLY SPEND BY CATEGORY" title
    - Row 2: header row (Category, period1, period2, ...)
    - Rows 3-11: category data (9 categories)
    - ~Row 15: MONTHLY TOTALS
    - Row 16: header (Period, Total)
    - Rows 17+: monthly total rows
    - ~Row 25: CURRENT PERIOD BREAKDOWN
    - Row 26: header (Category, Amount)
    - Rows 27+: per-category amounts
    """

    def cell_ref(sheet_id, row, col):
        return {
            "sheetId": sheet_id,
            "rowIndex": row,
            "columnIndex": col,
        }

    def range_ref(sheet_id, start_row, end_row, start_col, end_col):
        return {
            "sheetId": sheet_id,
            "startRowIndex": start_row,
            "endRowIndex": end_row,
            "startColumnIndex": start_col,
            "endColumnIndex": end_col,
        }

    return [
        # Chart 1: Stacked bar — Monthly spend by category
        # Data: A2:Z11 (header row + 9 category rows, up to 26 periods)
        {
            "addChart": {
                "chart": {
                    "spec": {
                        "title": "Monthly Spend by Category",
                        "basicChart": {
                            "chartType": "BAR",
                            "stackedType": "STACKED",
                            "legendPosition": "RIGHT_LEGEND",
                            "axis": [
                                {"position": "BOTTOM_AXIS", "title": "Amount (USD)"},
                                {"position": "LEFT_AXIS", "title": "Month"},
                            ],
                            "domains": [{
                                "domain": {
                                    "sourceRange": {
                                        "sources": [range_ref(dashboard_sheet_id, 2, 12, 0, 1)]
                                    }
                                }
                            }],
                            "series": [{
                                "series": {
                                    "sourceRange": {
                                        "sources": [range_ref(dashboard_sheet_id, 1, 12, i, i + 1)]
                                    }
                                },
                                "targetAxis": "BOTTOM_AXIS",
                            } for i in range(1, 13)]  # Up to 12 period columns
                        }
                    },
                    "position": {
                        "overlayPosition": {
                            "anchorCell": cell_ref(dashboard_sheet_id, 0, 3),
                            "widthPixels": 700,
                            "heightPixels": 400,
                        }
                    }
                }
            }
        },
        # Chart 2: Line chart — Monthly total spend
        # Data: Monthly Totals section (~rows 15-16+ with Period, Total columns)
        {
            "addChart": {
                "chart": {
                    "spec": {
                        "title": "Monthly Total Spend",
                        "basicChart": {
                            "chartType": "LINE",
                            "legendPosition": "NO_LEGEND",
                            "axis": [
                                {"position": "BOTTOM_AXIS", "title": "Month"},
                                {"position": "LEFT_AXIS", "title": "Total Spend (USD)"},
                            ],
                            "domains": [{
                                "domain": {
                                    "sourceRange": {
                                        "sources": [range_ref(dashboard_sheet_id, 15, 40, 0, 1)]
                                    }
                                }
                            }],
                            "series": [{
                                "series": {
                                    "sourceRange": {
                                        "sources": [range_ref(dashboard_sheet_id, 15, 40, 1, 2)]
                                    }
                                },
                                "targetAxis": "LEFT_AXIS",
                            }]
                        }
                    },
                    "position": {
                        "overlayPosition": {
                            "anchorCell": cell_ref(dashboard_sheet_id, 15, 3),
                            "widthPixels": 700,
                            "heightPixels": 300,
                        }
                    }
                }
            }
        },
        # Chart 3: Pie chart — Current period breakdown
        # Data: Current Period Breakdown section (~rows 26-36)
        {
            "addChart": {
                "chart": {
                    "spec": {
                        "title": "Current Period by Category",
                        "pieChart": {
                            "legendPosition": "RIGHT_LEGEND",
                            "pieHole": 0.4,
                            "domain": {
                                "sourceRange": {
                                    "sources": [range_ref(dashboard_sheet_id, 20, 40, 0, 1)]
                                }
                            },
                            "series": {
                                "sourceRange": {
                                    "sources": [range_ref(dashboard_sheet_id, 20, 40, 1, 2)]
                                }
                            }
                        }
                    },
                    "position": {
                        "overlayPosition": {
                            "anchorCell": cell_ref(dashboard_sheet_id, 30, 3),
                            "widthPixels": 500,
                            "heightPixels": 350,
                        }
                    }
                }
            }
        },
    ]


def add_charts(spreadsheet_id: str) -> None:
    service = get_service()
    dashboard_sheet_id = get_sheet_id(service, spreadsheet_id, 'Dashboard')

    requests = build_chart_requests(dashboard_sheet_id)

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": requests},
    ).execute()

    print(f"✅ Added {len(requests)} charts to Dashboard tab.")
    print("Charts will auto-refresh on every subsequent tracker run.")


if __name__ == '__main__':
    load_dotenv()

    spreadsheet_id = os.environ.get('GOOGLE_SPREADSHEET_ID')
    if not spreadsheet_id:
        print("Error: GOOGLE_SPREADSHEET_ID not set. Copy .env.example to .env and fill in values.")
        exit(1)

    print(f"Adding charts to spreadsheet {spreadsheet_id}...")
    add_charts(spreadsheet_id)
