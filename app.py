from flask import Flask, render_template, request, jsonify, send_file
import os
import io
import json
from datetime import datetime
import csv
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
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
else:
    print("WARNING: No GOOGLE_CREDENTIALS_JSON environment variable found.")

def init_sheets():
    if not SHEET: return
    tabs = {
        'cards': ['id', 'card_type', 'last_digits'],
        'platforms': ['id', 'platform_name', 'account_name'],
        'models': ['id', 'model_name'],
        'variants': ['id', 'model_id', 'variant_name'],
        'main_orders': ['id', 'card_type', 'last_digits', 'platform', 'account', 'order_name', 'model', 'variant', 'costing', 'delivery_date', 'created_at'],
        'secondary_orders': ['id', 'card_type', 'last_digits', 'platform', 'model', 'variant', 'costing', 'created_at']
    }
    for title, headers in tabs.items():
        try:
            ws = SHEET.worksheet(title)
            if not ws.row_values(1):
                ws.append_row(headers)
        except gspread.exceptions.WorksheetNotFound:
            ws = SHEET.add_worksheet(title=title, rows=100, cols=20)
            ws.append_row(headers)

# Initialize tabs on startup
init_sheets()

def get_next_id(ws):
    records = ws.get_all_records()
    if not records: return 1
    return max([int(r.get('id', 0)) for r in records]) + 1

# ── Page Routes ──────────────────────────────────────────────────────────────

@app.route('/')
def main_orders():
    return render_template('main_orders.html')

@app.route('/secondary')
def secondary_orders():
    return render_template('secondary_orders.html')

@app.route('/settings')
def settings():
    return render_template('settings.html')


# ── Cards API ─────────────────────────────────────────────────────────────────

@app.route('/api/cards', methods=['GET'])
def get_cards():
    if not SHEET: return jsonify([])
    ws = SHEET.worksheet('cards')
    cards = ws.get_all_records()
    return jsonify(list(reversed(cards)))

@app.route('/api/cards', methods=['POST'])
def add_card():
    data = request.json
    ws = SHEET.worksheet('cards')
    new_id = get_next_id(ws)
    ws.append_row([new_id, data.get('card_type', ''), data.get('last_digits', '')])
    return jsonify({'success': True})

@app.route('/api/cards/<int:card_id>', methods=['DELETE'])
def delete_card(card_id):
    ws = SHEET.worksheet('cards')
    try:
        cell = ws.find(str(card_id), in_column=1)
        ws.delete_rows(cell.row)
    except Exception: pass
    return jsonify({'success': True})

@app.route('/api/card-lookup')
def card_lookup():
    digits = request.args.get('digits', '').strip()
    if not SHEET: return jsonify({'found': False})
    ws = SHEET.worksheet('cards')
    for row in ws.get_all_records():
        if str(row.get('last_digits')) == digits:
            return jsonify({'card_type': row.get('card_type'), 'found': True})
    return jsonify({'found': False})


# ── Platforms API ─────────────────────────────────────────────────────────────

@app.route('/api/platforms', methods=['GET'])
def get_platforms():
    if not SHEET: return jsonify([])
    ws = SHEET.worksheet('platforms')
    return jsonify(ws.get_all_records())

@app.route('/api/platforms', methods=['POST'])
def add_platform():
    data = request.json
    ws = SHEET.worksheet('platforms')
    new_id = get_next_id(ws)
    ws.append_row([new_id, data.get('platform_name', ''), data.get('account_name', '')])
    return jsonify({'success': True})

@app.route('/api/platforms/<int:platform_id>', methods=['DELETE'])
def delete_platform(platform_id):
    ws = SHEET.worksheet('platforms')
    try:
        cell = ws.find(str(platform_id), in_column=1)
        ws.delete_rows(cell.row)
    except Exception: pass
    return jsonify({'success': True})

