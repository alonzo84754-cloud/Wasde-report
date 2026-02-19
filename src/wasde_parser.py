import os
import pandas as pd
import re
from datetime import datetime
from database_manager import replace_table_data

# Actual WASDE release dates from USDA (report always at 12:00 PM ET)
# Sources: USDA official schedule, filenames from archive, news articles
WASDE_RELEASE_DATES = {
    (2020, 1): 10, (2020, 2): 11, (2020, 3): 10, (2020, 4): 9,
    (2020, 5): 12, (2020, 6): 11, (2020, 7): 10, (2020, 8): 12,
    (2020, 9): 11, (2020, 10): 9, (2020, 11): 10, (2020, 12): 10,
    (2021, 1): 12, (2021, 2): 9, (2021, 3): 9, (2021, 4): 9,
    (2021, 5): 12, (2021, 6): 10, (2021, 7): 12, (2021, 8): 12,
    (2021, 9): 10, (2021, 10): 12, (2021, 11): 9, (2021, 12): 9,
    (2022, 1): 12, (2022, 2): 9, (2022, 3): 9, (2022, 4): 8,
    (2022, 5): 12, (2022, 6): 10, (2022, 7): 12, (2022, 8): 12,
    (2022, 9): 12, (2022, 10): 12, (2022, 11): 9, (2022, 12): 9,
    (2023, 1): 12, (2023, 2): 8, (2023, 3): 8, (2023, 4): 11,
    (2023, 5): 12, (2023, 6): 9, (2023, 7): 12, (2023, 8): 11,
    (2023, 9): 12, (2023, 10): 12, (2023, 11): 9, (2023, 12): 8,
    (2024, 1): 12, (2024, 2): 8, (2024, 3): 8, (2024, 4): 11,
    (2024, 5): 10, (2024, 6): 12, (2024, 7): 12, (2024, 8): 12,
    (2024, 9): 12, (2024, 10): 11, (2024, 11): 8, (2024, 12): 10,
    (2025, 1): 10, (2025, 2): 11, (2025, 3): 11, (2025, 4): 10,
    (2025, 5): 12, (2025, 6): 12, (2025, 7): 11, (2025, 8): 12,
    (2025, 9): 12, (2025, 10): 9, (2025, 11): 10, (2025, 12): 9,
    (2026, 1): 12, (2026, 2): 10, (2026, 3): 10, (2026, 4): 9,
    (2026, 5): 12, (2026, 6): 11, (2026, 7): 10, (2026, 8): 12,
    (2026, 9): 11, (2026, 10): 9, (2026, 11): 10, (2026, 12): 10,
}


def _get_release_date(year, month, filename):
    """Get the actual WASDE release date for a given year/month.
    Priority: 1) old-format filename with exact date, 2) lookup table, 3) 1st of month fallback.
    """
    # Try old-format filename: wasde_mon_DD_YYYY.txt (e.g. wasde_jan_10_2020.txt)
    fn_match = re.search(r'wasde_([a-z]+)_(\d{2})_(\d{4})', filename)
    if fn_match:
        try:
            return datetime.strptime(f"{fn_match.group(1)} {fn_match.group(2)} {fn_match.group(3)}", "%b %d %Y")
        except ValueError:
            pass

    # Lookup table
    day = WASDE_RELEASE_DATES.get((year, month))
    if day:
        return datetime(year, month, day)

    # Fallback to 1st of month
    return datetime(year, month, 1)


