import requests
from bs4 import BeautifulSoup

url = 'https://finance.yahoo.com/calendar/economic'
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}
try:
    response = requests.get(url, headers=headers, timeout=10)
    print(f'Status: {response.status_code}')
    soup = BeautifulSoup(response.text, 'html.parser')
    # Yahoo usually uses tables for this
    table = soup.find('table')
    if table:
        rows = table.find_all('tr')
        print(f'Found {len(rows)} rows in table')
    else:
        print('No table found')
except Exception as e:
    print(f'Error: {e}')