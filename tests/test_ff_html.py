import requests
from bs4 import BeautifulSoup
url = 'https://www.forexfactory.com/calendar?day=jan26.2026'
headers = {'User-Agent': 'Mozilla/5.0'}
response = requests.get(url, headers=headers)
print(f'Status: {response.status_code}')
soup = BeautifulSoup(response.text, 'html.parser')
events = soup.find_all('tr', class_='calendar__row')
print(f'Found {len(events)} events')
for event in events[:10]:
    title = event.find('td', class_='calendar__event')
    if title:
        actual = event.find('td', class_='calendar__actual')
        forecast = event.find('td', class_='calendar__forecast')
        print(f'{title.text.strip()} | A: {actual.text.strip()} | F: {forecast.text.strip()}')