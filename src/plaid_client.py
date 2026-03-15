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
