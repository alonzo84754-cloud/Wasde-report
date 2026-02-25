import streamlit as st
import pandas as pd
import requests
import datetime
import time as _time
import pytz
import os
import altair as alt
from tastytrade_client import get_intraday_multi, get_intraday_prices
from investing_scraper import fetch_investing_calendar
from economic_calendar_analysis import run_macro_analysis
from resilience import get_logger, now_et

logger = get_logger("dashboard")

st.set_page_config(page_title="WASDE Dashboard", layout="wide")

st.title("WASDE News Failure Dashboard")
st.markdown("Automated Commodity and Macro Intelligence")

# API Base URL
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000/api")


# ---------------------------------------------------------------------------
# Data fetching with retry + better error messages
# ---------------------------------------------------------------------------

def fetch_data(endpoint, retries=2, delay=1.0):
    """Fetch data from API with retry and envelope unwrapping.

    The API returns either:
      - {"data": [...], "last_updated": "..."} (new format)
      - [...] (old/direct format)
    This function normalises both to (list | None, last_updated | None).
    """
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            url = f"{API_URL}/{endpoint}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                body = response.json()
                if isinstance(body, dict) and "data" in body:
                    # Store last_updated in session state for freshness indicator
                    lu = body.get("last_updated")
                    if lu:
                        st.session_state.setdefault("_api_timestamps", {})[endpoint] = lu
                    return body["data"]
                if isinstance(body, list):
                    return body
                # Dict without "data" key — could be an error body
                if isinstance(body, dict) and "error" in body:
                    return body
                return body
            else:
                logger.warning("API %s returned %d", endpoint, response.status_code)
        except requests.exceptions.ConnectionError:
            last_exc = "API server not reachable. Is the FastAPI backend running?"
        except requests.exceptions.Timeout:
            last_exc = "API request timed out. The server may be overloaded."
        except Exception as e:
            last_exc = str(e)

        if attempt < retries:
            _time.sleep(delay)

    if last_exc:
        st.error(last_exc)
    return None


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

st.sidebar.header("Navigation")
view = st.sidebar.radio("Go to", ["WASDE News Failures", "Commodity Deep-Dive", "Economic Calendar", "Economic Events Analysis", "Market Monitor"], key="nav_view")

# Data freshness indicator in sidebar
st.sidebar.divider()
data_time = now_et()
st.sidebar.markdown(f"**Data as of:** {data_time.strftime('%I:%M %p ET')}")
api_ts = st.session_state.get("_api_timestamps", {})
if api_ts:
    try:
        latest_ts = max(api_ts.values())
        from dateutil.parser import isoparse
        ts_dt = isoparse(latest_ts)
        age_minutes = (datetime.datetime.now(datetime.timezone.utc) - ts_dt).total_seconds() / 60
        if age_minutes > 60:
            st.sidebar.warning(f"Data may be stale ({int(age_minutes)} min old)")
        elif age_minutes > 30:
            st.sidebar.info(f"Data is {int(age_minutes)} min old")
    except Exception:
        pass

# Manual refresh button
if st.sidebar.button("Refresh Data"):
    st.cache_data.clear()
    st.rerun()

# Fetch Dates for selectors
# 1. WASDE Dates
wasde_dates_data = fetch_data("wasde-all")
if isinstance(wasde_dates_data, list) and wasde_dates_data:
    df_wasde_dates = pd.DataFrame(wasde_dates_data)
    wasde_available_dates = sorted(df_wasde_dates['release_date'].unique(), reverse=True)
else:
    wasde_available_dates = [datetime.date.today().strftime('%Y-%m-%d')]

# 2. Economic Dates
econ_dates_data = fetch_data("economic-all")
if isinstance(econ_dates_data, list) and econ_dates_data:
    df_econ_dates = pd.DataFrame(econ_dates_data)
    econ_available_dates = sorted(df_econ_dates['release_date'].unique(), reverse=True)
else:
    econ_available_dates = [datetime.date.today().strftime('%Y-%m-%d')]

# Sidebar Layout
all_reports_label = "All Reports"

st.sidebar.divider()
st.sidebar.subheader("Date Selection")

if st.sidebar.button("Show All History", key="show_all_btn"):
    st.session_state.date_selector = all_reports_label

# Context-aware date selector
if view == "Economic Calendar":
    options = [all_reports_label]
    selected_date_str = all_reports_label
elif view == "Economic Events Analysis":
    options = [all_reports_label] + econ_available_dates
    selected_date_str = st.sidebar.selectbox(
        "Economic Release Date",
        options=options,
        key="date_selector",
        help="Daily economic events"
    )
