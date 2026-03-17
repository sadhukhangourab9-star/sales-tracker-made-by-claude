# OrderTrack — Mobile Sales Order Tracker

A Flask web application to track online platform orders with credit card data for mobile resale businesses.

## Features

- **Main Orders** — Full order tracking: card type (auto-fill), last digits, platform, account, order name, model, variant, costing, delivery date
- **Secondary Orders** — Simplified order entries: card, platform, model, variant, costing
- **Settings Portal** — Manage cards, platforms/accounts, mobile models and variants
- **Smart Auto-fill** — Card type auto-fills when you enter last digits; variant dropdown auto-loads on model entry
- **Date/Time** — Auto-stamped on creation
- **Edit** — All records fully editable via modal
- **Bulk Delete** — Select multiple records and delete at once
- **Export** — Download as CSV or Excel (.xlsx)
- **Search** — Live search/filter across all fields

## Local Setup

```bash
git clone <your-repo-url>
cd order-tracker

# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py
```

Open http://localhost:5000

## Deploy to Render

1. Push this repo to GitHub
2. Create a new account at [render.com](https://render.com)
3. Click **New → Web Service** → connect your GitHub repo
4. Render auto-detects `render.yaml` — just click **Create Web Service**

> **Important**: The `render.yaml` includes a persistent disk at `/var/data` for the SQLite database. This keeps your data safe across deployments.

## Usage Guide

### First-time Setup (Settings page)
1. **Add Cards** — Enter last 4–5 digits and card type (Visa, Mastercard, etc.)
2. **Add Platforms** — Enter platform name (Amazon, Flipkart, etc.) and account name
3. **Add Models** — Enter mobile model names
4. **Add Variants** — Select a model and add its storage/color variants

### Adding Orders (Main Orders page)
1. Click **Add New Order**
2. Type last digits → card type auto-fills
3. Select platform → accounts auto-populate
4. Type model name → variants dropdown loads automatically
5. Date auto-fills with today; created-at timestamps automatically

## Project Structure

```
order-tracker/
├── app.py              # Flask app + all API routes
├── requirements.txt
├── render.yaml         # Render deployment config
├── .gitignore
└── templates/
    ├── base.html           # Shared layout + sidebar
    ├── main_orders.html    # Main orders page
    ├── secondary_orders.html
    └── settings.html       # Cards, platforms, models config
```

## Tech Stack

- **Backend**: Python / Flask
- **Database**: SQLite (persistent disk on Render)
- **Frontend**: Bootstrap 5 + Vanilla JS
- **Export**: openpyxl (Excel), csv (CSV)