@app.route('/api/platform-lookup')
def platform_lookup():
    platform_name = request.args.get('platform', '')
    if not SHEET: return jsonify([])
    ws = SHEET.worksheet('platforms')
    accounts = list(set([r['account_name'] for r in ws.get_all_records() if r['platform_name'] == platform_name]))
    return jsonify(accounts)

@app.route('/api/platform-names')
def platform_names():
    if not SHEET: return jsonify([])
    ws = SHEET.worksheet('platforms')
    names = list(set([r['platform_name'] for r in ws.get_all_records()]))
    return jsonify(sorted(names))


# ── Models API ────────────────────────────────────────────────────────────────

@app.route('/api/models', methods=['GET'])
def get_models():
    if not SHEET: return jsonify([])
    ws = SHEET.worksheet('models')
    return jsonify(sorted(ws.get_all_records(), key=lambda x: str(x.get('model_name', ''))))

@app.route('/api/models', methods=['POST'])
def add_model():
    data = request.json
    ws = SHEET.worksheet('models')
    new_id = get_next_id(ws)
    ws.append_row([new_id, data.get('model_name', '')])
    return jsonify({'success': True, 'model_id': new_id})

@app.route('/api/models/<int:model_id>', methods=['DELETE'])
def delete_model(model_id):
    # Cascade delete variants
    v_ws = SHEET.worksheet('variants')
    variants = v_ws.get_all_records()
    rows_to_delete = [i + 2 for i, r in enumerate(variants) if r['model_id'] == model_id]
    for r_idx in sorted(rows_to_delete, reverse=True):
        v_ws.delete_rows(r_idx)
        
    m_ws = SHEET.worksheet('models')
    try:
        cell = m_ws.find(str(model_id), in_column=1)
        m_ws.delete_rows(cell.row)
    except Exception: pass
    return jsonify({'success': True})


# ── Variants API ──────────────────────────────────────────────────────────────

@app.route('/api/variants', methods=['GET'])
def get_variants():
    model_name = request.args.get('model', '')
    if not SHEET: return jsonify([])
    
    m_ws = SHEET.worksheet('models')
    model_id = next((r['id'] for r in m_ws.get_all_records() if r['model_name'] == model_name), None)
    if not model_id: return jsonify([])
    
    v_ws = SHEET.worksheet('variants')
    variants = [r['variant_name'] for r in v_ws.get_all_records() if r['model_id'] == model_id]
    return jsonify(variants)

@app.route('/api/variants/by-model/<int:model_id>', methods=['GET'])
def get_variants_by_model_id(model_id):
    if not SHEET: return jsonify([])
    ws = SHEET.worksheet('variants')
    variants = [r for r in ws.get_all_records() if r['model_id'] == model_id]
    return jsonify(variants)

@app.route('/api/variants', methods=['POST'])
def add_variant():
    data = request.json
    ws = SHEET.worksheet('variants')
    new_id = get_next_id(ws)
    ws.append_row([new_id, data.get('model_id'), data.get('variant_name', '')])
    return jsonify({'success': True})

@app.route('/api/variants/<int:variant_id>', methods=['DELETE'])
def delete_variant(variant_id):
    ws = SHEET.worksheet('variants')
    try:
        cell = ws.find(str(variant_id), in_column=1)
        ws.delete_rows(cell.row)
    except Exception: pass
    return jsonify({'success': True})


# ── Main Orders API ───────────────────────────────────────────────────────────

@app.route('/api/main-orders', methods=['GET'])
def get_main_orders():
    if not SHEET: return jsonify([])
    ws = SHEET.worksheet('main_orders')
    orders = ws.get_all_records()
    return jsonify(list(reversed(orders)))

@app.route('/api/main-orders', methods=['POST'])
def add_main_order():
    data = request.json
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ws = SHEET.worksheet('main_orders')
    new_id = get_next_id(ws)
    
    row_data = [
        new_id, data.get('card_type', ''), data.get('last_digits', ''),
        data.get('platform', ''), data.get('account', ''), data.get('order_name', ''),
        data.get('model', ''), data.get('variant', ''), float(data.get('costing') or 0),
        data.get('delivery_date', ''), now
    ]
    ws.append_row(row_data)
    headers = ws.row_values(1)
    return jsonify(dict(zip(headers, row_data)))

