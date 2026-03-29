# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, jsonify, send_file
import os, io, json, csv, requests
from datetime import datetime
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
    genai.configure(api_key=GEMINI_API_KEY)
    # Using 1.5-pro for a more stable free-tier quota in 2026
    ai_model = genai.GenerativeModel('gemini-1.5-pro')

# ── Helper Functions ──────────────────────────────────────────────────────────
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
def main_orders_page(): return render_template('main_orders.html')
@app.route('/secondary')
def secondary_orders_page(): return render_template('secondary_orders.html')
@app.route('/offline')
def offline_orders_page(): return render_template('offline_orders.html')
@app.route('/inventory')
def inventory_page(): return render_template('inventory.html')
@app.route('/dashboard')
def dashboard_page(): return render_template('dashboard.html')
@app.route('/settings')
def settings_page(): return render_template('settings.html')

# ── Master Data APIs (Settings) ───────────────────────────────────────────────
@app.route('/api/cards', methods=['GET', 'POST'])
def manage_cards():
    if not SHEET: return jsonify([])
    ws = SHEET.worksheet('cards')
    if request.method == 'GET':
        cards = safe_get_records(ws)
        return jsonify(list(reversed(cards)))
    data = request.json
    ws.append_row([get_next_id(ws), data.get('card_type', ''), "'" + str(data.get('last_digits', ''))])
    return jsonify({'success': True})

@app.route('/api/platforms', methods=['GET', 'POST'])
def api_platforms():
    ws = SHEET.worksheet('platforms')
    if request.method == 'GET': return jsonify(safe_get_records(ws))
    ws.append_row([get_next_id(ws), request.json.get('platform_name', '')])
    return jsonify({'success': True})

@app.route('/api/models', methods=['GET', 'POST'])
def api_models():
    ws = SHEET.worksheet('models')
    if request.method == 'GET': return jsonify(safe_get_records(ws))
    ws.append_row([get_next_id(ws), request.json.get('model_name', '')])
    return jsonify({'success': True})

@app.route('/api/sec-order-names', methods=['GET', 'POST'])
def api_sec_names():
    ws = SHEET.worksheet('sec_order_names')
    if request.method == 'GET': return jsonify(safe_get_records(ws))
    ws.append_row([get_next_id(ws), request.json.get('name', '')])
    return jsonify({'success': True})

@app.route('/api/variants', methods=['GET', 'POST'])
def api_variants():
    ws = SHEET.worksheet('variants')
    if request.method == 'GET':
        model_name = request.args.get('model')
        all_v = safe_get_records(ws)
        if model_name:
            m_ws = SHEET.worksheet('models')
            m_data = safe_get_records(m_ws)
            m_id = next((m.get('id') for m in m_data if (m.get('model_name') == model_name or m.get('name') == model_name)), None)
            if m_id: return jsonify([v for v in all_v if str(v.get('model_id')) == str(m_id)])
            return jsonify([])
        return jsonify(all_v)
    ws.append_row([get_next_id(ws), request.json.get('model_id'), request.json.get('variant_name', ''), request.json.get('costing', '')])
    return jsonify({'success': True})

# ── Main Orders logic ────────────────────────────────────────────────────────
@app.route('/api/main-orders', methods=['GET', 'POST'])
def api_main_orders():
    ws = SHEET.worksheet('main_orders')
    if request.method == 'GET': return jsonify(list(reversed(safe_get_records(ws))))
    data = request.json
    cost = float(data.get('costing') or 0)
    sell = float(data.get('selling_price') or 0)
    row = [
        get_next_id(ws), data.get('card_type', ''), "'" + str(data.get('last_digits', '')),
        data.get('platform', ''), data.get('account', ''), data.get('order_name', ''),
        data.get('model', ''), data.get('variant', ''), cost, sell, sell - cost,
        data.get('delivery_date', ''), data.get('sale_batch', 'Current Sale'), datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ]
    ws.append_row(row)
    return jsonify({'id': row[0], 'success': True, 'profit': sell-cost, 'created_at': row[-1]})

@app.route('/api/main-orders/bulk-update-batch', methods=['POST'])
def bulk_update_batch():
    data = request.json
    ids, new_batch = data.get('ids', []), data.get('batch', 'Current Sale')
    ws = SHEET.worksheet('main_orders')
    records = safe_get_records(ws)
    for i, r in enumerate(records):
        if r.get('id') in ids: ws.update_cell(i + 2, 13, new_batch)
    return jsonify({'success': True})

