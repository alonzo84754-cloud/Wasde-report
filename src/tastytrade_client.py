"""
Centralized market data wrapper.

Primary:   Tastytrade REST API (direct HTTP, no SDK)
Fallback:  Yahoo Finance (yfinance)

Auth via env vars: TT_CLIENT_SECRET, TT_REFRESH_TOKEN
Set TT_SANDBOX=true for sandbox (api.cert.tastyworks.com)
Set TT_SANDBOX=false for production (api.tastyworks.com)
"""

import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

from resilience import get_logger, retry, CircuitBreaker, TokenManager

_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path, override=True)

logger = get_logger("tastytrade")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_client_secret = os.getenv("TT_CLIENT_SECRET", "")
_refresh_token = os.getenv("TT_REFRESH_TOKEN", "")
_is_sandbox = os.getenv("TT_SANDBOX", "true").lower() in ("true", "1", "yes")

_BASE_URL = "https://api.cert.tastyworks.com" if _is_sandbox else "https://api.tastyworks.com"
_USER_AGENT = "WasdeDashboard/1.0"

# Thread-safe token cache (replaces bare globals)
_token_mgr = TokenManager()

# Circuit breaker for Tastytrade API
_tt_circuit = CircuitBreaker(failure_threshold=3, recovery_timeout=120, name="tastytrade")

# Yahoo Finance ticker <-> Tastytrade futures symbol
YAHOO_TO_TT = {
    "ZC=F": "/ZC", "ZW=F": "/ZW", "ZS=F": "/ZS", "ZM=F": "/ZM",
    "ZL=F": "/ZL", "CT=F": "/CT", "KC=F": "/KC", "SB=F": "/SB",
    "LE=F": "/LE", "GF=F": "/GF", "HE=F": "/HE", "CL=F": "/CL",
    "RB=F": "/RB", "HO=F": "/HO", "NG=F": "/NG", "ES=F": "/ES",
    "ZN=F": "/ZN",
}
TT_TO_YAHOO = {v: k for k, v in YAHOO_TO_TT.items()}


def _to_yahoo(symbol):
    """Convert any symbol to Yahoo Finance ticker."""
    if symbol.startswith("/"):
        return TT_TO_YAHOO.get(symbol, symbol)
    return symbol


def _to_tt(symbol):
    """Convert any symbol to Tastytrade format."""
    if symbol.startswith("/"):
        return symbol
    return YAHOO_TO_TT.get(symbol, symbol)


_resolve_symbol = _to_tt  # backward compat alias


# ---------------------------------------------------------------------------
# Tastytrade REST API (direct HTTP)
# ---------------------------------------------------------------------------

@retry(max_attempts=3, base_delay=2.0, exceptions=(requests.exceptions.RequestException,))
def _get_access_token():
    """Get a valid access token, refreshing if expired."""
    cached = _token_mgr.get_token()
    if cached:
        return cached

    if not _client_secret or not _refresh_token:
        return None

    resp = requests.post(
        f"{_BASE_URL}/oauth/token",
        json={
            "grant_type": "refresh_token",
            "refresh_token": _refresh_token,
            "client_secret": _client_secret,
        },
        headers={
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
        },
        timeout=10,
    )
    if resp.status_code == 200:
        data = resp.json()
        token = data.get("access_token") or data.get("data", {}).get("access_token")
        if token:
            _token_mgr.set_token(token, ttl_seconds=840)  # refresh at 14 min
            logger.info("Authenticated OK (%s)", _BASE_URL)
            return token
    logger.warning("Auth failed (%d): %s", resp.status_code, resp.text[:200])
    return None


