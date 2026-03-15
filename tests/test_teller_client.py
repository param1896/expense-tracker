# tests/test_teller_client.py
import base64
import json
import pytest
from unittest.mock import MagicMock, patch
from src.teller_client import fetch_transactions

SAMPLE_ACCOUNTS = [
    {'id': 'acc_1', 'type': 'credit', 'subtype': 'credit_card', 'last_four': '1001'},
]

SAMPLE_TRANSACTIONS = [
    {
        'id': 'txn_1',
        'date': '2026-03-01',
        'amount': '14.50',
        'description': 'SWEETGREEN',
        'status': 'posted',
        'details': {
            'category': 'dining',
            'counterparty': {'name': 'Sweetgreen', 'type': 'organization'},
        },
    },
    {
        'id': 'txn_2',
        'date': '2026-03-02',
        'amount': '15.99',
        'description': 'NETFLIX',
        'status': 'pending',  # should be skipped
        'details': {'category': 'entertainment', 'counterparty': {'name': 'Netflix'}},
    },
]


@patch('src.teller_client.requests.Session')
def test_fetch_transactions_returns_normalized_list(mock_session_class, monkeypatch):
    monkeypatch.setenv('TELLER_CERT', base64.b64encode(b'cert').decode())
    monkeypatch.setenv('TELLER_KEY', base64.b64encode(b'key').decode())
    monkeypatch.setenv('TELLER_ACCESS_TOKEN', 'token_test')

    mock_session = MagicMock()
    mock_session_class.return_value = mock_session

    accounts_resp = MagicMock()
    accounts_resp.json.return_value = SAMPLE_ACCOUNTS
    txns_resp = MagicMock()
    txns_resp.json.return_value = SAMPLE_TRANSACTIONS

    mock_session.get.side_effect = [accounts_resp, txns_resp]

    result = fetch_transactions(days_back=16)

    assert len(result) == 1  # pending filtered out
    assert result[0]['transaction_id'] == 'txn_1'
    assert result[0]['merchant'] == 'Sweetgreen'
    assert result[0]['amount'] == 14.50
    assert result[0]['date'] == '2026-03-01'
    assert result[0]['plaid_category'] == 'dining'


@patch('src.teller_client.requests.Session')
def test_fetch_transactions_skips_pending(mock_session_class, monkeypatch):
    monkeypatch.setenv('TELLER_CERT', base64.b64encode(b'cert').decode())
    monkeypatch.setenv('TELLER_KEY', base64.b64encode(b'key').decode())
    monkeypatch.setenv('TELLER_ACCESS_TOKEN', 'token_test')

    mock_session = MagicMock()
    mock_session_class.return_value = mock_session

    accounts_resp = MagicMock()
    accounts_resp.json.return_value = SAMPLE_ACCOUNTS
    all_pending = [dict(t, status='pending') for t in SAMPLE_TRANSACTIONS]
    txns_resp = MagicMock()
    txns_resp.json.return_value = all_pending
    mock_session.get.side_effect = [accounts_resp, txns_resp]

    result = fetch_transactions(days_back=16)
    assert result == []
