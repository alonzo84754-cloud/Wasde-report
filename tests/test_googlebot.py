import requests
url = 'https://www.investing.com/economic-calendar/'
headers = {'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'}
response = requests.get(url, headers=headers)
print(f'Status: {response.status_code}')
print(f'Content length: {len(response.text)}')
if 'js-event-item' in response.text:
    print('Found event items in HTML!')