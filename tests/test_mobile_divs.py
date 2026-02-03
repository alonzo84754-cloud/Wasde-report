import requests
from bs4 import BeautifulSoup
url = 'https://m.investing.com/economic-calendar/'
headers = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1'
}
response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.text, 'html.parser')
# Find all divs with 'event' in their class name
events = soup.find_all('div', class_=lambda x: x and 'event' in x.lower())
print(f'Found {len(events)} event-related divs')
if events:
    print(events[0].get_text(separator=' | '))