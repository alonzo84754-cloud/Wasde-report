import sqlite3
import pandas as pd
import os
from datetime import datetime

DB_PATH = 'data/wasde.db'

def get_latest_failures():
    if not os.path.exists(DB_PATH):
        return []
    
    conn = sqlite3.connect(DB_PATH)
    # Get last release date from reactions
    query_date = "SELECT MAX(release_date) FROM market_reactions"
    cursor = conn.cursor()
    cursor.execute(query_date)
    latest_date = cursor.fetchone()[0]
    
    if not latest_date:
        conn.close()
        return []
        
    # Get all results for that date
    query = """
    SELECT commodity, proj_val, act_val, surprise_percent, news_sentiment, news_failure, reason
    FROM market_reactions 
    WHERE release_date = ?
    """
    df = pd.read_sql_query(query, conn, params=(latest_date,))
    conn.close()
    return latest_date, df.to_dict(orient='records')

def print_dashboard():
    result = get_latest_failures()
    if not result:
        print("No analysis data found.")
        return
        
    latest_date, failures = result
    active_failures_count = sum(1 for f in failures if f['news_failure'] == 'YES')
    
    print("┌─────────────────────────────────────────────────────┐")
    print(f"│  WASDE TRADING PLATFORM                    [{latest_date}]   │")
    print("├─────────────────────────────────────────────────────┤")
    print(f"│                                                      │")
    print(f"│  ⚠️  ACTIVE NEWS FAILURES: {active_failures_count}                        │")
    print("│                                                      │")
    print("│  Note: PROJ/ACT = Ending Stocks (million bushels/tons)│")
    print("│  Lower stocks = Good News (Bullish)                 │")
    print("│  Higher stocks = Bad News (Bearish)                 │")
    print("│                                                      │")
    print("├─────────────────────────────────────────────────────┤")
    print("│  COMMODITY    │ PROJ │ ACT │ %DIFF │ NEWS │ FAILURE │")
    print("│  (Ending Stocks)                                     │")
    print("├─────────────────────────────────────────────────────┤")
    
    for f in failures:
        comm = f['commodity'].capitalize().ljust(13)
        proj = str(int(f['proj_val']) if pd.notna(f['proj_val']) else 'N/A').ljust(4)
        act = str(int(f['act_val']) if pd.notna(f['act_val']) else 'N/A').ljust(4)
        diff = f"{f['surprise_percent'] :+.1f}%".ljust(5)
        news = "GOOD" if f['news_sentiment'] == 'Bullish' else "BAD " if f['news_sentiment'] == 'Bearish' else "NEUT"
        fail_icon = "❌ YES" if f['news_failure'] == 'YES' else "✅ NO "
        
        print(f"│  {comm} │ {proj} │ {act} │ {diff} │ {news} │   {fail_icon} │")
        
        # Sub-note logic
        direction = "Lower" if f['proj_val'] > f['act_val'] else "Higher"
        sentiment = "Bullish" if news == "GOOD" else "Bearish" if news == "BAD " else "Neutral"
        
        if f['news_failure'] == 'YES':
            price_move = "fell" if sentiment == "Bullish" else "rose"
            print(f"│  ({proj.strip()}M→{act.strip()}M = {direction} = {sentiment}, but price {price_move})    │")
        else:
            price_move = "rose" if sentiment == "Bullish" else "fell"
            if sentiment != "Neutral":
                print(f"│  ({proj.strip()}M→{act.strip()}M = {direction} = {sentiment}, price {price_move})          │")

    print("└─────────────────────────────────────────────────────┘")

if __name__ == "__main__":
    print_dashboard()