def parse_wasde_txt(content, filename):
    # Determine month and year from the report content header
    date_match = re.search(r'([A-Za-z]+)\s+(20\d{2})', content)
    if not date_match:
        match = re.search(r'wasde(\d{2})(\d{2})', filename)
        if match:
            month_int, year_int = int(match.group(1)), int("20" + match.group(2))
        else:
            return None
    else:
        month_name, year_str = date_match.group(1), date_match.group(2)
        try:
            dt = datetime.strptime(f"{month_name} {year_str}", "%B %Y")
            month_int, year_int = dt.month, dt.year
        except ValueError:
            return None

    report_date = _get_release_date(year_int, month_int, filename)

    data = {
        'report_date': report_date.strftime('%Y-%m-%d'),
        'cotton_world_ending_stocks_proj_current': None, 'cotton_world_ending_stocks_proj_prev': None,
        'sugar_us_ending_stocks_proj_current': None, 'sugar_us_ending_stocks_proj_prev': None,
        'wheat_us_ending_stocks_proj_current': None, 'wheat_us_ending_stocks_proj_prev': None,
        'corn_us_ending_stocks_proj_current': None, 'corn_us_ending_stocks_proj_prev': None,
        'soybeans_us_ending_stocks_proj_current': None, 'soybeans_us_ending_stocks_proj_prev': None,
        'soybean meal_us_ending_stocks_proj_current': None, 'soybean meal_us_ending_stocks_proj_prev': None,
        'soybean oil_us_ending_stocks_proj_current': None, 'soybean oil_us_ending_stocks_proj_prev': None,
        'live cattle_us_ending_stocks_proj_current': None, 'live cattle_us_ending_stocks_proj_prev': None,
        'feeder cattle_us_ending_stocks_proj_current': None, 'feeder cattle_us_ending_stocks_proj_prev': None,
        'lean hogs_us_ending_stocks_proj_current': None, 'lean hogs_us_ending_stocks_proj_prev': None
    }

    # Cotton
    cotton_match = re.search(r'World and U.S. Supply and Use for Cotton.*?World(.*?)(?:United States|Foreign|====)', content, re.DOTALL | re.IGNORECASE)
    if cotton_match:
        lines = cotton_match.group(1).split('\n')
        found, vals = False, []
        for line in lines:
            if '(Proj.)' in line: found = True; continue
            if found and any(m in line for m in ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']):
                parts = line.split()
                if parts:
                    try: vals.append(float(parts[-1].replace(',', '')) if parts[-1].upper() != 'NA' else None)
                    except: continue
            if len(vals) == 2: break
        if len(vals) == 2: data['cotton_world_ending_stocks_proj_prev'], data['cotton_world_ending_stocks_proj_current'] = vals

    def find_stocks(pattern, row_label, prev_idx=-2, curr_idx=-1):
        m = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if m:
            start_pos = m.end()
            line_match = re.search(fr'{row_label}\s+(.*)', content[start_pos:], re.IGNORECASE)
            if line_match:
                parts = line_match.group(1).split('\n')[0].split()
                if len(parts) >= 2:
                    try: return float(parts[prev_idx].replace(',', '')), float(parts[curr_idx].replace(',', ''))
                    except: pass
        return None, None

    data['sugar_us_ending_stocks_proj_prev'], data['sugar_us_ending_stocks_proj_current'] = find_stocks(r'U.S. Sugar Supply and Use', 'Ending Stocks')
    data['wheat_us_ending_stocks_proj_prev'], data['wheat_us_ending_stocks_proj_current'] = find_stocks(r'U\.S\.\s*Wheat\s*Supply\s*and\s*Use', 'Ending Stocks')
    data['corn_us_ending_stocks_proj_prev'], data['corn_us_ending_stocks_proj_current'] = find_stocks(r'U\.S\.\s*Feed\s*Grain\s*and\s*Corn\s*Supply\s*and\s*Use.*?CORN', 'Ending Stocks')
    data['soybeans_us_ending_stocks_proj_prev'], data['soybeans_us_ending_stocks_proj_current'] = find_stocks(r'U\.S\.\s*Soybeans\s*and\s*Products\s*Supply\s*and\s*Use.*?SOYBEANS', 'Ending Stocks')
    data['soybean meal_us_ending_stocks_proj_prev'], data['soybean meal_us_ending_stocks_proj_current'] = find_stocks(r'U\.S\.\s*Soybeans\s*and\s*Products\s*Supply\s*and\s*Use.*?SOYBEAN MEAL', 'Ending Stocks')
    data['soybean oil_us_ending_stocks_proj_prev'], data['soybean oil_us_ending_stocks_proj_current'] = find_stocks(r'U\.S\.\s*Soybeans\s*and\s*Products\s*Supply\s*and\s*Use.*?SOYBEAN OIL', 'Ending Stocks')
    
    # Livestock proxies (Beef/Pork production)
    def find_meat_proj(commodity_keyword):
        # The production table shows current month proj and previous month proj on separate lines
        m = re.search(r'Million Pounds.*?Annual(.*?)U\.S\. Quarterly Prices', content, re.DOTALL | re.IGNORECASE)
        if m:
            lines = m.group(1).split('\n')
            prev_val = None
            curr_val = None
            for line in lines:
                parts = line.split()
                if len(parts) < 2: continue
                # Look for lines ending in Proj. like "OctProj." or "NovProj."
                label = parts[0]
                if 'Proj.' in label:
                    val = None
                    try:
                        if commodity_keyword == 'Beef' and len(parts) >= 2:
                            raw = parts[1].replace(',', '')
                            val = float(raw) if raw.upper() != 'NA' else None
                        elif commodity_keyword == 'Pork' and len(parts) >= 3:
                            raw = parts[2].replace(',', '')
                            val = float(raw) if raw.upper() != 'NA' else None
                    except:
                        val = None
                    
                    if val is not None:
                        # We assume the first Proj line found is the 'Previous' and the last is 'Current'
                        # Or more specifically, if we have two, the second one is newer.
                        if prev_val is None:
                            prev_val = val
                        else:
                            curr_val = val
            return prev_val, curr_val
        return None, None

    data['live cattle_us_ending_stocks_proj_prev'], data['live cattle_us_ending_stocks_proj_current'] = find_meat_proj('Beef')
    data['lean hogs_us_ending_stocks_proj_prev'], data['lean hogs_us_ending_stocks_proj_current'] = find_meat_proj('Pork')
    data['feeder cattle_us_ending_stocks_proj_prev'], data['feeder cattle_us_ending_stocks_proj_current'] = data['live cattle_us_ending_stocks_proj_prev'], data['live cattle_us_ending_stocks_proj_current']

    return data

def process_all_reports():
    from data_collection import download_wasde_reports
    # Match data_dir from data_collection
    data_dir = '/tmp/wasde' if os.getenv('VERCEL') else 'data/wasde'
    os.makedirs(data_dir, exist_ok=True)
    download_wasde_reports()
    results = []
    if os.path.exists(data_dir):
        for f in os.listdir(data_dir):
            if f.endswith('.txt'):
                with open(os.path.join(data_dir, f), 'r', encoding='utf-8', errors='ignore') as file:
                    parsed = parse_wasde_txt(file.read(), f)
                    if parsed: results.append(parsed)
    if results:
        df = pd.DataFrame(results).sort_values('report_date')
        replace_table_data(df, 'wasde_reports')

if __name__ == "__main__":
    process_all_reports()
