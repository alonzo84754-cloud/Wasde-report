import requests
url = 'https://www.investing.com/economic-calendar/'
headers = {'User-Agent': 'AppleTV11,1/11.1'}
response = requests.get(url, headers=headers)
print(f'Status: {response.status_code}')
if 'js-event-item' in response.text:
    print('Found it!')