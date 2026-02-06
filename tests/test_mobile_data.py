import requests
from bs4 import BeautifulSoup
url = 'https://m.investing.com/economic-calendar/'
headers = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1'
}
response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.text, 'html.parser')
# Look for any script tags containing data
for script in soup.find_all('script'):
    if 'JSON.parse' in script.text or 'window.__' in script.text:
        print(f'Found data script: {script.text[:200]}...')
