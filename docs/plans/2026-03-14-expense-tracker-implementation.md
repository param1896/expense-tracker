# Expense Tracker Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python expense tracker that pulls Amex transactions via Plaid, categorizes them with Claude AI, and writes results + insights to a Google Sheet, running automatically twice a month via GitHub Actions.

**Architecture:** Modular pipeline with four components (plaid_client, categorizer, sheets_writer, main) orchestrated by a GitHub Actions workflow. The Google Sheet acts as the source of truth for deduplication — transaction IDs already in the sheet are skipped on re-runs, making every run idempotent.

**Tech Stack:** Python 3.11, `plaid-python`, `anthropic`, `gspread`, `google-auth`, `python-dotenv`, `pytest`, `pytest-mock`

---

## Prerequisites (Manual Steps Before Coding)

Before running any code, the user must complete these one-time setup steps:

### A. Plaid Setup
1. Create a Plaid account at https://dashboard.plaid.com
2. Create an application and note your `client_id` and `secret` (use Production keys for real Amex data)
3. Use [Plaid Quickstart](https://github.com/plaid/quickstart) or the Plaid dashboard to link your Amex account and obtain an `access_token`
4. Store these three values — you'll add them as GitHub secrets in Prerequisite C

### B. Google Sheets + Service Account Setup
1. Create a new Google Sheet and note its ID (the long string in the URL between `/d/` and `/edit`)
2. Go to [Google Cloud Console](https://console.cloud.google.com), create a project, enable **Google Sheets API** and **Google Drive API**
3. Create a **Service Account**, download the JSON key file
4. Share your Google Sheet with the service account email (give it Editor access)
5. Base64-encode the JSON key: `base64 -i service-account.json | tr -d '\n'`
6. Store the base64 string — you'll add it as a GitHub secret in Prerequisite C

### C. GitHub Secrets
In your GitHub repo → Settings → Secrets → Actions, add:
- `PLAID_CLIENT_ID`
- `PLAID_SECRET`
- `PLAID_ACCESS_TOKEN`
- `ANTHROPIC_API_KEY`
- `GOOGLE_SERVICE_ACCOUNT_JSON` (the base64 string from step B5)
- `GOOGLE_SPREADSHEET_ID` (the Sheet ID from step B1)

---

## Task 1: Project Scaffold

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `src/__init__.py`
- Create: `tests/__init__.py`
- Create: `.gitignore`

**Step 1: Create requirements.txt**

```
plaid-python>=14.0.0
anthropic>=0.25.0
gspread>=6.0.0
google-auth>=2.28.0
python-dotenv>=1.0.0
pytest>=8.0.0
pytest-mock>=3.12.0
```

**Step 2: Create .env.example**

```
PLAID_CLIENT_ID=your_plaid_client_id
PLAID_SECRET=your_plaid_secret
PLAID_ACCESS_TOKEN=your_plaid_access_token
ANTHROPIC_API_KEY=your_anthropic_api_key
GOOGLE_SERVICE_ACCOUNT_JSON=base64_encoded_service_account_json
GOOGLE_SPREADSHEET_ID=your_google_sheet_id
```

**Step 3: Create .gitignore**

```
.env
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
dist/
.venv/
venv/
```

**Step 4: Create empty src/__init__.py and tests/__init__.py**

```python
# empty
```

**Step 5: Install dependencies**

```bash
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```

Expected: All packages install without errors.

**Step 6: Commit**

```bash
git add requirements.txt .env.example .gitignore src/__init__.py tests/__init__.py
git commit -m "feat: project scaffold"
```

---

## Task 2: Plaid Client

**Files:**
- Create: `src/plaid_client.py`
- Create: `tests/test_plaid_client.py`

**Step 1: Write the failing test**

```python
# tests/test_plaid_client.py
from unittest.mock import MagicMock, patch
import pytest
from src.plaid_client import fetch_transactions


def make_mock_transaction(txn_id="txn_1", pending=False):
    t = MagicMock()
    t.__getitem__ = lambda self, key: {
        'transaction_id': txn_id,
        'date': MagicMock(__str__=lambda s: '2026-03-01'),
        'merchant_name': 'Sweetgreen',
        'name': 'SWEETGREEN',
        'amount': 14.50,
        'category': ['Food and Drink', 'Restaurants'],
        'pending': pending,
    }[key]
    t.get = lambda key, default=None: {'merchant_name': 'Sweetgreen', 'category': ['Food and Drink', 'Restaurants'], 'pending': pending}.get(key, default)
    return t


@patch('src.plaid_client.plaid_api.PlaidApi')
def test_fetch_transactions_returns_normalized_list(mock_api_class, monkeypatch):
    monkeypatch.setenv('PLAID_CLIENT_ID', 'test_id')
    monkeypatch.setenv('PLAID_SECRET', 'test_secret')
    monkeypatch.setenv('PLAID_ACCESS_TOKEN', 'test_token')

    mock_api = MagicMock()
    mock_api_class.return_value = mock_api

    txn = make_mock_transaction('txn_1')
    mock_response = MagicMock()
    mock_response.__getitem__ = lambda self, key: {
        'transactions': [txn],
        'total_transactions': 1,
    }[key]
    mock_api.transactions_get.return_value = mock_response

    result = fetch_transactions(days_back=16)

    assert len(result) == 1
    assert result[0]['transaction_id'] == 'txn_1'
    assert result[0]['merchant'] == 'Sweetgreen'
    assert result[0]['amount'] == 14.50
    assert result[0]['date'] == '2026-03-01'
    assert result[0]['plaid_category'] == 'Food and Drink'


@patch('src.plaid_client.plaid_api.PlaidApi')
def test_fetch_transactions_skips_pending(mock_api_class, monkeypatch):
    monkeypatch.setenv('PLAID_CLIENT_ID', 'test_id')
    monkeypatch.setenv('PLAID_SECRET', 'test_secret')
    monkeypatch.setenv('PLAID_ACCESS_TOKEN', 'test_token')

    mock_api = MagicMock()
    mock_api_class.return_value = mock_api

    pending_txn = make_mock_transaction('txn_pending', pending=True)
    mock_response = MagicMock()
    mock_response.__getitem__ = lambda self, key: {
        'transactions': [pending_txn],
        'total_transactions': 1,
    }[key]
    mock_api.transactions_get.return_value = mock_response

    result = fetch_transactions(days_back=16)
    assert result == []
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_plaid_client.py -v
```
Expected: `ImportError` or `ModuleNotFoundError` — `src/plaid_client.py` doesn't exist yet.

**Step 3: Write the implementation**

```python
# src/plaid_client.py
import os
from datetime import date, timedelta
from typing import List, Dict

from plaid.api import plaid_api
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions
from plaid import ApiClient, Configuration, Environment


def get_plaid_client():
    configuration = Configuration(
        host=Environment.Production,
        api_key={
            'clientId': os.environ['PLAID_CLIENT_ID'],
            'secret': os.environ['PLAID_SECRET'],
        }
    )
    return plaid_api.PlaidApi(ApiClient(configuration))


def fetch_transactions(days_back: int = 16) -> List[Dict]:
    client = get_plaid_client()
    end_date = date.today()
    start_date = end_date - timedelta(days=days_back)

    request = TransactionsGetRequest(
        access_token=os.environ['PLAID_ACCESS_TOKEN'],
        start_date=start_date,
        end_date=end_date,
    )
    response = client.transactions_get(request)
    transactions = list(response['transactions'])

    # Paginate if needed
    while len(transactions) < response['total_transactions']:
        request = TransactionsGetRequest(
            access_token=os.environ['PLAID_ACCESS_TOKEN'],
            start_date=start_date,
            end_date=end_date,
            options=TransactionsGetRequestOptions(offset=len(transactions)),
        )
        response = client.transactions_get(request)
        transactions.extend(response['transactions'])

    return [
        {
            'transaction_id': t['transaction_id'],
            'date': str(t['date']),
            'merchant': t.get('merchant_name') or t['name'],
            'amount': t['amount'],
            'plaid_category': t['category'][0] if t.get('category') else 'Unknown',
        }
        for t in transactions
        if not t.get('pending', False)
    ]
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_plaid_client.py -v
```
Expected: 2 tests PASS.

**Step 5: Commit**

```bash
git add src/plaid_client.py tests/test_plaid_client.py
git commit -m "feat: add Plaid client with transaction fetch and pagination"
```

---

## Task 3: Claude Categorizer

**Files:**
- Create: `src/categorizer.py`
- Create: `tests/test_categorizer.py`

**Step 1: Write the failing test**

```python
# tests/test_categorizer.py
import json
import pytest
from unittest.mock import MagicMock, patch
from src.categorizer import categorize_transactions, CATEGORIES


SAMPLE_TRANSACTIONS = [
    {'transaction_id': 'txn_1', 'date': '2026-03-01', 'merchant': 'Sweetgreen', 'amount': 14.50, 'plaid_category': 'Food and Drink'},
    {'transaction_id': 'txn_2', 'date': '2026-03-02', 'merchant': 'Netflix', 'amount': 15.99, 'plaid_category': 'Service'},
]

MOCK_CLAUDE_RESPONSE = json.dumps([
    {"index": 1, "category": "Dining & Restaurants", "reasoning": "Sweetgreen is a restaurant chain. $14.50 is consistent with lunch."},
    {"index": 2, "category": "Subscriptions & Software", "reasoning": "Netflix is a streaming subscription service. $15.99 is the standard monthly fee."},
])


@patch('src.categorizer.Anthropic')
def test_categorize_transactions_returns_enriched_list(mock_anthropic_class, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test_key')

    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=MOCK_CLAUDE_RESPONSE)]
    mock_client.messages.create.return_value = mock_message

    result = categorize_transactions(SAMPLE_TRANSACTIONS)

    assert len(result) == 2
    assert result[0]['claude_category'] == 'Dining & Restaurants'
    assert result[0]['claude_reasoning'] == 'Sweetgreen is a restaurant chain. $14.50 is consistent with lunch.'
    assert result[0]['period'] == '2026-03'
    assert result[1]['claude_category'] == 'Subscriptions & Software'


@patch('src.categorizer.Anthropic')
def test_categorize_transactions_returns_empty_for_empty_input(mock_anthropic_class):
    result = categorize_transactions([])
    assert result == []
    mock_anthropic_class.return_value.messages.create.assert_not_called()


def test_categories_contains_expected_defaults():
    assert 'Dining & Restaurants' in CATEGORIES
    assert 'Groceries' in CATEGORIES
    assert 'Other' in CATEGORIES
    assert len(CATEGORIES) == 9
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_categorizer.py -v
```
Expected: `ImportError` — `src/categorizer.py` doesn't exist yet.

**Step 3: Write the implementation**

```python
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
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_categorizer.py -v
```
Expected: 3 tests PASS.

**Step 5: Commit**

```bash
git add src/categorizer.py tests/test_categorizer.py
git commit -m "feat: add Claude categorizer with batch transaction analysis"
```

---

## Task 4: Sheets Writer — Transactions Tab

**Files:**
- Create: `src/sheets_writer.py`
- Create: `tests/test_sheets_writer.py`

**Step 1: Write the failing test**

```python
# tests/test_sheets_writer.py
import pytest
from unittest.mock import MagicMock, patch, call
from src.sheets_writer import append_transactions, TRANSACTION_HEADERS

SAMPLE_CATEGORIZED = [
    {
        'transaction_id': 'txn_1',
        'date': '2026-03-01',
        'merchant': 'Sweetgreen',
        'amount': 14.50,
        'plaid_category': 'Food and Drink',
        'claude_category': 'Dining & Restaurants',
        'claude_reasoning': 'Restaurant chain.',
        'period': '2026-03',
    },
    {
        'transaction_id': 'txn_2',
        'date': '2026-03-02',
        'merchant': 'Netflix',
        'amount': 15.99,
        'plaid_category': 'Service',
        'claude_category': 'Subscriptions & Software',
        'claude_reasoning': 'Streaming service.',
        'period': '2026-03',
    },
]


def make_mock_worksheet(existing_records=None):
    ws = MagicMock()
    ws.get_all_records.return_value = existing_records or []
    ws.cell.return_value = MagicMock(value=None)
    ws.row_count = 0
    return ws


@patch('src.sheets_writer.get_sheets_client')
def test_append_transactions_writes_new_rows(mock_get_client, monkeypatch):
    monkeypatch.setenv('GOOGLE_SERVICE_ACCOUNT_JSON', 'dGVzdA==')

    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_spreadsheet = MagicMock()
    mock_client.open_by_key.return_value = mock_spreadsheet

    ws = make_mock_worksheet(existing_records=[])
    mock_spreadsheet.worksheet.return_value = ws

    count = append_transactions(SAMPLE_CATEGORIZED, 'sheet_id_123')

    assert count == 2
    ws.append_rows.assert_called_once()
    rows_written = ws.append_rows.call_args[0][0]
    assert len(rows_written) == 2
    assert rows_written[0][0] == 'txn_1'


@patch('src.sheets_writer.get_sheets_client')
def test_append_transactions_skips_existing_ids(mock_get_client, monkeypatch):
    monkeypatch.setenv('GOOGLE_SERVICE_ACCOUNT_JSON', 'dGVzdA==')

    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_spreadsheet = MagicMock()
    mock_client.open_by_key.return_value = mock_spreadsheet

    ws = make_mock_worksheet(existing_records=[{'transaction_id': 'txn_1'}])
    ws.cell.return_value = MagicMock(value='transaction_id')
    ws.row_count = 2
    mock_spreadsheet.worksheet.return_value = ws

    count = append_transactions(SAMPLE_CATEGORIZED, 'sheet_id_123')

    assert count == 1
    rows_written = ws.append_rows.call_args[0][0]
    assert rows_written[0][0] == 'txn_2'


@patch('src.sheets_writer.get_sheets_client')
def test_append_transactions_returns_zero_when_all_exist(mock_get_client, monkeypatch):
    monkeypatch.setenv('GOOGLE_SERVICE_ACCOUNT_JSON', 'dGVzdA==')

    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_spreadsheet = MagicMock()
    mock_client.open_by_key.return_value = mock_spreadsheet

    ws = make_mock_worksheet(existing_records=[
        {'transaction_id': 'txn_1'},
        {'transaction_id': 'txn_2'},
    ])
    ws.cell.return_value = MagicMock(value='transaction_id')
    ws.row_count = 3
    mock_spreadsheet.worksheet.return_value = ws

    count = append_transactions(SAMPLE_CATEGORIZED, 'sheet_id_123')

    assert count == 0
    ws.append_rows.assert_not_called()
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_sheets_writer.py -v
```
Expected: `ImportError`.

**Step 3: Write the implementation**

```python
# src/sheets_writer.py
import os
import base64
import json
from typing import List, Dict, Set
import gspread
from google.oauth2.service_account import Credentials

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
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_sheets_writer.py -v
```
Expected: 3 tests PASS.

**Step 5: Commit**

```bash
git add src/sheets_writer.py tests/test_sheets_writer.py
git commit -m "feat: add Sheets writer with idempotent deduplication"
```

---

## Task 5: Dashboard Summary Data Writer

**Files:**
- Modify: `src/sheets_writer.py` — add `update_dashboard_data()`
- Modify: `tests/test_sheets_writer.py` — add tests

**Step 1: Write the failing test** (add to `tests/test_sheets_writer.py`)

```python
from src.sheets_writer import update_dashboard_data

ALL_TRANSACTIONS = [
    {'period': '2026-02', 'claude_category': 'Dining & Restaurants', 'amount': 45.00, 'merchant': 'Shake Shack'},
    {'period': '2026-02', 'claude_category': 'Groceries', 'amount': 120.00, 'merchant': 'Whole Foods'},
    {'period': '2026-03', 'claude_category': 'Dining & Restaurants', 'amount': 180.00, 'merchant': 'Various'},
    {'period': '2026-03', 'claude_category': 'Groceries', 'amount': 95.00, 'merchant': 'Trader Joes'},
]


@patch('src.sheets_writer.get_sheets_client')
def test_update_dashboard_data_writes_pivot(mock_get_client, monkeypatch):
    monkeypatch.setenv('GOOGLE_SERVICE_ACCOUNT_JSON', 'dGVzdA==')

    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_spreadsheet = MagicMock()
    mock_client.open_by_key.return_value = mock_spreadsheet
    ws = MagicMock()
    mock_spreadsheet.worksheet.return_value = ws

    update_dashboard_data(ALL_TRANSACTIONS, 'sheet_id_123', insights_text="Test insights")

    ws.clear.assert_called_once()
    ws.update.assert_called()
    # Verify the first update call writes the summary header
    first_update_data = ws.update.call_args_list[0][0][1]
    assert first_update_data[0][0] == 'Category'
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_sheets_writer.py::test_update_dashboard_data_writes_pivot -v
```
Expected: `ImportError` for `update_dashboard_data`.

**Step 3: Add `update_dashboard_data` to `src/sheets_writer.py`**

```python
# Add this import at top of sheets_writer.py
from collections import defaultdict
from datetime import datetime


def update_dashboard_data(all_transactions: List[Dict], spreadsheet_id: str, insights_text: str = "") -> None:
    """Rebuilds the Dashboard tab with summary pivot tables and Claude insights."""
    client = get_sheets_client()
    spreadsheet = client.open_by_key(spreadsheet_id)
    ws = _get_or_create_worksheet(spreadsheet, 'Dashboard')
    ws.clear()

    # Build period × category pivot
    periods = sorted({t['period'] for t in all_transactions})
    categories = CATEGORIES_LIST

    pivot: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for t in all_transactions:
        pivot[t['period']][t['claude_category']] += float(t['amount'])

    # --- Section 1: Category × Period pivot table (feeds stacked bar chart) ---
    header_row = ['Category'] + periods
    pivot_rows = [header_row]
    for cat in categories:
        row = [cat] + [round(pivot[p][cat], 2) for p in periods]
        pivot_rows.append(row)

    ws.update('A1', [['MONTHLY SPEND BY CATEGORY']])
    ws.update('A2', pivot_rows)

    # --- Section 2: Monthly totals (feeds line chart) ---
    totals_start_row = len(pivot_rows) + 4
    totals_header = [['MONTHLY TOTALS'], ['Period', 'Total']]
    totals_rows = [[p, round(sum(pivot[p].values()), 2)] for p in periods]
    ws.update(f'A{totals_start_row}', totals_header + totals_rows)

    # --- Section 3: Current month breakdown (feeds pie chart) ---
    current_period = max(periods) if periods else ''
    pie_start_row = totals_start_row + len(totals_rows) + 4
    pie_header = [[f'CURRENT PERIOD BREAKDOWN ({current_period})'], ['Category', 'Amount']]
    pie_rows = [
        [cat, round(pivot[current_period][cat], 2)]
        for cat in categories
        if pivot[current_period][cat] > 0
    ]
    ws.update(f'A{pie_start_row}', pie_header + pie_rows)

    # --- Section 4: Top 10 merchants this period ---
    current_txns = [t for t in all_transactions if t['period'] == current_period]
    merchant_totals: Dict[str, float] = defaultdict(float)
    for t in current_txns:
        merchant_totals[t['merchant']] += float(t['amount'])
    top10 = sorted(merchant_totals.items(), key=lambda x: x[1], reverse=True)[:10]

    top10_start_row = pie_start_row + len(pie_rows) + 4
    top10_header = [[f'TOP 10 MERCHANTS ({current_period})'], ['Merchant', 'Total Spend']]
    top10_rows = [[m, round(amt, 2)] for m, amt in top10]
    ws.update(f'A{top10_start_row}', top10_header + top10_rows)

    # --- Section 5: Claude Insights ---
    if insights_text:
        insights_start_row = top10_start_row + len(top10_rows) + 4
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M UTC')
        ws.update(f'A{insights_start_row}', [
            ['CLAUDE INSIGHTS'],
            [f'Last updated: {timestamp}'],
            [insights_text],
        ])
```

Also add near the top of `sheets_writer.py`, after the imports:

```python
from src.categorizer import CATEGORIES as CATEGORIES_LIST
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_sheets_writer.py -v
```
Expected: 4 tests PASS.

**Step 5: Commit**

```bash
git add src/sheets_writer.py tests/test_sheets_writer.py
git commit -m "feat: add dashboard summary data writer with pivot tables"
```

---

## Task 6: Claude Insights Generator

**Files:**
- Create: `src/insights.py`
- Create: `tests/test_insights.py`

**Step 1: Write the failing test**

```python
# tests/test_insights.py
import pytest
from unittest.mock import MagicMock, patch
from src.insights import generate_insights

ALL_TRANSACTIONS = [
    {'period': '2026-02', 'claude_category': 'Dining & Restaurants', 'amount': 45.00, 'merchant': 'Shake Shack', 'date': '2026-02-10'},
    {'period': '2026-03', 'claude_category': 'Dining & Restaurants', 'amount': 350.00, 'merchant': 'Various', 'date': '2026-03-01'},
    {'period': '2026-03', 'claude_category': 'Groceries', 'amount': 95.00, 'merchant': 'Trader Joes', 'date': '2026-03-05'},
]


@patch('src.insights.Anthropic')
def test_generate_insights_returns_string(mock_anthropic_class, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test_key')

    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="⚠️ Dining is 677% above average this month.")]
    mock_client.messages.create.return_value = mock_message

    result = generate_insights(ALL_TRANSACTIONS)

    assert isinstance(result, str)
    assert len(result) > 0
    mock_client.messages.create.assert_called_once()


@patch('src.insights.Anthropic')
def test_generate_insights_passes_full_history(mock_anthropic_class, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test_key')

    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="Analysis here")]
    mock_client.messages.create.return_value = mock_message

    generate_insights(ALL_TRANSACTIONS)

    prompt_used = mock_client.messages.create.call_args[1]['messages'][0]['content']
    # Verify full history context is included
    assert '2026-02' in prompt_used
    assert '2026-03' in prompt_used
    assert 'Dining & Restaurants' in prompt_used
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_insights.py -v
```
Expected: `ImportError`.

**Step 3: Write the implementation**

```python
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
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_insights.py -v
```
Expected: 2 tests PASS.

**Step 5: Commit**

```bash
git add src/insights.py tests/test_insights.py
git commit -m "feat: add Claude insights generator with historical trend analysis"
```

---

## Task 7: Main Orchestrator

**Files:**
- Create: `src/main.py`
- Create: `tests/test_main.py`

**Step 1: Write the failing test**

```python
# tests/test_main.py
import pytest
from unittest.mock import patch, MagicMock
from src.main import run, validate_env


def test_validate_env_raises_on_missing_var(monkeypatch):
    for var in ['PLAID_CLIENT_ID', 'PLAID_SECRET', 'PLAID_ACCESS_TOKEN',
                'ANTHROPIC_API_KEY', 'GOOGLE_SERVICE_ACCOUNT_JSON', 'GOOGLE_SPREADSHEET_ID']:
        monkeypatch.delenv(var, raising=False)

    with pytest.raises(EnvironmentError) as exc_info:
        validate_env()
    assert 'PLAID_CLIENT_ID' in str(exc_info.value)


@patch('src.main.fetch_transactions')
@patch('src.main.categorize_transactions')
@patch('src.main.append_transactions')
@patch('src.main.generate_insights')
@patch('src.main.update_dashboard_data')
def test_run_orchestrates_pipeline(
    mock_dashboard, mock_insights, mock_append,
    mock_categorize, mock_fetch, monkeypatch
):
    for var, val in [
        ('PLAID_CLIENT_ID', 'x'), ('PLAID_SECRET', 'x'), ('PLAID_ACCESS_TOKEN', 'x'),
        ('ANTHROPIC_API_KEY', 'x'), ('GOOGLE_SERVICE_ACCOUNT_JSON', 'dGVzdA=='),
        ('GOOGLE_SPREADSHEET_ID', 'sheet123'),
    ]:
        monkeypatch.setenv(var, val)

    mock_fetch.return_value = [{'transaction_id': 'txn_1', 'amount': 10.0}]
    mock_categorize.return_value = [{'transaction_id': 'txn_1', 'amount': 10.0, 'period': '2026-03'}]
    mock_append.return_value = 1
    mock_insights.return_value = "Great job this month!"

    run()

    mock_fetch.assert_called_once()
    mock_categorize.assert_called_once()
    mock_append.assert_called_once()
    mock_insights.assert_called_once()
    mock_dashboard.assert_called_once()
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_main.py -v
```
Expected: `ImportError`.

**Step 3: Write the implementation**

```python
# src/main.py
import os
import sys
from dotenv import load_dotenv

from src.plaid_client import fetch_transactions
from src.categorizer import categorize_transactions
from src.sheets_writer import append_transactions, update_dashboard_data, TRANSACTION_HEADERS
from src.insights import generate_insights

REQUIRED_ENV_VARS = [
    'PLAID_CLIENT_ID',
    'PLAID_SECRET',
    'PLAID_ACCESS_TOKEN',
    'ANTHROPIC_API_KEY',
    'GOOGLE_SERVICE_ACCOUNT_JSON',
    'GOOGLE_SPREADSHEET_ID',
]


def validate_env() -> None:
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            f"See .env.example for the full list of required variables."
        )


def run() -> None:
    load_dotenv()
    validate_env()

    spreadsheet_id = os.environ['GOOGLE_SPREADSHEET_ID']

    print("Fetching transactions from Plaid...")
    transactions = fetch_transactions(days_back=16)
    print(f"  Fetched {len(transactions)} transactions.")

    if not transactions:
        print("No new transactions found. Exiting.")
        return

    print("Categorizing transactions with Claude...")
    categorized = categorize_transactions(transactions)
    print(f"  Categorized {len(categorized)} transactions.")

    print("Appending new transactions to Google Sheet...")
    new_count = append_transactions(categorized, spreadsheet_id)
    print(f"  Wrote {new_count} new transactions ({len(categorized) - new_count} already existed).")

    print("Generating Claude insights from full transaction history...")
    # Re-read all transactions from sheet for full historical context
    import gspread, base64, json as _json
    from google.oauth2.service_account import Credentials
    from src.sheets_writer import SCOPES, _get_or_create_worksheet
    creds_dict = _json.loads(base64.b64decode(os.environ['GOOGLE_SERVICE_ACCOUNT_JSON']).decode())
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(spreadsheet_id)
    ws = _get_or_create_worksheet(spreadsheet, 'Transactions')
    all_records = ws.get_all_records()

    insights = generate_insights(all_records)
    print("  Insights generated.")

    print("Updating Dashboard tab...")
    update_dashboard_data(all_records, spreadsheet_id, insights_text=insights)
    print("  Dashboard updated.")

    print(f"\nDone. {new_count} new transactions added, dashboard refreshed.")


if __name__ == '__main__':
    try:
        run()
    except EnvironmentError as e:
        print(f"Configuration error:\n{e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        raise
```

**Step 4: Run all tests**

```bash
pytest -v
```
Expected: All tests PASS.

**Step 5: Commit**

```bash
git add src/main.py tests/test_main.py
git commit -m "feat: add main orchestrator with env validation and pipeline coordination"
```

---

## Task 8: Categorizer Retry on Failure

**Files:**
- Modify: `src/categorizer.py` — wrap Claude call with one retry; fall back to `Uncategorized`
- Modify: `tests/test_categorizer.py` — add retry test

**Step 1: Write the failing test** (add to `tests/test_categorizer.py`)

```python
@patch('src.categorizer.Anthropic')
def test_categorize_transactions_falls_back_on_failure(mock_anthropic_class, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test_key')

    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client
    mock_client.messages.create.side_effect = Exception("API unavailable")

    result = categorize_transactions(SAMPLE_TRANSACTIONS)

    assert len(result) == 2
    assert all(r['claude_category'] == 'Uncategorized' for r in result)
    assert all('API error' in r['claude_reasoning'] for r in result)
    assert mock_client.messages.create.call_count == 2  # tried twice
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_categorizer.py::test_categorize_transactions_falls_back_on_failure -v
```
Expected: FAIL — no retry logic yet.

**Step 3: Wrap the Claude call in `src/categorizer.py` with retry**

Replace the `client.messages.create(...)` call and JSON parsing block with:

```python
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
                    "claude_category": results_by_index[i + 1]["category"],
                    "claude_reasoning": results_by_index[i + 1]["reasoning"],
                    "period": t["date"][:7],
                }
                for i, t in enumerate(transactions)
            ]
        except Exception as e:
            last_error = e
            continue

    # Both attempts failed — return transactions with Uncategorized
    return [
        {
            **t,
            "claude_category": "Uncategorized",
            "claude_reasoning": f"API error after 2 attempts: {last_error}",
            "period": t["date"][:7],
        }
        for t in transactions
    ]
```

**Step 4: Run all tests**

```bash
pytest -v
```
Expected: All tests PASS.

**Step 5: Commit**

```bash
git add src/categorizer.py tests/test_categorizer.py
git commit -m "feat: add retry logic with graceful fallback to Uncategorized"
```

---

## Task 9: GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/tracker.yml`

**Note:** No automated tests for the workflow itself — verify manually by triggering it once.

**Step 1: Create the workflow file**

```yaml
# .github/workflows/tracker.yml
name: Expense Tracker

on:
  schedule:
    # Runs at 9:00 AM UTC on the 1st and 15th of every month
    - cron: '0 9 1,15 * *'
  workflow_dispatch:  # Allow manual trigger from GitHub UI for testing

jobs:
  run-tracker:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run expense tracker
        env:
          PLAID_CLIENT_ID: ${{ secrets.PLAID_CLIENT_ID }}
          PLAID_SECRET: ${{ secrets.PLAID_SECRET }}
          PLAID_ACCESS_TOKEN: ${{ secrets.PLAID_ACCESS_TOKEN }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GOOGLE_SERVICE_ACCOUNT_JSON: ${{ secrets.GOOGLE_SERVICE_ACCOUNT_JSON }}
          GOOGLE_SPREADSHEET_ID: ${{ secrets.GOOGLE_SPREADSHEET_ID }}
        run: python -m src.main
```

**Step 2: Push to GitHub**

```bash
git add .github/workflows/tracker.yml
git commit -m "feat: add GitHub Actions workflow for twice-monthly scheduling"
git remote add origin https://github.com/YOUR_USERNAME/expense-tracker.git
git push -u origin main
```

**Step 3: Verify workflow appears**

In your GitHub repo → Actions tab → you should see "Expense Tracker" listed.

**Step 4: Trigger a manual test run**

Click "Run workflow" in the Actions tab → confirm it completes without errors.

---

## Task 10: One-Time Chart Setup Script

**Files:**
- Create: `scripts/setup_charts.py`

**Note:** Run this script once after the first successful tracker run to create charts in the Dashboard tab. Charts auto-refresh when data changes on subsequent runs.

**Step 1: Create the script**

```python
# scripts/setup_charts.py
"""
Run once after first successful tracker run to add charts to the Dashboard tab.
Charts will auto-update on every subsequent tracker run.

Usage:
    python scripts/setup_charts.py
"""
import os
import base64
import json
from dotenv import load_dotenv
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']


def get_service():
    creds_dict = json.loads(base64.b64decode(os.environ['GOOGLE_SERVICE_ACCOUNT_JSON']).decode())
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds)


def get_sheet_id(service, spreadsheet_id: str, sheet_name: str) -> int:
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for sheet in meta['sheets']:
        if sheet['properties']['title'] == sheet_name:
            return sheet['properties']['sheetId']
    raise ValueError(f"Sheet '{sheet_name}' not found")


def add_charts(spreadsheet_id: str):
    service = get_service()
    dashboard_id = get_sheet_id(service, spreadsheet_id, 'Dashboard')

    # Chart positions are relative to Dashboard tab data layout from sheets_writer.py
    # Row 1: title, Row 2: header, Rows 3+: category data (up to ~12 rows)
    # Adjust sourceRange row indices if your data grows significantly

    requests = [
        # Chart 1: Stacked bar — Monthly spend by category (data starts at A2)
        {
            "addChart": {
                "chart": {
                    "spec": {
                        "title": "Monthly Spend by Category",
                        "basicChart": {
                            "chartType": "BAR",
                            "stackedType": "STACKED",
                            "legendPosition": "RIGHT_LEGEND",
                            "domains": [{"domain": {"sourceRange": {"sources": [{"sheetId": dashboard_id, "startRowIndex": 2, "endRowIndex": 13, "startColumnIndex": 0, "endColumnIndex": 1}]}}}],
                            "series": []  # populated dynamically from columns
                        }
                    },
                    "position": {"overlayPosition": {"anchorCell": {"sheetId": dashboard_id, "rowIndex": 0, "columnIndex": 10}, "widthPixels": 600, "heightPixels": 400}}
                }
            }
        }
    ]

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": requests}
    ).execute()
    print("Charts added to Dashboard tab.")


if __name__ == '__main__':
    spreadsheet_id = os.environ['GOOGLE_SPREADSHEET_ID']
    add_charts(spreadsheet_id)
```

Also add to `requirements.txt`:
```
google-api-python-client>=2.120.0
```

**Step 2: Commit**

```bash
git add scripts/setup_charts.py requirements.txt
git commit -m "feat: add one-time chart setup script for Dashboard tab"
```

---

## Final Checklist

- [ ] All 6 prerequisite setup steps completed (Plaid account, Google Sheet, service account, GitHub secrets)
- [ ] `pytest -v` passes all tests locally
- [ ] GitHub Actions workflow triggers successfully via manual dispatch
- [ ] Google Sheet shows Transactions tab with data after first run
- [ ] Dashboard tab has summary tables after first run
- [ ] `scripts/setup_charts.py` run once to add charts
- [ ] Claude Insights section appears at bottom of Dashboard tab
