import cloudscraper
scraper = cloudscraper.create_scraper()
url = 'https://www.investing.com/economic-calendar/Service/getCalendarFilteredData'
data = {'dateFrom': '2026-01-01', 'dateTo': '2026-01-28', 'timeZone': 8, 'lang': 1}
headers = {'X-Requested-With': 'XMLHttpRequest', 'Referer': 'https://www.investing.com/economic-calendar/'}
response = scraper.post(url, data=data, headers=headers)
if 'data' in response.json():
    html = response.json()['data']
    print(f'HTML length: {len(html)}')
    if 'event' in html.lower():
        print('Found events in range!')
