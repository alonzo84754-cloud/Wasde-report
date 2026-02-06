import requests
url = 'https://www.investing.com/economic-calendar/Service/getCalendarFilteredData'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': 'https://www.investing.com/economic-calendar/',
    'Content-Type': 'application/x-www-form-urlencoded'
}
data = {
    'country[]': [5],
    'timeZone': 8,
    'lang': 1
}
response = requests.post(url, headers=headers, data=data)
if 'data' in response.json():
    print(response.json()['data'])