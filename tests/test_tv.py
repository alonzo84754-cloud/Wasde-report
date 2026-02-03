import requests
from bs4 import BeautifulSoup
url = 'https://www.tradingview.com/markets/currencies/economic-calendar/'
headers = {'User-Agent': 'Mozilla/5.0'}
response = requests.get(url, headers=headers)
print(f'Status: {response.status_code}')