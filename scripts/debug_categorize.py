"""Debug script: reads first 10 transactions from sheet and runs categorizer."""
import os
import base64
import json

import gspread
from google.oauth2.service_account import Credentials

from src.categorizer import categorize_transactions

creds_json = base64.b64decode(os.environ['GOOGLE_SERVICE_ACCOUNT_JSON']).decode()
creds_dict = json.loads(creds_json)
creds = Credentials.from_service_account_info(creds_dict, scopes=[
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
])
gc = gspread.authorize(creds)
spreadsheet = gc.open_by_key(os.environ['GOOGLE_SPREADSHEET_ID'])
ws = spreadsheet.worksheet('Transactions')
all_values = ws.get_all_values()
headers = all_values[0]
print('Headers:', headers)
print('Total rows:', len(all_values) - 1)

sample = all_values[1:11]
txns = [{headers[i]: (row[i] if i < len(row) else '') for i in range(len(headers))} for row in sample]
print()
print('Sample transactions:')
for t in txns:
    print(f"  {t['date']} | {t['merchant']} | {t['amount']} | category={repr(t['claude_category'])}")

print()
print('Running categorizer on first 10...')
results = categorize_transactions(txns)
print()
print('Results:')
for r in results:
    print(f"  {r['merchant']} -> {r['claude_category']} | {r['claude_reasoning'][:80]}")
