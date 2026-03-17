from flask import Flask, render_template, request, jsonify, send_file
import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

app = Flask(__name__)

# ── Google Sheets Setup ───────────────────────────────────────────────────────
# Load credentials from environment variable (set this in Render dashboard)
google_creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')

if google_creds_json:
    creds_dict = json.loads(google_creds_json)
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(creds)
    # Replace with your actual Google Sheet name or ID
    SHEET = gc.open("OrderTrack_DB") 
else:
    print("WARNING: No Google Credentials found.")

# Helper function to generate a fake "ID" based on row number
def get_next_id(worksheet):
    records = worksheet.get_all_records()
    if not records:
        return 1
    # Assuming the first column is 'id'
    return max([int(r.get('id', 0)) for r in records]) + 1

# ── Page Routes (Unchanged) ───────────────────────────────────────────────────
@app.route('/')
def main_orders():
    return render_template('main_orders.html')

@app.route('/settings')
def settings():
    return render_template('settings.html')

# ── Example: Main Orders API converted to Google Sheets ───────────────────────

@app.route('/api/main-orders', methods=['GET'])
def get_main_orders():
    ws = SHEET.worksheet('main_orders')
    # get_all_records automatically maps row 1 as headers
    orders = ws.get_all_records() 
    # Reverse to show newest first, matching your SQLite ORDER BY id DESC
    return jsonify(list(reversed(orders)))

@app.route('/api/main-orders', methods=['POST'])
def add_main_order():
    data = request.json
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ws = SHEET.worksheet('main_orders')
    
    new_id = get_next_id(ws)
    
    # Create the row data as a list matching your column order
    row_data = [
        new_id,
        data.get('card_type', ''),
        data.get('last_digits', ''),
        data.get('platform', ''),
        data.get('account', ''),
        data.get('order_name', ''),
        data.get('model', ''),
        data.get('variant', ''),
        data.get('costing', 0.0),
        data.get('delivery_date', ''),
        now
    ]
    
    # Append to the bottom of the sheet
    ws.append_row(row_data)
    
    # Return the created object so the frontend can display it
    created_order = dict(zip(ws.row_values(1), row_data))
    return jsonify(created_order)

@app.route('/api/main-orders/<int:order_id>', methods=['DELETE'])
def delete_main_order(order_id):
    ws = SHEET.worksheet('main_orders')
    # Find the cell in column A (column 1) that matches the ID
    cell = ws.find(str(order_id), in_column=1)
    if cell:
        ws.delete_rows(cell.row)
        return jsonify({'success': True})
    return jsonify({'error': 'Order not found'}), 404
