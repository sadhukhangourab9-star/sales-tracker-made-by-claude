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
        print(f"Failed to connect to Google Sheets: {e}")

# ── AI & Telegram Setup ───────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
ai_model = None

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    # Using the fast Flash model and forcing it to only return JSON data
    ai_model = genai.GenerativeModel('gemini-1.5-flash')

def get_next_id(ws):
    records = ws.get_all_records()
    if not records: return 1
    return max([int(r.get('id', 0)) for r in records]) + 1

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
        cards = ws.get_all_records()
        for c in cards:
            if str(c.get('last_digits', '')).startswith("'"): c['last_digits'] = str(c['last_digits'])[1:]
        return jsonify(list(reversed(cards)))
    data = request.json
    ws.append_row([get_next_id(ws), data.get('card_type', ''), f"'{data.get('last_digits', '')}"])
    return jsonify({'success': True})

@app.route('/api/cards/<int:card_id>', methods=['DELETE'])
def delete_card(card_id):
    try:
        ws = SHEET.worksheet('cards')
        ws.delete_rows(ws.find(str(card_id), in_column=1).row)
    except: pass
    return jsonify({'success': True})

def handle_master_table(table_name, req, field_name='name'):
    if not SHEET: return jsonify([])
    ws = SHEET.worksheet(table_name)
    if req.method == 'GET': return jsonify(ws.get_all_records())
    ws.append_row([get_next_id(ws), req.json.get(field_name, '')])
    return jsonify({'success': True})

def delete_master_table(table_name, item_id):
    try:
        ws = SHEET.worksheet(table_name)
        ws.delete_rows(ws.find(str(item_id), in_column=1).row)
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
        variants = ws.get_all_records()
        if model_name:
            models = SHEET.worksheet('models').get_all_records()
            m_id = next((m['id'] for m in models if m['model_name'] == model_name), None)
            return jsonify([v for v in variants if v['model_id'] == m_id]) if m_id else jsonify([])
        return jsonify(variants)
    ws.append_row([get_next_id(ws), request.json.get('model_id'), request.json.get('variant_name', ''), request.json.get('costing', '')])
    return jsonify({'success': True})
@app.route('/api/variants/<int:var_id>', methods=['DELETE'])
def del_variant(var_id): return delete_master_table('variants', var_id)

# ── Main Orders API ───────────────────────────────────────────────────────────
@app.route('/api/main-orders', methods=['GET', 'POST'])
def api_main_orders():
    ws = SHEET.worksheet('main_orders')
    if request.method == 'GET':
        orders = ws.get_all_records()
        for o in orders:
            if str(o.get('last_digits', '')).startswith("'"): o['last_digits'] = str(o['last_digits'])[1:]
            if str(o.get('account', '')).startswith("'"): o['account'] = str(o['account'])[1:]
        return jsonify(list(reversed(orders)))
    
    data = request.json
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    last_digits = str(data.get('last_digits', ''))
    costing, selling_price = float(data.get('costing') or 0), float(data.get('selling_price') or 0)
    
    row = [get_next_id(ws), data.get('card_type', ''), f"'{last_digits}" if last_digits else "", data.get('platform', ''), 
           data.get('account', ''), data.get('order_name', ''), data.get('model', ''), data.get('variant', ''), 
           costing, selling_price, selling_price - costing, data.get('delivery_date', ''), data.get('sale_batch', 'Current Sale'), now]
    ws.append_row(row)
    row[2] = last_digits
    return jsonify(dict(zip(ws.row_values(1), row)))
@app.route('/api/main-orders/<int:id>', methods=['DELETE'])
def del_main(id): return delete_master_table('main_orders', id)

# ── Secondary Orders API ──────────────────────────────────────────────────────
@app.route('/api/secondary-orders', methods=['GET', 'POST'])
def api_secondary_orders():
    ws = SHEET.worksheet('secondary_orders')
    if request.method == 'GET':
        orders = ws.get_all_records()
        for o in orders:
            if str(o.get('last_digits', '')).startswith("'"): o['last_digits'] = str(o['last_digits'])[1:]
        return jsonify(list(reversed(orders)))
    
    data = request.json
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    last_digits = str(data.get('last_digits', ''))
    costing, selling_price = float(data.get('costing') or 0), float(data.get('selling_price') or 0)
    
    row = [get_next_id(ws), data.get('card_type', ''), f"'{last_digits}" if last_digits else "", data.get('platform', ''), 
           data.get('order_name', ''), data.get('model', ''), data.get('variant', ''), 
           costing, selling_price, selling_price - costing, data.get('delivery_date', ''), data.get('sale_batch', 'Current Sale'), now]
    ws.append_row(row)
    row[2] = last_digits
    return jsonify(dict(zip(ws.row_values(1), row)))
