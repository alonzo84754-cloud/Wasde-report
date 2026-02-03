import requests
url = 'https://query1.finance.yahoo.com/v1/finance/calendar/economic'
response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
print(f'Status: {response.status_code}')
if response.status_code == 200:
    print(response.json())