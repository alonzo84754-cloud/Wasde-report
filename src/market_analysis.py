import pandas as pd
import numpy as np
import os
from datetime import datetime
from sqlalchemy.exc import OperationalError
from database_manager import load_from_db, replace_table_data
from tastytrade_client import get_historical_prices
from resilience import get_logger

logger = get_logger("market_analysis")

# WASDE Release Dates for 2026 (typically 12:00 PM ET)
WASDE_DATES = {
    2026: {
        1: "2026-01-12",
        2: "2026-02-10",
        3: "2026-03-10",
        4: "2026-04-09",
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


def fetch_price_data(ticker):
    """Fetch historical price data from Tastytrade."""
    days_back = (datetime.now() - datetime(2020, 1, 1)).days
    price_df = get_historical_prices(ticker, days_back=days_back)
    if price_df is not None and not price_df.empty:
        price_df = price_df.sort_values("Date")
        return price_df
    return None


def run_full_analysis():
    analyze_reactions()


def analyze_reactions():
    """Analyze relationship between WASDE surprises and 1-day market returns."""
    try:
        wasde_df = load_from_db("wasde_reports")
    except OperationalError as e:
        logger.error("Database error loading wasde_reports: %s", e)
        return
    except Exception as e:
        logger.error("Error loading wasde_reports: %s", e)
        return

    if wasde_df.empty:
        logger.warning("No WASDE reports found in database. Run wasde_parser.py first.")
        return

    wasde_df["report_date"] = pd.to_datetime(wasde_df["report_date"])
    logger.info("Loaded %d WASDE reports", len(wasde_df))

    commodities = {
        "cotton": "CT=F",
        "coffee": "KC=F",
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
    success_count = 0
    fail_count = 0

    for commodity, ticker in commodities.items():
        logger.info("Analyzing %s (%s)...", commodity, ticker)
        price_df = fetch_price_data(ticker)
        if price_df is None or price_df.empty:
            logger.warning("SKIPPED - no price data available for %s", ticker)
            fail_count += 1
            continue

        success_count += 1
        matched = 0

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
                    "price_before": prev_close,
                    "price_after": release_close
                }

                res["news_sentiment"] = "Bullish" if res["surprise"] < 0 else "Bearish" if res["surprise"] > 0 else "Neutral"
                res["news_failure"] = "NO"
                res["reason"] = "N/A"

                if res["news_sentiment"] == "Bullish" and res["return_1d"] < 0:
                    res["news_failure"] = "YES"
                    res["reason"] = "News Failure-Bearish"
                elif res["news_sentiment"] == "Bearish" and res["return_1d"] > 0:
                    res["news_failure"] = "YES"
                    res["reason"] = "News Failure-Bullish"

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
                matched += 1

        logger.info("  -> %d data points generated for %s", matched, commodity)

    logger.info("=== Summary ===")
    logger.info("Tickers fetched: %d/%d", success_count, len(commodities))
    logger.info("Tickers failed: %d/%d", fail_count, len(commodities))
    logger.info("Total data points: %d", len(report_results))

    if report_results:
        results_df = pd.DataFrame(report_results)
        replace_table_data(results_df, "market_reactions")
        logger.info("Saved %d rows to market_reactions table", len(results_df))
        failures = results_df[results_df["news_failure"] == "YES"]
        logger.info("News failures detected: %d", len(failures))
    else:
        logger.warning("No data points generated! Check TT credentials or Yahoo Finance connectivity.")


if __name__ == "__main__":
    analyze_reactions()
