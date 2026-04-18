from flask import Flask, render_template, request, jsonify, send_file
import os, io, json, csv, time
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

# ── Simple In-Memory Cache ────────────────────────────────────────────────────
_cache = {}
CACHE_TTL = 30  # seconds

def cache_get(key):
    if key in _cache:
        data, ts = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return data
    return None

def cache_set(key, data):
    _cache[key] = (data, time.time())

def cache_clear(key):
    _cache.pop(key, None)

def cache_clear_all():
    _cache.clear()

# ── Helpers ───────────────────────────────────────────────────────────────────
def get_next_id(ws):
    try:
        col = ws.col_values(1)  # Only fetch column A — much faster
        ids = [int(x) for x in col[1:] if str(x).isdigit()]  # skip header
        return max(ids) + 1 if ids else 1
    except Exception:
        return 1

# ── Page Routes ───────────────────────────────────────────────────────────────
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
        cached = cache_get('cards')
        if cached: return jsonify(cached)
        try:
            cards = ws.get_all_records()
        except Exception:
            cards = []
        for c in cards:
            if str(c.get('last_digits', '')).startswith("'"): 
                c['last_digits'] = str(c['last_digits'])[1:]
        result = list(reversed(cards))
        cache_set('cards', result)
        return jsonify(result)
    data = request.json
    new_id = get_next_id(ws)
    last_digits = str(data.get('last_digits', ''))
    save_digits = f"'{last_digits}" if last_digits else ""
    ws.append_row([new_id, data.get('card_type', ''), save_digits])
    cache_clear('cards')
    cache_clear('card_lookup')
    return jsonify({'success': True})

@app.route('/api/cards/<int:card_id>', methods=['DELETE'])
def delete_card(card_id):
    ws = SHEET.worksheet('cards')
    try:
        cell = ws.find(str(card_id), in_column=1)
        ws.delete_rows(cell.row)
    except: pass
    cache_clear('cards')
    cache_clear('card_lookup')
    return jsonify({'success': True})

@app.route('/api/card-lookup')
def card_lookup():
    digits = request.args.get('digits', '').strip()
    if digits.startswith("'"): digits = digits[1:]
    if not SHEET: return jsonify({'found': False})
    ws = SHEET.worksheet('cards')
    try:
        records = ws.get_all_records()
    except Exception:
        records = []
    for row in records:
        db_digits = str(row.get('last_digits', ''))
        if db_digits.startswith("'"): db_digits = db_digits[1:]
        if db_digits == digits: return jsonify({'card_type': row.get('card_type'), 'found': True})
    return jsonify({'found': False})

def handle_master_table(table_name, req, field_name='name'):
    if not SHEET: return jsonify([])
    ws = SHEET.worksheet(table_name)
    if req.method == 'GET':
        cached = cache_get(f'master_{table_name}')
        if cached: return jsonify(cached)
        try:
            result = ws.get_all_records()
        except Exception:
            result = []
        cache_set(f'master_{table_name}', result)
        return jsonify(result)
    data = req.json
    new_id = get_next_id(ws)
    ws.append_row([new_id, data.get(field_name, '')])
    cache_clear(f'master_{table_name}')
    # Also clear dependent caches
    if table_name == 'platforms':
        cache_clear('platform_names')
    if table_name == 'models':
        for k in list(_cache.keys()):
            if k.startswith('variants'): cache_clear(k)
    return jsonify({'success': True})

def delete_master_table(table_name, item_id):
    ws = SHEET.worksheet(table_name)
    try:
        cell = ws.find(str(item_id), in_column=1)
        ws.delete_rows(cell.row)
    except: pass
    cache_clear(f'master_{table_name}')
    return jsonify({'success': True})

@app.route('/api/platforms', methods=['GET', 'POST'])
def api_platforms(): return handle_master_table('platforms', request, 'platform_name')
@app.route('/api/platforms/<int:id>', methods=['DELETE'])
def api_del_platforms(id):
    cache_clear('platform_names')
    return delete_master_table('platforms', id)

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

@app.route('/api/platform-names')
def platform_names():
    if not SHEET: return jsonify([])
    cached = cache_get('platform_names')
    if cached: return jsonify(cached)
    try:
        records = SHEET.worksheet('platforms').get_all_records()
    except Exception:
        records = []
    result = sorted(list(set([r['platform_name'] for r in records if r.get('platform_name')])))
    cache_set('platform_names', result)
    return jsonify(result)

