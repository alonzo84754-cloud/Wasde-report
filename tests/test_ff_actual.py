import requests
url = 'https://nfs.faireconomy.media/ff_calendar_thisweek.json'
response = requests.get(url)
if response.status_code == 200:
    data = response.json()
    for item in data:
        if item['title'] == 'Core Durable Goods Orders m/m':
            print(item)