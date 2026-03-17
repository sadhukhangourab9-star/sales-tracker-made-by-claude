from flask import Flask, render_template, request, jsonify, send_file
import sqlite3
import os
import io
from datetime import datetime
import csv
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

app = Flask(__name__)
DATABASE = os.environ.get('DATABASE_PATH', 'orders.db')


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_type TEXT NOT NULL,
            last_digits TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS platforms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform_name TEXT NOT NULL,
            account_name TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS variants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id INTEGER NOT NULL,
            variant_name TEXT NOT NULL,
            FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS main_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_type TEXT,
            last_digits TEXT,
            platform TEXT,
            account TEXT,
            order_name TEXT,
            model TEXT,
            variant TEXT,
            costing REAL,
            delivery_date TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS secondary_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_type TEXT,
            last_digits TEXT,
            platform TEXT,
            model TEXT,
            variant TEXT,
            costing REAL,
            created_at TEXT
        );
    ''')
    conn.commit()
    conn.close()


init_db()


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
    conn = get_db()
    cards = conn.execute('SELECT * FROM cards ORDER BY id DESC').fetchall()
    conn.close()
    return jsonify([dict(c) for c in cards])


@app.route('/api/cards', methods=['POST'])
def add_card():
    data = request.json
    conn = get_db()
    try:
        conn.execute('INSERT INTO cards (card_type, last_digits) VALUES (?, ?)',
                     (data['card_type'], data['last_digits']))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    finally:
        conn.close()


@app.route('/api/cards/<int:card_id>', methods=['DELETE'])
def delete_card(card_id):
    conn = get_db()
    conn.execute('DELETE FROM cards WHERE id = ?', (card_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/card-lookup')
def card_lookup():
    digits = request.args.get('digits', '').strip()
    conn = get_db()
    card = conn.execute('SELECT * FROM cards WHERE last_digits = ?', (digits,)).fetchone()
    conn.close()
    if card:
        return jsonify({'card_type': card['card_type'], 'found': True})
    return jsonify({'found': False})


# ── Platforms API ─────────────────────────────────────────────────────────────

@app.route('/api/platforms', methods=['GET'])
def get_platforms():
    conn = get_db()
    platforms = conn.execute('SELECT * FROM platforms ORDER BY platform_name').fetchall()
    conn.close()
    return jsonify([dict(p) for p in platforms])


@app.route('/api/platforms', methods=['POST'])
def add_platform():
    data = request.json
    conn = get_db()
    try:
        conn.execute('INSERT INTO platforms (platform_name, account_name) VALUES (?, ?)',
                     (data['platform_name'], data['account_name']))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    finally:
        conn.close()


@app.route('/api/platforms/<int:platform_id>', methods=['DELETE'])
def delete_platform(platform_id):
    conn = get_db()
    conn.execute('DELETE FROM platforms WHERE id = ?', (platform_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/platform-lookup')
def platform_lookup():
    platform_name = request.args.get('platform', '')
    conn = get_db()
    rows = conn.execute(
        'SELECT DISTINCT account_name FROM platforms WHERE platform_name = ?',
        (platform_name,)).fetchall()
    conn.close()
    return jsonify([r['account_name'] for r in rows])


@app.route('/api/platform-names')
def platform_names():
    conn = get_db()
    rows = conn.execute(
        'SELECT DISTINCT platform_name FROM platforms ORDER BY platform_name').fetchall()
    conn.close()
    return jsonify([r['platform_name'] for r in rows])


# ── Models API ────────────────────────────────────────────────────────────────

@app.route('/api/models', methods=['GET'])
def get_models():
    conn = get_db()
    models = conn.execute('SELECT * FROM models ORDER BY model_name').fetchall()
    conn.close()
    return jsonify([dict(m) for m in models])


@app.route('/api/models', methods=['POST'])
def add_model():
    data = request.json
    conn = get_db()
    try:
        cursor = conn.execute('INSERT INTO models (model_name) VALUES (?)', (data['model_name'],))
        model_id = cursor.lastrowid
        conn.commit()
        return jsonify({'success': True, 'model_id': model_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    finally:
        conn.close()


@app.route('/api/models/<int:model_id>', methods=['DELETE'])
def delete_model(model_id):
    conn = get_db()
    conn.execute('DELETE FROM variants WHERE model_id = ?', (model_id,))
    conn.execute('DELETE FROM models WHERE id = ?', (model_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ── Variants API ──────────────────────────────────────────────────────────────

@app.route('/api/variants', methods=['GET'])
def get_variants():
    model_name = request.args.get('model', '')
    conn = get_db()
    model = conn.execute('SELECT id FROM models WHERE model_name = ?', (model_name,)).fetchone()
    if not model:
        conn.close()
        return jsonify([])
    variants = conn.execute('SELECT * FROM variants WHERE model_id = ?', (model['id'],)).fetchall()
    conn.close()
    return jsonify([v['variant_name'] for v in variants])


@app.route('/api/variants/by-model/<int:model_id>', methods=['GET'])
def get_variants_by_model_id(model_id):
    conn = get_db()
    variants = conn.execute('SELECT * FROM variants WHERE model_id = ?', (model_id,)).fetchall()
    conn.close()
    return jsonify([dict(v) for v in variants])


@app.route('/api/variants', methods=['POST'])
def add_variant():
    data = request.json
    conn = get_db()
    try:
        conn.execute('INSERT INTO variants (model_id, variant_name) VALUES (?, ?)',
                     (data['model_id'], data['variant_name']))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    finally:
        conn.close()


@app.route('/api/variants/<int:variant_id>', methods=['DELETE'])
def delete_variant(variant_id):
    conn = get_db()
    conn.execute('DELETE FROM variants WHERE id = ?', (variant_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ── Main Orders API ───────────────────────────────────────────────────────────

@app.route('/api/main-orders', methods=['GET'])
def get_main_orders():
    conn = get_db()
    orders = conn.execute('SELECT * FROM main_orders ORDER BY id DESC').fetchall()
    conn.close()
    return jsonify([dict(o) for o in orders])


@app.route('/api/main-orders', methods=['POST'])
def add_main_order():
    data = request.json
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db()
    try:
        cursor = conn.execute('''
            INSERT INTO main_orders
            (card_type, last_digits, platform, account, order_name, model, variant, costing, delivery_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('card_type'), data.get('last_digits'), data.get('platform'),
            data.get('account'), data.get('order_name'), data.get('model'),
            data.get('variant'), data.get('costing'), data.get('delivery_date'), now
        ))
        order_id = cursor.lastrowid
        conn.commit()
        order = conn.execute('SELECT * FROM main_orders WHERE id = ?', (order_id,)).fetchone()
        return jsonify(dict(order))
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    finally:
        conn.close()