@app.route('/api/variants', methods=['GET', 'POST'])
def api_variants():
    if not SHEET: return jsonify([])
    ws = SHEET.worksheet('variants')
    if request.method == 'GET':
        model_name = request.args.get('model')
        cache_key = f'variants_{model_name}' if model_name else 'variants_all'
        cached = cache_get(cache_key)
        if cached: return jsonify(cached)
        try:
            variants = ws.get_all_records()
        except Exception:
            variants = []
        if model_name:
            try:
                models = SHEET.worksheet('models').get_all_records()
            except Exception:
                models = []
            m_id = next((m['id'] for m in models if m['model_name'] == model_name), None)
            result = [v for v in variants if v['model_id'] == m_id] if m_id else []
        else:
            result = variants
        cache_set(cache_key, result)
        return jsonify(result)
    # POST — now saves selling_price as column 5
    data = request.json
    new_id = get_next_id(ws)
    ws.append_row([
        new_id,
        data.get('model_id'),
        data.get('variant_name', ''),
        data.get('costing', ''),
        data.get('selling_price', '')   # ← new column E
    ])
    for k in list(_cache.keys()):
        if k.startswith('variants'): cache_clear(k)
    return jsonify({'success': True})

@app.route('/api/variants/<int:var_id>', methods=['DELETE', 'PUT'])
def del_variant(var_id):
    if request.method == 'DELETE':
        for k in list(_cache.keys()):
            if k.startswith('variants'): cache_clear(k)
        return delete_master_table('variants', var_id)
    # PUT — update selling_price (and optionally costing) on the variant row
    if not SHEET: return jsonify({'success': False})
    data = request.json
    ws = SHEET.worksheet('variants')
    try:
        cell = ws.find(str(var_id), in_column=1)
        # Read existing row to preserve model_id, variant_name, costing unless sent
        row = ws.row_values(cell.row)
        new_cost = data.get('costing',       row[3] if len(row) > 3 else '')
        new_sell = data.get('selling_price', row[4] if len(row) > 4 else '')
        ws.update(f'D{cell.row}:E{cell.row}', [[new_cost, new_sell]])
        for k in list(_cache.keys()):
            if k.startswith('variants'): cache_clear(k)
        return jsonify({'success': True, 'costing': new_cost, 'selling_price': new_sell})
    except Exception as e:
        print("Variant PUT error:", e)
        return jsonify({'success': False})


@app.route('/api/variants/<int:var_id>/sync-sell-price', methods=['POST'])
def sync_variant_sell_price(var_id):
    """Push the variant's sell price to ALL existing orders that use this variant,
    recalculating profit = selling_price - costing for each row."""
    if not SHEET: return jsonify({'success': False})
    data = request.json
    variant_name = data.get('variant_name', '')
    new_sell     = data.get('selling_price', '')
    if not variant_name or new_sell == '':
        return jsonify({'success': False, 'error': 'variant_name and selling_price required'})
    try:
        new_sell_f = float(new_sell)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'invalid selling_price'})

    updated = 0
    errors  = []

    for sheet_name, variant_col, sell_col, profit_col, cost_col in [
        ('main_orders',      8, 10, 11, 9),    # variant=H, sell=J, profit=K, cost=I
        ('secondary_orders', 7,  9, 10, 8),    # variant=G, sell=I, profit=J, cost=H
    ]:
        try:
            ws = SHEET.worksheet(sheet_name)
            all_rows = ws.get_all_values()
            if not all_rows: continue
            for row_idx, row in enumerate(all_rows[1:], start=2):  # skip header
                cell_variant = row[variant_col - 1] if len(row) >= variant_col else ''
                if cell_variant.strip() == variant_name.strip():
                    try:
                        cost_val = float(row[cost_col - 1]) if len(row) >= cost_col and row[cost_col - 1] else 0.0
                    except (ValueError, TypeError):
                        cost_val = 0.0
                    profit = new_sell_f - cost_val
                    ws.update_cell(row_idx, sell_col,   new_sell_f)
                    ws.update_cell(row_idx, profit_col, round(profit, 2))
                    updated += 1
        except Exception as e:
            errors.append(f"{sheet_name}: {e}")

    cache_clear('main_orders')
    cache_clear('secondary_orders')
    return jsonify({'success': True, 'updated': updated, 'errors': errors})


