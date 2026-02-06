import pandas as pd
import requests
url = 'https://finance.yahoo.com/calendar/economic'
headers = {'User-Agent': 'Mozilla/5.0'}
response = requests.get(url, headers=headers)
tables = pd.read_html(response.text)
print(f'Found {len(tables)} tables')
if tables:
    print(tables[0].head())