@app.route('/api/main-orders/<int:order_id>', methods=['PUT'])
def update_main_order(order_id):
    data = request.json
    ws = SHEET.worksheet('main_orders')
    records = ws.get_all_records()
    original = next((r for r in records if r['id'] == order_id), None)
    
    if original:
        row_idx = records.index(original) + 2
        row_data = [
            order_id, data.get('card_type', ''), data.get('last_digits', ''),
            data.get('platform', ''), data.get('account', ''), data.get('order_name', ''),
            data.get('model', ''), data.get('variant', ''), float(data.get('costing') or 0),
            data.get('delivery_date', ''), original.get('created_at', '')
        ]
        ws.update(f'A{row_idx}:K{row_idx}', [row_data])
        headers = ws.row_values(1)
        return jsonify(dict(zip(headers, row_data)))
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/main-orders/<int:order_id>', methods=['DELETE'])
def delete_main_order(order_id):
    ws = SHEET.worksheet('main_orders')
    try:
        cell = ws.find(str(order_id), in_column=1)
        ws.delete_rows(cell.row)
    except Exception: pass
    return jsonify({'success': True})

@app.route('/api/main-orders/bulk-delete', methods=['POST'])
def bulk_delete_main_orders():
    ids = request.json.get('ids', [])
    if not ids: return jsonify({'error': 'No IDs provided'}), 400
    ws = SHEET.worksheet('main_orders')
    records = ws.get_all_records()
    
    rows_to_delete = [i + 2 for i, r in enumerate(records) if r['id'] in ids]
    for r_idx in sorted(rows_to_delete, reverse=True):
        ws.delete_rows(r_idx)
    return jsonify({'success': True, 'deleted': len(ids)})

@app.route('/api/main-orders/export')
def export_main_orders():
    fmt = request.args.get('format', 'csv')
    ws = SHEET.worksheet('main_orders')
    orders = list(reversed(ws.get_all_records()))
    headers = ['ID', 'Card Type', 'Last Digits', 'Platform', 'Account', 'Order Name', 'Model', 'Variant', 'Costing', 'Delivery Date', 'Created At']

    if fmt == 'excel':
        wb = openpyxl.Workbook()
        ws_excel = wb.active
        ws_excel.title = 'Main Orders'
        hfill = PatternFill(start_color='1E3A5F', end_color='1E3A5F', fill_type='solid')
        hfont = Font(color='FFFFFF', bold=True)
        for col, h in enumerate(headers, 1):
            cell = ws_excel.cell(row=1, column=col, value=h)
            cell.fill = hfill
            cell.font = hfont
        
        for rn, o in enumerate(orders, 2):
            vals = [o.get('id'), o.get('card_type'), o.get('last_digits'), o.get('platform'), o.get('account'), o.get('order_name'), o.get('model'), o.get('variant'), o.get('costing'), o.get('delivery_date'), o.get('created_at')]
            for cn, v in enumerate(vals, 1):
                ws_excel.cell(row=rn, column=cn, value=v)
                
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name='main_orders.xlsx')
    else:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        for o in orders:
            writer.writerow([o.get('id'), o.get('card_type'), o.get('last_digits'), o.get('platform'), o.get('account'), o.get('order_name'), o.get('model'), o.get('variant'), o.get('costing'), o.get('delivery_date'), o.get('created_at')])
        return send_file(io.BytesIO(output.getvalue().encode()), mimetype='text/csv', as_attachment=True, download_name='main_orders.csv')


# ── Secondary Orders API ──────────────────────────────────────────────────────

@app.route('/api/secondary-orders', methods=['GET'])
def get_secondary_orders():
    if not SHEET: return jsonify([])
    ws = SHEET.worksheet('secondary_orders')
    return jsonify(list(reversed(ws.get_all_records())))

