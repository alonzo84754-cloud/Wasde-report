import requests
from bs4 import BeautifulSoup
url = 'https://www.marketwatch.com/economy-politics/calendar'
headers = {'User-Agent': 'Mozilla/5.0'}
response = requests.get(url, headers=headers)
print(f'Status: {response.status_code}')
if response.status_code == 200:
    print('MarketWatch is 200!')