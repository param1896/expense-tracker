# src/teller_client.py
import os
import base64
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Dict

import requests

TELLER_API = "https://api.teller.io"


def _write_temp_file(content: str) -> str:
    """Write content to a temp file and return the path."""
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False)
    f.write(content)
    f.flush()
    f.close()
    return f.name


def get_teller_session() -> requests.Session:
    cert_pem = base64.b64decode(os.environ['TELLER_CERT']).decode()
    key_pem = base64.b64decode(os.environ['TELLER_KEY']).decode()

    cert_path = _write_temp_file(cert_pem)
    key_path = _write_temp_file(key_pem)

    session = requests.Session()
    session.cert = (cert_path, key_path)
    session.auth = (os.environ['TELLER_ACCESS_TOKEN'], '')
    session.headers.update({'Teller-Version': '2020-10-12'})
    return session


def fetch_transactions(days_back: int = 16) -> List[Dict]:
    session = get_teller_session()
    start_date = (date.today() - timedelta(days=days_back)).isoformat()

    # Get all accounts, filter for credit cards
    accounts_resp = session.get(f"{TELLER_API}/accounts")
    accounts_resp.raise_for_status()
    all_accounts = accounts_resp.json()
    accounts = [
        a for a in all_accounts
        if a.get('type') == 'credit' and a.get('subtype') == 'credit_card'
    ]

    if not accounts:
        account_summary = [
            f"{a.get('id')}: {a.get('institution', {}).get('name', '?')} {a.get('type')}/{a.get('subtype')}"
            for a in all_accounts
        ]
        raise RuntimeError(
            f"No credit card accounts found. Accounts returned by Teller: {account_summary}. "
            "Check that TELLER_ACCESS_TOKEN is enrolled against your Amex credit card."
        )

    all_transactions = []
    for account in accounts:
        account_id = account['id']
        params = {'start_date': start_date}
        page_from = None

        while True:
            if page_from:
                params['from_id'] = page_from
            resp = session.get(
                f"{TELLER_API}/accounts/{account_id}/transactions",
                params=params,
            )
            resp.raise_for_status()
            page = resp.json()
            if not page:
                break
            all_transactions.extend(page)
            if len(page) < 250:
                break
            page_from = page[-1]['id']  # paginate backward

    return [
        {
            'transaction_id': t['id'],
            'date': t['date'],
            'merchant': (
                (t.get('details') or {}).get('counterparty') or {}
            ).get('name') or t.get('description', 'Unknown'),
            'amount': float(Decimal(t['amount'])),
            'plaid_category': (t.get('details') or {}).get('category') or 'Unknown',
        }
        for t in all_transactions
        if t.get('status') == 'posted'
    ]
