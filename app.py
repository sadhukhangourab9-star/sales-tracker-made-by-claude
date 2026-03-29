# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, jsonify, send_file
import os, io, json, csv, requests
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, PatternFill
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai

app = Flask(__name__)

# ── Google Sheets Setup ───────────────────────────────────────────────────────
SHEET_NAME = os.environ.get('GOOGLE_SHEET_NAME', 'OrderTrack_DB')
creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
SHEET = None

if creds_json:
    try:
        creds_dict = json.loads(creds_json)
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        SHEET = client.open(SHEET_NAME)
    except Exception as e:
        print("Failed to connect to Google Sheets: " + str(e))

# ── AI & Telegram Setup ───────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
ai_model = None

if GEMINI_API_KEY:
    # Use 4 spaces for the lines below
    genai.configure(api_key=GEMINI_API_KEY)
    ai_model = genai.GenerativeModel('gemini-2.0-flash')
# ──────────────────────────────────────────────────────────────────────────────
# FIX: A bulletproof wrapper to prevent gspread from crashing on empty/weird sheets
# ──────────────────────────────────────────────────────────────────────────────
def safe_get_records(ws):
    try:
        return ws.get_all_records()
    except Exception:
        return []

def get_next_id(ws):
    records = safe_get_records(ws)
    if not records: return 1
    return max([int(r.get('id', 0) or 0) for r in records]) + 1

# ── Page Routes ──────────────────────────────────────────────────────────────
@app.route('/')
def main_orders(): return render_template('main_orders.html')
@app.route('/secondary')
def secondary_orders(): return render_template('secondary_orders.html')
@app.route('/offline')
def offline_orders(): return render_template('offline_orders.html')
@app.route('/inventory')
def inventory(): return render_template('inventory.html')
@app.route('/dashboard')
def dashboard(): return render_template('dashboard.html')
@app.route('/settings')
def settings(): return render_template('settings.html')

# ── Settings APIs ─────────────────────────────────────────────────────────────
@app.route('/api/cards', methods=['GET', 'POST'])
def manage_cards():
    if not SHEET: return jsonify([])
    ws = SHEET.worksheet('cards')
    if request.method == 'GET':
        cards = safe_get_records(ws)
        for c in cards:
            if str(c.get('last_digits', '')).startswith("'"): c['last_digits'] = str(c['last_digits'])[1:]
        return jsonify(list(reversed(cards)))
    data = request.json
    
    safe_digits = "'" + str(data.get('last_digits', ''))
    ws.append_row([get_next_id(ws), data.get('card_type', ''), safe_digits])
    return jsonify({'success': True})

@app.route('/api/cards/<int:card_id>', methods=['DELETE'])
def delete_card(card_id):
    if not SHEET: return jsonify({'success': False})
    try:
        ws = SHEET.worksheet('cards')
        ws.delete_row(ws.find(str(card_id), in_column=1).row)
    except: pass
    return jsonify({'success': True})

def handle_master_table(table_name, req, field_name='name'):
    if not SHEET: return jsonify([])
    ws = SHEET.worksheet(table_name)
    if req.method == 'GET': return jsonify(safe_get_records(ws))
    ws.append_row([get_next_id(ws), req.json.get(field_name, '')])
    return jsonify({'success': True})

def delete_master_table(table_name, item_id):
    if not SHEET: return jsonify({'success': False})
    try:
        ws = SHEET.worksheet(table_name)
        ws.delete_row(ws.find(str(item_id), in_column=1).row)
    except: pass
    return jsonify({'success': True})

@app.route('/api/platforms', methods=['GET', 'POST'])
def api_platforms(): return handle_master_table('platforms', request, 'platform_name')
@app.route('/api/platforms/<int:id>', methods=['DELETE'])
def api_del_platforms(id): return delete_master_table('platforms', id)

@app.route('/api/models', methods=['GET', 'POST'])
def api_models(): return handle_master_table('models', request, 'model_name')
@app.route('/api/models/<int:id>', methods=['DELETE'])
def api_del_models(id): return delete_master_table('models', id)

@app.route('/api/sec-order-names', methods=['GET', 'POST'])
def api_sec_names(): return handle_master_table('sec_order_names', request, 'name')
@app.route('/api/sec-order-names/<int:id>', methods=['DELETE'])
def api_del_sec_names(id): return delete_master_table('sec_order_names', id)

