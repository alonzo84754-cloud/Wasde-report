import pandas as pd


def normalize_yahoo_prices(df):
    """Force yfinance/local price frames into: Date | Close.

    This is the single source of truth used by WASDE + macro analysis.
    """
    if df is None or df.empty:
        return None

    df = df.copy()

    # yfinance may return MultiIndex columns (even for single tickers in some configurations).
    # Flatten to strings like Close_ZC=F so we can normalize consistently.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            "_".join([str(part) for part in col if part not in ("", None)]).strip()
            for col in df.columns
        ]

    # Ensure Date column
    if "Date" not in df.columns:
        df = df.reset_index()

    if "Date" not in df.columns:
        for candidate in ("Datetime", "datetime", "index", "level_0", "Unnamed: 0"):
            if candidate in df.columns:
                df = df.rename(columns={candidate: "Date"})
                break

    if "Date" not in df.columns:
        # Last resort: find something date-ish
        for col in df.columns:
            col_lower = str(col).lower()
            if col_lower == "date" or "date" in col_lower or col_lower in {"time", "timestamp"}:
                df = df.rename(columns={col: "Date"})
                break

    if "Date" not in df.columns:
        return None

    # Normalize Close column
    if "Close" not in df.columns:
        # Common variants from CSVs
        for candidate in ("Adj Close", "Adj_Close", "AdjClose", "close"):
            if candidate in df.columns:
                df = df.rename(columns={candidate: "Close"})
                break

    if "Close" not in df.columns:
        close_cols = [
            c
            for c in df.columns
            if str(c).startswith("Close_")
            or str(c).lower().startswith("close_")
            or str(c).lower().endswith("_close")
        ]
        if len(close_cols) == 1:
            df = df.rename(columns={close_cols[0]: "Close"})
        else:
            return None  # ambiguous or missing

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    try:
        df["Date"] = df["Date"].dt.tz_localize(None)
    except Exception:
        # Some Series may already be tz-naive or non-datetimelike; coercion above should handle most.
        pass
    df["Date"] = df["Date"].dt.date
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")

    df = df.dropna(subset=["Date", "Close"])
    return df[["Date", "Close"]].copy()


def normalize_yahoo_ohlc(df):
    """Force yfinance/local OHLC frames into: Date | Open | Close.

    Use this when you need same-day Open→Close returns.
    """
    if df is None or df.empty:
        return None

    df = df.copy()

    # yfinance may return MultiIndex columns.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            "_".join([str(part) for part in col if part not in ("", None)]).strip()
            for col in df.columns
        ]

    # Ensure Date column
    if "Date" not in df.columns:
        df = df.reset_index()

    if "Date" not in df.columns:
        for candidate in ("Datetime", "datetime", "index", "level_0", "Unnamed: 0"):
            if candidate in df.columns:
                df = df.rename(columns={candidate: "Date"})
                break

    if "Date" not in df.columns:
        for col in df.columns:
            col_lower = str(col).lower()
            if col_lower == "date" or "date" in col_lower or col_lower in {"time", "timestamp"}:
                df = df.rename(columns={col: "Date"})
                break

    if "Date" not in df.columns:
        return None

    def _normalize_field(field_name: str):
        if field_name in df.columns:
            return field_name

        prefixed = [
            c
            for c in df.columns
            if str(c).startswith(f"{field_name}_")
            or str(c).lower().startswith(f"{field_name.lower()}_")
            or str(c).lower().endswith(f"_{field_name.lower()}")
        ]
        if len(prefixed) == 1:
            df.rename(columns={prefixed[0]: field_name}, inplace=True)
            return field_name

        return None

    open_col = _normalize_field("Open")
    close_col = _normalize_field("Close")
    if open_col is None or close_col is None:
        return None

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    try:
        df["Date"] = df["Date"].dt.tz_localize(None)
    except Exception:
        pass
    df["Date"] = df["Date"].dt.date

    df["Open"] = pd.to_numeric(df["Open"], errors="coerce")
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")

    df = df.dropna(subset=["Date", "Open", "Close"])
    return df[["Date", "Open", "Close"]].copy()
