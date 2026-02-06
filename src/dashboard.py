import streamlit as st
import pandas as pd
import requests
import datetime
import pytz
import os
import altair as alt
import yfinance as yf

st.set_page_config(page_title="WASDE Dashboard", layout="wide")

st.title("🏗️ WASDE News Failure Dashboard")
st.markdown("Automated Commodity and Macro Intelligence")

# API Base URL
# For AWS deployment, 127.0.0.1 is most reliable for internal requests
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000/api")

def fetch_data(endpoint):
    try:
        url = f"{API_URL}/{endpoint}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"API Error {response.status_code}: {response.text}")
    except Exception as e:
        st.error(f"Connection Error: {e}")
        return None
    return None

# Sidebar
st.sidebar.header("Navigation")
view = st.sidebar.radio("Go to", ["WASDE News Failures", "Commodity Deep-Dive", "Economic Event Failures", "Market Monitor"])

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
st.sidebar.subheader("📅 Date Selection")

if st.sidebar.button("Show All History", use_container_width=True):
    st.session_state.date_selector = all_reports_label

# Context-aware date selector
if view == "Economic Event Failures":
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
    except:
        selected_date = None

TICKERS = {
    "Corn": "ZC=F",
    "Wheat": "ZW=F",
    "Soybeans": "ZS=F",
    "Soy. Meal": "ZM=F",
    "Soy. Oil": "ZL=F",
    "Sugar": "SB=F",
    "Cotton": "CT=F",
    "Live Cattle": "LE=F",
    "Feeder Cattle": "GF=F",
    "Lean Hogs": "HE=F",
    "Crude Oil": "CL=F",
    "Gasoline": "RB=F",
    "Heating Oil": "HO=F",
    "Natural Gas": "NG=F"
}

# Map Display Names to Database Commodity Names
DB_NAME_MAP = {
    "Soy. Meal": "soybean meal",
    "Soy. Oil": "soybean oil",
    "Crude Oil": "Crude Oil",
    "Gasoline": "Gasoline",
    "Heating Oil": "Heating Oil",
    "Natural Gas": "Natural Gas",
    "Sugar": "sugar",
    "Corn": "corn",
    "Wheat": "wheat",
    "Soybeans": "soybeans",
    "Cotton": "cotton",
    "Live Cattle": "live cattle",
    "Feeder Cattle": "feeder cattle",
    "Lean Hogs": "lean hogs"
}

@st.cache_data(ttl=5)
def fetch_pulse_data(tickers_dict):
    try:
        tickers = list(tickers_dict.values())
        # Use 7d to ensure news releases from Friday are captured on Monday morning
        data = yf.download(tickers, period="7d", interval="15m", group_by='ticker', progress=False)
        return data
    except Exception as e:
        return None

@st.cache_data(ttl=60)
def fetch_latest_wasde_status():
    """Fetch the latest reaction for each commodity from both WASDE and Economic data."""
    wasde_data = fetch_data("wasde-all")
    econ_data = fetch_data("economic-all")
    
    all_rows = []
    if wasde_data:
        all_rows.extend(wasde_data)
    if econ_data:
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

