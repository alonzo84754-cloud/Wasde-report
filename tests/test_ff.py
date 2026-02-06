import requests
url = 'https://nfs.faireconomy.media/ff_calendar_thisweek.json'
response = requests.get(url)
print(f'Status: {response.status_code}')
if response.status_code == 200:
    data = response.json()
    print(f'Found {len(data)} events')
    for item in data[:5]:
        print(item)