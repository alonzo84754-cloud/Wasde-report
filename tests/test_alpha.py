import requests
url = 'https://www.alphavantage.co/query?function=ECONOMIC_CALENDAR&apikey=demo'
response = requests.get(url)
print(f'Status: {response.status_code}')
print(response.text[:500])