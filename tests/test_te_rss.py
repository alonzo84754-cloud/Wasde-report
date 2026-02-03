import requests
from bs4 import BeautifulSoup
url = 'https://tradingeconomics.com/rss/calendar.aspx'
response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
print(f'Status: {response.status_code}')
if response.status_code == 200:
    print(response.text[:1000])