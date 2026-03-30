from flask import Flask, render_template, request, jsonify, send_file
import os, io, json, csv
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, PatternFill
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
        print(f"Failed to connect to Google Sheets: {e}")

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

# ── Settings APIs (Cards, Platforms, Models, Variants, SecNames) ──────────────
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
    new_id = get_next_id(ws)
    last_digits = str(data.get('last_digits', ''))
    save_digits = f"'{last_digits}" if last_digits else ""
    ws.append_row([new_id, data.get('card_type', ''), save_digits])
    return jsonify({'success': True})

@app.route('/api/cards/<int:card_id>', methods=['DELETE'])
def delete_card(card_id):
    ws = SHEET.worksheet('cards')
    try:
        cell = ws.find(str(card_id), in_column=1)
        ws.delete_rows(cell.row)
    except: pass
    return jsonify({'success': True})

@app.route('/api/card-lookup')
def card_lookup():
    digits = request.args.get('digits', '').strip()
    if digits.startswith("'"): digits = digits[1:]
    if not SHEET: return jsonify({'found': False})
    ws = SHEET.worksheet('cards')
    for row in ws.get_all_records():
        db_digits = str(row.get('last_digits', ''))
        if db_digits.startswith("'"): db_digits = db_digits[1:]
        if db_digits == digits: return jsonify({'card_type': row.get('card_type'), 'found': True})
    return jsonify({'found': False})

# Generic Master Data Handler for simple ID/Name tables
def handle_master_table(table_name, req, field_name='name'):
    if not SHEET: return jsonify([])
    ws = SHEET.worksheet(table_name)
    if req.method == 'GET':
        return jsonify(ws.get_all_records())
    data = req.json
    new_id = get_next_id(ws)
    ws.append_row([new_id, data.get(field_name, '')])
    return jsonify({'success': True})

def delete_master_table(table_name, item_id):
    ws = SHEET.worksheet(table_name)
    try:
        cell = ws.find(str(item_id), in_column=1)
        ws.delete_rows(cell.row)
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

# New Offline Master Data
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

# Lookups & Variants
@app.route('/api/platform-names')
def platform_names():
    if not SHEET: return jsonify([])
    records = SHEET.worksheet('platforms').get_all_records()
    return jsonify(sorted(list(set([r['platform_name'] for r in records if r.get('platform_name')]))))

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
            if m_id: return jsonify([v for v in variants if v['model_id'] == m_id])
            return jsonify([])
        return jsonify(variants)
    data = request.json
    new_id = get_next_id(ws)
    ws.append_row([new_id, data.get('model_id'), data.get('variant_name', ''), data.get('costing', '')])
    return jsonify({'success': True})

@app.route('/api/variants/<int:var_id>', methods=['DELETE'])
def del_variant(var_id): return delete_master_table('variants', var_id)

# ── Main Orders API (Unchanged) ───────────────────────────────────────────────
@app.route('/api/main-orders', methods=['GET', 'POST'])
def api_main_orders(): # (Your function name here might be api_main, leave your name as is)
    ws = SHEET.worksheet('main_orders')
    
    if request.method == 'GET':
        # FIX: Try to get records, but don't crash if the sheet is empty
        try:
            records = ws.get_all_records()
        except Exception:
            records = []
            
        return jsonify(list(reversed(records)))
        
    # ... KEEP YOUR EXISTING POST LOGIC BELOW THIS LINE ...
    
    data = request.json
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    new_id = get_next_id(ws)
    last_digits = str(data.get('last_digits', ''))
    costing, selling_price = float(data.get('costing') or 0), float(data.get('selling_price') or 0)
    
    row = [new_id, data.get('card_type', ''), f"'{last_digits}" if last_digits else "", data.get('platform', ''), 
           data.get('account', ''), data.get('order_name', ''), data.get('model', ''), data.get('variant', ''), 
           costing, selling_price, selling_price - costing, data.get('delivery_date', ''), data.get('sale_batch', 'Current Sale'), now]
    ws.append_row(row)
    row[2] = last_digits
    return jsonify(dict(zip(ws.row_values(1), row)))

@app.route('/api/main-orders/bulk-delete', methods=['POST'])
def bulk_del_main():
    if not SHEET: return jsonify({'success': False})
    ids = request.json.get('ids', [])
    ws = SHEET.worksheet('main_orders')
    
    # FIX: Using your original data-fetching method
    try:
        records = ws.get_all_records()
    except Exception:
        records = []
        
    rows_to_delete = [i + 2 for i, r in enumerate(records) if r.get('id') in ids]
    for r_idx in sorted(rows_to_delete, reverse=True): 
        ws.delete_row(r_idx)
    return jsonify({'success': True})

@app.route('/api/main-orders/<int:id>', methods=['DELETE'])
def del_main(id): return delete_master_table('main_orders', id)

# ── Secondary Orders API (Unchanged) ──────────────────────────────────────────
@app.route('/api/secondary-orders', methods=['GET', 'POST'])
def api_sec_orders():
    ws = SHEET.worksheet('secondary_orders')
    if request.method == 'GET':
        try:
            records = ws.get_all_records()
        except Exception:
            records = []
        return jsonify(list(reversed(records)))
    # ... keep your POST logic ...
    
    data = request.json
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    new_id = get_next_id(ws)
    last_digits = str(data.get('last_digits', ''))
    costing, selling_price = float(data.get('costing') or 0), float(data.get('selling_price') or 0)
    
    row = [new_id, data.get('card_type', ''), f"'{last_digits}" if last_digits else "", data.get('platform', ''), 
           data.get('order_name', ''), data.get('model', ''), data.get('variant', ''), 
           costing, selling_price, selling_price - costing, data.get('delivery_date', ''), data.get('sale_batch', 'Current Sale'), now]
    ws.append_row(row)
    row[2] = last_digits
    return jsonify(dict(zip(ws.row_values(1), row)))

@app.route('/api/secondary-orders/bulk-delete', methods=['POST'])
def bulk_del_sec():
    if not SHEET: return jsonify({'success': False})
    ids = request.json.get('ids', [])
    ws = SHEET.worksheet('secondary_orders')
    
    # FIX: Using your original data-fetching method
    try:
        records = ws.get_all_records()
    except Exception:
        records = []
        
    rows_to_delete = [i + 2 for i, r in enumerate(records) if r.get('id') in ids]
    for r_idx in sorted(rows_to_delete, reverse=True): 
        ws.delete_row(r_idx)
    return jsonify({'success': True})

@app.route('/api/secondary-orders/<int:id>', methods=['DELETE'])
def del_sec(id): return delete_master_table('secondary_orders', id)

# ── Offline Orders API (NEW) ──────────────────────────────────────────────────
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
    new_id = get_next_id(ws)
    last_digits = str(data.get('last_digits', ''))
    costing, selling_price = float(data.get('costing') or 0), float(data.get('selling_price') or 0)
    
    row = [new_id, data.get('card_type', ''), f"'{last_digits}" if last_digits else "", 
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
    records = ws.get_all_records()
    rows_to_delete = [i + 2 for i, r in enumerate(records) if r['id'] in ids]
    for r_idx in sorted(rows_to_delete, reverse=True): ws.delete_rows(r_idx)
    return jsonify({'success': True})

# ── PWA Setup ─────────────────────────────────────────────────────────────────
@app.route('/manifest.json')
def serve_manifest(): return send_file('static/manifest.json', mimetype='application/manifest+json')
@app.route('/sw.js')
def serve_sw(): return send_file('static/sw.js', mimetype='application/javascript')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
