# WASDE: Advanced News Failure Detection Platform

WASDE (World Agricultural Supply and Demand Estimates) Intelligence is a sophisticated market analysis platform designed to identify **"News Failures"**—powerful market anomalies where price action moves in the opposite direction of fundamental news surprises.

## 🚀 The Core Philosophy: "News Failure"
In a standard market, bullish news (e.g., lower supply) should lead to higher prices. A **News Failure** occurs when bullish news leads to lower prices, or bearish news leads to higher prices. These divergences often signal institutional positioning and impending trend reversals.

---

## 🏗️ System Architecture

### 1. Fundamental Intelligence Flows
*   **Commodity Flow (WASDE)**:
    *   **Automation**: Scrapers for USDA WASDE reports (XML/TXT) from 2020-2026.
    *   **Precision Parsing**: Extracts U.S. and World 'Ending Stocks' for Corn, Soybeans, Wheat, Cotton, and Sugar.
    *   **Sentiment Engine**: Calculates Supply Surprises vs. Forecasts and assigns raw sentiment.
*   **Macroeconomic Flow (Investing.com)**:
    *   **Broad Coverage**: 50+ tier-1 indicators (CPI, NFP, GDP, FED, Retail Sales).
    *   **Instrument Correlation**: Maps macro surprises to correlated assets (S&P 500, 10Y Treasuries, USD Index, Crude Oil).

### 2. The Analytical Engine
*   **Failure Logic**: Cross-references fundamental sentiment with 1-day post-release price returns.
*   **Automated Summaries**: Generates natural language report takeaways (e.g., *"Soybean stocks fell by 5M bushels (-2.1%) while market dropped 1% -> News Failure Detected"*).
*   **Database**: Dual support for local SQLite (`wasde.db`) and Cloud PostgreSQL (Neon).

### 3. Visualization Suite (Streamlit)
*   **Quadrant Analysis**: Scatter plots mapping Surprise vs. Price Return to visualize failure clusters.
*   **Failure Timeline**: Interactive bar charts showing the historical sequence of report reactions.
*   **Live Market Pulse**: Real-time price monitoring using Yahoo Finance with optimized bulk-fetching and caching.

---

## 🛠️ Tech Stack
*   **Backend**: Python 3.12, FastAPI.
*   **Frontend**: Streamlit, Altair (Charting).
*   **Data Science**: Pandas, NumPy, SQLAlchemy.
*   **Scraping**: Cloudscraper, BeautifulSoup4.
*   **Deployment**: Vercel (Serverless), Neon (Postgres).

---

## 📂 Project Structure
```text
wasde/
├── api/                # Vercel Serverless Functions (FastAPI)
├── src/                # Core Application Logic
│   ├── dashboard.py    # Streamlit UI
│   ├── market_analysis.py # Calculation Engine
│   ├── wasde_scraper.py   # USDA Scrapers
│   └── macro_scraper.py   # Macro Scrapers
├── tests/              # Diagnostic and Validation Scripts
├── data/               # Local SQLite Storage
├── Makefile            # Automation Shortcuts
└── requirements.txt    # Production Dependencies
```

---

## 📋 Getting Started

### 1. Installation
```bash
make setup
```

### 2. Running the Data Pipeline
```bash
# Initialize DB, Scrape data, and Analyze reactions
make run-all
```

### 3. Launching the Interfaces
```bash
# Start FastAPI Backend (localhost:8000)
make api

# Start Streamlit Dashboard (localhost:8501)
make dashboard
```

---

## 🌐 Deployment

### 1. AWS Deployment (52.90.166.187)
The platform is ready for deployment on the dedicated AWS EC2 instance:
1. SSH into the instance.
2. Clone the repository.
3. Run the automated setup script:
   ```bash
   bash aws_setup.sh
   ```
   *This script handles system dependencies, creates systemd services, and starts both the API (Port 8000) and Dashboard (Port 8501).*

### 2. Cloud-Serverless Deployment (Vercel)
The platform is also optimized for **Vercel**:
1. Connect this repo to Vercel.
2. Set `DATABASE_URL` as an environment variable (PostgreSQL).
3. Deployment is automatic on `git push`.

---
*Developed for Identifying Institutional Trading Opportunities via Fundamental Divergence.*
