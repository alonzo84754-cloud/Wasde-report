import cloudscraper
scraper = cloudscraper.create_scraper()
response = scraper.get('https://www.investing.com/economic-calendar/')
print(response.text[:1000])
print('event_item' in response.text)