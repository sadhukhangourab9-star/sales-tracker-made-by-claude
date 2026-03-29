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
    ai_model = genai.GenerativeModel('gemini-1.5-flash')

def get_next_id(ws):
    records = ws.get_all_records()
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
        cards = ws.get_all_records()
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
    if req.method == 'GET': return jsonify(ws.get_all_records())
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
    if not SHEET: return jsonify([])
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

# ── Secondary Orders API ──────────────────────────────────────────────────────
@app.route('/api/secondary-orders', methods=['GET', 'POST'])
def api_secondary_orders():
    if not SHEET: return jsonify([])
    ws = SHEET.worksheet('secondary_orders')
    if request.method == 'GET':
        orders = ws.get_all_records()
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

@app.route('/api/secondary-orders/<int:id>', methods=['DELETE'])
def del_sec(id): return delete_master_table('secondary_orders', id)

# ── Offline Orders API ────────────────────────────────────────────────────────
@app.route('/api/offline-orders', methods=['GET', 'POST'])
def api_offline_orders():
    if not SHEET: return jsonify([])
    ws = SHEET.worksheet('offline_orders')
    if request.method == 'GET':
        orders = ws.get_all_records()
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
    rows_to_delete = [i + 2 for i, r in enumerate(ws.get_all_records()) if r['id'] in ids]
    for r_idx in sorted(rows_to_delete, reverse=True): 
        ws.delete_row(r_idx)
    return jsonify({'success': True})

# ── 🤖 TELEGRAM AI AGENT WEBHOOK 🤖 ───────────────────────────────────────────
@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    update = request.get_json(silent=True)
    
    if not update or "message" not in update or "text" not in update["message"]:
        return jsonify({"status": "ok"})
        
    chat_id = update["message"]["chat"]["id"]
    text = update["message"]["text"]
    bot_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    if text == "/start":
        start_msg = "🤖 OrderTrack AI is online! Send me a messy sale text and I'll log it."
        requests.post(bot_url, json={"chat_id": chat_id, "text": start_msg})
        return jsonify({"status": "ok"})

    try:
        # Building the string using an array to completely bypass editor multi-line bugs
        prompt_lines = [
            "You are a data extraction bot for a mobile phone business. Extract the offline sale details from the text below.",
            "Format the output ONLY as a valid JSON object. Do not include markdown formatting or backticks.",
            "Required JSON keys:",
            "- \"last_digits\" (string, just the numbers)",
            "- \"card_type\" (string, e.g., SBI, HDFC)",
            "- \"machine\" (string)",
            "- \"vendor\" (string)",
            "- \"brand\" (string, e.g., iPhone 15)",
            "- \"sale_type\" (string: must be either \"INSTANT\" or \"EMI\")",
            "- \"costing\" (number, digits only)",
            "- \"selling_price\" (number, digits only)",
            "",
            f"Text: \"{text}\""
        ]
        prompt = "\n".join(prompt_lines)
        
        response = ai_model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(response_mime_type="application/json")
        )
        
        raw_text = response.text.strip()
        if raw_text.startswith("
http://googleusercontent.com/immersive_entry_chip/0
http://googleusercontent.com/immersive_entry_chip/1
http://googleusercontent.com/immersive_entry_chip/2

Did this finally slay the syntax error for good? Let me know so we can move on to actually using the app!
