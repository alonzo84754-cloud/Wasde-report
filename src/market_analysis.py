import pandas as pd
import numpy as np
import os
import yfinance as yf
from datetime import datetime
from database_manager import save_to_db, load_from_db, clear_table
from price_utils import normalize_yahoo_ohlc

# Noise thresholds to avoid false positives.
# `surprise_percent` is in percent units (e.g. 2.0 = 2%).
# `return_1d` is a fraction (e.g. 0.003 = 0.3%).
MIN_SURPRISE_PCT = float(os.getenv("MIN_SURPRISE_PCT", "2.0"))
MIN_MOVE = float(os.getenv("MIN_MOVE", "0.003"))

DEBUG_PRICE_WINDOWS = os.getenv("DEBUG_PRICE_WINDOWS", "").strip().lower() in {"1", "true", "yes", "y"}
INCLUDE_PRICE_DATES_IN_SUMMARY = os.getenv("INCLUDE_PRICE_DATES_IN_SUMMARY", "").strip().lower() in {"1", "true", "yes", "y"}

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
        
    wasde_df["report_date"] = pd.to_datetime(wasde_df["report_date"]).dt.date
    
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
            price_df = normalize_yahoo_ohlc(price_df)
            if price_df is None:
                print(f"  WARNING: Failed to normalize prices for {ticker}")
                continue
            price_df = price_df.sort_values("Date").drop_duplicates(subset=["Date"], keep="last")
        except Exception as e:
            print(f"Error fetching {ticker}: {e}")
            continue
        
        for _, row in wasde_df.iterrows():
            release_date = row["report_date"]
            trade_row = price_df.loc[price_df["Date"] >= release_date, ["Date", "Open", "Close"]].head(1)

            if trade_row.empty:
                if DEBUG_PRICE_WINDOWS:
                    min_date = price_df["Date"].min() if not price_df.empty else None
                    max_date = price_df["Date"].max() if not price_df.empty else None
                    print(
                        f"  Price window missing for {commodity} ({ticker}) | "
                        f"release_date={release_date} | price_range={min_date}..{max_date}"
                    )
                continue

            trade_date = trade_row["Date"].iloc[0]
            release_open = float(trade_row["Open"].iloc[0])
            release_close = float(trade_row["Close"].iloc[0])
            if release_open == 0:
                if DEBUG_PRICE_WINDOWS:
                    print(f"  Zero release_open for {commodity} ({ticker}) on {trade_date}")
                continue

            if DEBUG_PRICE_WINDOWS:
                print(
                    f"  Price window {commodity} ({ticker}): trade_date={trade_date} (event={release_date})"
                )

            # Canonical 1-day market return (Jeremy): % change from when news hits until market close.
            # With daily bars, we approximate the release price by same-day Open.
            return_1d = (release_close - release_open) / release_open

            proj_col = f"{commodity}_us_ending_stocks_proj_prev"
            act_col = f"{commodity}_us_ending_stocks_proj_current"
            if commodity == "cotton":
                proj_col = "cotton_world_ending_stocks_proj_prev"
                act_col = "cotton_world_ending_stocks_proj_current"

            proj_val = row[proj_col] if proj_col in row else np.nan
            act_val = row[act_col] if act_col in row else np.nan

            if pd.isna(proj_val) or pd.isna(act_val):
                continue

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
                "price_before": release_open,
                "price_after": release_close,
            }

            res["news_sentiment"] = (
                "Bullish" if res["surprise"] < 0 else "Bearish" if res["surprise"] > 0 else "Neutral"
            )
            res["news_failure"] = "NO"
            res["reason"] = "N/A"

            # Check for failure
            # Good news (Bullish) > Price down = "News Failure-Bearish"
            # Bad news (Bearish) > Price up = "News Failure-Bullish"
            # Guard against noise: require meaningful fundamental surprise AND meaningful price move.
            if abs(res["surprise_percent"]) < MIN_SURPRISE_PCT:
                res["reason"] = "Below surprise threshold"
            elif abs(res["return_1d"]) < MIN_MOVE:
                res["reason"] = "Below move threshold"
            else:
                # Jeremy's truth table:
                # - Good news (Bullish) + price lower => failure (bearish price reaction)
                # - Bad news (Bearish) + price higher => failure (bullish price reaction)
                if res["news_sentiment"] == "Bullish" and res["return_1d"] < -MIN_MOVE:
                    res["news_failure"] = "YES"
                    res["reason"] = "News Failure-Bearish"
                elif res["news_sentiment"] == "Bearish" and res["return_1d"] > MIN_MOVE:
                    res["news_failure"] = "YES"
                    res["reason"] = "News Failure-Bullish"

            # Generate Summary (always)
            s_val = res["surprise"]
            s_pct = res["surprise_percent"]
            direction = "lower" if s_val < 0 else "higher" if s_val > 0 else "unchanged"
            if s_val == 0:
                res["summary"] = f"{commodity.capitalize()} stocks were unchanged from last month."
            else:
                res["summary"] = (
                    f"{commodity.capitalize()} stocks were projected {direction} by {abs(s_val):.2f} units ({s_pct:+.2f}%)."
                )

            if INCLUDE_PRICE_DATES_IN_SUMMARY:
                res["summary"] += f" (Prices: {trade_date} open→close)"

            res["status"] = res["reason"] if res["news_failure"] == "YES" else "Expected Reaction"
            res["is_realtime"] = 0
            report_results.append(res)

    if report_results:
        results_df = pd.DataFrame(report_results)
        clear_table("market_reactions")
        save_to_db(results_df, "market_reactions", if_exists="replace")

if __name__ == "__main__":
    analyze_reactions()