else:
    options = [all_reports_label] + wasde_available_dates
    selected_date_str = st.sidebar.selectbox(
        "WASDE Report Date",
        options=options,
        key="date_selector",
        help="Monthly WASDE reports"
    )

selected_date = None
if selected_date_str != all_reports_label:
    try:
        selected_date = pd.to_datetime(selected_date_str).date()
    except Exception:
        selected_date = None

TICKERS = {
    "Corn": "ZC=F",
    "Wheat": "ZW=F",
    "Soybeans": "ZS=F",
    "Soy. Meal": "ZM=F",
    "Soy. Oil": "ZL=F",
    "Sugar": "SB=F",
    "Coffee": "KC=F",
    "Cotton": "CT=F",
    "Live Cattle": "LE=F",
    "Feeder Cattle": "GF=F",
    "Lean Hogs": "HE=F",
    "Crude Oil": "CL=F",
    "Gasoline": "RB=F",
    "Heating Oil": "HO=F",
    "Natural Gas": "NG=F"
}

DB_NAME_MAP = {
    "Soy. Meal": "soybean meal",
    "Soy. Oil": "soybean oil",
    "Crude Oil": "Crude Oil",
    "Gasoline": "Gasoline",
    "Heating Oil": "Heating Oil",
    "Natural Gas": "Natural Gas",
    "Sugar": "sugar",
    "Coffee": "coffee",
    "Corn": "corn",
    "Wheat": "wheat",
    "Soybeans": "soybeans",
    "Cotton": "cotton",
    "Live Cattle": "live cattle",
    "Feeder Cattle": "feeder cattle",
    "Lean Hogs": "lean hogs"
}


def fetch_pulse_data():
    try:
        tickers = list(TICKERS.values())
        data = get_intraday_multi(tickers, period="7d", interval="15m")
        return data
    except Exception as e:
        logger.warning("Pulse data fetch failed: %s", e)
        return None


def _trigger_status_refresh():
    """Ask the API to recalculate failure statuses using live market prices."""
    try:
        resp = requests.get(f"{API_URL}/refresh-status", timeout=15)
        if resp.status_code == 200:
            body = resp.json()
            updated = body.get("updated", {})
            logger.info(
                "Live refresh: %d WASDE rows, %d Economic rows updated",
                updated.get("market_reactions", 0),
                updated.get("economic_event_reactions", 0),
            )
    except Exception as e:
        logger.debug("Status refresh failed (non-fatal): %s", e)


def fetch_latest_wasde_status():
    """Fetch the latest reaction for each commodity from both WASDE and Economic data."""
    wasde_data = fetch_data("wasde-all")
    econ_data = fetch_data("economic-all")

    all_rows = []
    if isinstance(wasde_data, list) and wasde_data:
        all_rows.extend(wasde_data)
    if isinstance(econ_data, list) and econ_data:
        for row in econ_data:
            row['commodity'] = row.get('instrument')
            all_rows.append(row)

    if not all_rows:
        return {}

    df = pd.DataFrame(all_rows)
    df['release_date'] = pd.to_datetime(df['release_date'])
    latest = df.sort_values('release_date', ascending=False).drop_duplicates('commodity')

    status_map = {}
    for _, row in latest.iterrows():
        status_map[str(row['commodity']).lower()] = {
            'news_failure': row.get('news_failure', 'NO'),
            'news_sentiment': row.get('news_sentiment', 'Neutral'),
            'reason': row.get('reason', 'N/A'),
            'release_date': row.get('release_date')
        }
    return status_map