@app.route('/api/main-orders/<int:order_id>', methods=['PUT'])
def update_main_order(order_id):
    data = request.json
    conn = get_db()
    try:
        conn.execute('''
            UPDATE main_orders SET
            card_type=?, last_digits=?, platform=?, account=?, order_name=?,
            model=?, variant=?, costing=?, delivery_date=?
            WHERE id=?
        ''', (
            data.get('card_type'), data.get('last_digits'), data.get('platform'),
            data.get('account'), data.get('order_name'), data.get('model'),
            data.get('variant'), data.get('costing'), data.get('delivery_date'),
            order_id
        ))
        conn.commit()
        order = conn.execute('SELECT * FROM main_orders WHERE id = ?', (order_id,)).fetchone()
        return jsonify(dict(order))
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    finally:
        conn.close()


@app.route('/api/main-orders/<int:order_id>', methods=['DELETE'])
def delete_main_order(order_id):
    conn = get_db()
    conn.execute('DELETE FROM main_orders WHERE id = ?', (order_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/main-orders/bulk-delete', methods=['POST'])
def bulk_delete_main_orders():
    data = request.json
    ids = data.get('ids', [])
    if not ids:
        return jsonify({'error': 'No IDs provided'}), 400
    conn = get_db()
    placeholders = ','.join('?' * len(ids))
    conn.execute(f'DELETE FROM main_orders WHERE id IN ({placeholders})', ids)
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'deleted': len(ids)})


@app.route('/api/main-orders/export')
def export_main_orders():
    fmt = request.args.get('format', 'csv')
    conn = get_db()
    orders = conn.execute('SELECT * FROM main_orders ORDER BY id DESC').fetchall()
    conn.close()
    headers = ['ID', 'Card Type', 'Last Digits', 'Platform', 'Account',
               'Order Name', 'Model', 'Variant', 'Costing', 'Delivery Date', 'Created At']

    if fmt == 'excel':
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Main Orders'
        hfill = PatternFill(start_color='1E3A5F', end_color='1E3A5F', fill_type='solid')
        hfont = Font(color='FFFFFF', bold=True)
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.fill = hfill
            cell.font = hfont
            cell.alignment = Alignment(horizontal='center')
        for rn, o in enumerate(orders, 2):
            d = dict(o)
            vals = [d.get('id'), d.get('card_type'), d.get('last_digits'), d.get('platform'),
                    d.get('account'), d.get('order_name'), d.get('model'), d.get('variant'),
                    d.get('costing'), d.get('delivery_date'), d.get('created_at')]
            for cn, v in enumerate(vals, 1):
                ws.cell(row=rn, column=cn, value=v)
        for col in ws.columns:
            max_len = max((len(str(cell.value or '')) for cell in col), default=10)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 30)
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return send_file(output,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True, download_name='main_orders.xlsx')
    else:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        for o in orders:
            d = dict(o)
            writer.writerow([d.get('id'), d.get('card_type'), d.get('last_digits'),
                             d.get('platform'), d.get('account'), d.get('order_name'),
                             d.get('model'), d.get('variant'), d.get('costing'),
                             d.get('delivery_date'), d.get('created_at')])
        return send_file(io.BytesIO(output.getvalue().encode()),
                         mimetype='text/csv', as_attachment=True,
                         download_name='main_orders.csv')


