import requests
url = 'https://api.investing.com/api/financialdata/events/calendar'
params = {
    'importance': '2,3',
    'countries': '5',
    'time_zone': 'UTC',
    'lang_id': '1'
}
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'application/json'
}
response = requests.get(url, params=params, headers=headers)
print(f'Status: {response.status_code}')
if response.status_code == 200:
    print(response.json())
else:
    print(response.text[:200])