@app.route('/api/secondary-orders', methods=['POST'])
def add_secondary_order():
    data = request.json
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ws = SHEET.worksheet('secondary_orders')
    new_id = get_next_id(ws)
    
    row_data = [
        new_id, data.get('card_type', ''), data.get('last_digits', ''),
        data.get('platform', ''), data.get('model', ''), data.get('variant', ''), 
        float(data.get('costing') or 0), now
    ]
    ws.append_row(row_data)
    headers = ws.row_values(1)
    return jsonify(dict(zip(headers, row_data)))

@app.route('/api/secondary-orders/<int:order_id>', methods=['PUT'])
def update_secondary_order(order_id):
    data = request.json
    ws = SHEET.worksheet('secondary_orders')
    records = ws.get_all_records()
    original = next((r for r in records if r['id'] == order_id), None)
    
    if original:
        row_idx = records.index(original) + 2
        row_data = [
            order_id, data.get('card_type', ''), data.get('last_digits', ''),
            data.get('platform', ''), data.get('model', ''), data.get('variant', ''), 
            float(data.get('costing') or 0), original.get('created_at', '')
        ]
        ws.update(f'A{row_idx}:H{row_idx}', [row_data])
        headers = ws.row_values(1)
        return jsonify(dict(zip(headers, row_data)))
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/secondary-orders/<int:order_id>', methods=['DELETE'])
def delete_secondary_order(order_id):
    ws = SHEET.worksheet('secondary_orders')
    try:
        cell = ws.find(str(order_id), in_column=1)
        ws.delete_rows(cell.row)
    except Exception: pass
    return jsonify({'success': True})

@app.route('/api/secondary-orders/bulk-delete', methods=['POST'])
def bulk_delete_secondary_orders():
    ids = request.json.get('ids', [])
    if not ids: return jsonify({'error': 'No IDs provided'}), 400
    ws = SHEET.worksheet('secondary_orders')
    records = ws.get_all_records()
    
    rows_to_delete = [i + 2 for i, r in enumerate(records) if r['id'] in ids]
    for r_idx in sorted(rows_to_delete, reverse=True):
        ws.delete_rows(r_idx)
    return jsonify({'success': True, 'deleted': len(ids)})

@app.route('/api/secondary-orders/export')
def export_secondary_orders():
    fmt = request.args.get('format', 'csv')
    ws = SHEET.worksheet('secondary_orders')
    orders = list(reversed(ws.get_all_records()))
    headers = ['ID', 'Card Type', 'Last Digits', 'Platform', 'Model', 'Variant', 'Costing', 'Created At']

    if fmt == 'excel':
        wb = openpyxl.Workbook()
        ws_excel = wb.active
        ws_excel.title = 'Secondary Orders'
        hfill = PatternFill(start_color='1E3A5F', end_color='1E3A5F', fill_type='solid')
        hfont = Font(color='FFFFFF', bold=True)
        for col, h in enumerate(headers, 1):
            cell = ws_excel.cell(row=1, column=col, value=h)
            cell.fill = hfill
            cell.font = hfont
        
        for rn, o in enumerate(orders, 2):
            vals = [o.get('id'), o.get('card_type'), o.get('last_digits'), o.get('platform'), o.get('model'), o.get('variant'), o.get('costing'), o.get('created_at')]
            for cn, v in enumerate(vals, 1):
                ws_excel.cell(row=rn, column=cn, value=v)
                
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name='secondary_orders.xlsx')
    else:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        for o in orders:
            writer.writerow([o.get('id'), o.get('card_type'), o.get('last_digits'), o.get('platform'), o.get('model'), o.get('variant'), o.get('costing'), o.get('created_at')])
        return send_file(io.BytesIO(output.getvalue().encode()), mimetype='text/csv', as_attachment=True, download_name='secondary_orders.csv')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