@st.fragment(run_every=60)
def _render_pulse_grid():
    """Render the Live Market Pulse grid, auto-refreshes every 60 seconds."""
    est = pytz.timezone('America/New_York')
    now_est = datetime.datetime.now(est).strftime('%I:%M:%S %p ET')
    st.caption(f"Last updated: {now_est} — refreshes every 60s")
    # Recalculate failure statuses with live prices before displaying
    _trigger_status_refresh()
    pulse_data = fetch_pulse_data()
    wasde_status = fetch_latest_wasde_status()
    ticker_items = list(TICKERS.items())
    for i in range(0, len(ticker_items), 5):
        chunk = ticker_items[i:i+5]
        cols = st.columns(len(chunk))
        for j, (name, ticker) in enumerate(chunk):
            with cols[j]:
                with st.container(height=200, border=True):
                    try:
                        if pulse_data is not None and ticker in pulse_data:
                            ticker_df = pulse_data[ticker].dropna()
                            if not ticker_df.empty:
                                last_p = float(ticker_df['Close'].iloc[-1])
                                prev_p = float(ticker_df['Close'].iloc[-2]) if len(ticker_df) > 1 else last_p
                                change = (last_p - prev_p) / prev_p if len(ticker_df) > 1 else 0
                                st.metric(name, f"{last_p:.2f}", f"{change:.4%}")

                                db_name = DB_NAME_MAP.get(name, name.lower())
                                status = wasde_status.get(db_name)
                                if status and status.get('news_failure') == 'YES':
                                    label = status.get('reason', '')
                                    if not label or "News Failure" not in label:
                                        label = "News Failure-Bullish" if status.get('news_sentiment') == 'Bearish' else "News Failure-Bearish"
                                    st.markdown(f"**:red[{label}]**")
                                    fail_date = status.get('release_date')
                                    if fail_date:
                                        st.caption(f"{pd.to_datetime(fail_date).strftime('%b %d, %Y %I:%M %p')}")
                            else:
                                st.markdown(f"**{name}**")
                                st.caption("No price data")
                        else:
                            st.markdown(f"**{name}**")
                            st.caption("Awaiting data")
                    except Exception:
                        st.markdown(f"**{name}**")


if view == "WASDE News Failures":
    st.header("WASDE News Failure Analysis")

    data = fetch_data("wasde-failures")
    if data is not None:
        if isinstance(data, dict) and "error" in data:
            st.error(f"Backend Error: {data['error']}")
        else:
            df = pd.DataFrame(data)

            if selected_date:
                df['release_date_dt'] = pd.to_datetime(df['release_date']).dt.date
                df = df[df['release_date_dt'] == selected_date]

            if not df.empty:
                col1, col2, col3 = st.columns(3)
                col1.metric("Total Failures Detected", len(df))
                col2.metric("Latest failure", df.iloc[0]['commodity'].capitalize(), df.iloc[0]['release_date'])

                cols_to_show = ['release_date', 'commodity', 'surprise', 'surprise_percent', 'return_1d', 'news_failure', 'reason', 'summary']
                df_display = df[cols_to_show].copy() if all(c in df.columns for c in cols_to_show) else df.copy()

                df_chart = df.copy()
                if 'news_failure' in df_chart.columns and 'reason' in df_chart.columns:
                    df_chart['news_failure_label'] = df_chart.apply(
                        lambda x: str(x['reason']) if str(x['news_failure']).upper() == 'YES' and x['reason'] != 'N/A' else 'Aligned',
                        axis=1
                    )

                st.subheader("Historical Failure Timeline")
                timeline_all = alt.Chart(df_chart).mark_bar().encode(
                    x=alt.X('release_date:T', title='Date'),
                    y=alt.Y('return_1d:Q', title='1D Return (%)', axis=alt.Axis(format='%')),
                    color=alt.Color('commodity:N', title='Commodity'),
                    tooltip=[
                        alt.Tooltip('release_date:T', title='Release Date', format='%Y-%m-%d'),
                        alt.Tooltip('commodity:N', title='Commodity'),
                        alt.Tooltip('surprise_percent:Q', title='Surprise %', format='.4f'),
                        alt.Tooltip('return_1d:Q', title='Return 1D', format='.4%'),
                        alt.Tooltip('news_failure_label:N', title='Status')
                    ]
                ).properties(height=300).interactive()
                st.altair_chart(timeline_all, width="stretch")

                if 'news_failure' in df_display.columns and 'reason' in df_display.columns:
                    df_display['news_failure'] = df_display.apply(
                        lambda x: f"Yes: {str(x['reason']).replace('Failure-', 'Failure - ')}" if str(x['news_failure']).upper() == 'YES' and x['reason'] != 'N/A' else x['news_failure'],
                        axis=1
                    )

                if 'reason' in df_display.columns:
                    df_display = df_display.drop(columns=['reason'])

                if 'release_date' in df_display.columns:
                    df_display['release_date'] = pd.to_datetime(df_display['release_date']).dt.strftime('%Y-%m-%d')

                if 'news_failure' in df_display.columns:
                    df_display = df_display.rename(columns={'news_failure': 'News Failure - Status'})

                st.dataframe(df_display.style.format({
                    'surprise': "{:.2f}",
                    'surprise_percent': "{:.2f}%",
                    'return_1d': "{:.2%}"
                }), width="stretch")

                st.subheader("Surprise (%) vs Market Return")
                st.scatter_chart(df.reset_index(drop=True), x="surprise_percent", y="return_1d", color="commodity")
            else:
                st.info("No failure data available for the selected date.")
    else:
        st.warning("Could not connect to API. Is the FastAPI backend running?")

