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