if view == "WASDE News Failures":
    st.header("🌾 WASDE News Failure Analysis")
    
    data = fetch_data("wasde-failures")
    if data is not None:
        if isinstance(data, dict) and "error" in data:
            st.error(f"Backend Error: {data['error']}")
            if "env_status" in data:
                st.warning(f"Diagnostic: {data['env_status']}")
            if "hint" in data:
                st.info(data['hint'])
        else:
            df = pd.DataFrame(data)
            
            # Apply Date Filter
            if selected_date:
                df['release_date_dt'] = pd.to_datetime(df['release_date']).dt.date
                df = df[df['release_date_dt'] == selected_date]
            
            # Display key metrics at top
            if not df.empty:
                col1, col2, col3 = st.columns(3)
                col1.metric("Total Failures Detected", len(df))
                col2.metric("Latest failure", df.iloc[0]['commodity'].capitalize(), df.iloc[0]['release_date'])

                # Add column formatting
                # Select and reorder columns for better readability
                # Include 'reason' to build the custom label
                cols_to_show = ['release_date', 'commodity', 'surprise', 'surprise_percent', 'return_1d', 'news_failure', 'reason', 'summary']
                df_display = df[cols_to_show].copy() if all(c in df.columns for c in cols_to_show) else df.copy()

                # Prepare data for charts with descriptive tooltips
                df_chart = df.copy()
                if 'news_failure' in df_chart.columns and 'reason' in df_chart.columns:
                    df_chart['news_failure_label'] = df_chart.apply(
                        lambda x: str(x['reason']) if str(x['news_failure']).upper() == 'YES' and x['reason'] != 'N/A' else 'Aligned',
                        axis=1
                    )

                # Timeline of all failures
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
                st.altair_chart(timeline_all, use_container_width=True)

                # Create the descriptive "Yes: News Failure - ..." label
                if 'news_failure' in df_display.columns and 'reason' in df_display.columns:
                    df_display['news_failure'] = df_display.apply(
                        lambda x: f"Yes: {str(x['reason']).replace('Failure-', 'Failure - ')}" if str(x['news_failure']).upper() == 'YES' and x['reason'] != 'N/A' else x['news_failure'],
                        axis=1
                    )

                # Drop the helper column and format date
                if 'reason' in df_display.columns:
                    df_display = df_display.drop(columns=['reason'])

                if 'release_date' in df_display.columns:
                    df_display['release_date'] = pd.to_datetime(df_display['release_date']).dt.strftime('%Y-%m-%d')

                # Rename for clearer display
                if 'news_failure' in df_display.columns:
                    df_display = df_display.rename(columns={'news_failure': 'News Failure - Status'})

                st.dataframe(df_display.style.format({
                    'surprise': "{:.2f}",
                    'surprise_percent': "{:.2f}%",
                    'return_1d': "{:.2%}"
                }), use_container_width=True)

                # Simple Visualization
                st.subheader("Surprise (%) vs Market Return")
                # Reset index to avoid KeyError: 0 in st.scatter_chart when index is non-standard
                st.scatter_chart(df.reset_index(drop=True), x="surprise_percent", y="return_1d", color="commodity")
            else:
                st.info("No failure data available for the selected date. Make sure the API server is running (run `uvicorn src.api_server:app` in another terminal).")
    else:
        st.warning("Could not connect to API.")

