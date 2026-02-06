import requests
from bs4 import BeautifulSoup

url = 'https://www.investing.com/economic-calendar/'
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'X-Requested-With': 'XMLHttpRequest'
}
try:
    response = requests.get(url, headers=headers, timeout=10)
    print(f'Status: {response.status_code}')
    print(f'Content length: {len(response.text)}')
    soup = BeautifulSoup(response.text, 'html.parser')
    events = soup.find_all('tr', {'class': 'js-event-item'})
    print(f'Found {len(events)} events')
except Exception as e:
    print(f'Error: {e}')