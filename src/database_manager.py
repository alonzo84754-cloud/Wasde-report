import pandas as pd
import os
import threading
from sqlalchemy import create_engine, text

from resilience import get_logger

logger = get_logger("database")

# ---------------------------------------------------------------------------
# Singleton engine (thread-safe)
# ---------------------------------------------------------------------------

_engine = None
_engine_lock = threading.Lock()

# Whitelist of tables that can be cleared/replaced
_ALLOWED_TABLES = frozenset({
    "economic_calendar_today",
    "wasde_reports",
    "market_reactions",
    "economic_event_reactions",
    "trade_log",
})


def get_db_url():
    """Use DATABASE_URL or POSTGRES_URL (Vercel default) from environment.
    Otherwise fallback to local SQLite."""
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

    if os.getenv('VERCEL'):
        return None

    return 'sqlite:///data/wasde.db'


def get_engine():
    """Return a singleton SQLAlchemy engine (created once, reused)."""
    global _engine
    if _engine is not None:
        return _engine

    with _engine_lock:
        if _engine is not None:
            return _engine

        url = get_db_url()
        if not url:
            raise ValueError(
                "Database connection string not found. "
                "Ensure DATABASE_URL is set in Vercel environment variables."
            )

        kwargs = {}
        if "postgresql" in url:
            kwargs.update(pool_pre_ping=True, pool_size=10)

        _engine = create_engine(url, **kwargs)
        logger.info("Engine created: %s", url.split("@")[-1] if "@" in url else url[:30])
        return _engine


def init_db():
    """Initialize the database and create tables if they don't exist."""
    engine = get_engine()
    db_url = get_db_url()
    if db_url and db_url.startswith('sqlite'):
        os.makedirs('data', exist_ok=True)

    with engine.begin() as conn:
        conn.execute(text('''
            CREATE TABLE IF NOT EXISTS economic_calendar_today (
                date TEXT,
                time TEXT,
                event TEXT,
                importance INTEGER,
                actual REAL,
                forecast REAL,
                previous REAL,
                actual_raw TEXT,
                forecast_raw TEXT,
                previous_raw TEXT
            )
        '''))

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
                    release_time TEXT,
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
            conn.execute(text('''
                CREATE TABLE IF NOT EXISTS trade_log (
                    id SERIAL PRIMARY KEY,
                    signal_type TEXT,
                    commodity TEXT,
                    futures_symbol TEXT,
                    direction TEXT,
                    quantity INTEGER,
                    order_type TEXT,
                    price REAL,
                    order_id TEXT,
                    order_status TEXT,
                    fill_price REAL,
                    signal_date TEXT,
                    signal_reason TEXT,
                    surprise_percent REAL,
                    created_at TEXT,
                    updated_at TEXT
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
                    release_time TEXT,
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
            conn.execute(text('''
                CREATE TABLE IF NOT EXISTS trade_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_type TEXT,
                    commodity TEXT,
                    futures_symbol TEXT,
                    direction TEXT,
                    quantity INTEGER,
                    order_type TEXT,
                    price REAL,
                    order_id TEXT,
                    order_status TEXT,
                    fill_price REAL,
                    signal_date TEXT,
                    signal_reason TEXT,
                    surprise_percent REAL,
                    created_at TEXT,
                    updated_at TEXT
                )
            '''))

    logger.info("Database initialized successfully")


def save_to_db(df, table_name, if_exists='append'):
    """Save a DataFrame to the database."""
    engine = get_engine()
    df = df.copy()
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
    if table_name not in _ALLOWED_TABLES:
        raise ValueError(f"Table '{table_name}' is not in the allowed whitelist: {_ALLOWED_TABLES}")
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(f"DELETE FROM {table_name}"))


def replace_table_data(df, table_name):
    """Atomically replace all data in a table: DELETE + INSERT in one transaction.

    If the INSERT fails, the DELETE is rolled back — no data loss.
    """
    if table_name not in _ALLOWED_TABLES:
        raise ValueError(f"Table '{table_name}' is not in the allowed whitelist: {_ALLOWED_TABLES}")

    engine = get_engine()
    df = df.copy()
    for col in df.select_dtypes(include=['datetime64']).columns:
        df[col] = df[col].dt.strftime('%Y-%m-%d')

    with engine.begin() as conn:
        conn.execute(text(f"DELETE FROM {table_name}"))
        df.to_sql(table_name, conn, if_exists="append", index=False)

    logger.info("Replaced %d rows in %s", len(df), table_name)


if __name__ == "__main__":
    logger.info("Initializing WASDE database...")
    init_db()
    logger.info("Database initialized successfully.")