# ── Secondary Orders API ──────────────────────────────────────────────────────

@app.route('/api/secondary-orders', methods=['GET'])
def get_secondary_orders():
    conn = get_db()
    orders = conn.execute('SELECT * FROM secondary_orders ORDER BY id DESC').fetchall()
    conn.close()
    return jsonify([dict(o) for o in orders])


@app.route('/api/secondary-orders', methods=['POST'])
def add_secondary_order():
    data = request.json
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db()
    try:
        cursor = conn.execute('''
            INSERT INTO secondary_orders
            (card_type, last_digits, platform, model, variant, costing, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('card_type'), data.get('last_digits'), data.get('platform'),
            data.get('model'), data.get('variant'), data.get('costing'), now
        ))
        order_id = cursor.lastrowid
        conn.commit()
        order = conn.execute('SELECT * FROM secondary_orders WHERE id = ?', (order_id,)).fetchone()
        return jsonify(dict(order))
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    finally:
        conn.close()


@app.route('/api/secondary-orders/<int:order_id>', methods=['PUT'])
def update_secondary_order(order_id):
    data = request.json
    conn = get_db()
    try:
        conn.execute('''
            UPDATE secondary_orders SET
            card_type=?, last_digits=?, platform=?, model=?, variant=?, costing=?
            WHERE id=?
        ''', (
            data.get('card_type'), data.get('last_digits'), data.get('platform'),
            data.get('model'), data.get('variant'), data.get('costing'), order_id
        ))
        conn.commit()
        order = conn.execute('SELECT * FROM secondary_orders WHERE id = ?', (order_id,)).fetchone()
        return jsonify(dict(order))
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    finally:
        conn.close()


@app.route('/api/secondary-orders/<int:order_id>', methods=['DELETE'])
def delete_secondary_order(order_id):
    conn = get_db()
    conn.execute('DELETE FROM secondary_orders WHERE id = ?', (order_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/secondary-orders/bulk-delete', methods=['POST'])
def bulk_delete_secondary_orders():
    data = request.json
    ids = data.get('ids', [])
    if not ids:
        return jsonify({'error': 'No IDs provided'}), 400
    conn = get_db()
    placeholders = ','.join('?' * len(ids))
    conn.execute(f'DELETE FROM secondary_orders WHERE id IN ({placeholders})', ids)
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'deleted': len(ids)})


@app.route('/api/secondary-orders/export')
def export_secondary_orders():
    fmt = request.args.get('format', 'csv')
    conn = get_db()
    orders = conn.execute('SELECT * FROM secondary_orders ORDER BY id DESC').fetchall()
    conn.close()
    headers = ['ID', 'Card Type', 'Last Digits', 'Platform', 'Model', 'Variant', 'Costing', 'Created At']

    if fmt == 'excel':
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Secondary Orders'
        hfill = PatternFill(start_color='1E3A5F', end_color='1E3A5F', fill_type='solid')
        hfont = Font(color='FFFFFF', bold=True)
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.fill = hfill
            cell.font = hfont
            cell.alignment = Alignment(horizontal='center')
        for rn, o in enumerate(orders, 2):
            d = dict(o)
            vals = [d.get('id'), d.get('card_type'), d.get('last_digits'), d.get('platform'),
                    d.get('model'), d.get('variant'), d.get('costing'), d.get('created_at')]
            for cn, v in enumerate(vals, 1):
                ws.cell(row=rn, column=cn, value=v)
        for col in ws.columns:
            max_len = max((len(str(cell.value or '')) for cell in col), default=10)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 30)
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return send_file(output,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True, download_name='secondary_orders.xlsx')
    else:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        for o in orders:
            d = dict(o)
            writer.writerow([d.get('id'), d.get('card_type'), d.get('last_digits'),
                             d.get('platform'), d.get('model'), d.get('variant'),
                             d.get('costing'), d.get('created_at')])
        return send_file(io.BytesIO(output.getvalue().encode()),
                         mimetype='text/csv', as_attachment=True,
                         download_name='secondary_orders.csv')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