elif view == "Commodity Deep-Dive":
    st.header("Commodity Deep-Dive: News vs. Reality")

    selected_commodity = st.selectbox("Select Commodity", list(TICKERS.keys()), format_func=lambda x: x.capitalize())

    wasde_data = fetch_data("wasde-all")
    econ_data = fetch_data("economic-all")

    all_rows = []
    if isinstance(wasde_data, list) and wasde_data:
        all_rows.extend(wasde_data)
    if isinstance(econ_data, list) and econ_data:
        for row in econ_data:
            row['commodity'] = row.get('instrument')
            row['surprise_percent'] = 0.0
            if row.get('actual') and row.get('forecast') and row.get('forecast') != 0:
                row['surprise_percent'] = (row['actual'] - row['forecast']) / row['forecast'] * 100
            all_rows.append(row)

    if all_rows:
        df_all = pd.DataFrame(all_rows)

        df_all['commodity'] = df_all['commodity'].fillna('unknown').astype(str)

        db_name = DB_NAME_MAP.get(selected_commodity, selected_commodity.lower())
        df_sub_full = df_all[df_all['commodity'].str.lower().str.strip() == db_name.lower().strip()].copy()

        df_sub = df_sub_full.copy()
        if selected_date:
            df_sub['release_date_dt'] = pd.to_datetime(df_sub['release_date']).dt.date
            df_sub = df_sub[df_sub['release_date_dt'] == selected_date]

        if not df_sub_full.empty:
            df_sub_full = df_sub_full.copy()
            if 'news_failure' in df_sub_full.columns and 'reason' in df_sub_full.columns:
                df_sub_full['news_failure_label'] = df_sub_full.apply(
                    lambda x: str(x['reason']) if str(x['news_failure']).upper() == 'YES' and x['reason'] != 'N/A' else 'Aligned',
                    axis=1
                )

            # --- Row 1: Surprise vs Market Return | Commodity Price Action (50/50) ---
            col_chart, col_price = st.columns([1, 1])

            with col_chart:
                st.subheader("Surprise vs. Market Return")

                scatter = alt.Chart(df_sub_full).mark_circle(size=100).encode(
                    x=alt.X('surprise_percent:Q', title='News Surprise (%)'),
                    y=alt.Y('return_1d:Q', title='1D Market Return', axis=alt.Axis(format='%')),
                    color=alt.Color('news_failure:N', scale=alt.Scale(domain=['YES', 'NO'], range=['red', 'steelblue'])),
                    tooltip=[
                        alt.Tooltip('release_date:T', title='Release Date', format='%Y-%m-%d'),
                        alt.Tooltip('surprise_percent:Q', title='Surprise %', format='.4f'),
                        alt.Tooltip('return_1d:Q', title='Return 1D', format='.4%'),
                        alt.Tooltip('news_failure_label:N', title='Status'),
                        'summary'
                    ]
                ).interactive()

                vline = alt.Chart(pd.DataFrame({'x': [0]})).mark_rule(color='gray', strokeDash=[5, 5]).encode(x='x')
                hline = alt.Chart(pd.DataFrame({'y': [0]})).mark_rule(color='gray', strokeDash=[5, 5]).encode(y='y')

                max_x = max(df_sub['surprise_percent'].abs().max(), 1.0) * 1.2 if not df_sub.empty else 1.0
                max_y = max(df_sub['return_1d'].abs().max(), 0.05) * 1.2 if not df_sub.empty else 0.05

                failures_bg = alt.Chart(pd.DataFrame([
                    {'x1': -max_x, 'x2': 0, 'y1': 0, 'y2': max_y, 'type': 'Failure Zone'},
                    {'x1': 0, 'x2': max_x, 'y1': -max_y, 'y2': 0, 'type': 'Failure Zone'}
                ])).mark_rect(opacity=0.1, color='red').encode(
                    x='x1:Q', x2='x2:Q', y='y1:Q', y2='y2:Q'
                )

                st.altair_chart(failures_bg + vline + hline + scatter, width="stretch")
                st.info("Red zones indicate 'News Failures' (Divergent behavior).")

            with col_price:
                st.subheader(f"{selected_commodity.capitalize()} Price Action")

                period_map = {
                    "1D": {"period": "1d", "interval": "5m"},
                    "2D": {"period": "2d", "interval": "15m"},
                    "5D": {"period": "5d", "interval": "1h"},
                    "6M": {"period": "6mo", "interval": "1d"},
                    "1Y": {"period": "1y", "interval": "1d"}
                }

                if "chart_period" not in st.session_state:
                    st.session_state.chart_period = "5D"

                cols_p = st.columns(len(period_map))
                for i, p in enumerate(period_map.keys()):
                    if cols_p[i].button(p, key=f"period_{p}", type="primary" if st.session_state.chart_period == p else "secondary"):
                        st.session_state.chart_period = p
                        st.rerun()

                ticker = TICKERS.get(selected_commodity)
                try:
                    p_params = period_map[st.session_state.chart_period]
                    hist = get_intraday_prices(ticker, period=p_params["period"], interval=p_params["interval"])
                    if hist is not None and not hist.empty:
                        hist = hist.set_index("Date")
                        if st.session_state.chart_period == "1Y":
                            st.area_chart(hist['Close'], width="stretch")
                        else:
                            st.line_chart(hist['Close'], width="stretch")
                except Exception as e:
                    st.error(f"Chart error: {e}")

            # --- Row 2: Price Action (full width) ---
            display_date = selected_date if selected_date else (pd.to_datetime(df_sub_full['release_date']).dt.date.max() if not df_sub_full.empty else None)

            if display_date:
                st.subheader(f"Price Action: {display_date}")
                report_row = df_sub_full[pd.to_datetime(df_sub_full['release_date']).dt.date == display_date]
                if not report_row.empty:
                    report_row = report_row.iloc[0]
                    p_updown = "UP" if report_row['return_1d'] > 0 else "DOWN"
                    st.metric("1D Change", f"{report_row['return_1d']:.2%}", p_updown)

                    if str(report_row.get('news_failure')).upper() == 'YES':
                        st.error(f"News Failure on {display_date}: Divergent behavior.")
                    else:
                        st.success(f"Market aligned on {display_date}.")
            else:
                st.info("No report data available.")

            st.divider()
            st.subheader(f"Timeline of {selected_commodity.capitalize()} Reports")

            df_sub_full['is_selected'] = pd.to_datetime(df_sub_full['release_date']).dt.date == selected_date if selected_date else False
            timeline = alt.Chart(df_sub_full).mark_bar().encode(
                x=alt.X('release_date:T', title='Release Date'),
                y=alt.Y('return_1d:Q', title='Market Reaction (%)', axis=alt.Axis(format='%')),
                color=alt.condition(
                    alt.datum.is_selected,
                    alt.value('orange'),
                    alt.Color('news_failure:N', scale=alt.Scale(domain=['YES', 'NO'], range=['red', 'steelblue']))
                ),
                tooltip=[
                    alt.Tooltip('release_date:T', title='Release Date', format='%Y-%m-%d'),
                    alt.Tooltip('surprise_percent:Q', title='Surprise %', format='.4f'),
                    alt.Tooltip('return_1d:Q', title='Return 1D', format='.4%'),
                    alt.Tooltip('news_failure_label:N', title='Status')
                ]
            ).properties(height=300).interactive()

            st.altair_chart(timeline, width="stretch")
            st.caption("Red bars signify historical days where the market failed to react as expected to the news (News Failure). Blue bars are aligned reactions. Orange highlights your current selection.")

            st.subheader("Historical Reactions")
            display_cols = ['release_date', 'surprise_percent', 'return_1d', 'news_failure', 'reason', 'summary']
            available_cols = [c for c in display_cols if c in df_sub.columns]
            df_hist = df_sub[available_cols].copy()

            if 'release_date' in df_hist.columns:
                df_hist['release_date'] = pd.to_datetime(df_hist['release_date']).dt.strftime('%Y-%m-%d')

            if 'news_failure' in df_hist.columns and 'reason' in df_hist.columns:
                df_hist['news_failure'] = df_hist.apply(
                    lambda x: f"Yes: {str(x['reason']).replace('Failure-', 'Failure - ')}" if x['news_failure'] == 'YES' and x['reason'] != 'N/A' else x['news_failure'],
                    axis=1
                )
                df_hist = df_hist.drop(columns=['reason'])
                df_hist = df_hist.rename(columns={'news_failure': 'News Failure - Status'})

            format_dict = {}
            if 'return_1d' in df_hist.columns:
                format_dict['return_1d'] = "{:.4%}"
            if 'surprise_percent' in df_hist.columns:
                format_dict['surprise_percent'] = "{:.4f}%"

            st.dataframe(df_hist.style.format(format_dict), width="stretch")
        else:
            st.info(f"No data available for {selected_commodity}.")

