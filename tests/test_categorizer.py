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
