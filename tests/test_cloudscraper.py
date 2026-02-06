import cloudscraper
scraper = cloudscraper.create_scraper()
response = scraper.get('https://www.investing.com/economic-calendar/')
print(f'Status: {response.status_code}')
if 'js-event-item' in response.text:
    print('Found it with cloudscraper!')