elif view == "Economic Calendar":
    st.header("Economic Calendar — US Events")

    est = pytz.timezone('America/New_York')
    now_est_val = datetime.datetime.now(est)
    st.caption(f"Current Time: {now_est_val.strftime('%I:%M %p ET')}")

    col_day, col_imp = st.columns([1, 2])
    with col_day:
        today_et = now_est_val.date()
        tomorrow_et = today_et + datetime.timedelta(days=1)
        yesterday_et = today_et - datetime.timedelta(days=1)
        day_options = {
            f"Yesterday ({yesterday_et.strftime('%b %d')})": yesterday_et.strftime('%Y-%m-%d'),
            f"Today ({today_et.strftime('%b %d')})": today_et.strftime('%Y-%m-%d'),
            f"Tomorrow ({tomorrow_et.strftime('%b %d')})": tomorrow_et.strftime('%Y-%m-%d'),
        }
        selected_day_label = st.radio("Day", list(day_options.keys()), horizontal=True, index=1)
        selected_day = day_options[selected_day_label]
    with col_imp:
        star_options = {"All": [1, 2, 3], "2-3 Star": [2, 3], "3 Star Only": [3]}
        star_filter = st.radio("Importance Filter", list(star_options.keys()), horizontal=True, index=0)

    @st.cache_data(ttl=300)
    def fetch_calendar_data():
        try:
            url = f"{API_URL}/economic-calendar"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                body = resp.json()
                api_data = body.get("data", body) if isinstance(body, dict) else body
            else:
                api_data = None
        except Exception:
            api_data = None
        if api_data and isinstance(api_data, list) and len(api_data) > 0:
            return pd.DataFrame(api_data)
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        tomorrow_str = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        frames = []
        df1 = fetch_investing_calendar(date_from=today_str, date_to=today_str)
        if df1 is not None and not df1.empty:
            frames.append(df1)
        df2 = fetch_investing_calendar(date_from=tomorrow_str, date_to=tomorrow_str)
        if df2 is not None and not df2.empty:
            frames.append(df2)
        if frames:
            combined = pd.concat(frames, ignore_index=True, sort=False)
            try:
                from database_manager import replace_table_data
                replace_table_data(combined, 'economic_calendar_today')
            except Exception:
                pass
            return combined
        return None

    with st.spinner("Fetching economic calendar..."):
        df_cal = fetch_calendar_data()

    if df_cal is not None and not df_cal.empty:
        if 'date' in df_cal.columns:
            df_cal = df_cal.copy()
            df_cal['date_str'] = df_cal['date'].astype(str).str[:10]
            df_cal = df_cal[df_cal['date_str'] == selected_day]

        allowed = star_options[star_filter]
        if 'importance' in df_cal.columns:
            df_cal = df_cal.copy()
            df_cal['importance'] = pd.to_numeric(df_cal['importance'], errors='coerce').fillna(1).astype(int)
            df_cal = df_cal[df_cal['importance'].isin(allowed)]

        if df_cal.empty:
            st.info(f"No events found for {selected_day_label.lower()}.")
        else:
            df_display = pd.DataFrame()
            df_display['Time (ET)'] = df_cal['time'] if 'time' in df_cal.columns else ''
            df_display['Event'] = df_cal['event'] if 'event' in df_cal.columns else ''
            if 'importance' in df_cal.columns:
                df_display['Imp.'] = df_cal['importance'].apply(lambda x: '*' * int(x) if pd.notna(x) else '')
            df_display['Actual'] = df_cal['actual_raw'] if 'actual_raw' in df_cal.columns else df_cal.get('actual', pd.Series(dtype=str)).apply(lambda x: f"{x}" if pd.notna(x) else "")
            df_display['Forecast'] = df_cal['forecast_raw'] if 'forecast_raw' in df_cal.columns else df_cal.get('forecast', pd.Series(dtype=str)).apply(lambda x: f"{x}" if pd.notna(x) else "")
            df_display['Previous'] = df_cal['previous_raw'] if 'previous_raw' in df_cal.columns else df_cal.get('previous', pd.Series(dtype=str)).apply(lambda x: f"{x}" if pd.notna(x) else "")

            df_display = df_display.reset_index(drop=True)
            st.dataframe(df_display, width="stretch", height=600, hide_index=True)

            total = len(df_display)
            released = (df_display['Actual'] != '').sum()
            st.caption(f"{released} of {total} events released so far today")
    elif df_cal is not None and df_cal.empty:
        st.info("No US economic events scheduled for today.")
    else:
        st.warning("Could not fetch calendar data. The scraper may be rate-limited — try again in a few minutes.")

    if st.button("Refresh Calendar"):
        with st.spinner("Scraping fresh calendar data..."):
            today_str = datetime.datetime.now().strftime("%Y-%m-%d")
            fresh = fetch_investing_calendar(date_from=today_str, date_to=today_str)
            if fresh is not None and not fresh.empty:
                try:
                    from database_manager import replace_table_data
                    replace_table_data(fresh, 'economic_calendar_today')
                except Exception:
                    pass
                st.success(f"Refreshed: {len(fresh)} events loaded")
            else:
                st.warning("Scraper returned no data — may be rate-limited")
        st.cache_data.clear()
        st.rerun()

