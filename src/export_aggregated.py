import pandas as pd
import sqlite3
import os
from datetime import datetime

# Import helper from existing logic
from market_analysis import get_precise_date

def export_master_csv():
    """Joins wasde metrics with market reactions into a single master file."""
    if not os.path.exists('data/wasde.db'):
        print("Database not found.")
        return

    conn = sqlite3.connect('data/wasde.db')
    
    # Load reactions
    reactions_df = pd.read_sql("SELECT * FROM market_reactions", conn)
    
    # Load wasde reports
    wasde_df = pd.read_sql("SELECT * FROM wasde_reports", conn)
    conn.close()

    # Convert dates for joining
    wasde_df['report_date_dt'] = pd.to_datetime(wasde_df['report_date'])
    # Map report_date to release_date to join with market_reactions
    wasde_df['release_date'] = wasde_df['report_date_dt'].apply(get_precise_date).dt.strftime('%Y-%m-%d')
    wasde_df.drop(columns=['report_date_dt'], inplace=True)

    # Join on release_date
    # Since reactions has multiple rows per release_date (different commodities), 
    # we use a left join to keep all reactions.
    master_df = pd.merge(reactions_df, wasde_df, on='release_date', how='left')

    # Reorder columns to put core data first
    cols = ['release_date', 'commodity', 'status', 'surprise', 'return_1d', 'price_before', 'price_after']
    # Add all other columns that aren't in the prefix
    others = [c for c in master_df.columns if c not in cols and c != 'report_date']
    master_df = master_df[cols + ['report_date'] + others]

    output_path = 'data/aggregated_master.csv'
    master_df.to_csv(output_path, index=False)
    print(f"Master aggregated data exported to {output_path}")

if __name__ == "__main__":
    export_master_csv()
