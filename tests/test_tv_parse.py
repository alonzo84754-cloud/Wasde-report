import requests
from bs4 import BeautifulSoup
url = 'https://www.tradingview.com/markets/currencies/economic-calendar/'
headers = {'User-Agent': 'Mozilla/5.0'}
response = requests.get(url, headers=headers)
if 'calendar-item' in response.text:
    print('Found calendar items!')
else:
    print('No items found, checking script tags')
    import re
    match = re.search(r'"events":(\[.*?\])', response.text)
    if match:
        print('Found events JSON!')
