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
