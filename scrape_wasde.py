import requests
from bs4 import BeautifulSoup
import re

def get_wasde_links(page):
    url = f"https://esmis.nal.usda.gov/publication/world-agricultural-supply-and-demand-estimates?page={page}"
    response = requests.get(url)
    if response.status_code != 200:
        return []
    
    soup = BeautifulSoup(response.text, 'html.parser')
    results = []
    
    # Try finding rows in table
    table = soup.find('table') 
    if table:
        for row in table.find_all('tr'):
            cols = row.find_all('td')
            if len(cols) >= 2:
                date = cols[0].get_text(strip=True)
                links = cols[1].find_all('a', href=True)
                for l in links:
                    txt = l.get_text().upper()
                    if "TXT" in txt or "XML" in txt:
                         href = l['href']
                         if not href.startswith('http'):
                             href = "https://esmis.nal.usda.gov" + href
                         results.append((date, href))
    else:
        # Fallback to general search
        for l in soup.find_all('a', href=True):
            txt = l.get_text().upper()
            if "TXT" in txt or "XML" in txt:
                text = l.find_parent().get_text()
                date_match = re.search(r'([A-Z][a-z]{2})\s+(\d{1,2})\s+(202[456])', text)
                if date_match:
                    date_str = f"{date_match.group(1)} {date_match.group(2)} {date_match.group(3)}"
                    href = l['href']
                    if not href.startswith('http'):
                        href = "https://esmis.nal.usda.gov" + href
                    results.append((date_str, href))
    return results

all_links = []
for p in range(15): # More pages
    all_links.extend(get_wasde_links(p))

unique_results = {}
for d, h in all_links:
    if h not in unique_results.values():
        unique_results[d] = h

months = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6, "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}
sorted_dates = sorted(unique_results.keys(), key=lambda x: (int(x.split()[2]) if len(x.split())>2 else 0, months.get(x.split()[0], 0), int(x.split()[1]) if len(x.split())>1 else 0))

for d in sorted_dates:
    if "2024" in d or "2025" in d:
        print(f"{d}: {unique_results[d]}")