@retry(max_attempts=3, base_delay=2.0, exceptions=(requests.exceptions.RequestException,))
def _tt_get_market_data(tt_symbols):
    """Fetch current market data for futures symbols via REST API.

    Returns dict of {symbol: {price, bid, ask, open, high, low, close, volume, prev_close}}.
    """
    token = _get_access_token()
    if not token:
        return {}

    # Build query params: future=/ZC&future=/ZW&...
    params = [("future", s) for s in tt_symbols]
    resp = requests.get(
        f"{_BASE_URL}/market-data/by-type",
        params=params,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": _USER_AGENT,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        logger.warning("Market data error (%d): %s", resp.status_code, resp.text[:200])
        return {}

    data = resp.json()
    # Response structure: {"data": {"items": [...]}} or {"items": [...]}
    items = data.get("data", {}).get("items", []) if isinstance(data.get("data"), dict) else data.get("items", [])
    if not items and isinstance(data, list):
        items = data

    result = {}
    for item in items:
        sym = item.get("symbol", "")
        bid = float(item.get("bid") or item.get("bid-price") or 0)
        ask = float(item.get("ask") or item.get("ask-price") or 0)
        last = float(item.get("last") or item.get("last-price") or 0)
        mid_price = float(item.get("mid") or item.get("mark") or 0)
        price = last or mid_price or ((bid + ask) / 2 if bid and ask else 0)

        result[sym] = {
            "price": price,
            "bid": bid,
            "ask": ask,
            "open": float(item.get("open") or 0),
            "high": float(item.get("day-high-price") or item.get("dayHighPrice") or 0),
            "low": float(item.get("day-low-price") or item.get("dayLowPrice") or 0),
            "close": float(item.get("close") or 0),
            "volume": float(item.get("volume") or 0),
            "prev_close": float(item.get("prev-close") or item.get("prevClose") or 0),
        }
    return result


# ---------------------------------------------------------------------------
# Yahoo Finance (fallback for historical/intraday)
# ---------------------------------------------------------------------------

def _yf_get_historical(symbol, days_back=730):
    """Fetch daily OHLC data via yfinance."""
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed. Run: pip install yfinance")
        return None

    ticker = _to_yahoo(symbol)
    try:
        data = yf.download(ticker, period=f"{days_back}d", interval="1d", progress=False)
        if data is None or data.empty:
            return None
        df = data.reset_index()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] if col[1] == '' else col[0] for col in df.columns]
        df = df.rename(columns={"index": "Date"})
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col not in df.columns:
                df[col] = None
        df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
        df = df[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
        df = df.dropna(subset=["Close"])
        logger.info("Yahoo Finance: Got %d daily bars for %s", len(df), ticker)
        return df
    except Exception as e:
        logger.warning("Yahoo Finance error for %s: %s", ticker, e)
        return None


def _yf_get_intraday(symbol, period="7d", interval="15m"):
    """Fetch intraday data via yfinance."""
    try:
        import yfinance as yf
    except ImportError:
        return None

    ticker = _to_yahoo(symbol)
    try:
        data = yf.download(ticker, period=period, interval=interval, progress=False)
        if data is None or data.empty:
            return None
        df = data.reset_index()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] if col[1] == '' else col[0] for col in df.columns]
        date_col = "Datetime" if "Datetime" in df.columns else "Date"
        df = df.rename(columns={date_col: "Date"})
        df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
        df = df[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
        df = df.dropna(subset=["Close"])
        return df
    except Exception as e:
        logger.warning("Yahoo Finance intraday error for %s: %s", ticker, e)
        return None


def _yf_get_single_quote(ticker):
    """Fetch a single current quote from Yahoo Finance."""
    try:
        import yfinance as yf
        t = yf.Ticker(_to_yahoo(ticker))
        info = t.fast_info
        price = getattr(info, 'last_price', None) or getattr(info, 'previous_close', 0)
        return {
            "price": float(price) if price else 0.0,
            "bid": float(price) if price else 0.0,
            "ask": float(price) if price else 0.0,
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_historical_prices(symbol, days_back=730):
    """Fetch daily OHLC data. Uses Yahoo Finance (best source for history)."""
    return _yf_get_historical(symbol, days_back)


def get_intraday_prices(symbol, period="7d", interval="15m"):
    """Fetch intraday candle data. Uses Yahoo Finance."""
    return _yf_get_intraday(symbol, period=period, interval=interval)


def get_intraday_multi(tickers, period="7d", interval="15m"):
    """Fetch intraday data for multiple tickers."""
    result = {}
    for ticker in tickers:
        df = get_intraday_prices(ticker, period=period, interval=interval)
        if df is not None and not df.empty:
            result[ticker] = df
    return result


def get_current_quotes(symbols):
    """Fetch current quotes. Tries Tastytrade first, falls back to Yahoo.

    Uses circuit breaker: when TT is down, skips straight to Yahoo.
    Fills partial TT results from Yahoo for any missing symbols.

    Args:
        symbols: List of Yahoo Finance tickers or Tastytrade symbols.

    Returns:
        Dict of {original_symbol: {price, bid, ask, ...}}.
    """
    result = {}
    remaining = list(symbols)

    # Try Tastytrade REST API first (if circuit allows)
    if _client_secret and _refresh_token and _tt_circuit.allow_request():
        tt_symbols = [_to_tt(s) for s in symbols]
        tt_to_original = {_to_tt(s): s for s in symbols}

        try:
            tt_data = _tt_get_market_data(tt_symbols)
            if tt_data:
                _tt_circuit.record_success()
                for tt_sym, data in tt_data.items():
                    original = tt_to_original.get(tt_sym, tt_sym)
                    result[original] = data
                # Identify symbols NOT returned by TT
                remaining = [s for s in symbols if s not in result]
                if remaining:
                    logger.info(
                        "TT returned %d/%d symbols, fetching %d from Yahoo",
                        len(result), len(symbols), len(remaining),
                    )
            else:
                _tt_circuit.record_failure()
        except Exception as e:
            _tt_circuit.record_failure()
            logger.warning("TT quotes failed (%s), falling back to Yahoo", e)

    # Fill remaining from Yahoo Finance
    for s in remaining:
        quote = _yf_get_single_quote(s)
        if quote:
            result[s] = quote

    return result


# Startup info
_src = "sandbox" if _is_sandbox else "production"
if _client_secret and _refresh_token:
    logger.info("Credentials loaded (%s: %s)", _src, _BASE_URL)
else:
    logger.info("No credentials, using Yahoo Finance only")


if __name__ == "__main__":
    logger.info("Testing Market Data Client")

    # Test 1: Tastytrade REST quotes
    if _client_secret and _refresh_token:
        logger.info("1. Tastytrade REST API - current quotes...")
        quotes = _tt_get_market_data(["/ZC", "/ES", "/CL"])
        for sym, q in quotes.items():
            logger.info("   %s: price=%.2f, bid=%.2f, ask=%.2f", sym, q['price'], q['bid'], q['ask'])
    else:
        logger.info("1. Skipping Tastytrade (no credentials)")

    # Test 2: Yahoo Finance historical
    logger.info("2. Yahoo Finance - historical corn (30d)...")
    df = get_historical_prices("ZC=F", days_back=30)
    if df is not None:
        logger.info("   Got %d rows", len(df))
    else:
        logger.info("   No data")

    # Test 3: Yahoo Finance intraday
    logger.info("3. Yahoo Finance - intraday corn (5d, 1h)...")
    df = get_intraday_prices("ZC=F", period="5d", interval="1h")
    if df is not None:
        logger.info("   Got %d rows", len(df))
    else:
        logger.info("   No data")

    # Test 4: Combined quotes
    logger.info("4. Combined quotes (Tastytrade -> Yahoo fallback)...")
    quotes = get_current_quotes(["ZC=F", "ES=F", "CL=F"])
    for sym, q in quotes.items():
        logger.info("   %s: price=%.2f", sym, q['price'])

    logger.info("Done")
