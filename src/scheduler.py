import time
import schedule
import subprocess
from datetime import datetime
import os
import sys

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))
from market_analysis import WASDE_DATES

def run_full_pipeline():
    print(f"[{datetime.now()}] Running full WASDE pipeline...")
    subprocess.run(["make", "run-all"], check=True)

def daily_check():
    now = datetime.now()
    year = now.year
    month = now.month
    today_str = now.strftime('%Y-%m-%d')
    
    # Check if today is a WASDE release day
    if year in WASDE_DATES and month in WASDE_DATES[year]:
        release_date = WASDE_DATES[year][month]
        if today_str == release_date:
            print(f"[{datetime.now()}] WASDE Release Day Detected! Scheduling run at 12:05 PM.")
            # Run slightly after 12:00 PM to ensure report is published
            schedule.every().day.at("12:05").do(run_full_pipeline).tag('wasde-run')

def start_scheduler():
    print("WASDE Scheduler Started...")
    # Check for release day every morning at 8:00 AM
    schedule.every().day.at("08:00").do(daily_check)
    
    # Initial check upon startup
    daily_check()
    
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    start_scheduler()