# ── Secondary Orders logic ───────────────────────────────────────────────────
@app.route('/api/secondary-orders', methods=['GET', 'POST'])
def api_secondary_orders():
    ws = SHEET.worksheet('secondary_orders')
    if request.method == 'GET': return jsonify(list(reversed(safe_get_records(ws))))
    data = request.json
    cost, sell = float(data.get('costing') or 0), float(data.get('selling_price') or 0)
    row = [
        get_next_id(ws), data.get('card_type', ''), "'" + str(data.get('last_digits', '')),
        data.get('platform', ''), data.get('account', ''), data.get('order_name', ''),
        data.get('model', ''), data.get('variant', ''), cost, sell, sell - cost,
        data.get('delivery_date', ''), data.get('sale_batch', 'Current Sale'), datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ]
    ws.append_row(row)
    return jsonify({'id': row[0], 'success': True, 'profit': sell-cost, 'created_at': row[-1]})

@app.route('/api/secondary-orders/bulk-update-batch', methods=['POST'])
def bulk_update_secondary_batch():
    data = request.json
    ids, new_batch = data.get('ids', []), data.get('batch', 'Current Sale')
    ws = SHEET.worksheet('secondary_orders')
    records = safe_get_records(ws)
    for i, r in enumerate(records):
        if r.get('id') in ids: ws.update_cell(i + 2, 13, new_batch)
    return jsonify({'success': True})

# ── Offline Orders logic ─────────────────────────────────────────────────────
@app.route('/api/offline-orders', methods=['GET', 'POST'])
def api_offline_orders():
    ws = SHEET.worksheet('offline_orders')
    if request.method == 'GET': return jsonify(list(reversed(safe_get_records(ws))))
    data = request.json
    cost, sell = float(data.get('costing') or 0), float(data.get('selling_price') or 0)
    row = [
        get_next_id(ws), data.get('card_type', ''), "'" + str(data.get('last_digits', '')),
        data.get('machine', ''), data.get('vendor', ''), data.get('brand', ''), data.get('sale_type', ''),
        cost, sell, sell - cost, data.get('sale_month', ''), datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ]
    ws.append_row(row)
    return jsonify({'id': row[0], 'success': True, 'profit': sell-cost, 'created_at': row[-1]})

# ── TELEGRAM AI WEBHOOK (WITH QUOTA HANDLER) ──────────────────────────────────
@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    update = request.get_json(silent=True)
    if not update or "message" not in update or "text" not in update["message"]: return jsonify({"status": "ok"})
    
    chat_id = update["message"]["chat"]["id"]
    text = str(update["message"]["text"])
    bot_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    if text == "/start":
        requests.post(bot_url, json={"chat_id": chat_id, "text": "AI OrderTrack Bot Online! Send sale text to log."})
        return jsonify({"status": "ok"})

    try:
        prompt = f"Extract offline sale JSON: last_digits, card_type, machine, vendor, brand, sale_type(INSTANT/EMI), costing, selling_price. Text: {text}"
        
        # AI Logic with Error Catching
        response = ai_model.generate_content(prompt)
        raw_text = response.text.replace('```json', '').replace('```', '').strip()
        p = json.loads(raw_text)

        ws = SHEET.worksheet('offline_orders')
        cost, sell = float(p.get('costing') or 0), float(p.get('selling_price') or 0)
        row = [get_next_id(ws), p.get('card_type','?'), "'" + str(p.get('last_digits','')), p.get('machine','?'), 
               p.get('vendor','?'), p.get('brand','?'), p.get('sale_type','INSTANT'), cost, sell, sell-cost, 
               datetime.now().strftime('%Y-%m'), datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
        ws.append_row(row)

        requests.post(bot_url, json={"chat_id": chat_id, "text": f"✅ LOGGED: {p.get('brand')} | Profit: ₹{sell-cost}"})

    except Exception as e:
        msg = "⚠️ AI Busy. Try again in 1 min." if "429" in str(e) else f"Error: {str(e)}"
        requests.post(bot_url, json={"chat_id": chat_id, "text": msg})

    return jsonify({"status": "ok"})

# ── PWA & App Launch ──────────────────────────────────────────────────────────
@app.route('/manifest.json')
def serve_manifest(): return send_file('static/manifest.json', mimetype='application/manifest+json')
@app.route('/sw.js')
def serve_sw(): return send_file('static/sw.js', mimetype='application/javascript')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