# ── Main Orders API ───────────────────────────────────────────────────────────
@app.route('/api/main-orders', methods=['GET', 'POST'])
def api_main_orders():
    if not SHEET: return jsonify([])
    ws = SHEET.worksheet('main_orders')

    if request.method == 'GET':
        cached = cache_get('main_orders')
        if cached: return jsonify(cached)
        try:
            records = ws.get_all_records()
        except Exception:
            records = []
        for o in records:
            if str(o.get('last_digits', '')).startswith("'"): 
                o['last_digits'] = str(o['last_digits'])[1:]
        result = list(reversed(records))
        cache_set('main_orders', result)
        return jsonify(result)

    try:
        data = request.json
        next_id = get_next_id(ws)
        try: costing = float(data.get('costing') or 0)
        except ValueError: costing = 0.0
        try: selling = float(data.get('selling_price') or 0)
        except ValueError: selling = 0.0
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        last_digits = str(data.get('last_digits', ''))
        safe_digits = f"'{last_digits}" if last_digits else ""
        row = [
            next_id, data.get('card_type', ''), safe_digits, data.get('platform', ''),
            data.get('account', ''), data.get('order_name', ''), data.get('model', ''),
            data.get('variant', ''), costing, selling, selling - costing,
            data.get('delivery_date', ''), data.get('sale_batch', 'Current Sale'), now
        ]
        ws.append_row(row)
        cache_clear('main_orders')
        new_order = {
            'success': True, 'id': next_id,
            'card_type': data.get('card_type', ''), 'last_digits': last_digits,
            'platform': data.get('platform', ''), 'account': data.get('account', ''),
            'order_name': data.get('order_name', ''), 'model': data.get('model', ''),
            'variant': data.get('variant', ''), 'costing': costing,
            'selling_price': selling, 'profit': selling - costing,
            'delivery_date': data.get('delivery_date', ''),
            'sale_batch': data.get('sale_batch', 'Current Sale'), 'created_at': now
        }
        return jsonify(new_order)
    except Exception as e:
        print(f"Main Orders POST Error: {e}")
        return jsonify({'success': False}), 500

@app.route('/api/main-orders/bulk-delete', methods=['POST'])
def bulk_del_main():
    if not SHEET: return jsonify({'success': False})
    ids = request.json.get('ids', [])
    ws = SHEET.worksheet('main_orders')
    try:
        records = ws.get_all_records()
    except Exception:
        records = []
    rows_to_delete = [i + 2 for i, r in enumerate(records) if r.get('id') in ids]
    for r_idx in sorted(rows_to_delete, reverse=True):
        ws.delete_row(r_idx)
    cache_clear('main_orders')
    return jsonify({'success': True, 'deleted': len(rows_to_delete)})

@app.route('/api/main-orders/bulk-update-sale', methods=['POST'])
def bulk_sale_main():
    if not SHEET: return jsonify({'success': False})
    ids = request.json.get('ids', [])
    new_batch = request.json.get('sale_batch', 'Current Sale')
    ws = SHEET.worksheet('main_orders')
    try:
        records = ws.get_all_records()
        for i, r in enumerate(records):
            if r.get('id') in ids:
                ws.update_cell(i + 2, 13, new_batch)
        cache_clear('main_orders')
        return jsonify({'success': True})
    except Exception as e:
        print("Bulk Sale Error:", e)
        return jsonify({'success': False})

@app.route('/api/main-orders/export')
def export_main():
    if not SHEET: return "No sheet connected", 500
    fmt = request.args.get('format', 'csv')
    sale_filter = request.args.get('sale', '')
    try:
        records = SHEET.worksheet('main_orders').get_all_records()
    except Exception:
        records = []
    for o in records:
        if str(o.get('last_digits', '')).startswith("'"):
            o['last_digits'] = str(o['last_digits'])[1:]
    if sale_filter and sale_filter != 'ALL':
        records = [r for r in records if r.get('sale_batch', '') == sale_filter]
    headers = ['id','card_type','last_digits','platform','account','order_name',
               'model','variant','costing','selling_price','profit','delivery_date',
               'sale_batch','created_at']
    if fmt == 'csv':
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=headers, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'main_orders_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'
        )
    else:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Main Orders"
        header_fill = PatternFill("solid", fgColor="1A2D45")
        header_font = Font(bold=True, color="5BB8F5")
        ws.append(headers)
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
        for r in records:
            ws.append([r.get(h, '') for h in headers])
        for col in ws.columns:
            max_len = max((len(str(cell.value or '')) for cell in col), default=10)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 40)
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'main_orders_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx'
        )