elif view == "Economic Events Analysis":
    st.header("Economic Events Analysis")

    INSTRUMENT_DESCRIPTIONS = {
        "ES": "ES - S&P 500 Futures",
        "ZN": "ZN - 10Y Treasury Note",
        "NQ": "NQ - Nasdaq 100 Futures",
        "Crude Oil": "CL - Crude Oil Futures",
        "Natural Gas": "NG - Natural Gas Futures",
        "Gasoline": "RB - RBOB Gasoline Futures",
        "Heating Oil": "HO - Heating Oil Futures",
        "Gold": "GC - Gold Futures",
    }

    @st.cache_data(ttl=3600)
    def ensure_fresh_economic_data():
        existing = fetch_data("economic-all")
        if existing and isinstance(existing, list):
            est = pytz.timezone('America/New_York')
            today_str = datetime.datetime.now(est).strftime('%Y-%m-%d')
            dates = [r.get('release_date', '')[:10] for r in existing]
            if today_str in dates:
                return
        run_macro_analysis(days_back=14)

    with st.spinner("Checking for new economic data..."):
        try:
            ensure_fresh_economic_data()
        except Exception as e:
            st.caption(f"Auto-refresh note: {e}")

    data = fetch_data("economic-all")
    if data is not None:
        if isinstance(data, dict) and "error" in data:
            st.error(f"Backend Error: {data['error']}")
        else:
            df = pd.DataFrame(data)

            if selected_date:
                df['release_date_dt'] = pd.to_datetime(df['release_date']).dt.date
                df = df[df['release_date_dt'] == selected_date]

            if not df.empty:
                show_failures_only = st.toggle("Show only News Failures", value=False)
                if show_failures_only:
                    df = df[df['news_failure'] == 'YES']

                if df.empty:
                    st.info("No news failures detected for the selected filters.")
                else:
                    total_events = len(df)
                    failures = len(df[df['news_failure'] == 'YES']) if 'news_failure' in df.columns else 0
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Total Events", total_events)
                    col2.metric("News Failures", failures)
                    col3.metric("Failure Rate", f"{failures/total_events*100:.0f}%" if total_events > 0 else "0%")

                    if 'instrument' in df.columns:
                        df['Instrument'] = df['instrument'].map(
                            lambda x: INSTRUMENT_DESCRIPTIONS.get(x, x)
                        )

                    def sentiment_label(row):
                        s = str(row.get('news_sentiment', ''))
                        f = str(row.get('news_failure', 'NO'))
                        if f.upper() == 'YES':
                            reason = str(row.get('reason', ''))
                            return f"FAILURE: {reason}" if reason != 'N/A' else "FAILURE"
                        return s

                    df['Status'] = df.apply(sentiment_label, axis=1)

                    if 'release_date' in df.columns:
                        df['release_date'] = pd.to_datetime(df['release_date']).dt.strftime('%Y-%m-%d')

                    df = df.sort_values(['release_date', 'release_time'] if 'release_time' in df.columns else ['release_date'], ascending=[False] * (2 if 'release_time' in df.columns else 1))

                    display_cols = ['release_date', 'event_name', 'Instrument', 'actual', 'forecast', 'news_sentiment', 'return_1d', 'Status', 'summary']
                    if 'release_time' in df.columns:
                        display_cols.insert(1, 'release_time')
                    display_cols = [c for c in display_cols if c in df.columns]
                    df_display = df[display_cols].copy()

                    rename_map = {
                        'release_date': 'Date',
                        'release_time': 'Time',
                        'event_name': 'Event',
                        'actual': 'Actual',
                        'forecast': 'Forecast',
                        'news_sentiment': 'Sentiment',
                        'return_1d': '1D Return',
                        'summary': 'Summary'
                    }
                    df_display = df_display.rename(columns={k: v for k, v in rename_map.items() if k in df_display.columns})

                    def color_status(val):
                        if 'FAILURE' in str(val):
                            return 'background-color: #ffcccc; color: #cc0000; font-weight: bold'
                        if val == 'Bullish':
                            return 'background-color: #ccffcc; color: #006600'
                        if val == 'Bearish':
                            return 'background-color: #ffcccc; color: #cc0000'
                        return ''

                    def color_sentiment(val):
                        if val == 'Bullish':
                            return 'color: #006600; font-weight: bold'
                        if val == 'Bearish':
                            return 'color: #cc0000; font-weight: bold'
                        return 'color: #888888'

                    format_dict = {}
                    if '1D Return' in df_display.columns:
                        format_dict['1D Return'] = "{:.4%}"
                    if 'Actual' in df_display.columns:
                        format_dict['Actual'] = "{:.2f}"
                    if 'Forecast' in df_display.columns:
                        format_dict['Forecast'] = "{:.2f}"

                    styled = df_display.style.format(format_dict)
                    if 'Status' in df_display.columns:
                        styled = styled.map(color_status, subset=['Status'])
                    if 'Sentiment' in df_display.columns:
                        styled = styled.map(color_sentiment, subset=['Sentiment'])

                    st.dataframe(styled, width="stretch", height=500)
            else:
                st.info("No economic events available for the selected date.")
    else:
        st.warning("Could not connect to API. Is the FastAPI backend running?")