@app.route('/api/machines', methods=['GET', 'POST'])
def api_machines(): return handle_master_table('machines', request, 'name')
@app.route('/api/machines/<int:id>', methods=['DELETE'])
def api_del_machines(id): return delete_master_table('machines', id)

@app.route('/api/vendors', methods=['GET', 'POST'])
def api_vendors(): return handle_master_table('vendors', request, 'name')
@app.route('/api/vendors/<int:id>', methods=['DELETE'])
def api_del_vendors(id): return delete_master_table('vendors', id)

@app.route('/api/brands', methods=['GET', 'POST'])
def api_brands(): return handle_master_table('brands', request, 'name')
@app.route('/api/brands/<int:id>', methods=['DELETE'])
def api_del_brands(id): return delete_master_table('brands', id)

@app.route('/api/variants', methods=['GET', 'POST'])
def api_variants():
    if not SHEET: return jsonify([])
    ws = SHEET.worksheet('variants')
    if request.method == 'GET':
        model_name = request.args.get('model')
        all_variants = safe_get_records(ws)
        
        if model_name:
            # Get models to find the ID of the selected model name
            models_ws = SHEET.worksheet('models')
            models_data = safe_get_records(models_ws)
            
            # Find the ID for the model name (checking 'model_name' or 'name' columns)
            m_id = next((m.get('id') for m in models_data if (m.get('model_name') == model_name or m.get('name') == model_name)), None)
            
            if m_id:
                # Filter variants that match this model_id
                filtered = [v for v in all_variants if str(v.get('model_id')) == str(m_id)]
                return jsonify(filtered)
            return jsonify([]) # Return nothing if model ID wasn't found
            
        return jsonify(all_variants)
    
    # POST logic for adding new variants
    data = request.json
    ws.append_row([get_next_id(ws), data.get('model_id'), data.get('variant_name', ''), data.get('costing', '')])
    return jsonify({'success': True})
@app.route('/api/variants/<int:var_id>', methods=['DELETE'])
def del_variant(var_id): return delete_master_table('variants', var_id)

# ── Main Orders API ───────────────────────────────────────────────────────────
@app.route('/api/main-orders', methods=['GET', 'POST'])
def api_main_orders():
    if not SHEET: return jsonify([])
    ws = SHEET.worksheet('main_orders')
    if request.method == 'GET':
        orders = safe_get_records(ws)
        for o in orders:
            if str(o.get('last_digits', '')).startswith("'"): o['last_digits'] = str(o['last_digits'])[1:]
            if str(o.get('account', '')).startswith("'"): o['account'] = str(o['account'])[1:]
        return jsonify(list(reversed(orders)))
    
    data = request.json
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    last_digits = str(data.get('last_digits', ''))
    costing = float(data.get('costing') or 0)
    selling_price = float(data.get('selling_price') or 0)
    
    safe_digits = "'" + last_digits if last_digits else ""
    
    row = [
        get_next_id(ws), data.get('card_type', ''), safe_digits, data.get('platform', ''), 
        data.get('account', ''), data.get('order_name', ''), data.get('model', ''), data.get('variant', ''), 
        costing, selling_price, selling_price - costing, data.get('delivery_date', ''), data.get('sale_batch', 'Current Sale'), now
    ]
    ws.append_row(row)
    row[2] = last_digits
    return jsonify(dict(zip(ws.row_values(1), row)))

@app.route('/api/main-orders/<int:id>', methods=['DELETE'])
def del_main(id): return delete_master_table('main_orders', id)

@app.route('/api/main-orders/bulk-update-batch', methods=['POST'])
def bulk_update_batch():
    if not SHEET: return jsonify({'success': False})
    data = request.json
    ids = data.get('ids', [])
    new_batch = data.get('batch', 'Current Sale')
    
    ws = SHEET.worksheet('main_orders')
    records = safe_get_records(ws)
    
    # Find the row index for each ID and update the 'sale_batch' column (Column 13 / M)
    for i, r in enumerate(records):
        if r.get('id') in ids:
            row_idx = i + 2  # +2 because of header row and 0-indexing
            ws.update_cell(row_idx, 13, new_batch)
            
    return jsonify({'success': True})