elif view == "Commodity Deep-Dive":
    st.header("🔍 Commodity Deep-Dive: News vs. Reality")
    
    selected_commodity = st.selectbox("Select Commodity", list(TICKERS.keys()), format_func=lambda x: x.capitalize())
    
    # Fetch ALL data to show the scatter chart with failures highlighted
    wasde_data = fetch_data("wasde-all")
    econ_data = fetch_data("economic-all")
    
    all_rows = []
    if wasde_data:
        all_rows.extend(wasde_data)
    if econ_data:
        # Map economic columns to wasde columns if naming differs
        for row in econ_data:
            row['commodity'] = row.get('instrument')
            row['surprise_percent'] = 0.0 # Economic data doesn't use surprise_percent the same way yet
            if row.get('actual') and row.get('forecast') and row.get('forecast') != 0:
                row['surprise_percent'] = (row['actual'] - row['forecast']) / row['forecast'] * 100
            all_rows.append(row)

    if all_rows:
        df_all = pd.DataFrame(all_rows)
        
        # Ensure commodity column is string and drop any nulls
        df_all['commodity'] = df_all['commodity'].fillna('unknown').astype(str)
        
        # Normalize commodity names for matching
        db_name = DB_NAME_MAP.get(selected_commodity, selected_commodity.lower())
        df_sub_full = df_all[df_all['commodity'].str.lower().str.strip() == db_name.lower().strip()].copy()
        
        # Apply Date Filter for the metrics and price action
        df_sub = df_sub_full.copy()
        if selected_date:
            df_sub['release_date_dt'] = pd.to_datetime(df_sub['release_date']).dt.date
            df_sub = df_sub[df_sub['release_date_dt'] == selected_date]

        if not df_sub_full.empty:
            # Prepare data for Deep-Dive charts
            df_sub_full = df_sub_full.copy()
            if 'news_failure' in df_sub_full.columns and 'reason' in df_sub_full.columns:
                df_sub_full['news_failure_label'] = df_sub_full.apply(
                    lambda x: str(x['reason']) if str(x['news_failure']).upper() == 'YES' and x['reason'] != 'N/A' else 'Aligned',
                    axis=1
                )
            
            col_chart, col_price = st.columns([1, 1])
            
            with col_chart:
                st.subheader("Surprise vs. Market Return")
                # Define Failure Quadrants
                # Q2: Surprise < 0, Return > 0 (Divergence/Failure)
                # Q4: Surprise > 0, Return < 0 (Divergence/Failure)
                
                # Show all history in scatter chart for comparison, but maybe highlight selection if any
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
                
                # Add quadrant lines
                vline = alt.Chart(pd.DataFrame({'x': [0]})).mark_rule(color='gray', strokeDash=[5,5]).encode(x='x')
                hline = alt.Chart(pd.DataFrame({'y': [0]})).mark_rule(color='gray', strokeDash=[5,5]).encode(y='y')
                
                # Add background colors for failure zones
                # Q2 (Top Left) and Q4 (Bottom Right)
                max_x = max(df_sub['surprise_percent'].abs().max(), 1.0) * 1.2
                max_y = max(df_sub['return_1d'].abs().max(), 0.05) * 1.2
                
                failures_bg = alt.Chart(pd.DataFrame([
                    {'x1': -max_x, 'x2': 0, 'y1': 0, 'y2': max_y, 'type': 'Failure Zone'},
                    {'x1': 0, 'x2': max_x, 'y1': -max_y, 'y2': 0, 'type': 'Failure Zone'}
                ])).mark_rect(opacity=0.1, color='red').encode(
                    x='x1:Q', x2='x2:Q', y='y1:Q', y2='y2:Q'
                )
                
                st.altair_chart(failures_bg + vline + hline + scatter, use_container_width=True)
                st.info("Red zones indicate 'News Failures' (Divergent behavior).")

            with col_price:
                # Show specific date if selected, otherwise show latest
                display_date = selected_date if selected_date else (pd.to_datetime(df_sub_full['release_date']).dt.date.max() if not df_sub_full.empty else None)
                
                if display_date:
                    st.subheader(f"Price Action: {display_date}")
                    # Find the specific row for this date
                    report_row = df_sub_full[pd.to_datetime(df_sub_full['release_date']).dt.date == display_date]
                    if not report_row.empty:
                        report_row = report_row.iloc[0]
                        p_updown = "📈 UP" if report_row['return_1d'] > 0 else "📉 DOWN"
                        st.metric("1D Change", f"{report_row['return_1d']:.2%}", p_updown)
                        
                        if str(report_row.get('news_failure')).upper() == 'YES':
                            st.error(f"⚠️ News Failure on {display_date}: Divergent behavior.")
                        else:
                            st.success(f"✅ Market aligned on {display_date}.")
                    
                    st.divider()
                    st.write(f"**{selected_commodity} Price Action**")
                    
                    # Period Selector
                    period_map = {
                        "1D": {"period": "1d", "interval": "5m"},
                        "2D": {"period": "2d", "interval": "15m"},
                        "5D": {"period": "5d", "interval": "1h"},
                        "6M": {"period": "6mo", "interval": "1d"},
                        "1Y": {"period": "1y", "interval": "1d"}
                    }
                    
                    # Store selected period in session state to persist across interactions
                    if "chart_period" not in st.session_state:
                        st.session_state.chart_period = "5D"
                        
                    cols_p = st.columns(len(period_map))
                    for i, p in enumerate(period_map.keys()):
                        if cols_p[i].button(p, use_container_width=True, type="primary" if st.session_state.chart_period == p else "secondary"):
                            st.session_state.chart_period = p
                            st.rerun()

                    ticker = TICKERS.get(selected_commodity)
                    try:
                        p_params = period_map[st.session_state.chart_period]
                        hist = yf.download(ticker, period=p_params["period"], interval=p_params["interval"], progress=False, threads=False)
                        if not hist.empty:
                            if isinstance(hist.columns, pd.MultiIndex):
                                hist.columns = hist.columns.get_level_values(0)
                            
                            # Line chart for most, Area chart specifically for 1Y
                            if st.session_state.chart_period == "1Y":
                                st.area_chart(hist['Close'], use_container_width=True)
                            else:
                                st.line_chart(hist['Close'], use_container_width=True)
                    except Exception as e:
                        st.error(f"Error: {e}")
                else:
                    st.info("No report data available.")

            # Timeline of News Failures
            st.divider()
            st.subheader(f"Timeline of {selected_commodity.capitalize()} Reports")
            
            # Highlight selected in timeline
            df_sub_full['is_selected'] = pd.to_datetime(df_sub_full['release_date']).dt.date == selected_date if selected_date else False
            timeline = alt.Chart(df_sub_full).mark_bar().encode(
                x=alt.X('release_date:T', title='Release Date'),
                y=alt.Y('return_1d:Q', title='Market Reaction (%)', axis=alt.Axis(format='%')),
                color=alt.condition(
                    alt.datum.is_selected,
                    alt.value('orange'), # Highlight selected
                    alt.Color('news_failure:N', scale=alt.Scale(domain=['YES', 'NO'], range=['red', 'steelblue']))
                ),
                tooltip=[
                    alt.Tooltip('release_date:T', title='Release Date', format='%Y-%m-%d'),
                    alt.Tooltip('surprise_percent:Q', title='Surprise %', format='.4f'),
                    alt.Tooltip('return_1d:Q', title='Return 1D', format='.4%'),
                    alt.Tooltip('news_failure_label:N', title='Status')
                ]
            ).properties(height=300).interactive()
            
            st.altair_chart(timeline, use_container_width=True)
            st.caption("Red bars signify historical days where the market failed to react as expected to the news (News Failure). Blue bars are aligned reactions. Orange highlights your current selection.")

            st.subheader("Historical Reactions")
            display_cols = ['release_date', 'surprise_percent', 'return_1d', 'news_failure', 'reason', 'summary']
            df_hist = df_sub[display_cols].copy()
            
            # Format date for display
            df_hist['release_date'] = pd.to_datetime(df_hist['release_date']).dt.strftime('%Y-%m-%d')
            
            # Update news_failure to be more descriptive if it's a failure
            df_hist['news_failure'] = df_hist.apply(
                lambda x: f"Yes: {str(x['reason']).replace('Failure-', 'Failure - ')}" if x['news_failure'] == 'YES' and x['reason'] != 'N/A' else x['news_failure'],
                axis=1
            )
            df_hist = df_hist.drop(columns=['reason'])
            df_hist = df_hist.rename(columns={'news_failure': 'News Failure - Status'})
            
            st.dataframe(df_hist.style.format({
                'return_1d': "{:.4%}",
                'surprise_percent': "{:.4f}%"
            }), use_container_width=True)
        else:
            st.info(f"No data available for {selected_commodity}.")