elif view == "Market Monitor":
    st.header("Real-time Monitor (Recent Events)")
    st.info("Showing market reactions from the last 24 hours.")

    # Refresh failure statuses with live prices on view load
    _trigger_status_refresh()
    data = fetch_data("realtime-monitor")
    if data is not None:
        if isinstance(data, dict) and "error" in data:
            st.error(f"API Error: {data['error']}")
        else:
            if isinstance(data, dict) and "data" in data:
                data = data["data"]
            df = pd.DataFrame(data)
            latest_wasde_status = fetch_latest_wasde_status()

            if not df.empty:
                wasde_day = df[df['type'] == 'WASDE']
                if not wasde_day.empty:
                    st.subheader("Commodity Releases")
                    for i in range(0, len(wasde_day), 3):
                        chunk = wasde_day.iloc[i:i+3]
                        cols = st.columns(3)
                        for j, (_, row) in enumerate(chunk.iterrows()):
                            with cols[j]:
                                with st.container(height=200, border=True):
                                    color = "normal" if str(row['news_failure']).upper() == 'NO' else "inverse"
                                    st.metric(f"{row['name'].capitalize()}", f"${row['price']:.2f}", f"{row['return_1d']:.4%}", delta_color=color)
                                    if str(row['news_failure']).upper() == 'YES':
                                        label = row.get('reason')
                                        if not label or "News Failure" not in label:
                                            label = "News Failure-Bullish" if row.get('news_sentiment') == 'Bearish' else "News Failure-Bearish"
                                        st.markdown(f"**:red[{label}]**")

                econ_day = df[df['type'] == 'Economic']
                if not econ_day.empty:
                    if not wasde_day.empty:
                        st.divider()

                    st.subheader("Economic Releases")
                    econ_day = econ_day.drop_duplicates(subset=['name', 'price'])
                    for i in range(0, len(econ_day), 3):
                        chunk = econ_day.iloc[i:i+3]
                        cols = st.columns(3)
                        for j, (_, row) in enumerate(chunk.iterrows()):
                            with cols[j]:
                                with st.container(height=200, border=True):
                                    color = "normal" if str(row['news_failure']).upper() == 'NO' else "inverse"
                                    st.metric(f"{row['name']}", f"{row['price']:.2f}", f"{row['return_1d']:.4%}", delta_color=color)
                                    if str(row['news_failure']).upper() == 'YES':
                                        label = row.get('reason')
                                        if not label or label == 'N/A' or label == '':
                                            label = "News Failure"
                                        st.markdown(f"**:red[{label}]**")

                if wasde_day.empty and econ_day.empty:
                    st.info("No recent reports in the last 24-48 hours.")

                st.divider()
                st.subheader("Live Market Pulse")

                _render_pulse_grid()

            else:
                st.write("No active news events today. Showing general market pulse:")
                _render_pulse_grid()
    else:
        st.error("Failed to fetch real-time monitoring data. Is the API server running?")

# Footer
st.sidebar.markdown("---")
est = pytz.timezone('America/New_York')
last_sync = datetime.datetime.now(est).strftime('%Y-%m-%d %H:%M')
st.sidebar.write(f"Last sync: {last_sync} EST")
