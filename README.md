# OrderTrack — Mobile Sales ERP & Dashboard (Google Sheets Edition)

A powerful, stateless Flask web application designed to track online platform orders, calculate profits, and visualize financial data for mobile resale businesses. 

**Powered entirely by Google Sheets**, this application requires no persistent local database, meaning it can be hosted 100% for free on platforms like Render.

## ✨ Key Features

* **Financial Dashboard:** Real-time visual analytics (powered by Chart.js) showing Total Spend, Total Profit, and Card Utilization, filterable by specific sales events.
* **Main & Secondary Orders:** Two distinct entry flows with full parity, tracking card details, platforms, models, variants, costing, and selling prices.
* **Profit Tracking:** Automatically calculates profit margins (Selling Price - Costing) for every single order.
* **Sale Batches:** Group orders into distinct events (e.g., "Sale 1", "Current Sale") for organized accounting and bulk management.
* **Smart Auto-Fill:** * Entering card digits automatically fetches the associated Bank Name.
  * Selecting a variant automatically populates its predetermined Cost.
* **Settings Management:** Control your predefined Cards, Platforms, Models, Variants, and Secondary Order Names.
* **High Performance:** Server-side pagination (50 items/page) ensures the app remains blazing fast even with thousands of rows of data.
* **Bulk Actions:** Select multiple orders to bulk-delete or bulk-assign them to a new Sale Batch.
* **Export:** One-click export your filtered data to CSV or Excel (.xlsx).

---

## 🛠️ Prerequisites & Google Sheets Setup

Because this app uses Google Sheets as its database, you must set up a Google Cloud Service Account before deploying.

### 1. Generate Google Credentials
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project.
3. Enable the **Google Sheets API** and **Google Drive API**.
4. Go to **APIs & Services > Credentials** and create a new **Service Account**.
5. Generate and download a **JSON Key** for this service account.

### 2. Prepare the Database (Google Sheet)
1. Create a new Google Sheet in your Google Drive. Name it `OrderTrack_DB` (or any name you prefer).
2. **Crucial:** Share this Google Sheet as an "Editor" with the `client_email` address found inside your downloaded JSON key file.
3. The app will automatically generate most tabs on startup, but ensure your **`main_orders`** and **`secondary_orders`** tabs have the following headers in Row 1 (Columns A through N):
   * `id`, `card_type`, `last_digits`, `platform`, `account` *(Main Orders only)*, `order_name`, `model`, `variant`, `costing`, `selling_price`, `profit`, `delivery_date`, `sale_batch`, `created_at`
4. Ensure you have a tab named **`sec_order_names`** with headers `id` and `name`.

---

## 🚀 Deployment (Render Free Tier)

This application is optimized for [Render's](https://render.com) Free Web Service tier.

1. Push this repository to GitHub.
2. Log into Render and click **New → Web Service**.
3. Connect your GitHub repository.
4. Render will auto-detect the `render.yaml` file.
5. Once created, go to the **Environment** tab of your Render Web Service and add the following Environment Variables:
   * **Key:** `GOOGLE_SHEET_NAME` | **Value:** `OrderTrack_DB` (Or the exact name of your sheet)
   * **Key:** `GOOGLE_CREDENTIALS_JSON` | **Value:** *(Paste the ENTIRE contents of your downloaded Service Account JSON file here)*
6. Deploy the latest commit!

---

## 📂 Project Structure

```text
order-tracker/
├── app.py              # Flask backend, APIs, and Google Sheets logic
├── requirements.txt    # Python dependencies
├── render.yaml         # Render deployment configuration
├── .gitignore
└── templates/
    ├── base.html           # Shared layout, styling, and core JS functions
    ├── dashboard.html      # Financial analytics and Chart.js visualizations
    ├── main_orders.html    # Main order entry and management table
    ├── secondary_orders.html # Secondary order entry and management table
    └── settings.html       # Configuration portal for app variables
