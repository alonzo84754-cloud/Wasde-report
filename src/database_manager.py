import pandas as pd
import os
from sqlalchemy import create_engine, text

# Use DATABASE_URL or POSTGRES_URL (Vercel default) from environment
# Otherwise fallback to local SQLite
def get_db_url():
    # Priority: Direct DATABASE_URL, then Vercel's various Postgres environment variables
    url = (
        os.getenv('DATABASE_URL') or 
        os.getenv('POSTGRES_URL') or 
        os.getenv('POSTGRES_PRISMA_URL') or 
        os.getenv('POSTGRES_URL_NON_POOLING')
    )
    if url:
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url
    
    # Check if we are in Vercel - if so, we SHOULD have a postgres URL
    if os.getenv('VERCEL'):
        # Do not fallback to sqlite on Vercel as it is read-only
        return None
        
    return 'sqlite:///data/wasde.db'

def get_engine():
    url = get_db_url()
    if not url:
        raise ValueError("Database connection string not found. Ensure DATABASE_URL is set in Vercel environment variables.")
    return create_engine(url)

def init_db():
    """Initialize the database and create tables if they don't exist."""
    engine = get_engine()
    db_url = get_db_url()
    if db_url and db_url.startswith('sqlite'):
        os.makedirs('data', exist_ok=True)
        
    with engine.begin() as conn:
        # Table for parsed WASDE reports
        conn.execute(text('''
            CREATE TABLE IF NOT EXISTS wasde_reports (
                report_date TEXT PRIMARY KEY,
                cotton_world_ending_stocks_proj_current REAL,
                cotton_world_ending_stocks_proj_prev REAL,
                sugar_us_ending_stocks_proj_current REAL,
                sugar_us_ending_stocks_proj_prev REAL,
                wheat_us_ending_stocks_proj_current REAL,
                wheat_us_ending_stocks_proj_prev REAL,
                corn_us_ending_stocks_proj_current REAL,
                corn_us_ending_stocks_proj_prev REAL,
                soybeans_us_ending_stocks_proj_current REAL,
                soybeans_us_ending_stocks_proj_prev REAL,
                "soybean meal_us_ending_stocks_proj_current" REAL,
                "soybean meal_us_ending_stocks_proj_prev" REAL,
                "soybean oil_us_ending_stocks_proj_current" REAL,
                "soybean oil_us_ending_stocks_proj_prev" REAL,
                "live cattle_us_ending_stocks_proj_current" REAL,
                "live cattle_us_ending_stocks_proj_prev" REAL,
                "feeder cattle_us_ending_stocks_proj_current" REAL,
                "feeder cattle_us_ending_stocks_proj_prev" REAL,
                "lean hogs_us_ending_stocks_proj_current" REAL,
                "lean hogs_us_ending_stocks_proj_prev" REAL
            )
        '''))
        
        # Table for market reactions and news failures
        if db_url and 'postgresql' in db_url:
             conn.execute(text('''
                CREATE TABLE IF NOT EXISTS market_reactions (
                    id SERIAL PRIMARY KEY,
                    commodity TEXT,
                    release_date TEXT,
                    release_time TEXT,
                    proj_val REAL,
                    act_val REAL,
                    surprise REAL,
                    surprise_percent REAL,
                    news_sentiment TEXT,
                    return_1d REAL,
                    price_before REAL,
                    price_after REAL,
                    news_failure TEXT,
                    reason TEXT,
                    summary TEXT,
                    is_realtime INTEGER DEFAULT 0,
                    status TEXT,
                    UNIQUE(commodity, release_date)
                )
            '''))
             conn.execute(text('''
                CREATE TABLE IF NOT EXISTS economic_event_reactions (
                    id SERIAL PRIMARY KEY,
                    event_name TEXT,
                    instrument TEXT,
                    release_date TEXT,
                    actual REAL,
                    forecast REAL,
                    news_sentiment TEXT,
                    return_1d REAL,
                    price_before REAL,
                    price_after REAL,
                    news_failure TEXT,
                    reason TEXT,
                    summary TEXT,
                    UNIQUE(event_name, release_date, instrument)
                )
            '''))
        else:
            conn.execute(text('''
                CREATE TABLE IF NOT EXISTS market_reactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    commodity TEXT,
                    release_date TEXT,
                    release_time TEXT,
                    proj_val REAL,
                    act_val REAL,
                    surprise REAL,
                    surprise_percent REAL,
                    news_sentiment TEXT,
                    return_1d REAL,
                    price_before REAL,
                    price_after REAL,
                    news_failure TEXT,
                    reason TEXT,
                    summary TEXT,
                    is_realtime INTEGER DEFAULT 0,
                    status TEXT,
                    UNIQUE(commodity, release_date)
                )
            '''))
            conn.execute(text('''
                CREATE TABLE IF NOT EXISTS economic_event_reactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_name TEXT,
                    instrument TEXT,
                    release_date TEXT,
                    actual REAL,
                    forecast REAL,
                    news_sentiment TEXT,
                    return_1d REAL,
                    price_before REAL,
                    price_after REAL,
                    news_failure TEXT,
                    reason TEXT,
                    summary TEXT,
                    UNIQUE(event_name, release_date, instrument)
                )
            '''))

def save_to_db(df, table_name, if_exists='append'):
    """Save a DataFrame to the database."""
    engine = get_engine()
    for col in df.select_dtypes(include=['datetime64']).columns:
        df[col] = df[col].dt.strftime('%Y-%m-%d')
    df.to_sql(table_name, engine, if_exists=if_exists, index=False)

def load_from_db(table_name):
    """Load a table from the database."""
    engine = get_engine()
    return pd.read_sql(table_name, engine)

def execute_query(query, params=None):
    """Execute a SQL query."""
    engine = get_engine()
    return pd.read_sql_query(query, engine, params=params)

def clear_table(table_name):
    """Delete all rows from a table while keeping the schema."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(f"DELETE FROM {table_name}"))

if __name__ == "__main__":
    print("Initializing WASDE database...")
    init_db()
    print("Database initialized successfully.")