elif view == "Economic Event Failures":
    st.header("📈 Economic Event News Failures") # the current system doesnt have release time for the app

    
    data = fetch_data("economic-failures")
    if data is not None:
        if isinstance(data, dict) and "error" in data:
            st.error(f"Backend Error: {data['error']}")
        else:
            df = pd.DataFrame(data)


            # Apply Date Filter
            if selected_date:
                df['release_date_dt'] = pd.to_datetime(df['release_date']).dt.date
                df = df[df['release_date_dt'] == selected_date]
            
            if not df.empty:
                # Create the descriptive "Yes: News Failure - ..." label
                if 'news_failure' in df.columns and 'reason' in df.columns:
                    df['news_failure'] = df.apply(
                        lambda x: f"Yes: {str(x['reason']).replace('Failure-', 'Failure - ')}" if str(x['news_failure']).upper() == 'YES' and x['reason'] != 'N/A' else x['news_failure'],
                        axis=1
                    )
                
                # Format release date
                if 'release_date' in df.columns:
                    df['release_date'] = pd.to_datetime(df['release_date']).dt.strftime('%Y-%m-%d')
                    # df['release_date'] = pd.to_datetime(df['release_date']).dt.strftime('%b %d, %Y %I:%M %p')

                
                # Rename for clearer display
                rename_map = {}
                if 'news_failure' in df.columns:
                    rename_map['news_failure'] = 'News Failure - Status'
                if 'release_time' in df.columns:
                    rename_map['release_time'] = 'News Release Time'
                if rename_map:
                    df = df.rename(columns=rename_map)
                
                # Drop id and reason columns for cleaner look
                cols_to_drop = ['id', 'reason', 'release_date_dt']
                df = df.drop(columns=[c for c in cols_to_drop if c in df.columns])

                st.dataframe(df.style.format({
                    'return_1d': "{:.4%}",
                    'actual': "{:.2f}",
                    'forecast': "{:.2f}",
                    'price_before': "{:.2f}",
                    'price_after': "{:.2f}"
                }), use_container_width=True)
            else:
                st.info("No economic failures detected yet.")
    else:
        st.warning("No economic failures found or API is offline.")

