import requests
from bs4 import BeautifulSoup
url = 'https://www.investing-widgets.com/economic-calendar?theme=darkTheme&roundedCorners=true&countries=5&importance=2,3'
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}
response = requests.get(url, headers=headers)
print(f'Status: {response.status_code}')
soup = BeautifulSoup(response.text, 'html.parser')
items = soup.find_all('tr', class_='js-event-item')
print(f'Found {len(items)} items')
for item in items[:5]:
    time = item.find('td', class_='time').text.strip()
    event = item.find('td', class_='event').text.strip()
    actual = item.find('td', class_='actual').text.strip()
    forecast = item.find('td', class_='forecast').text.strip()
    print(f'{time} | {event} | {actual} | {forecast}')