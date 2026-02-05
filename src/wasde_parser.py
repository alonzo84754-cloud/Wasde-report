import os
import re
from datetime import datetime, date

_MONTHS_FULL = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

_MONTHS_ABBR = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def _year_from_2digits(two_digit_year: int) -> int:
    # Treat 00-49 as 2000s; 50-99 as 1900s
    return two_digit_year + (2000 if two_digit_year < 50 else 1900)


def extract_release_date(filename: str, content: str) -> date:
    name = (filename or "").lower()

    for pat in [
        r"wasde[^0-9]*(\d{2})(\d{2})(\d{4})",
        r"(?<!\d)(\d{2})(\d{2})(\d{4})(?!\d)",
    ]:
        m = re.search(pat, name)
        if m:
            mm, dd, yyyy = map(int, m.groups())
            return datetime(yyyy, mm, dd).date()

    for pat in [
        r"wasde[^0-9]*(\d{2})(\d{2})(\d{2})",
        r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)",
    ]:
        m = re.search(pat, name)
        if m:
            mm, dd, yy = map(int, m.groups())
            yyyy = _year_from_2digits(yy)
            return datetime(yyyy, mm, dd).date()

    month_token = "|".join(sorted(set([*list(_MONTHS_FULL.keys()), *list(_MONTHS_ABBR.keys())]), key=len, reverse=True))
    # NOTE: Don't use \b here because '_' counts as a word character, so "_jul_" would not match.
    m = re.search(
        rf"(?<![a-z])({month_token})(?![a-z])[^0-9]*(\d{{1,2}})[^0-9]*(\d{{4}})(?!\d)",
        name,
        re.IGNORECASE,
    )
    if m:
        month_str, day_str, year_str = m.groups()
        month_key = month_str.lower().rstrip(".")
        month = _MONTHS_FULL.get(month_key) or _MONTHS_ABBR.get(month_key)
        if month is not None:
            return datetime(int(year_str), int(month), int(day_str)).date()

    header = "\n".join((content or "").splitlines()[:80])

    release_patterns = [
        r"For\s+release.*?\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:,)?\s+(\d{4})",
        r"Released.*?\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:,)?\s+(\d{4})",
    ]

    for pat in release_patterns:
        m = re.search(pat, header, re.IGNORECASE | re.DOTALL)
        if m:
            month, day, year = m.groups()
            return datetime(
                int(year),
                _MONTHS_FULL[month.lower()],
                int(day),
            ).date()

    raise ValueError(f"Could not determine WASDE release date for {filename}")

def parse_wasde_txt(content, filename):
    report_date = extract_release_date(filename, content)
    # Hard guard: WASDE reports should never be silently defaulted to the 1st.
    if report_date.day == 1:
        raise ValueError(f"Suspicious WASDE date (day=1): {report_date} in {filename}")

    if report_date.day == 8:
        print(f"WARNING: Suspicious WASDE date (day=8): {report_date} from {filename}")

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
    import pandas as pd
    from database_manager import save_to_db, clear_table
    from data_collection import download_wasde_reports
    # Match data_dir from data_collection
    data_dir = '/tmp/wasde' if os.getenv('VERCEL') else 'data/wasde'
    os.makedirs(data_dir, exist_ok=True)
    download_wasde_reports()
    results = []
    errors = []
    if os.path.exists(data_dir):
        for f in os.listdir(data_dir):
            if f.endswith('.txt'):
                with open(os.path.join(data_dir, f), 'r', encoding='utf-8', errors='ignore') as file:
                    try:
                        parsed = parse_wasde_txt(file.read(), f)
                        if parsed:
                            results.append(parsed)
                    except Exception as e:
                        errors.append((f, str(e)))
    if results:
        df = pd.DataFrame(results).sort_values('report_date')
        df = df.drop_duplicates(subset=['report_date'], keep='last')
        clear_table('wasde_reports')
        save_to_db(df, 'wasde_reports', if_exists='append')

    if errors:
        print("\nWASDE parsing errors (date extraction):")
        for fname, err in errors:
            print(f" - {fname}: {err}")

    if not results:
        raise RuntimeError("No WASDE reports were parsed successfully. Check the errors above.")

if __name__ == "__main__":
    process_all_reports()