elif view == "Market Monitor": 
    st.header("🕒 Real-time Monitor (Recent Events)")
    st.info("Showing market reactions from the last 24 hours.")
    
    data = fetch_data("realtime-monitor")
    if data is not None:
        if isinstance(data, dict) and "error" in data:
            st.error(f"API Error: {data['error']}")
        else:
            df = pd.DataFrame(data)
            # Fetch latest status for pulse badges
            latest_wasde_status = fetch_latest_wasde_status() 

            if not df.empty:
                # Vertical stacking: Each section gets full width
                wasde_day = df[df['type'] == 'WASDE']
                if not wasde_day.empty:
                    st.subheader("🌾 Commodity Releases")
                    # Use columns to keep metrics compact within the vertical section
                    for i in range(0, len(wasde_day), 3):
                        chunk = wasde_day.iloc[i:i+3]
                        cols = st.columns(3)
                        for j, (_, row) in enumerate(chunk.iterrows()):
                            with cols[j]:
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
                        
                    st.subheader("📈 Economic Releases") 
                    # Drop duplicates based on the pre-formatted name and price
                    econ_day = econ_day.drop_duplicates(subset=['name', 'price'])
                    # Use columns to keep metrics compact within the vertical section
                    for i in range(0, len(econ_day), 3):
                        chunk = econ_day.iloc[i:i+3]
                        cols = st.columns(3)
                        for j, (_, row) in enumerate(chunk.iterrows()):
                            with cols[j]:
                                # Highlight failures with inverse color logic
                                color = "normal" if str(row['news_failure']).upper() == 'NO' else "inverse"
                                # name is already formatted as "Event (Instrument)" by the API
                                st.metric(f"{row['name']}", f"{row['price']:.2f}", f"{row['return_1d']:.4%}", delta_color=color)
                                
                                if str(row['news_failure']).upper() == 'YES':
                                    label = row.get('reason')
                                    if not label or label == 'N/A' or label == '':
                                        label = "News Failure"
                                    st.markdown(f"**:red[{label}]**")
                
                if wasde_day.empty and econ_day.empty:
                    st.info("No recent reports in the last 24-48 hours.")
                
                # Add a "Real-Time Ticker" at the bottom
                st.divider()
                st.subheader("Live Market Pulse")
                
                pulse_data = fetch_pulse_data(TICKERS)
            
                # Render pulse data in rows of 5
                ticker_items = list(TICKERS.items())
                for i in range(0, len(ticker_items), 5):
                    chunk = ticker_items[i:i+5]
                    cols = st.columns(len(chunk))
                    for j, (name, ticker) in enumerate(chunk):
                        with cols[j]:
                            try:
                                if pulse_data is not None:
                                    if ticker in pulse_data.columns.get_level_values(0):
                                        ticker_df = pulse_data[ticker].dropna()
                                        if not ticker_df.empty:
                                            last_p = float(ticker_df['Close'].iloc[-1])
                                            prev_p = float(ticker_df['Close'].iloc[-2]) if len(ticker_df) > 1 else last_p
                                            change = (last_p - prev_p) / prev_p if len(ticker_df) > 1 else 0
                                            st.metric(name, f"{last_p:.2f}", f"{change:.4%}")
                                            
                                            # Add News Failure Badge
                                            db_name = DB_NAME_MAP.get(name, name.lower())
                                            status = latest_wasde_status.get(db_name)
                                            if status and status.get('news_failure') == 'YES':
                                                label = status.get('reason')
                                                if not label or "News Failure" not in label:
                                                    label = "News Failure-Bullish" if status['news_sentiment'] == 'Bearish' else "News Failure-Bearish"
                                                st.markdown(f"**:red[{label}]**")
                                                fail_date = status.get('release_date')
                                                if fail_date:
                                                    st.caption(f"Identified: {pd.to_datetime(fail_date).strftime('%b %d, %Y %I:%M %p')}")
                                        else:
                                            st.write(f"**{name}**")
                                            st.caption("No price data")
                                    else:
                                        st.write(f"**{name}**")
                                        st.caption("Ticker missing")
                                else:
                                    st.write(f"**{name}**")
                            except Exception as e:
                                st.write(f"**{name}**")
                                # st.caption(f"Error: {e}")

            else:
                st.write("No active news events today. Showing general market pulse:")
                pulse_data = fetch_pulse_data(TICKERS)
                ticker_items = list(TICKERS.items())
                for i in range(0, len(ticker_items), 5):
                    chunk = ticker_items[i:i+5]
                    cols = st.columns(len(chunk))
                    for j, (name, ticker) in enumerate(chunk):
                        with cols[j]:
                            if pulse_data is not None:
                                try:
                                    if ticker in pulse_data.columns.get_level_values(0):
                                        ticker_df = pulse_data[ticker].dropna()
                                        if not ticker_df.empty:
                                            last_p = float(ticker_df['Close'].iloc[-1])
                                            st.metric(name, f"{last_p:.2f}")
                                            
                                            # Add News Failure Badge
                                            db_name = DB_NAME_MAP.get(name, name.lower())
                                            status = latest_wasde_status.get(db_name)
                                            if status and status.get('news_failure') == 'YES':
                                                label = status.get('reason')
                                                if not label or "News Failure" not in label:
                                                    label = "News Failure-Bullish" if status['news_sentiment'] == 'Bearish' else "News Failure-Bearish"
                                                st.markdown(f"**:red[{label}]**")
                                                fail_date = status.get('release_date')
                                                if fail_date:
                                                    st.caption(f"Identified: {pd.to_datetime(fail_date).strftime('%b %d, %Y %I:%M %p')}")
                                        else:
                                            st.write(f"**{name}**")
                                    else:
                                        st.write(f"**{name}**")
                                except:
                                    st.write(f"**{name}**")
                            else:
                                st.write(f"**{name}**")
    else:
        st.error("Failed to fetch real-time monitoring data.")

# Footer
st.sidebar.markdown("---")
# Convert to EST/EDT (Eastern Time)
est = pytz.timezone('America/New_York')
last_sync = datetime.datetime.now(est).strftime('%Y-%m-%d %H:%M')
st.sidebar.write(f"Last sync: {last_sync} EST")