@app.route('/api/main-orders/<int:id>', methods=['DELETE', 'PUT'])
def modify_main(id):
    if request.method == 'DELETE':
        cache_clear('main_orders')
        return delete_master_table('main_orders', id)
    if not SHEET: return jsonify({'success': False})
    data = request.json
    ws = SHEET.worksheet('main_orders')
    try:
        cell = ws.find(str(id), in_column=1)
        cost = float(data.get('costing', 0) or 0)
        sell = float(data.get('selling_price', 0) or 0)
        profit = sell - cost
        last_digits = str(data.get('last_digits', ''))
        safe_digits = f"'{last_digits}" if last_digits else ""
        ws.update(f'B{cell.row}:M{cell.row}', [[
            data.get('card_type', ''), safe_digits, data.get('platform', ''),
            data.get('account', ''), data.get('order_name', ''), data.get('model', ''),
            data.get('variant', ''), cost, sell, profit,
            data.get('delivery_date', ''), data.get('sale_batch', 'Current Sale')
        ]])
        cache_clear('main_orders')
        return jsonify({
            'success': True, 'id': id,
            'card_type': data.get('card_type', ''), 'last_digits': last_digits,
            'platform': data.get('platform', ''), 'account': data.get('account', ''),
            'order_name': data.get('order_name', ''), 'model': data.get('model', ''),
            'variant': data.get('variant', ''), 'costing': cost, 'selling_price': sell,
            'profit': profit, 'delivery_date': data.get('delivery_date', ''),
            'sale_batch': data.get('sale_batch', 'Current Sale')
        })
    except Exception as e:
        print("Edit Error:", e)
        return jsonify({'success': False})


# ── Secondary Orders API ──────────────────────────────────────────────────────
@app.route('/api/secondary-orders', methods=['GET', 'POST'])
def api_secondary_orders():
    if not SHEET: return jsonify([])
    ws = SHEET.worksheet('secondary_orders')

    if request.method == 'GET':
        cached = cache_get('secondary_orders')
        if cached: return jsonify(cached)
        try:
            records = ws.get_all_records()
        except Exception:
            records = []
        for o in records:
            if str(o.get('last_digits', '')).startswith("'"): 
                o['last_digits'] = str(o['last_digits'])[1:]
        result = list(reversed(records))
        cache_set('secondary_orders', result)
        return jsonify(result)

    try:
        data = request.json
        next_id = get_next_id(ws)
        try: costing = float(data.get('costing') or 0)
        except ValueError: costing = 0.0
        try: selling = float(data.get('selling_price') or 0)
        except ValueError: selling = 0.0
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        last_digits = str(data.get('last_digits', ''))
        safe_digits = f"'{last_digits}" if last_digits else ""
        row = [
            next_id, data.get('card_type', ''), safe_digits, data.get('platform', ''),
            data.get('order_name', ''), data.get('model', ''),
            data.get('variant', ''), costing, selling, selling - costing,
            data.get('delivery_date', ''), data.get('sale_batch', 'Current Sale'), now
        ]
        ws.append_row(row)
        cache_clear('secondary_orders')
        new_order = {
            'success': True, 'id': next_id,
            'card_type': data.get('card_type', ''), 'last_digits': last_digits,
            'platform': data.get('platform', ''),
            'order_name': data.get('order_name', ''), 'model': data.get('model', ''),
            'variant': data.get('variant', ''), 'costing': costing,
            'selling_price': selling, 'profit': selling - costing,
            'delivery_date': data.get('delivery_date', ''),
            'sale_batch': data.get('sale_batch', 'Current Sale'), 'created_at': now
        }
        return jsonify(new_order)
    except Exception as e:
        print(f"Secondary Orders POST Error: {e}")
        return jsonify({'success': False}), 500

@app.route('/api/secondary-orders/bulk-delete', methods=['POST'])
def bulk_del_sec():
    if not SHEET: return jsonify({'success': False})
    ids = request.json.get('ids', [])
    ws = SHEET.worksheet('secondary_orders')
    try:
        records = ws.get_all_records()
    except Exception:
        records = []
    rows_to_delete = [i + 2 for i, r in enumerate(records) if r.get('id') in ids]
    for r_idx in sorted(rows_to_delete, reverse=True):
        ws.delete_row(r_idx)
    cache_clear('secondary_orders')
    return jsonify({'success': True, 'deleted': len(rows_to_delete)})

