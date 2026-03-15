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


@patch('src.insights.Anthropic')
def test_generate_insights_returns_placeholder_for_empty_input(mock_anthropic_class):
    result = generate_insights([])
    assert 'No transaction data' in result
    mock_anthropic_class.return_value.messages.create.assert_not_called()