@app.route('/api/secondary-orders/<int:id>', methods=['DELETE'])
def del_sec(id): return delete_master_table('secondary_orders', id)

# ── Offline Orders API ────────────────────────────────────────────────────────
@app.route('/api/offline-orders', methods=['GET', 'POST'])
def api_offline_orders():
    ws = SHEET.worksheet('offline_orders')
    if request.method == 'GET':
        orders = ws.get_all_records()
        for o in orders:
            if str(o.get('last_digits', '')).startswith("'"): o['last_digits'] = str(o['last_digits'])[1:]
        return jsonify(list(reversed(orders)))
    
    data = request.json
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    last_digits = str(data.get('last_digits', ''))
    costing, selling_price = float(data.get('costing') or 0), float(data.get('selling_price') or 0)
    
    row = [get_next_id(ws), data.get('card_type', ''), f"'{last_digits}" if last_digits else "", 
           data.get('machine', ''), data.get('vendor', ''), data.get('brand', ''), data.get('sale_type', ''),
           costing, selling_price, selling_price - costing, data.get('sale_month', ''), now]
    ws.append_row(row)
    row[2] = last_digits
    return jsonify(dict(zip(ws.row_values(1), row)))

@app.route('/api/offline-orders/<int:id>', methods=['DELETE'])
def del_offline(id): return delete_master_table('offline_orders', id)
@app.route('/api/offline-orders/bulk-delete', methods=['POST'])
def bulk_del_offline():
    ids = request.json.get('ids', [])
    ws = SHEET.worksheet('offline_orders')
    rows_to_delete = [i + 2 for i, r in enumerate(ws.get_all_records()) if r['id'] in ids]
    for r_idx in sorted(rows_to_delete, reverse=True): ws.delete_rows(r_idx)
    return jsonify({'success': True})

# ── 🤖 TELEGRAM AI AGENT WEBHOOK 🤖 ───────────────────────────────────────────
@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    update = request.json
    
    # Only process text messages
    if "message" in update and "text" in update["message"]:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"]["text"]
        
        # Simple health check command
        if text == "/start":
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", 
                          json={"chat_id": chat_id, "text": "🤖 OrderTrack AI is online! Send me a messy sale text and I'll log it."})
            return jsonify({"status": "ok"})

        try:
            # 1. Ask Gemini to read the text and extract the data
            prompt = f"""
            You are a data extraction bot for a mobile phone business. Extract the offline sale details from the text below.
            Format the output ONLY as a valid JSON object. Do not include markdown formatting or backticks.
            Required JSON keys:
            - "last_digits" (string, just the numbers)
            - "card_type" (string, e.g., SBI, HDFC)
            - "machine" (string)
            - "vendor" (string)
            - "brand" (string, e.g., iPhone 15)
            - "sale_type" (string: must be either "INSTANT" or "EMI")
            - "costing" (number, digits only)
            - "selling_price" (number, digits only)
            
            Text: "{text}"
            """
            
            response = ai_model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(response_mime_type="application/json")
            )
            parsed_data = json.loads(response.text)

            # 2. Save the extracted data to Google Sheets
            ws = SHEET.worksheet('offline_orders')
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            sale_month = datetime.now().strftime('%Y-%m')
            
            costing = float(parsed_data.get('costing', 0))
            selling_price = float(parsed_data.get('selling_price', 0))
            profit = selling_price - costing
            
            row = [
                get_next_id(ws),
                parsed_data.get('card_type', 'UNKNOWN'),
                f"'{parsed_data.get('last_digits', '')}",
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

            # 3. Send a success message back to Telegram
            reply_msg = f"✅ **Sale Logged to Cloud**\n\n📱 Brand: {parsed_data.get('brand')}\n💳 Card: {parsed_data.get('card_type')} ({parsed_data.get('last_digits')})\n💰 Profit: ₹{profit:,.2f}"
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", 
                          json={"chat_id": chat_id, "text": reply_msg, "parse_mode": "Markdown"})

        except Exception as e:
            # If the AI fails or sheet fails, tell the user
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", 
                          json={"chat_id": chat_id, "text": f"❌ Error processing sale: {str(e)}"})

    return jsonify({"status": "ok"})

# ── PWA Setup ─────────────────────────────────────────────────────────────────
@app.route('/manifest.json')
def serve_manifest(): return send_file('static/manifest.json', mimetype='application/manifest+json')
@app.route('/sw.js')
def serve_sw(): return send_file('static/sw.js', mimetype='application/javascript')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