@app.route('/api/secondary-orders/bulk-update-sale', methods=['POST'])
def bulk_sale_sec():
    if not SHEET: return jsonify({'success': False})
    ids = request.json.get('ids', [])
    new_batch = request.json.get('sale_batch', 'Current Sale')
    ws = SHEET.worksheet('secondary_orders')
    try:
        records = ws.get_all_records()
        for i, r in enumerate(records):
            if r.get('id') in ids:
                ws.update_cell(i + 2, 12, new_batch)
        cache_clear('secondary_orders')
        return jsonify({'success': True})
    except Exception as e:
        print("Bulk Sale Error:", e)
        return jsonify({'success': False})

@app.route('/api/secondary-orders/export')
def export_secondary():
    if not SHEET: return "No sheet connected", 500
    fmt = request.args.get('format', 'csv')
    sale_filter = request.args.get('sale', '')
    try:
        records = SHEET.worksheet('secondary_orders').get_all_records()
    except Exception:
        records = []
    for o in records:
        if str(o.get('last_digits', '')).startswith("'"):
            o['last_digits'] = str(o['last_digits'])[1:]
    if sale_filter and sale_filter != 'ALL':
        records = [r for r in records if r.get('sale_batch', '') == sale_filter]
    headers = ['id','card_type','last_digits','platform','order_name','model',
               'variant','costing','selling_price','profit','delivery_date',
               'sale_batch','created_at']
    if fmt == 'csv':
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=headers, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'secondary_orders_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'
        )
    else:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Secondary Orders"
        header_fill = PatternFill("solid", fgColor="1A2D45")
        header_font = Font(bold=True, color="5BB8F5")
        ws.append(headers)
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
        for r in records:
            ws.append([r.get(h, '') for h in headers])
        for col in ws.columns:
            max_len = max((len(str(cell.value or '')) for cell in col), default=10)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 40)
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'secondary_orders_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx'
        )

@app.route('/api/secondary-orders/<int:id>', methods=['DELETE', 'PUT'])
def modify_sec(id):
    if request.method == 'DELETE':
        cache_clear('secondary_orders')
        return delete_master_table('secondary_orders', id)
    if not SHEET: return jsonify({'success': False})
    data = request.json
    ws = SHEET.worksheet('secondary_orders')
    try:
        cell = ws.find(str(id), in_column=1)
        cost = float(data.get('costing', 0) or 0)
        sell = float(data.get('selling_price', 0) or 0)
        profit = sell - cost
        last_digits = str(data.get('last_digits', ''))
        safe_digits = f"'{last_digits}" if last_digits else ""
        ws.update(f'B{cell.row}:L{cell.row}', [[
            data.get('card_type', ''), safe_digits, data.get('platform', ''),
            data.get('order_name', ''), data.get('model', ''),
            data.get('variant', ''), cost, sell, profit,
            data.get('delivery_date', ''), data.get('sale_batch', 'Current Sale')
        ]])
        cache_clear('secondary_orders')
        return jsonify({
            'success': True, 'id': id,
            'card_type': data.get('card_type', ''), 'last_digits': last_digits,
            'platform': data.get('platform', ''),
            'order_name': data.get('order_name', ''), 'model': data.get('model', ''),
            'variant': data.get('variant', ''), 'costing': cost, 'selling_price': sell,
            'profit': profit, 'delivery_date': data.get('delivery_date', ''),
            'sale_batch': data.get('sale_batch', 'Current Sale')
        })
    except Exception as e:
        print("Edit Error:", e)
        return jsonify({'success': False})


# ── Offline Orders API ────────────────────────────────────────────────────────
@app.route('/api/offline-orders', methods=['GET', 'POST'])
def api_offline_orders():
    if not SHEET: return jsonify([])
    ws = SHEET.worksheet('offline_orders')

    if request.method == 'GET':
        cached = cache_get('offline_orders')
        if cached: return jsonify(cached)
        try:
            records = ws.get_all_records()
        except Exception:
            records = []
        for o in records:
            if str(o.get('last_digits', '')).startswith("'"): 
                o['last_digits'] = str(o['last_digits'])[1:]
        result = list(reversed(records))
        cache_set('offline_orders', result)
        return jsonify(result)

    try:
        data = request.json
        next_id = get_next_id(ws)
        try: costing = float(data.get('costing') or 0)
        except ValueError: costing = 0.0
        try: selling = float(data.get('selling_price') or 0)
        except ValueError: selling = 0.0
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        last_digits = str(data.get('last_digits', ''))
        safe_digits = f"'{last_digits}" if last_digits else ""
        row = [
            next_id, data.get('card_type', ''), safe_digits, data.get('machine', ''),
            data.get('vendor', ''), data.get('brand', ''), data.get('sale_type', ''),
            costing, selling, selling - costing, data.get('sale_month', ''), now
        ]
        ws.append_row(row)
        cache_clear('offline_orders')
        new_order = {
            'success': True, 'id': next_id,
            'card_type': data.get('card_type', ''), 'last_digits': last_digits,
            'machine': data.get('machine', ''), 'vendor': data.get('vendor', ''),
            'brand': data.get('brand', ''), 'sale_type': data.get('sale_type', ''),
            'costing': costing, 'selling_price': selling, 'profit': selling - costing,
            'sale_month': data.get('sale_month', ''), 'created_at': now
        }
        return jsonify(new_order)
    except Exception as e:
        print(f"Offline POST Error: {e}")
        return jsonify({'success': False}), 500