# Add this for the Edit functionality
@app.route('/api/main-orders/<int:id>', methods=['PUT'])
def update_order(id):
    if not SHEET: return jsonify({'success': False})
    data = request.json
    ws = SHEET.worksheet('main_orders')
    try:
        cell = ws.find(str(id), in_column=1)
        # Update specific columns (Costing: 9, Selling: 10, Batch: 13, etc.)
        ws.update_cell(cell.row, 9, data.get('costing', 0))
        ws.update_cell(cell.row, 10, data.get('selling_price', 0))
        ws.update_cell(cell.row, 13, data.get('sale_batch', 'Current Sale'))
        return jsonify({'success': True})
    except:
        return jsonify({'success': False})

# ── Secondary Orders API ──────────────────────────────────────────────────────
@app.route('/api/secondary-orders', methods=['GET', 'POST'])
def api_secondary_orders():
    if not SHEET: return jsonify([])
    ws = SHEET.worksheet('secondary_orders')
    if request.method == 'GET':
        orders = safe_get_records(ws)
        for o in orders:
            if str(o.get('last_digits', '')).startswith("'"): o['last_digits'] = str(o['last_digits'])[1:]
        return jsonify(list(reversed(orders)))
    
    data = request.json
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    last_digits = str(data.get('last_digits', ''))
    costing = float(data.get('costing') or 0)
    selling_price = float(data.get('selling_price') or 0)
    
    safe_digits = "'" + last_digits if last_digits else ""
    
    row = [
        get_next_id(ws), data.get('card_type', ''), safe_digits, data.get('platform', ''), 
        data.get('order_name', ''), data.get('model', ''), data.get('variant', ''), 
        costing, selling_price, selling_price - costing, data.get('delivery_date', ''), data.get('sale_batch', 'Current Sale'), now
    ]
    ws.append_row(row)
    row[2] = last_digits
    return jsonify(dict(zip(ws.row_values(1), row)))

@app.route('/api/secondary-orders/bulk-update-batch', methods=['POST'])
def bulk_update_secondary_batch():
    if not SHEET: return jsonify({'success': False})
    data = request.json
    ids = data.get('ids', [])
    new_batch = data.get('batch', 'Current Sale')
    ws = SHEET.worksheet('secondary_orders')
    records = safe_get_records(ws)
    for i, r in enumerate(records):
        if r.get('id') in ids:
            ws.update_cell(i + 2, 13, new_batch) # Column M
    return jsonify({'success': True})

@app.route('/api/secondary-orders/<int:id>', methods=['PUT'])
def update_secondary_order(id):
    if not SHEET: return jsonify({'success': False})
    data = request.json
    ws = SHEET.worksheet('secondary_orders')
    try:
        cell = ws.find(str(id), in_column=1)
        ws.update_cell(cell.row, 9, data.get('costing', 0))
        ws.update_cell(cell.row, 10, data.get('selling_price', 0))
        ws.update_cell(cell.row, 13, data.get('sale_batch', 'Current Sale'))
        return jsonify({'success': True})
    except:
        return jsonify({'success': False})

@app.route('/api/secondary-orders/<int:id>', methods=['DELETE'])
def del_sec(id): return delete_master_table('secondary_orders', id)

# ── Offline Orders API ────────────────────────────────────────────────────────
@app.route('/api/offline-orders', methods=['GET', 'POST'])
def api_offline_orders():
    if not SHEET: return jsonify([])
    ws = SHEET.worksheet('offline_orders')
    if request.method == 'GET':
        orders = safe_get_records(ws)
        for o in orders:
            if str(o.get('last_digits', '')).startswith("'"): o['last_digits'] = str(o['last_digits'])[1:]
        return jsonify(list(reversed(orders)))
    
    data = request.json
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    last_digits = str(data.get('last_digits', ''))
    costing = float(data.get('costing') or 0)
    selling_price = float(data.get('selling_price') or 0)
    
    safe_digits = "'" + last_digits if last_digits else ""
    
    row = [
        get_next_id(ws), data.get('card_type', ''), safe_digits, 
        data.get('machine', ''), data.get('vendor', ''), data.get('brand', ''), data.get('sale_type', ''),
        costing, selling_price, selling_price - costing, data.get('sale_month', ''), now
    ]
    ws.append_row(row)
    row[2] = last_digits
    return jsonify(dict(zip(ws.row_values(1), row)))

@app.route('/api/offline-orders/<int:id>', methods=['DELETE'])
def del_offline(id): return delete_master_table('offline_orders', id)

