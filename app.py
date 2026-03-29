# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, jsonify, send_file
import os, json
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

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
@app.route('/api/models', methods=['GET', 'POST'])
def api_models(): return handle_master_table('models', request, 'model_name')
@app.route('/api/sec-order-names', methods=['GET', 'POST'])
def api_sec_names(): return handle_master_table('sec_order_names', request, 'name')
@app.route('/api/machines', methods=['GET', 'POST'])
def api_machines(): return handle_master_table('machines', request, 'name')
@app.route('/api/vendors', methods=['GET', 'POST'])
def api_vendors(): return handle_master_table('vendors', request, 'name')
@app.route('/api/brands', methods=['GET', 'POST'])
def api_brands(): return handle_master_table('brands', request, 'name')

@app.route('/api/variants', methods=['GET', 'POST'])
def api_variants():
    if not SHEET: return jsonify([])
    ws = SHEET.worksheet('variants')
    if request.method == 'GET':
        model_name = request.args.get('model')
        variants = safe_get_records(ws)
        if model_name:
            models = safe_get_records(SHEET.worksheet('models'))
            m_id = next((m.get('id') for m in models if (m.get('model_name') == model_name or m.get('name') == model_name)), None)
            return jsonify([v for v in variants if str(v.get('model_id')) == str(m_id)]) if m_id else jsonify([])
        return jsonify(variants)
    ws.append_row([get_next_id(ws), request.json.get('model_id'), request.json.get('variant_name', ''), request.json.get('costing', '')])
    return jsonify({'success': True})

# ── Main Orders API ───────────────────────────────────────────────────────────
@app.route('/api/main-orders', methods=['GET', 'POST'])
def api_main_orders():
    if not SHEET: return jsonify([])
    ws = SHEET.worksheet('main_orders')
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
        data.get('account', ''), data.get('order_name', ''), data.get('model', ''), data.get('variant', ''), 
        costing, selling_price, selling_price - costing, data.get('delivery_date', ''), data.get('sale_batch', 'Current Sale'), now
    ]
    ws.append_row(row)
    row[2] = last_digits
    return jsonify(dict(zip(ws.row_values(1), row)))

@app.route('/api/main-orders/<int:id>', methods=['DELETE'])
def del_main(id): return delete_master_table('main_orders', id)

@app.route('/api/main-orders/bulk-update-batch', methods=['POST'])
def bulk_main_batch():
    if not SHEET: return jsonify({'success': False})
    data = request.json
    ws = SHEET.worksheet('main_orders')
    records = safe_get_records(ws)
    for i, r in enumerate(records):
        if r.get('id') in data.get('ids', []): ws.update_cell(i + 2, 13, data.get('batch'))
    return jsonify({'success': True})

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
        data.get('account', ''), data.get('order_name', ''), data.get('model', ''), data.get('variant', ''), 
        costing, selling_price, selling_price - costing, data.get('delivery_date', ''), data.get('sale_batch', 'Current Sale'), now
    ]
    ws.append_row(row)
    row[2] = last_digits
    return jsonify(dict(zip(ws.row_values(1), row)))

@app.route('/api/secondary-orders/<int:id>', methods=['DELETE'])
def del_sec(id): return delete_master_table('secondary_orders', id)

@app.route('/api/secondary-orders/bulk-update-batch', methods=['POST'])
def bulk_sec_batch():
    if not SHEET: return jsonify({'success': False})
    data = request.json
    ws = SHEET.worksheet('secondary_orders')
    records = safe_get_records(ws)
    for i, r in enumerate(records):
        if r.get('id') in data.get('ids', []): ws.update_cell(i + 2, 13, data.get('batch'))
    return jsonify({'success': True})

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
    records = safe_get_records(ws)
    rows_to_delete = [i + 2 for i, r in enumerate(records) if r.get('id') in ids]
    for r_idx in sorted(rows_to_delete, reverse=True): 
        ws.delete_row(r_idx)
    return jsonify({'success': True})

# ── PWA Setup ─────────────────────────────────────────────────────────────────
@app.route('/manifest.json')
def serve_manifest(): return send_file('static/manifest.json', mimetype='application/manifest+json')
@app.route('/sw.js')
def serve_sw(): return send_file('static/sw.js', mimetype='application/javascript')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