@app.route('/api/offline-orders/bulk-delete', methods=['POST'])
def bulk_del_offline():
    if not SHEET: return jsonify({'success': False})
    ids = request.json.get('ids', [])
    ws = SHEET.worksheet('offline_orders')
    try:
        records = ws.get_all_records()
    except Exception:
        records = []
    rows_to_delete = [i + 2 for i, r in enumerate(records) if r.get('id') in ids]
    for r_idx in sorted(rows_to_delete, reverse=True):
        ws.delete_row(r_idx)
    cache_clear('offline_orders')
    return jsonify({'success': True, 'deleted': len(rows_to_delete)})

@app.route('/api/offline-orders/export')
def export_offline():
    if not SHEET: return "No sheet connected", 500
    fmt = request.args.get('format', 'csv')
    month_filter = request.args.get('month', '')
    try:
        records = SHEET.worksheet('offline_orders').get_all_records()
    except Exception:
        records = []
    for o in records:
        if str(o.get('last_digits', '')).startswith("'"):
            o['last_digits'] = str(o['last_digits'])[1:]
    if month_filter:
        records = [r for r in records if r.get('sale_month', '') == month_filter]
    headers = ['id','card_type','last_digits','machine','vendor','brand',
               'sale_type','costing','selling_price','profit','sale_month','created_at']
    if fmt == 'csv':
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=headers, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'offline_orders_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'
        )
    else:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Offline Sales"
        header_fill = PatternFill("solid", fgColor="1A2D45")
        header_font = Font(bold=True, color="2ECC8F")
        ws.append(headers)
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
        for r in records:
            ws.append([r.get(h, '') for h in headers])
        for col in ws.columns:
            max_len = max((len(str(cell.value or '')) for cell in col), default=10)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 40)
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'offline_orders_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx'
        )

@app.route('/api/offline-orders/<int:id>', methods=['DELETE', 'PUT'])
def modify_offline(id):
    if request.method == 'DELETE':
        cache_clear('offline_orders')
        return delete_master_table('offline_orders', id)
    if not SHEET: return jsonify({'success': False})
    data = request.json
    ws = SHEET.worksheet('offline_orders')
    try:
        cell = ws.find(str(id), in_column=1)
        cost = float(data.get('costing', 0) or 0)
        sell = float(data.get('selling_price', 0) or 0)
        profit = sell - cost
        last_digits = str(data.get('last_digits', ''))
        safe_digits = f"'{last_digits}" if last_digits else ""
        ws.update(f'B{cell.row}:K{cell.row}', [[
            data.get('card_type', ''), safe_digits, data.get('machine', ''),
            data.get('vendor', ''), data.get('brand', ''), data.get('sale_type', ''),
            cost, sell, profit, data.get('sale_month', '')
        ]])
        cache_clear('offline_orders')
        return jsonify({
            'success': True, 'id': id,
            'card_type': data.get('card_type', ''), 'last_digits': last_digits,
            'machine': data.get('machine', ''), 'vendor': data.get('vendor', ''),
            'brand': data.get('brand', ''), 'sale_type': data.get('sale_type', ''),
            'costing': cost, 'selling_price': sell, 'profit': profit,
            'sale_month': data.get('sale_month', '')
        })
    except Exception as e:
        print("Edit Error:", e)
        return jsonify({'success': False})


# ── PWA Setup ─────────────────────────────────────────────────────────────────
@app.route('/manifest.json')
def serve_manifest(): return send_file('static/manifest.json', mimetype='application/manifest+json')
@app.route('/sw.js')
def serve_sw(): return send_file('static/sw.js', mimetype='application/javascript')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