@app.route('/api/offline-orders/bulk-delete', methods=['POST'])
def bulk_del_offline():
    if not SHEET: return jsonify({'success': False})
    ids = request.json.get('ids', [])
    ws = SHEET.worksheet('offline_orders')
    
    # Safe fetch for bulk deletion too
    records = safe_get_records(ws)
    rows_to_delete = [i + 2 for i, r in enumerate(records) if r.get('id') in ids]
    
    for r_idx in sorted(rows_to_delete, reverse=True): 
        ws.delete_row(r_idx)
    return jsonify({'success': True})

# ── TELEGRAM AI AGENT WEBHOOK ─────────────────────────────────────────────────
@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    update = request.get_json(silent=True)
    
    if not update or "message" not in update or "text" not in update["message"]:
        return jsonify({"status": "ok"})
        
    chat_id = update["message"]["chat"]["id"]
    text = str(update["message"]["text"])
    bot_url = "https://api.telegram.org/bot" + str(TELEGRAM_BOT_TOKEN) + "/sendMessage"
    
    if text == "/start":
        start_msg = "OrderTrack AI is online! Send me a messy sale text and I will log it."
        requests.post(bot_url, json={"chat_id": chat_id, "text": start_msg})
        return jsonify({"status": "ok"})

    try:
        prompt = "You are a data extraction bot for a mobile phone business. Extract the offline sale details from the text below.\n"
        prompt += "Format the output ONLY as a valid JSON object. Do not include markdown formatting or backticks.\n"
        prompt += "Required JSON keys:\n"
        prompt += "- \"last_digits\" (string, just the numbers)\n"
        prompt += "- \"card_type\" (string, e.g., SBI, HDFC)\n"
        prompt += "- \"machine\" (string)\n"
        prompt += "- \"vendor\" (string)\n"
        prompt += "- \"brand\" (string, e.g., iPhone 15)\n"
        prompt += "- \"sale_type\" (string: must be either INSTANT or EMI)\n"
        prompt += "- \"costing\" (number, digits only)\n"
        prompt += "- \"selling_price\" (number, digits only)\n\n"
        prompt += "Text: \"" + text + "\""
        
        response = ai_model.generate_content(prompt)
        
        raw_text = response.text.strip()
        
        bt = chr(96) + chr(96) + chr(96) 
        
        if raw_text.startswith(bt + "json"): 
            raw_text = raw_text[7:]
        elif raw_text.startswith(bt): 
            raw_text = raw_text[3:]
        if raw_text.endswith(bt): 
            raw_text = raw_text[:-3]
            
        parsed_data = json.loads(raw_text.strip())

        if not SHEET:
            raise Exception("Google Sheets not configured.")

        ws = SHEET.worksheet('offline_orders')
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        sale_month = datetime.now().strftime('%Y-%m')
        
        costing = float(parsed_data.get('costing') or 0)
        selling_price = float(parsed_data.get('selling_price') or 0)
        profit = selling_price - costing
        
        sheet_last_digits = "'" + str(parsed_data.get('last_digits', ''))
        
        row = [
            get_next_id(ws),
            parsed_data.get('card_type', 'UNKNOWN'),
            sheet_last_digits,
            parsed_data.get('machine', 'UNKNOWN'),
            parsed_data.get('vendor', 'UNKNOWN'),
            parsed_data.get('brand', 'UNKNOWN'),
            parsed_data.get('sale_type', 'INSTANT').upper(),
            costing,
            selling_price,
            profit,
            sale_month,
            now
        ]
        ws.append_row(row)

        b_text = str(parsed_data.get('brand', 'N/A'))
        c_type = str(parsed_data.get('card_type', 'N/A'))
        l_dig = str(parsed_data.get('last_digits', 'N/A'))
        p_val = "{:.2f}".format(profit)
        
        reply_msg = "SUCCESS: Sale Logged to Cloud\n\n"
        reply_msg += "Brand: " + b_text + "\n"
        reply_msg += "Card: " + c_type + " (" + l_dig + ")\n"
        reply_msg += "Profit: INR " + p_val
        
        requests.post(bot_url, json={"chat_id": chat_id, "text": reply_msg})

    except Exception as e:
        error_msg = "Error processing sale: " + str(e)
        requests.post(bot_url, json={"chat_id": chat_id, "text": error_msg})

    return jsonify({"status": "ok"})

# ── PWA Setup ─────────────────────────────────────────────────────────────────
@app.route('/manifest.json')
def serve_manifest(): return send_file('static/manifest.json', mimetype='application/manifest+json')
@app.route('/sw.js')
def serve_sw(): return send_file('static/sw.js', mimetype='application/javascript')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
