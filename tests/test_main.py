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
@patch('src.main.read_all_transactions')
@patch('src.main.generate_insights')
@patch('src.main.update_dashboard_data')
def test_run_orchestrates_pipeline(
    mock_dashboard, mock_insights, mock_read_all,
    mock_append, mock_categorize, mock_fetch, monkeypatch
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
    mock_read_all.return_value = [
        {'transaction_id': 'txn_1', 'amount': 10.0, 'period': '2026-03'},
        {'transaction_id': 'txn_old', 'amount': 50.0, 'period': '2026-02'},
    ]
    mock_insights.return_value = "Great job this month!"

    run()

    mock_fetch.assert_called_once()
    mock_categorize.assert_called_once()
    mock_append.assert_called_once()
    mock_read_all.assert_called_once()
    mock_insights.assert_called_once()
    mock_dashboard.assert_called_once()
    # Verify full history is passed (not just current batch)
    insights_arg = mock_insights.call_args[0][0]
    assert len(insights_arg) == 2  # full history, not just 1 current transaction
