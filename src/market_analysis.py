import pandas as pd
import numpy as np
import os
import yfinance as yf
from datetime import datetime
from database_manager import save_to_db, load_from_db, clear_table

# WASDE Release Dates for 2026 (typically 12:00 PM ET)
WASDE_DATES = {
    2026: {
        1: "2026-01-12",
        2: "2026-02-10",
        3: "2026-03-10",
        4: "2026-04-10",
        5: "2026-05-12",
        6: "2026-06-11",
        7: "2026-07-10",
        8: "2026-08-12",
        9: "2026-09-11",
        10: "2026-10-09",
        11: "2026-11-10",
        12: "2026-12-10"
    }
}

def run_full_analysis():
    analyze_reactions()

def analyze_reactions():
    """Analyze relationship between WASDE surprises and 1-day market returns."""
    try:
        wasde_df = load_from_db("wasde_reports")
    except Exception as e:
        print(f"Error loading wasde_reports: {e}")
        return
        
    wasde_df["report_date"] = pd.to_datetime(wasde_df["report_date"])
    
    commodities = {
        "cotton": "CT=F",
        "sugar": "SB=F",
        "wheat": "ZW=F",
        "corn": "ZC=F",
        "soybeans": "ZS=F",
        "soybean meal": "ZM=F",
        "soybean oil": "ZL=F",
        "live cattle": "LE=F",
        "feeder cattle": "GF=F",
        "lean hogs": "HE=F"
    }
    
    report_results = []

    for commodity, ticker in commodities.items():
        print(f"Analyzing {commodity} ({ticker})...")
        try:
            price_df = yf.download(ticker, start="2020-01-01", progress=False)
            if price_df.empty: continue
            price_df = price_df.reset_index()
            if isinstance(price_df.columns, pd.MultiIndex):
                price_df.columns = price_df.columns.get_level_values(0)
            price_df["Date"] = pd.to_datetime(price_df["Date"]).dt.tz_localize(None)
            price_df = price_df.sort_values("Date")
        except Exception as e:
            print(f"Error fetching {ticker}: {e}")
            continue
        
        for _, row in wasde_df.iterrows():
            release_date = row["report_date"]
            day_before = price_df[price_df["Date"] < release_date].tail(1)
            day_of = price_df[price_df["Date"] >= release_date].head(1)
            
            if not day_before.empty and not day_of.empty:
                prev_close = float(day_before["Close"].values[0])
                release_close = float(day_of["Close"].values[0])
                return_1d = (release_close - prev_close) / prev_close
                
                proj_col = f"{commodity}_us_ending_stocks_proj_prev"
                act_col = f"{commodity}_us_ending_stocks_proj_current"
                if commodity == "cotton":
                    proj_col = "cotton_world_ending_stocks_proj_prev"
                    act_col = "cotton_world_ending_stocks_proj_current"
                
                proj_val = row[proj_col] if proj_col in row else np.nan
                act_val = row[act_col] if act_col in row else np.nan
                
                if pd.isna(proj_val) or pd.isna(act_val): continue

                surprise = act_val - proj_val
                surprise_percent = (surprise / proj_val * 100) if proj_val != 0 else 0

                res = {
                    "commodity": commodity,
                    "release_date": release_date.strftime("%Y-%m-%d"),
                    "release_time": "12:00 PM",
                    "proj_val": proj_val,
                    "act_val": act_val,
                    "surprise": surprise,
                    "surprise_percent": surprise_percent,
                    "return_1d": return_1d,
                    "price_before": prev_close,
                    "price_after": release_close
                }
                
                res["news_sentiment"] = "Bullish" if res["surprise"] < 0 else "Bearish" if res["surprise"] > 0 else "Neutral"
                res["news_failure"] = "NO"
                res["reason"] = "N/A"
                
                # Check for failure
                # New Logic:
                # Good news (Bullish) > Price down = "News Failure-Bearish"
                # Bad news (Bearish) > Price up = "News Failure-Bullish"
                if res["news_sentiment"] == "Bullish" and res["return_1d"] < 0:
                    res["news_failure"] = "YES"
                    res["reason"] = "News Failure-Bearish"
                elif res["news_sentiment"] == "Bearish" and res["return_1d"] > 0:
                    res["news_failure"] = "YES"
                    res["reason"] = "News Failure-Bullish"

                # Generate Summary
                s_val = res["surprise"]
                s_pct = res["surprise_percent"]
                direction = "lower" if s_val < 0 else "higher" if s_val > 0 else "unchanged"
                if s_val == 0:
                    res["summary"] = f"{commodity.capitalize()} stocks were unchanged from last month."
                else:
                    res["summary"] = f"{commodity.capitalize()} stocks were projected {direction} by {abs(s_val):.2f} units ({s_pct:+.2f}%)."

                res["status"] = res["reason"] if res["news_failure"] == "YES" else "Expected Reaction"
                res["is_realtime"] = 0
                report_results.append(res)

    if report_results:
        results_df = pd.DataFrame(report_results)
        clear_table("market_reactions")
        save_to_db(results_df, "market_reactions", if_exists="replace")

if __name__ == "__main__":
    analyze_reactions()
