import cloudscraper
scraper = cloudscraper.create_scraper()
url = 'https://www.investing.com/economic-calendar/Service/getCalendarFilteredData'
data = {'country[]': [5], 'timeZone': 8, 'lang': 1}
headers = {'X-Requested-With': 'XMLHttpRequest', 'Referer': 'https://www.investing.com/economic-calendar/'}
response = scraper.post(url, data=data, headers=headers)
print(f'Status: {response.status_code}')
if 'data' in response.json():
    print('Data found!')
    print(response.json()['data'][:200])