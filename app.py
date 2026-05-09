from flask import Flask, render_template, request, jsonify, send_file, send_from_directory, session, redirect, url_for
from flask_socketio import SocketIO, emit
import sqlite3, json, os, io, csv, hashlib, secrets, base64
from datetime import datetime, date, timedelta
from functools import wraps
import werkzeug.utils

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'pos-ultra-secret-2024-xK9mP-DEV-ONLY')
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB upload limit
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=os.environ.get('SOCKETIO_ASYNC_MODE','threading'))

_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('DB_PATH', os.path.join(_HERE, 'data', 'pos.db'))
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', os.path.join(_HERE, 'static', 'uploads'))
UPLOAD_URL_PREFIX = os.environ.get('UPLOAD_URL_PREFIX', '/static/uploads')

# ── ADMIN CREDENTIALS (override via env in production) ────────────────────────
ADMIN_ID = os.environ.get('ADMIN_ID', 'POSADMIN2024')
ADMIN_PASS = os.environ.get('ADMIN_PASS', 'Adm!nX9@Secure')

# ── DB ────────────────────────────────────────────────────────────────────────
def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    conn = get_db(); c = conn.cursor()
    c.executescript('''
        CREATE TABLE IF NOT EXISTS billers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            biller_id TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, color TEXT DEFAULT '#6366f1');
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, phone TEXT, email TEXT,
            address TEXT, notes TEXT,
            due_amount REAL DEFAULT 0,
            total_purchased REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE, unit TEXT DEFAULT 'unit',
            stock REAL DEFAULT 0, low_threshold REAL DEFAULT 5,
            cost_per_unit REAL DEFAULT 0, supplier_id INTEGER,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY(supplier_id) REFERENCES suppliers(id)
        );
        CREATE TABLE IF NOT EXISTS purchase_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inventory_id INTEGER, supplier_id INTEGER,
            quantity REAL NOT NULL, cost_per_unit REAL DEFAULT 0,
            total_cost REAL DEFAULT 0,
            payment_method TEXT DEFAULT 'cash',
            is_due INTEGER DEFAULT 0,
            notes TEXT DEFAULT '',
            purchased_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY(inventory_id) REFERENCES inventory(id),
            FOREIGN KEY(supplier_id) REFERENCES suppliers(id)
        );
        CREATE TABLE IF NOT EXISTS menu_customizations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            menu_item_id INTEGER NOT NULL, name TEXT NOT NULL,
            options TEXT NOT NULL, is_required INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS menu_portions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            menu_item_id INTEGER NOT NULL, inventory_id INTEGER NOT NULL,
            qty_used REAL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS menu_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, price REAL NOT NULL,
            category_id INTEGER, stock INTEGER DEFAULT 999,
            low_stock_threshold INTEGER DEFAULT 10,
            is_available INTEGER DEFAULT 1, description TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS tables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number TEXT NOT NULL UNIQUE, status TEXT DEFAULT 'free',
            capacity INTEGER DEFAULT 4, section TEXT DEFAULT 'Main');
        CREATE TABLE IF NOT EXISTS hotel_rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_number TEXT NOT NULL UNIQUE,
            room_type TEXT DEFAULT 'Standard',
            floor INTEGER DEFAULT 1,
            capacity INTEGER DEFAULT 2,
            price_per_night REAL DEFAULT 0,
            status TEXT DEFAULT 'available',
            current_guest TEXT DEFAULT '',
            checkin_date TEXT DEFAULT '',
            checkout_date TEXT DEFAULT '',
            notes TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, phone TEXT,
            email TEXT, due_amount REAL DEFAULT 0,
            total_spent REAL DEFAULT 0, visit_count INTEGER DEFAULT 0,
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_type TEXT DEFAULT 'dine_in', table_id INTEGER,
            customer_id INTEGER, status TEXT DEFAULT 'open',
            payment_method TEXT, payment_subtype TEXT DEFAULT '',
            is_due INTEGER DEFAULT 0,
            subtotal REAL DEFAULT 0, tax REAL DEFAULT 0,
            discount REAL DEFAULT 0, total REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            closed_at TEXT, customer_name TEXT, notes TEXT,
            source TEXT DEFAULT 'pos',
            kot_printed INTEGER DEFAULT 0, bill_printed INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER, item_id INTEGER, item_name TEXT,
            price REAL, quantity INTEGER DEFAULT 1,
            customizations TEXT DEFAULT '', notes TEXT
        );
        CREATE TABLE IF NOT EXISTS due_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL, order_id INTEGER,
            amount REAL NOT NULL,
            payment_method TEXT DEFAULT 'cash',
            payment_subtype TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL, amount REAL NOT NULL,
            category TEXT DEFAULT 'other',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            biller_id TEXT,
            action TEXT NOT NULL,
            entity TEXT NOT NULL,
            detail TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS hotel_bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id INTEGER NOT NULL,
            room_number TEXT NOT NULL,
            guest_name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            checkin_date TEXT NOT NULL,
            checkout_date TEXT NOT NULL,
            nights INTEGER DEFAULT 1,
            price_per_night REAL DEFAULT 0,
            total_amount REAL DEFAULT 0,
            payment_method TEXT DEFAULT 'cash',
            status TEXT DEFAULT 'checked_in',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            checked_out_at TEXT DEFAULT ''
        );
    ''')

    # Migrations for existing DBs
    try:
        c.execute('SELECT 1 FROM audit_logs LIMIT 1')
    except:
        c.execute('''CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            biller_id TEXT, action TEXT NOT NULL, entity TEXT NOT NULL,
            detail TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now','localtime')))''')
    try:
        c.execute('SELECT 1 FROM hotel_bookings LIMIT 1')
    except:
        c.execute('''CREATE TABLE IF NOT EXISTS hotel_bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, room_id INTEGER NOT NULL,
            room_number TEXT NOT NULL, guest_name TEXT NOT NULL, phone TEXT DEFAULT '',
            checkin_date TEXT NOT NULL, checkout_date TEXT NOT NULL, nights INTEGER DEFAULT 1,
            price_per_night REAL DEFAULT 0, total_amount REAL DEFAULT 0,
            payment_method TEXT DEFAULT 'cash', status TEXT DEFAULT 'checked_in',
            notes TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now','localtime')),
            checked_out_at TEXT DEFAULT '')''')
    migrations = [
        ("orders","payment_subtype","ALTER TABLE orders ADD COLUMN payment_subtype TEXT DEFAULT ''"),
        ("due_payments","payment_subtype","ALTER TABLE due_payments ADD COLUMN payment_subtype TEXT DEFAULT ''"),
        ("menu_items","description","ALTER TABLE menu_items ADD COLUMN description TEXT DEFAULT ''"),
        ("orders","customer_id","ALTER TABLE orders ADD COLUMN customer_id INTEGER"),
        ("orders","is_due","ALTER TABLE orders ADD COLUMN is_due INTEGER DEFAULT 0"),
        ("orders","source","ALTER TABLE orders ADD COLUMN source TEXT DEFAULT 'pos'"),
        ("order_items","customizations","ALTER TABLE order_items ADD COLUMN customizations TEXT DEFAULT ''"),
        ("inventory","supplier_id","ALTER TABLE inventory ADD COLUMN supplier_id INTEGER"),
        ("tables","section","ALTER TABLE tables ADD COLUMN section TEXT DEFAULT 'Main'"),
    ]
    for table, col, sql in migrations:
        try:
            cols = [r[1] for r in c.execute(f'PRAGMA table_info({table})').fetchall()]
            if col not in cols: c.execute(sql)
        except: pass

    # Default settings
    defaults = [
        ('restaurant_name','Highway Rasoi'),('tax_rate','5'),('currency','₹'),
        ('baseline_daily_sales','5000'),('upi_id','restaurant@upi'),('upi_qr_url',''),
        ('gstin',''),('logo_url',''),('profile_pic_url',''),
    ]
    for k,v in defaults: c.execute('INSERT OR IGNORE INTO settings VALUES(?,?)',(k,v))

    # Seed data — only on a truly fresh install. The 'seeded' flag prevents re-seeding
    # after an admin/test wipe of categories.
    seeded_row = c.execute("SELECT value FROM settings WHERE key='seeded'").fetchone()
    if not (seeded_row and seeded_row[0] == '1'):
        c.execute('SELECT COUNT(*) FROM categories')
        if c.fetchone()[0] == 0:
            for cat in [('Starters','#f59e0b'),('Mains','#10b981'),('Beverages','#3b82f6'),('Desserts','#ec4899'),('Breads','#8b5cf6')]:
                c.execute('INSERT INTO categories(name,color) VALUES(?,?)',cat)
            items=[('Paneer Tikka',220,1,50),('Veg Spring Roll',160,1,40),('Chicken Wings',280,1,30),
                   ('Dal Makhani',200,2,100),('Butter Chicken',320,2,80),('Veg Biryani',240,2,60),
                   ('Masala Chai',40,3,200),('Cold Coffee',80,3,100),('Gulab Jamun',80,4,80),('Naan',40,5,200)]
            for item in items: c.execute('INSERT INTO menu_items(name,price,category_id,stock) VALUES(?,?,?,?)',item)
            for i in range(1,13): c.execute('INSERT OR IGNORE INTO tables(number,capacity) VALUES(?,?)',(str(i),4 if i<=8 else 6))
        c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('seeded','1')")

    # Default biller
    c.execute('SELECT COUNT(*) FROM billers')
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO billers(biller_id,password_hash,name) VALUES(?,?,?)',
            ('BILLER001', hash_pw('Pass@1234'), 'Default Biller'))

    conn.commit(); conn.close()

def get_setting(key, default=''):
    conn=get_db(); row=conn.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone(); conn.close()
    return row['value'] if row else default

def get_all_settings():
    conn=get_db(); rows=conn.execute('SELECT key,value FROM settings').fetchall(); conn.close()
    return {r['key']:r['value'] for r in rows}

def broadcast(ev,data=None): socketio.emit('update',{'type':ev,'data':data or {}})

def log_action(action, entity, detail='', biller_id=None, conn=None):
    """Write audit log directly to SQLite - works in any context."""
    import sqlite3 as _sq3
    try:
        bid = biller_id or 'system'
        # Try to get from Flask session if we are in a request context
        try:
            from flask.globals import _request_ctx_err_msg
        except ImportError:
            pass
        try:
            if session:
                bid = session.get('biller_id') or session.get('admin_id') or bid
        except Exception:
            pass
        if conn is not None:
            conn.execute('INSERT INTO audit_logs(biller_id,action,entity,detail) VALUES(?,?,?,?)',
                         (str(bid), str(action), str(entity), str(detail)[:500]))
            return
        _c = _sq3.connect(DB_PATH, timeout=0.1)
        _c.execute('INSERT INTO audit_logs(biller_id,action,entity,detail) VALUES(?,?,?,?)',
                   (str(bid), str(action), str(entity), str(detail)[:500]))
        _c.commit()
        _c.close()
    except Exception:
        pass

def _recalc(conn,oid):
    items=conn.execute('SELECT price,quantity FROM order_items WHERE order_id=?',(oid,)).fetchall()
    sub=sum(i['price']*i['quantity'] for i in items)
    tax=round(sub*(float(get_setting('tax_rate','5'))/100),2)
    disc=conn.execute('SELECT discount FROM orders WHERE id=?',(oid,)).fetchone()['discount']
    conn.execute('UPDATE orders SET subtotal=?,tax=?,total=? WHERE id=?',(sub,tax,round(sub+tax-disc,2),oid))

# ── AUTH DECORATORS ───────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('biller_logged_in') and not session.get('admin_logged_in'):
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login_page'))
        return f(*args, **kwargs)
    return decorated

# ── AUTH PAGES ────────────────────────────────────────────────────────────────
@app.route('/login', methods=['GET'])
def login_page(): return render_template('login.html', settings=get_all_settings())

@app.route('/api/auth/login', methods=['POST'])
def do_login():
    d = request.json
    uid = d.get('id','').strip()
    pw  = d.get('password','').strip()
    # Admin check
    if uid == ADMIN_ID and pw == ADMIN_PASS:
        session['admin_logged_in'] = True
        session['admin_id'] = ADMIN_ID
        session.permanent = True
        return jsonify({'ok':True,'role':'admin','redirect':'/admin'})
    # Biller check
    conn = get_db()
    biller = conn.execute('SELECT * FROM billers WHERE biller_id=? AND is_active=1',(uid,)).fetchone()
    conn.close()
    if biller and biller['password_hash'] == hash_pw(pw):
        session['biller_logged_in'] = True
        session['biller_id'] = uid
        session['biller_name'] = biller['name']
        session.permanent = True
        return jsonify({'ok':True,'role':'biller','redirect':'/'})
    return jsonify({'ok':False,'error':'Invalid ID or password'}), 401

@app.route('/api/auth/logout', methods=['POST'])
def do_logout():
    session.clear()
    return jsonify({'ok':True})

@app.route('/admin/login', methods=['GET'])
def admin_login_page(): return render_template('admin_login.html', settings=get_all_settings())

@app.route('/admin')
@admin_required
def admin_page(): return render_template('admin.html', settings=get_all_settings(), admin_id=ADMIN_ID)

# Admin: manage billers
@app.route('/api/admin/billers', methods=['GET','POST'])
@admin_required
def admin_billers():
    conn = get_db()
    if request.method == 'POST':
        d = request.json
        bid = d.get('biller_id','').strip().upper()
        if not bid or not d.get('password') or not d.get('name'):
            return jsonify({'ok':False,'error':'All fields required'}), 400
        try:
            conn.execute('INSERT INTO billers(biller_id,password_hash,name) VALUES(?,?,?)',
                (bid, hash_pw(d['password']), d['name']))
            conn.commit(); conn.close(); return jsonify({'ok':True})
        except: conn.close(); return jsonify({'ok':False,'error':'ID already exists'}), 400
    rows = conn.execute('SELECT id,biller_id,name,is_active,created_at FROM billers ORDER BY created_at DESC').fetchall()
    conn.close(); return jsonify([dict(r) for r in rows])

@app.route('/api/admin/billers/<int:bid>', methods=['PUT','DELETE'])
@admin_required
def admin_biller(bid):
    conn = get_db()
    if request.method == 'DELETE':
        biller = conn.execute('SELECT biller_id FROM billers WHERE id=?',(bid,)).fetchone()
        conn.execute('DELETE FROM billers WHERE id=?',(bid,))
        log_action('delete_biller','biller', biller['biller_id'] if biller else str(bid), conn=conn)
    else:
        d = request.json
        if d.get('password'):
            conn.execute('UPDATE billers SET name=?,is_active=?,password_hash=? WHERE id=?',
                (d['name'],d.get('is_active',1),hash_pw(d['password']),bid))
        else:
            conn.execute('UPDATE billers SET name=?,is_active=? WHERE id=?',
                (d['name'],d.get('is_active',1),bid))
        log_action('edit_biller','biller',d.get('name',''), conn=conn)
    conn.commit(); conn.close(); return jsonify({'ok':True})

# ── FILE UPLOAD ───────────────────────────────────────────────────────────────
@app.route('/api/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files: return jsonify({'error':'No file'}), 400
    f = request.files['file']
    field = request.form.get('field','logo')
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    ext = f.filename.rsplit('.',1)[-1].lower() if '.' in f.filename else 'png'
    if ext not in ['png','jpg','jpeg','gif','webp']: return jsonify({'error':'Invalid file type'}), 400
    filename = f'{field}.{ext}'
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    f.save(filepath)
    url = f'{UPLOAD_URL_PREFIX.rstrip("/")}/{filename}'
    conn = get_db()
    conn.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(f'{field}_url',url))
    conn.commit(); conn.close()
    return jsonify({'ok':True,'url':url})

# Serve uploads when UPLOAD_FOLDER is moved off the static/ tree (e.g. persistent disk in prod)
@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# ── MAIN PAGES ────────────────────────────────────────────────────────────────
@app.route('/')
@login_required
def index(): return render_template('pos.html', settings=get_all_settings())

@app.route('/dashboard')
@login_required
def dashboard(): return render_template('dashboard.html', settings=get_all_settings())

@app.route('/reports')
@login_required
def reports(): return render_template('reports.html', settings=get_all_settings())

@app.route('/menu')
@login_required
def menu_mgmt(): return render_template('menu.html', settings=get_all_settings())

@app.route('/inventory')
@login_required
def inventory_page(): return render_template('inventory.html', settings=get_all_settings())

@app.route('/customers')
@login_required
def customers_page(): return render_template('customers.html', settings=get_all_settings())

@app.route('/hotel')
@login_required
def hotel_page(): return render_template('hotel.html', settings=get_all_settings())

@app.route('/settings')
@login_required
def settings_page(): return render_template('settings.html', settings=get_all_settings())

# ── INVENTORY ─────────────────────────────────────────────────────────────────
@app.route('/api/inventory', methods=['GET','POST'])
@login_required
def api_inventory():
    conn=get_db()
    if request.method=='POST':
        d=request.json
        existing=conn.execute('SELECT id FROM inventory WHERE name=?',(d['name'],)).fetchone()
        is_new = not existing
        conn.execute('''INSERT INTO inventory(name,unit,stock,low_threshold,cost_per_unit,supplier_id) VALUES(?,?,?,?,?,?)
            ON CONFLICT(name) DO UPDATE SET unit=excluded.unit,stock=excluded.stock,
            low_threshold=excluded.low_threshold,cost_per_unit=excluded.cost_per_unit,supplier_id=excluded.supplier_id''',
            (d['name'],d.get('unit','unit'),d.get('stock',0),d.get('low_threshold',5),d.get('cost',0),d.get('supplier_id') or None))
        item=conn.execute('SELECT id FROM inventory WHERE name=?',(d['name'],)).fetchone()
        iid=item['id'] if item else None
        # Auto-record initial stock as a purchase + expense (only on first creation)
        expense_logged=False; sid_changed=None
        if is_new and iid:
            qty=float(d.get('stock',0) or 0); cpu=float(d.get('cost',0) or 0); total=qty*cpu
            if qty>0 and cpu>0:
                sid=d.get('supplier_id') or None
                unit=d.get('unit','unit')
                conn.execute('INSERT INTO purchase_records(inventory_id,supplier_id,quantity,cost_per_unit,total_cost,payment_method,is_due,notes) VALUES(?,?,?,?,?,?,?,?)',
                    (iid,sid,qty,cpu,total,'cash',0,'Initial stock (auto on item add)'))
                if sid:
                    conn.execute('UPDATE suppliers SET total_purchased=total_purchased+? WHERE id=?',(total,sid))
                    sid_changed=sid
                conn.execute('INSERT INTO expenses(description,amount,category) VALUES(?,?,?)',
                    (f"Inventory: {d['name']} ({qty} {unit})",total,'ingredients'))
                expense_logged=True
        log_action('update_inventory','inventory',d.get('name','?'), conn=conn)
        conn.commit(); conn.close()
        broadcast('inventory_updated',{'id':iid})
        if expense_logged: broadcast('expense_added')
        if sid_changed: broadcast('supplier_updated',{'id':sid_changed})
        return jsonify({'ok':True,'id':iid,'expense_recorded':expense_logged})
    rows=conn.execute('''SELECT i.*,s.name as supplier_name FROM inventory i
        LEFT JOIN suppliers s ON i.supplier_id=s.id ORDER BY i.name''').fetchall()
    conn.close(); return jsonify([dict(r) for r in rows])

@app.route('/api/inventory/<int:iid>', methods=['PUT','DELETE'])
@login_required
def edit_inventory(iid):
    conn=get_db()
    if request.method=='DELETE': conn.execute('DELETE FROM inventory WHERE id=?',(iid,))
    else:
        d=request.json
        conn.execute('UPDATE inventory SET name=?,unit=?,stock=?,low_threshold=?,cost_per_unit=?,supplier_id=? WHERE id=?',
            (d['name'],d.get('unit','unit'),d['stock'],d.get('low_threshold',5),d.get('cost',0),d.get('supplier_id') or None,iid))
    conn.commit(); conn.close(); broadcast('inventory_updated',{'id':iid}); return jsonify({'ok':True,'id':iid})

@app.route('/api/inventory/<int:iid>/adjust', methods=['POST'])
@login_required
def adjust_stock(iid):
    d=request.json; conn=get_db()
    conn.execute('UPDATE inventory SET stock=MAX(0,stock+?) WHERE id=?',(d['delta'],iid))
    conn.commit(); conn.close(); broadcast('inventory_updated',{'id':iid}); return jsonify({'ok':True})

@app.route('/api/inventory/<int:iid>/purchase', methods=['POST'])
@login_required
def record_purchase(iid):
    d=request.json; conn=get_db()
    qty=float(d.get('quantity',0)); cpu=float(d.get('cost_per_unit',0)); total=qty*cpu
    is_due=1 if d.get('is_due') else 0
    conn.execute('INSERT INTO purchase_records(inventory_id,supplier_id,quantity,cost_per_unit,total_cost,payment_method,is_due,notes) VALUES(?,?,?,?,?,?,?,?)',
        (iid,d.get('supplier_id') or None,qty,cpu,total,d.get('payment_method','cash'),is_due,d.get('notes','')))
    conn.execute('UPDATE inventory SET stock=stock+? WHERE id=?',(qty,iid))
    if d.get('supplier_id') and is_due:
        conn.execute('UPDATE suppliers SET due_amount=due_amount+?,total_purchased=total_purchased+? WHERE id=?',(total,total,d['supplier_id']))
    elif d.get('supplier_id'):
        conn.execute('UPDATE suppliers SET total_purchased=total_purchased+? WHERE id=?',(total,d['supplier_id']))
    # Auto-record this purchase as an expense (raw materials = expense)
    expense_logged=False
    if total>0:
        info=conn.execute('SELECT name,unit FROM inventory WHERE id=?',(iid,)).fetchone()
        nm=info['name'] if info else f'Item #{iid}'
        un=info['unit'] if info else 'unit'
        conn.execute('INSERT INTO expenses(description,amount,category) VALUES(?,?,?)',
            (f"Inventory: {nm} ({qty} {un})",total,'ingredients'))
        expense_logged=True
    conn.commit(); conn.close()
    broadcast('inventory_updated',{'id':iid})
    broadcast('supplier_updated',{'id':d.get('supplier_id')})
    if expense_logged: broadcast('expense_added')
    return jsonify({'ok':True,'expense_recorded':expense_logged})

@app.route('/api/inventory/export')
@login_required
def export_inventory():
    conn=get_db()
    rows=conn.execute('''SELECT i.name,i.unit,i.stock,i.low_threshold,i.cost_per_unit,
        ROUND(i.stock*i.cost_per_unit,2) as total_value,s.name as supplier
        FROM inventory i LEFT JOIN suppliers s ON i.supplier_id=s.id ORDER BY i.name''').fetchall()
    conn.close()
    out=io.StringIO(); w=csv.writer(out)
    w.writerow(['Item','Unit','Stock','Low Alert','Cost/Unit','Total Value','Supplier'])
    for r in rows: w.writerow([r['name'],r['unit'],r['stock'],r['low_threshold'],r['cost_per_unit'],r['total_value'],r['supplier'] or ''])
    out.seek(0)
    return send_file(io.BytesIO(out.getvalue().encode('utf-8-sig')),mimetype='text/csv',as_attachment=True,download_name='inventory.csv')

# ── SUPPLIERS ─────────────────────────────────────────────────────────────────
@app.route('/api/suppliers', methods=['GET','POST'])
@login_required
def api_suppliers():
    conn=get_db()
    if request.method=='POST':
        d=request.json
        cur=conn.execute('INSERT INTO suppliers(name,phone,email,address,notes) VALUES(?,?,?,?,?)',
            (d['name'],d.get('phone',''),d.get('email',''),d.get('address',''),d.get('notes','')))
        sid=cur.lastrowid
        log_action('add_supplier','inventory',d['name'], conn=conn)
        conn.commit(); conn.close(); broadcast('supplier_updated',{'id':sid}); return jsonify({'ok':True,'id':sid})
    rows=conn.execute('SELECT * FROM suppliers ORDER BY name').fetchall()
    conn.close(); return jsonify([dict(r) for r in rows])

@app.route('/api/suppliers/<int:sid>', methods=['GET','PUT','DELETE'])
@login_required
def edit_supplier(sid):
    conn=get_db()
    if request.method=='GET':
        s=conn.execute('SELECT * FROM suppliers WHERE id=?',(sid,)).fetchone()
        purchases=conn.execute('''SELECT pr.*,i.name as item_name FROM purchase_records pr
            LEFT JOIN inventory i ON pr.inventory_id=i.id
            WHERE pr.supplier_id=? ORDER BY pr.purchased_at DESC LIMIT 100''',(sid,)).fetchall()
        conn.close(); return jsonify({'supplier':dict(s),'purchases':[dict(p) for p in purchases]})
    if request.method=='DELETE':
        conn.execute('DELETE FROM suppliers WHERE id=?',(sid,))
    else:
        d=request.json
        conn.execute('UPDATE suppliers SET name=?,phone=?,email=?,address=?,notes=? WHERE id=?',
            (d['name'],d.get('phone',''),d.get('email',''),d.get('address',''),d.get('notes',''),sid))
    conn.commit(); conn.close(); broadcast('supplier_updated',{'id':sid}); return jsonify({'ok':True})

@app.route('/api/suppliers/<int:sid>/pay_due', methods=['POST'])
@login_required
def pay_supplier_due(sid):
    d=request.json; conn=get_db()
    conn.execute('UPDATE suppliers SET due_amount=MAX(0,due_amount-?) WHERE id=?',(float(d['amount']),sid))
    conn.commit(); conn.close(); broadcast('supplier_updated',{'id':sid}); return jsonify({'ok':True})

@app.route('/api/suppliers/report')
@login_required
def supplier_report():
    sid=request.args.get('supplier_id'); start=request.args.get('start'); end=request.args.get('end')
    conn=get_db()
    q="SELECT pr.*,i.name as item_name,s.name as supplier_name FROM purchase_records pr LEFT JOIN inventory i ON pr.inventory_id=i.id LEFT JOIN suppliers s ON pr.supplier_id=s.id WHERE 1=1"
    params=[]
    if sid: q+=" AND pr.supplier_id=?"; params.append(sid)
    if start: q+=" AND date(pr.purchased_at)>=?"; params.append(start)
    if end: q+=" AND date(pr.purchased_at)<=?"; params.append(end)
    q+=" ORDER BY pr.purchased_at DESC"
    rows=conn.execute(q,params).fetchall()
    total=conn.execute("SELECT COALESCE(SUM(total_cost),0) as t,COALESCE(SUM(CASE WHEN is_due=1 THEN total_cost ELSE 0 END),0) as due FROM purchase_records pr WHERE 1=1"+
        (" AND pr.supplier_id=?" if sid else "")+(" AND date(pr.purchased_at)>=?" if start else "")+(" AND date(pr.purchased_at)<=?" if end else ""),
        [p for p in params]).fetchone()
    conn.close()
    return jsonify({'purchases':[dict(r) for r in rows],'total':dict(total)})

@app.route('/api/suppliers/export')
@login_required
def export_supplier_report():
    sid=request.args.get('supplier_id'); start=request.args.get('start'); end=request.args.get('end')
    conn=get_db()
    q="SELECT pr.*,i.name as item_name,s.name as supplier_name FROM purchase_records pr LEFT JOIN inventory i ON pr.inventory_id=i.id LEFT JOIN suppliers s ON pr.supplier_id=s.id WHERE 1=1"
    params=[]
    if sid: q+=" AND pr.supplier_id=?"; params.append(sid)
    if start: q+=" AND date(pr.purchased_at)>=?"; params.append(start)
    if end: q+=" AND date(pr.purchased_at)<=?"; params.append(end)
    rows=conn.execute(q,params).fetchall(); conn.close()
    out=io.StringIO(); w=csv.writer(out)
    w.writerow(['Date','Supplier','Item','Qty','Cost/Unit','Total','Payment','Due?'])
    for r in rows: w.writerow([r['purchased_at'],r['supplier_name'],r['item_name'],r['quantity'],r['cost_per_unit'],r['total_cost'],r['payment_method'],'Yes' if r['is_due'] else 'No'])
    out.seek(0)
    return send_file(io.BytesIO(out.getvalue().encode('utf-8-sig')),mimetype='text/csv',as_attachment=True,download_name='supplier_purchases.csv')

# ── MENU ──────────────────────────────────────────────────────────────────────
@app.route('/api/menu')
@login_required
def api_menu():
    conn=get_db()
    cats=conn.execute('SELECT * FROM categories').fetchall()
    items=conn.execute('''SELECT m.*,c.name as cat_name,c.color as cat_color
        FROM menu_items m LEFT JOIN categories c ON m.category_id=c.id
        WHERE m.is_available=1 ORDER BY c.name,m.name''').fetchall()
    result=[]
    for item in items:
        d=dict(item)
        d['customizations']=[dict(r) for r in conn.execute('SELECT * FROM menu_customizations WHERE menu_item_id=?',(d['id'],)).fetchall()]
        d['portions']=[dict(r) for r in conn.execute('''SELECT mp.*,inv.name as inv_name,inv.unit FROM menu_portions mp
            JOIN inventory inv ON mp.inventory_id=inv.id WHERE mp.menu_item_id=?''',(d['id'],)).fetchall()]
        result.append(d)
    conn.close(); return jsonify({'categories':[dict(c) for c in cats],'items':result})

@app.route('/api/menu/item', methods=['POST'])
@login_required
def add_menu_item():
    d=request.json
    log_action('add_menu_item','menu',d.get('name','?'))
    conn=get_db()
    cur=conn.execute('INSERT INTO menu_items(name,price,category_id,stock,low_stock_threshold,description) VALUES(?,?,?,?,?,?)',
        (d['name'],d['price'],d['category_id'],d.get('stock',999),d.get('threshold',10),d.get('description','')))
    iid=cur.lastrowid
    try: _save_custs(conn,iid,d.get('customizations',[]))
    except Exception: pass
    try: _save_portions(conn,iid,d.get('portions',[]))
    except Exception: pass
    conn.commit(); conn.close(); broadcast('menu_updated',{'id':iid}); return jsonify({'ok':True,'id':iid})

@app.route('/api/menu/item/<int:iid>', methods=['GET','PUT','DELETE'])
@login_required
def edit_menu_item(iid):
    conn=get_db()
    if request.method=='GET':
        item=conn.execute('SELECT * FROM menu_items WHERE id=?',(iid,)).fetchone()
        if not item: return jsonify({'error':'Not found'}),404
        d=dict(item)
        d['customizations']=[dict(r) for r in conn.execute('SELECT * FROM menu_customizations WHERE menu_item_id=?',(iid,)).fetchall()]
        d['portions']=[dict(r) for r in conn.execute('''SELECT mp.*,inv.name as inv_name,inv.unit FROM menu_portions mp
            JOIN inventory inv ON mp.inventory_id=inv.id WHERE mp.menu_item_id=?''',(iid,)).fetchall()]
        conn.close(); return jsonify(d)
    if request.method=='DELETE':
        item_name=conn.execute('SELECT name FROM menu_items WHERE id=?',(iid,)).fetchone()
        log_action('delete_menu_item','menu',item_name['name'] if item_name else str(iid))
        conn.execute('UPDATE menu_items SET is_available=0 WHERE id=?',(iid,))
    else:
        d=request.json
        conn.execute('UPDATE menu_items SET name=?,price=?,category_id=?,stock=?,low_stock_threshold=?,description=? WHERE id=?',
            (d['name'],d['price'],d['category_id'],d['stock'],d.get('threshold',10),d.get('description',''),iid))
        _save_custs(conn,iid,d.get('customizations',[])); _save_portions(conn,iid,d.get('portions',[]))
    conn.commit(); conn.close(); broadcast('menu_updated',{'id':iid}); return jsonify({'ok':True})

def _save_custs(conn,iid,custs):
    conn.execute('DELETE FROM menu_customizations WHERE menu_item_id=?',(iid,))
    for c in custs:
        if c.get('name') and c.get('options'):
            conn.execute('INSERT INTO menu_customizations(menu_item_id,name,options,is_required) VALUES(?,?,?,?)',
                (iid,c['name'],c['options'],1 if c.get('required') else 0))

def _save_portions(conn,iid,portions):
    conn.execute('DELETE FROM menu_portions WHERE menu_item_id=?',(iid,))
    for p in portions:
        if p.get('inventory_id') and p.get('qty_used'):
            conn.execute('INSERT INTO menu_portions(menu_item_id,inventory_id,qty_used) VALUES(?,?,?)',(iid,p['inventory_id'],p['qty_used']))

@app.route('/api/categories', methods=['GET','POST'])
@login_required
def categories():
    conn=get_db()
    if request.method=='POST':
        d=request.json; conn.execute('INSERT INTO categories(name,color) VALUES(?,?)',(d['name'],d.get('color','#6366f1')))
        conn.commit(); conn.close()
        log_action('add_category','menu',d['name'])
        broadcast('menu_updated')
        return jsonify({'ok':True})
    rows=conn.execute('SELECT * FROM categories').fetchall(); conn.close(); return jsonify([dict(r) for r in rows])

@app.route('/api/categories/<int:cid>', methods=['DELETE'])
@login_required
def delete_category(cid):
    conn=get_db()
    cat=conn.execute('SELECT name FROM categories WHERE id=?',(cid,)).fetchone()
    # Move items in this category to uncategorized (null)
    conn.execute('UPDATE menu_items SET category_id=NULL WHERE category_id=?',(cid,))
    conn.execute('DELETE FROM categories WHERE id=?',(cid,))
    conn.commit(); conn.close()
    log_action('delete_category','menu',cat['name'] if cat else str(cid))
    broadcast('menu_updated')
    return jsonify({'ok':True})

# ── TABLES ────────────────────────────────────────────────────────────────────
@app.route('/api/tables', methods=['GET'])
@login_required
def api_tables():
    conn=get_db()
    tables=conn.execute('''SELECT t.*,o.id as open_order_id,
        (SELECT COUNT(*) FROM order_items oi WHERE oi.order_id=o.id) as item_count,
        o.total as order_total FROM tables t
        LEFT JOIN orders o ON o.table_id=t.id AND o.status='open'
        ORDER BY CAST(t.number AS INTEGER)''').fetchall()
    conn.close(); return jsonify([dict(t) for t in tables])

@app.route('/api/tables', methods=['POST'])
@login_required
def add_table():
    d=request.json; conn=get_db()
    try:
        conn.execute('INSERT INTO tables(number,capacity,section) VALUES(?,?,?)',(d['number'],d.get('capacity',4),d.get('section','Main')))
        conn.commit(); conn.close(); return jsonify({'ok':True})
    except: conn.close(); return jsonify({'ok':False,'error':'Table number already exists'}),400

@app.route('/api/tables/<int:tid>', methods=['PUT','DELETE'])
@login_required
def edit_table(tid):
    conn=get_db()
    if request.method=='DELETE':
        occupied=conn.execute("SELECT id FROM orders WHERE table_id=? AND status='open'",(tid,)).fetchone()
        if occupied: conn.close(); return jsonify({'ok':False,'error':'Table has open order'}),400
        conn.execute('DELETE FROM tables WHERE id=?',(tid,))
    else:
        d=request.json
        conn.execute('UPDATE tables SET number=?,capacity=?,section=? WHERE id=?',(d['number'],d.get('capacity',4),d.get('section','Main'),tid))
    conn.commit(); conn.close(); return jsonify({'ok':True})

# ── CUSTOMERS ─────────────────────────────────────────────────────────────────
@app.route('/api/customers', methods=['GET','POST'])
@login_required
def api_customers():
    conn=get_db()
    if request.method=='POST':
        d=request.json
        existing=None
        if d.get('phone') and d['phone'].strip():
            existing=conn.execute('SELECT id FROM customers WHERE phone=?',(d['phone'].strip(),)).fetchone()
        if existing:
            conn.execute('UPDATE customers SET name=?,email=?,notes=? WHERE id=?',(d['name'],d.get('email',''),d.get('notes',''),existing['id']))
            cid=existing['id']
        else:
            cur=conn.execute('INSERT INTO customers(name,phone,email,notes) VALUES(?,?,?,?)',
                (d['name'],d.get('phone','').strip() or None,d.get('email',''),d.get('notes','')))
            cid=cur.lastrowid
        log_action('add_customer','customer',d['name'], conn=conn)
        customer=conn.execute('SELECT * FROM customers WHERE id=?',(cid,)).fetchone()
        conn.commit(); conn.close()
        broadcast('customer_added',{'id':cid,'name':d['name'],'phone':d.get('phone','')})
        return jsonify({'ok':True,'id':cid,'customer':dict(customer)})
    q=request.args.get('q','').strip()
    if q: rows=conn.execute("SELECT * FROM customers WHERE name LIKE ? OR phone LIKE ? ORDER BY name",(f'%{q}%',f'%{q}%')).fetchall()
    else: rows=conn.execute('SELECT * FROM customers ORDER BY name').fetchall()
    conn.close(); return jsonify([dict(r) for r in rows])

@app.route('/api/customers/<int:cid>', methods=['GET','PUT','DELETE'])
@login_required
def edit_customer(cid):
    conn=get_db()
    if request.method=='GET':
        cust=conn.execute('SELECT * FROM customers WHERE id=?',(cid,)).fetchone()
        if not cust: return jsonify({'error':'Not found'}),404
        orders=conn.execute('''SELECT o.*,t.number as table_number FROM orders o
            LEFT JOIN tables t ON o.table_id=t.id WHERE o.customer_id=? ORDER BY o.created_at DESC LIMIT 50''',(cid,)).fetchall()
        order_items_map={o['id']:[dict(i) for i in conn.execute('SELECT * FROM order_items WHERE order_id=?',(o['id'],)).fetchall()] for o in orders}
        due_payments=conn.execute('SELECT * FROM due_payments WHERE customer_id=? ORDER BY created_at DESC',(cid,)).fetchall()
        conn.close(); return jsonify({'customer':dict(cust),'orders':[dict(o) for o in orders],'order_items':order_items_map,'due_payments':[dict(p) for p in due_payments]})
    if request.method=='DELETE': conn.execute('DELETE FROM customers WHERE id=?',(cid,))
    else:
        d=request.json
        conn.execute('UPDATE customers SET name=?,phone=?,email=?,notes=? WHERE id=?',(d['name'],d.get('phone',''),d.get('email',''),d.get('notes',''),cid))
    conn.commit(); conn.close(); broadcast('customer_updated',{'id':cid}); return jsonify({'ok':True})

@app.route('/api/customers/<int:cid>/pay_due', methods=['POST'])
@login_required
def pay_due(cid):
    d=request.json; conn=get_db()
    amount=float(d.get('amount',0)); method=d.get('method','cash'); subtype=d.get('subtype','')
    conn.execute('INSERT INTO due_payments(customer_id,order_id,amount,payment_method,payment_subtype,notes) VALUES(?,?,?,?,?,?)',
        (cid,d.get('order_id'),amount,method,subtype,d.get('notes','')))
    conn.execute('UPDATE customers SET due_amount=MAX(0,due_amount-?) WHERE id=?',(amount,cid))
    conn.commit(); conn.close(); broadcast('due_paid',{'customer_id':cid}); return jsonify({'ok':True})

# ── ORDERS ────────────────────────────────────────────────────────────────────
@app.route('/api/order', methods=['POST'])
@login_required
def create_order():
    d=request.json; conn=get_db()
    cur=conn.execute('INSERT INTO orders(order_type,table_id,customer_id,customer_name,notes,source) VALUES(?,?,?,?,?,?)',
        (d.get('order_type','dine_in'),d.get('table_id'),d.get('customer_id'),d.get('customer_name',''),d.get('notes',''),d.get('source','pos')))
    oid=cur.lastrowid
    if d.get('table_id'): conn.execute('UPDATE tables SET status="occupied" WHERE id=?',(d['table_id'],))
    conn.commit(); conn.close(); broadcast('order_created',{'order_id':oid}); return jsonify({'order_id':oid})

@app.route('/api/order/<int:oid>')
@login_required
def get_order(oid):
    conn=get_db()
    order=conn.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
    items=conn.execute('SELECT * FROM order_items WHERE order_id=?',(oid,)).fetchall()
    conn.close()
    if not order: return jsonify({'error':'Not found'}),404
    return jsonify({'order':dict(order),'items':[dict(i) for i in items]})

@app.route('/api/order/<int:oid>/items', methods=['POST'])
@login_required
def add_order_items(oid):
    items=request.json.get('items',[]); conn=get_db()
    for item in items:
        ex=conn.execute('SELECT id,quantity FROM order_items WHERE order_id=? AND item_id=? AND customizations=?',
            (oid,item['item_id'],item.get('customizations',''))).fetchone()
        if ex: conn.execute('UPDATE order_items SET quantity=quantity+? WHERE id=?',(item['quantity'],ex['id']))
        else: conn.execute('INSERT INTO order_items(order_id,item_id,item_name,price,quantity,customizations,notes) VALUES(?,?,?,?,?,?,?)',
            (oid,item['item_id'],item['item_name'],item['price'],item['quantity'],item.get('customizations',''),item.get('notes','')))
        for p in conn.execute('SELECT * FROM menu_portions WHERE menu_item_id=?',(item['item_id'],)).fetchall():
            conn.execute('UPDATE inventory SET stock=MAX(0,stock-?) WHERE id=?',(p['qty_used']*item['quantity'],p['inventory_id']))
        conn.execute('UPDATE menu_items SET stock=MAX(0,stock-?) WHERE id=?',(item['quantity'],item['item_id']))
    _recalc(conn,oid); conn.commit(); conn.close(); broadcast('order_updated',{'order_id':oid}); return jsonify({'ok':True})

@app.route('/api/order/<int:oid>/item/<int:iid>', methods=['DELETE','PUT'])
@login_required
def modify_order_item(oid,iid):
    conn=get_db()
    if request.method=='DELETE':
        item=conn.execute('SELECT item_id,quantity FROM order_items WHERE id=?',(iid,)).fetchone()
        if item:
            conn.execute('UPDATE menu_items SET stock=stock+? WHERE id=?',(item['quantity'],item['item_id']))
            for p in conn.execute('SELECT * FROM menu_portions WHERE menu_item_id=?',(item['item_id'],)).fetchall():
                conn.execute('UPDATE inventory SET stock=stock+? WHERE id=?',(p['qty_used']*item['quantity'],p['inventory_id']))
        conn.execute('DELETE FROM order_items WHERE id=?',(iid,))
    else:
        d=request.json; old=conn.execute('SELECT item_id,quantity FROM order_items WHERE id=?',(iid,)).fetchone()
        conn.execute('UPDATE order_items SET quantity=? WHERE id=?',(d['quantity'],iid))
        conn.execute('UPDATE menu_items SET stock=stock-? WHERE id=?',(d['quantity']-old['quantity'],old['item_id']))
    _recalc(conn,oid); conn.commit(); conn.close(); broadcast('order_updated',{'order_id':oid}); return jsonify({'ok':True})

@app.route('/api/order/<int:oid>/discount', methods=['POST'])
@login_required
def apply_discount(oid):
    d=request.json; conn=get_db()
    conn.execute('UPDATE orders SET discount=? WHERE id=?',(d['discount'],oid)); _recalc(conn,oid); conn.commit(); conn.close(); return jsonify({'ok':True})

@app.route('/api/order/<int:oid>/close', methods=['POST'])
@login_required
def close_order(oid):
    d=request.json; conn=get_db()
    is_due=1 if d.get('is_due') else 0
    method='due' if is_due else d.get('payment_method','cash')
    subtype=d.get('payment_subtype','')
    cid=d.get('customer_id')
    if not cid:
        conn.close()
        return jsonify({'ok':False,'error':'A linked customer is required before closing the bill'}), 400
    conn.execute("""UPDATE orders SET status='closed',payment_method=?,payment_subtype=?,is_due=?,
        closed_at=datetime('now','localtime'),customer_id=?,customer_name=? WHERE id=?""",
        (method,subtype,is_due,cid,d.get('customer_name',''),oid))
    order=conn.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
    if order['table_id']: conn.execute('UPDATE tables SET status="free" WHERE id=?',(order['table_id'],))
    if cid:
        conn.execute('UPDATE customers SET visit_count=visit_count+1,total_spent=total_spent+? WHERE id=?',(order['total'],cid))
        if is_due: conn.execute('UPDATE customers SET due_amount=due_amount+? WHERE id=?',(order['total'],cid))
    log_action('close_order','order','Order #'+str(oid)+' '+str(method)+('+'+str(subtype) if subtype else ''), conn=conn)
    conn.commit(); conn.close(); broadcast('order_closed',{'order_id':oid}); return jsonify({'ok':True})

@app.route('/api/orders/open')
@login_required
def open_orders():
    conn=get_db()
    orders=conn.execute('''SELECT o.*,t.number as table_number,
        (SELECT COUNT(*) FROM order_items oi WHERE oi.order_id=o.id) as item_count
        FROM orders o LEFT JOIN tables t ON o.table_id=t.id
        WHERE o.status='open' ORDER BY o.created_at DESC''').fetchall()
    conn.close(); return jsonify([dict(o) for o in orders])

@app.route('/api/order/<int:oid>/kot')
@login_required
def get_kot(oid):
    conn=get_db()
    order=conn.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
    items=conn.execute('SELECT * FROM order_items WHERE order_id=?',(oid,)).fetchall()
    conn.execute('UPDATE orders SET kot_printed=1 WHERE id=?',(oid,)); conn.commit(); conn.close()
    return jsonify({'order':dict(order),'items':[dict(i) for i in items],'time':datetime.now().strftime('%d/%m/%Y %H:%M'),'restaurant':get_setting('restaurant_name')})

@app.route('/api/order/<int:oid>/bill')
@login_required
def get_bill(oid):
    conn=get_db()
    order=conn.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
    items=conn.execute('SELECT * FROM order_items WHERE order_id=?',(oid,)).fetchall()
    table=conn.execute('SELECT number FROM tables WHERE id=?',(order['table_id'],)).fetchone() if order['table_id'] else None
    customer=conn.execute('SELECT * FROM customers WHERE id=?',(order['customer_id'],)).fetchone() if order['customer_id'] else None
    conn.execute('UPDATE orders SET bill_printed=1 WHERE id=?',(oid,)); conn.commit(); conn.close()
    return jsonify({'order':dict(order),'items':[dict(i) for i in items],
        'table':dict(table) if table else None,'customer':dict(customer) if customer else None,
        'time':datetime.now().strftime('%d/%m/%Y %H:%M'),
        'restaurant':get_setting('restaurant_name'),'gstin':get_setting('gstin'),
        'currency':get_setting('currency'),'tax_rate':get_setting('tax_rate'),
        'upi_id':get_setting('upi_id'),'upi_qr_url':get_setting('upi_qr_url'),
        'logo_url':get_setting('logo_url')})

# ── EXPENSES ──────────────────────────────────────────────────────────────────
@app.route('/api/expenses', methods=['GET','POST'])
@login_required
def expenses():
    conn=get_db()
    if request.method=='POST':
        d=request.json
        conn.execute('INSERT INTO expenses(description,amount,category) VALUES(?,?,?)',(d['description'],d['amount'],d.get('category','other')))
        conn.commit(); conn.close(); broadcast('expense_added'); return jsonify({'ok':True})
    dt=request.args.get('date',date.today().isoformat())
    rows=conn.execute("SELECT * FROM expenses WHERE date(created_at)=? ORDER BY created_at DESC",(dt,)).fetchall()
    conn.close(); return jsonify([dict(r) for r in rows])

@app.route('/api/expenses/<int:eid>', methods=['DELETE'])
@login_required
def delete_expense(eid):
    conn=get_db(); conn.execute('DELETE FROM expenses WHERE id=?',(eid,)); conn.commit(); conn.close(); return jsonify({'ok':True})

# ── HOTEL ─────────────────────────────────────────────────────────────────────
@app.route('/api/hotel/rooms', methods=['GET','POST'])
@login_required
def hotel_rooms():
    conn=get_db()
    if request.method=='POST':
        d=request.json
        try:
            conn.execute('INSERT INTO hotel_rooms(room_number,room_type,floor,capacity,price_per_night,notes) VALUES(?,?,?,?,?,?)',
                (d['room_number'],d.get('room_type','Standard'),d.get('floor',1),d.get('capacity',2),d.get('price',0),d.get('notes','')))
            conn.commit(); conn.close(); return jsonify({'ok':True})
        except: conn.close(); return jsonify({'ok':False,'error':'Room number already exists'}),400
    rooms=conn.execute('SELECT * FROM hotel_rooms ORDER BY floor,room_number').fetchall()
    conn.close(); return jsonify([dict(r) for r in rooms])

@app.route('/api/hotel/rooms/<int:rid>', methods=['PUT','DELETE'])
@login_required
def edit_room(rid):
    conn=get_db()
    if request.method=='DELETE':
        conn.execute('DELETE FROM hotel_rooms WHERE id=?',(rid,))
    else:
        d=request.json
        conn.execute('''UPDATE hotel_rooms SET room_number=?,room_type=?,floor=?,capacity=?,price_per_night=?,
            status=?,current_guest=?,checkin_date=?,checkout_date=?,notes=? WHERE id=?''',
            (d['room_number'],d.get('room_type','Standard'),d.get('floor',1),d.get('capacity',2),
             d.get('price',0),d.get('status','available'),d.get('current_guest',''),
             d.get('checkin_date',''),d.get('checkout_date',''),d.get('notes',''),rid))
    conn.commit(); conn.close(); return jsonify({'ok':True})

@app.route('/api/hotel/rooms/<int:rid>/checkin', methods=['POST'])
@login_required
def checkin_room(rid):
    d = request.json or {}
    conn = get_db()
    room = conn.execute('SELECT room_number, price_per_night FROM hotel_rooms WHERE id=?', (rid,)).fetchone()
    if not room:
        conn.close(); return jsonify({'ok': False, 'error': 'Room not found'}), 404
    today_iso = date.today().isoformat()
    checkin = d.get('checkin') or today_iso
    checkout = d.get('checkout') or ''
    guest = d.get('guest', '')
    phone = d.get('phone', '')
    price = float(d.get('price_per_night') or room['price_per_night'] or 0)
    try:
        from datetime import datetime as _dt
        nights = max(1, (_dt.fromisoformat(checkout).date() - _dt.fromisoformat(checkin).date()).days) if (checkout and checkin) else 1
    except Exception:
        nights = 1
    total = nights * price
    # Future check-in => reserved; today/past => occupied (matches the modal copy)
    room_status = 'reserved' if checkin > today_iso else 'occupied'
    booking_status = 'reserved' if room_status == 'reserved' else 'checked_in'
    conn.execute("""INSERT INTO hotel_bookings(room_id, room_number, guest_name, phone,
                        checkin_date, checkout_date, nights, price_per_night, total_amount,
                        payment_method, status, notes)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (rid, room['room_number'], guest, phone, checkin, checkout, nights, price, total,
                  d.get('payment_method', 'cash'), booking_status, d.get('notes', '')))
    conn.execute("UPDATE hotel_rooms SET status=?, current_guest=?, checkin_date=?, checkout_date=? WHERE id=?",
                 (room_status, guest, checkin, checkout, rid))
    conn.commit(); conn.close()
    broadcast('hotel_updated', {'room_id': rid})
    return jsonify({'ok': True})

@app.route('/api/hotel/rooms/<int:rid>/checkout', methods=['POST'])
@login_required
def checkout_room(rid):
    conn = get_db()
    conn.execute("""UPDATE hotel_bookings
                    SET status='checked_out', checked_out_at=datetime('now','localtime')
                    WHERE room_id=? AND status IN ('checked_in','reserved')""", (rid,))
    conn.execute("UPDATE hotel_rooms SET status='available', current_guest='', checkin_date='', checkout_date='' WHERE id=?", (rid,))
    conn.commit(); conn.close()
    broadcast('hotel_updated', {'room_id': rid})
    return jsonify({'ok': True})

@app.route('/api/hotel/calendar')
@login_required
def hotel_calendar():
    """Per-day occupancy across [start, end]. Booking covers days [checkin, checkout)."""
    from datetime import datetime as _dt, timedelta as _td
    today_iso = date.today().isoformat()
    start = request.args.get('start', today_iso)
    end = request.args.get('end', today_iso)
    conn = get_db()
    rooms_total = conn.execute('SELECT COUNT(*) AS c FROM hotel_rooms').fetchone()['c']
    bookings = conn.execute("""SELECT id, room_id, room_number, guest_name, phone,
                                  checkin_date, checkout_date, nights, price_per_night, total_amount,
                                  payment_method, status
                               FROM hotel_bookings
                               WHERE status != 'cancelled'
                                 AND checkin_date <= ?
                                 AND checkout_date > ?""",
                            (end, start)).fetchall()
    conn.close()
    try:
        s = _dt.fromisoformat(start).date(); e = _dt.fromisoformat(end).date()
    except Exception:
        s = date.today(); e = date.today()
    days = {}
    cur = s
    while cur <= e:
        days[cur.isoformat()] = {'booked': 0, 'bookings': []}
        cur = cur + _td(days=1)
    for b in bookings:
        try:
            ci = _dt.fromisoformat(b['checkin_date']).date()
            co = _dt.fromisoformat(b['checkout_date']).date()
        except Exception:
            continue
        cur = max(ci, s)
        end_day = min(co, e + _td(days=1))
        while cur < end_day:
            iso = cur.isoformat()
            if iso in days:
                days[iso]['booked'] += 1
                days[iso]['bookings'].append({
                    'id': b['id'], 'room_id': b['room_id'], 'room_number': b['room_number'],
                    'guest_name': b['guest_name'], 'phone': b['phone'],
                    'checkin_date': b['checkin_date'], 'checkout_date': b['checkout_date'],
                    'nights': b['nights'], 'total_amount': b['total_amount'],
                    'status': b['status']
                })
            cur = cur + _td(days=1)
    return jsonify({'start': start, 'end': end, 'rooms_total': rooms_total, 'days': days})

# ── ANALYTICS ─────────────────────────────────────────────────────────────────
@app.route('/api/analytics/today')
@login_required
def analytics_today():
    conn=get_db(); today=date.today().isoformat()
    rev=conn.execute("SELECT COALESCE(SUM(total),0) as total,COALESCE(SUM(subtotal),0) as subtotal,COALESCE(SUM(tax),0) as tax,COUNT(*) as orders FROM orders WHERE status='closed' AND date(closed_at)=?",(today,)).fetchone()
    # Payment split including due payments collected today
    pay_orders=conn.execute("SELECT payment_method,payment_subtype,COALESCE(SUM(total),0) as amount,COUNT(*) as count FROM orders WHERE status='closed' AND is_due=0 AND date(closed_at)=? GROUP BY payment_method,payment_subtype",(today,)).fetchall()
    pay_due_collected=conn.execute("SELECT payment_method,payment_subtype,COALESCE(SUM(amount),0) as amount,COUNT(*) as count FROM due_payments WHERE date(created_at)=? GROUP BY payment_method,payment_subtype",(today,)).fetchall()
    # Merge orders + due payments into one unified breakdown so dashboard charts include due collections
    pay_merged={}
    for r in pay_orders:
        k=(r['payment_method'] or 'other', r['payment_subtype'] or '')
        pay_merged[k]={'payment_method':k[0],'payment_subtype':k[1],'amount':float(r['amount'] or 0),'count':r['count']}
    for r in pay_due_collected:
        k=(r['payment_method'] or 'cash', r['payment_subtype'] or '')
        if k in pay_merged:
            pay_merged[k]['amount']+=float(r['amount'] or 0)
            pay_merged[k]['count']+=r['count']
        else:
            pay_merged[k]={'payment_method':k[0],'payment_subtype':k[1],'amount':float(r['amount'] or 0),'count':r['count']}
    pay_breakdown=list(pay_merged.values())
    due_collected_total=sum(float(r['amount'] or 0) for r in pay_due_collected)
    hourly=conn.execute("SELECT strftime('%H',closed_at) as hour,COALESCE(SUM(total),0) as amount FROM orders WHERE status='closed' AND date(closed_at)=? GROUP BY hour ORDER BY hour",(today,)).fetchall()
    top=conn.execute("SELECT oi.item_name,SUM(oi.quantity) as qty,SUM(oi.price*oi.quantity) as revenue FROM order_items oi JOIN orders o ON oi.order_id=o.id WHERE o.status='closed' AND date(o.closed_at)=? GROUP BY oi.item_name ORDER BY qty DESC LIMIT 8",(today,)).fetchall()
    exp=conn.execute("SELECT COALESCE(SUM(amount),0) as total FROM expenses WHERE date(created_at)=?",(today,)).fetchone()
    open_count=conn.execute("SELECT COUNT(*) as c FROM orders WHERE status='open'").fetchone()
    low=conn.execute("SELECT name,stock,low_stock_threshold FROM menu_items WHERE stock<=low_stock_threshold AND is_available=1 ORDER BY stock ASC LIMIT 10").fetchall()
    due=conn.execute("SELECT COUNT(*) as c,COALESCE(SUM(due_amount),0) as total FROM customers WHERE due_amount>0").fetchone()
    baseline=float(get_setting('baseline_daily_sales','5000')); total_rev=float(rev['total'])
    conn.close()
    return jsonify({'revenue':dict(rev),'expenses':dict(exp),'net':round(total_rev-float(exp['total']),2),
        'payment_breakdown':pay_breakdown,'due_collected':[dict(p) for p in pay_due_collected],
        'due_collected_total':due_collected_total,
        'hourly':[dict(h) for h in hourly],'top_items':[dict(t) for t in top],
        'open_orders':open_count['c'],'low_stock':[dict(l) for l in low],
        'due_customers':dict(due),'baseline':baseline,
        'performance_pct':round((total_rev/baseline*100) if baseline>0 else 0,1),'date':today})

@app.route('/api/analytics/range')
@login_required
def analytics_range():
    conn=get_db(); today=date.today(); period=request.args.get('period','7d')
    if period=='today': start=end=today.isoformat()
    elif period=='week': start=(today-timedelta(days=today.weekday())).isoformat(); end=today.isoformat()
    elif period=='month': start=today.replace(day=1).isoformat(); end=today.isoformat()
    elif period=='last_month':
        first=today.replace(day=1); lm=first-timedelta(days=1)
        start=lm.replace(day=1).isoformat(); end=lm.isoformat()
    elif period=='7d': start=(today-timedelta(days=6)).isoformat(); end=today.isoformat()
    elif period=='30d': start=(today-timedelta(days=29)).isoformat(); end=today.isoformat()
    else: start=request.args.get('start',today.isoformat()); end=request.args.get('end',today.isoformat())
    daily=conn.execute("SELECT date(closed_at) as day,COALESCE(SUM(total),0) as revenue,COUNT(*) as orders FROM orders WHERE status='closed' AND date(closed_at) BETWEEN ? AND ? GROUP BY day ORDER BY day",(start,end)).fetchall()
    summary=conn.execute("SELECT COALESCE(SUM(total),0) as revenue,COUNT(*) as orders FROM orders WHERE status='closed' AND date(closed_at) BETWEEN ? AND ?",(start,end)).fetchone()
    top=conn.execute("SELECT oi.item_name,SUM(oi.quantity) as qty,SUM(oi.price*oi.quantity) as revenue FROM order_items oi JOIN orders o ON oi.order_id=o.id WHERE o.status='closed' AND date(o.closed_at) BETWEEN ? AND ? GROUP BY oi.item_name ORDER BY revenue DESC LIMIT 10",(start,end)).fetchall()
    pay=conn.execute("SELECT payment_method,payment_subtype,SUM(total) as amount,COUNT(*) as count FROM orders WHERE status='closed' AND is_due=0 AND date(closed_at) BETWEEN ? AND ? GROUP BY payment_method,payment_subtype",(start,end)).fetchall()
    pay_due=conn.execute("SELECT payment_method,payment_subtype,COALESCE(SUM(amount),0) as amount,COUNT(*) as count FROM due_payments WHERE date(created_at) BETWEEN ? AND ? GROUP BY payment_method,payment_subtype",(start,end)).fetchall()
    # Merge orders + due payments into a single breakdown
    pay_merged={}
    for r in pay:
        k=(r['payment_method'] or 'other', r['payment_subtype'] or '')
        pay_merged[k]={'payment_method':k[0],'payment_subtype':k[1],'amount':float(r['amount'] or 0),'count':r['count']}
    for r in pay_due:
        k=(r['payment_method'] or 'cash', r['payment_subtype'] or '')
        if k in pay_merged:
            pay_merged[k]['amount']+=float(r['amount'] or 0)
            pay_merged[k]['count']+=r['count']
        else:
            pay_merged[k]={'payment_method':k[0],'payment_subtype':k[1],'amount':float(r['amount'] or 0),'count':r['count']}
    pay_breakdown=list(pay_merged.values())
    due_collected_total=sum(float(r['amount'] or 0) for r in pay_due)
    exp=conn.execute("SELECT COALESCE(SUM(amount),0) as total FROM expenses WHERE date(created_at) BETWEEN ? AND ?",(start,end)).fetchone()
    conn.close()
    return jsonify({'daily':[dict(d) for d in daily],'summary':dict(summary),'top_items':[dict(t) for t in top],
        'payment_breakdown':pay_breakdown,'due_collected':[dict(p) for p in pay_due],
        'due_collected_total':due_collected_total,'expenses':dict(exp),
        'baseline':float(get_setting('baseline_daily_sales','5000')),'period':period,'start':start,'end':end})

@app.route('/api/daily_sheet')
@login_required
def daily_sheet():
    dt=request.args.get('date',date.today().isoformat()); conn=get_db()
    orders=conn.execute("SELECT o.*,t.number as table_number FROM orders o LEFT JOIN tables t ON o.table_id=t.id WHERE o.status='closed' AND date(o.closed_at)=? ORDER BY o.closed_at",(dt,)).fetchall()
    items_summary=conn.execute("SELECT oi.item_name,SUM(oi.quantity) as qty,SUM(oi.price*oi.quantity) as revenue FROM order_items oi JOIN orders o ON oi.order_id=o.id WHERE o.status='closed' AND date(o.closed_at)=? GROUP BY oi.item_name ORDER BY revenue DESC",(dt,)).fetchall()
    hourly=conn.execute("SELECT strftime('%H',closed_at) as hour,SUM(total) as amount,COUNT(*) as count FROM orders WHERE status='closed' AND date(closed_at)=? GROUP BY hour ORDER BY hour",(dt,)).fetchall()
    pay_orders=conn.execute("SELECT payment_method,payment_subtype,SUM(total) as amount,COUNT(*) as count FROM orders WHERE status='closed' AND is_due=0 AND date(closed_at)=? GROUP BY payment_method,payment_subtype",(dt,)).fetchall()
    # Due payments collected today (received from customers paying off their dues)
    pay_due_collected=conn.execute("SELECT payment_method,payment_subtype,COALESCE(SUM(amount),0) as amount,COUNT(*) as count FROM due_payments WHERE date(created_at)=? GROUP BY payment_method,payment_subtype",(dt,)).fetchall()
    due_payments_list=conn.execute("""SELECT dp.*,c.name as customer_name FROM due_payments dp
        LEFT JOIN customers c ON dp.customer_id=c.id
        WHERE date(dp.created_at)=? ORDER BY dp.created_at""",(dt,)).fetchall()
    # Merge orders + due payments into a unified breakdown for the daily report
    pay_merged={}
    for r in pay_orders:
        k=(r['payment_method'] or 'other', r['payment_subtype'] or '')
        pay_merged[k]={'payment_method':k[0],'payment_subtype':k[1],'amount':float(r['amount'] or 0),'count':r['count']}
    for r in pay_due_collected:
        k=(r['payment_method'] or 'cash', r['payment_subtype'] or '')
        if k in pay_merged:
            pay_merged[k]['amount']+=float(r['amount'] or 0)
            pay_merged[k]['count']+=r['count']
        else:
            pay_merged[k]={'payment_method':k[0],'payment_subtype':k[1],'amount':float(r['amount'] or 0),'count':r['count']}
    pay_breakdown=list(pay_merged.values())
    due_collected_total=sum(float(r['amount'] or 0) for r in pay_due_collected)
    exps=conn.execute("SELECT * FROM expenses WHERE date(created_at)=? ORDER BY created_at",(dt,)).fetchall()
    totals=conn.execute("SELECT COALESCE(SUM(total),0) as revenue,COALESCE(SUM(tax),0) as tax,COALESCE(SUM(discount),0) as discount FROM orders WHERE status='closed' AND date(closed_at)=?",(dt,)).fetchone()
    exp_total=conn.execute("SELECT COALESCE(SUM(amount),0) as total FROM expenses WHERE date(created_at)=?",(dt,)).fetchone()
    baseline=float(get_setting('baseline_daily_sales','5000')); rev=float(totals['revenue']); conn.close()
    return jsonify({'date':dt,'orders':[dict(o) for o in orders],'items_summary':[dict(i) for i in items_summary],
        'hourly':[dict(h) for h in hourly],'payment_breakdown':pay_breakdown,
        'due_collected':[dict(p) for p in pay_due_collected],
        'due_payments_list':[dict(p) for p in due_payments_list],
        'due_collected_total':due_collected_total,
        'expenses':[dict(e) for e in exps],'totals':dict(totals),'expense_total':float(exp_total['total']),
        'net':round(rev-float(exp_total['total']),2),'baseline':baseline,
        'performance_pct':round((rev/baseline*100) if baseline>0 else 0,1),
        'restaurant':get_setting('restaurant_name'),'currency':get_setting('currency')})

@app.route('/api/reports/export')
@login_required
def export_report():
    period=request.args.get('period','7d'); today=date.today()
    if period=='week': start=(today-timedelta(days=today.weekday())).isoformat(); end=today.isoformat()
    elif period=='month': start=today.replace(day=1).isoformat(); end=today.isoformat()
    elif period=='last_month':
        first=today.replace(day=1); lm=first-timedelta(days=1); start=lm.replace(day=1).isoformat(); end=lm.isoformat()
    elif period=='30d': start=(today-timedelta(days=29)).isoformat(); end=today.isoformat()
    else: start=request.args.get('start',today.isoformat()); end=request.args.get('end',today.isoformat())
    conn=get_db()
    orders=conn.execute("""SELECT o.id,date(o.closed_at) as date,strftime('%H:%M',o.closed_at) as time,
        o.order_type,t.number as table_number,o.customer_name,o.payment_method,o.payment_subtype,
        o.subtotal,o.tax,o.discount,o.total,o.is_due,o.source
        FROM orders o LEFT JOIN tables t ON o.table_id=t.id
        WHERE o.status='closed' AND date(o.closed_at) BETWEEN ? AND ? ORDER BY o.closed_at""",(start,end)).fetchall()
    due_pays=conn.execute("""SELECT dp.id,date(dp.created_at) as date,strftime('%H:%M',dp.created_at) as time,
        c.name as customer_name,dp.payment_method,dp.payment_subtype,dp.amount,dp.notes
        FROM due_payments dp LEFT JOIN customers c ON dp.customer_id=c.id
        WHERE date(dp.created_at) BETWEEN ? AND ? ORDER BY dp.created_at""",(start,end)).fetchall()
    conn.close()
    out=io.StringIO(); w=csv.writer(out)
    # Sales section
    w.writerow(['=== SALES ORDERS ==='])
    w.writerow(['Order ID','Date','Time','Type','Table','Customer','Payment','Sub-type','Subtotal','Tax','Discount','Total','Due?','Source'])
    for o in orders:
        w.writerow([o['id'],o['date'],o['time'],o['order_type'],o['table_number'] or '',o['customer_name'] or '',o['payment_method'] or '',o['payment_subtype'] or '',o['subtotal'],o['tax'],o['discount'],o['total'],'Yes' if o['is_due'] else 'No',o['source'] or 'pos'])
    # Due payments section
    w.writerow([])
    w.writerow(['=== DUE PAYMENTS RECEIVED ==='])
    w.writerow(['Payment ID','Date','Time','Customer','Payment Method','Sub-type','Amount Received','Notes'])
    for p in due_pays:
        w.writerow([p['id'],p['date'],p['time'],p['customer_name'] or '',p['payment_method'] or '',p['payment_subtype'] or '',p['amount'],p['notes'] or ''])
    out.seek(0)
    return send_file(io.BytesIO(out.getvalue().encode('utf-8-sig')),mimetype='text/csv',as_attachment=True,download_name=f'sales_{start}_to_{end}.csv')

@app.route('/api/settings', methods=['GET','POST'])
@login_required
def api_settings():
    conn=get_db()
    if request.method=='POST':
        for k,v in request.json.items(): conn.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(k,v))
        conn.commit(); conn.close(); return jsonify({'ok':True})
    rows=conn.execute('SELECT * FROM settings').fetchall(); conn.close(); return jsonify({r['key']:r['value'] for r in rows})


# ── AUDIT LOG ─────────────────────────────────────────────────────────────────
@app.route('/api/admin/logs')
@admin_required
def admin_logs():
    conn = get_db()
    limit = int(request.args.get('limit', 200))
    entity = request.args.get('entity', '')
    biller = request.args.get('biller', '')
    q = 'SELECT * FROM audit_logs WHERE 1=1'
    params = []
    if entity: q += ' AND entity=?'; params.append(entity)
    if biller: q += ' AND biller_id=?'; params.append(biller)
    q += ' ORDER BY created_at DESC LIMIT ?'; params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/admin/stats')
@admin_required
def admin_stats():
    conn = get_db()
    from datetime import date, timedelta
    today = date.today().isoformat()
    month_start = date.today().replace(day=1).isoformat()
    # Overall
    total_rev = conn.execute("SELECT COALESCE(SUM(total),0) as t FROM orders WHERE status='closed'").fetchone()
    today_rev = conn.execute("SELECT COALESCE(SUM(total),0) as t,COUNT(*) as c FROM orders WHERE status='closed' AND date(closed_at)=?", (today,)).fetchone()
    month_rev = conn.execute("SELECT COALESCE(SUM(total),0) as t,COUNT(*) as c FROM orders WHERE status='closed' AND date(closed_at)>=?", (month_start,)).fetchone()
    # Per biller (from audit logs - orders closed)
    biller_stats = conn.execute("""
        SELECT al.biller_id, COUNT(*) as actions,
               (SELECT COUNT(*) FROM audit_logs al2 WHERE al2.biller_id=al.biller_id AND al2.action='close_order') as orders_closed
        FROM audit_logs al GROUP BY al.biller_id ORDER BY actions DESC LIMIT 20
    """).fetchall()
    billers = conn.execute('SELECT biller_id, name, is_active FROM billers').fetchall()
    conn.close()
    return jsonify({
        'total_revenue': float(total_rev['t']),
        'today': dict(today_rev),
        'month': dict(month_rev),
        'biller_stats': [dict(b) for b in biller_stats],
        'billers': [dict(b) for b in billers],
    })

# ── HOTEL HISTORY ─────────────────────────────────────────────────────────────
@app.route('/api/hotel/bookings')
@login_required
def hotel_bookings():
    conn = get_db()
    room_id = request.args.get('room_id', '')
    start = request.args.get('start', '')
    end = request.args.get('end', '')
    q = 'SELECT * FROM hotel_bookings WHERE 1=1'
    params = []
    if room_id: q += ' AND room_id=?'; params.append(room_id)
    if start: q += ' AND checkin_date>=?'; params.append(start)
    if end: q += ' AND checkin_date<=?'; params.append(end)
    q += ' ORDER BY created_at DESC LIMIT 200'
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/hotel/bookings/export')
@login_required
def export_hotel_bookings():
    conn = get_db()
    rows = conn.execute('SELECT * FROM hotel_bookings ORDER BY created_at DESC').fetchall()
    conn.close()
    out = io.StringIO(); w = csv.writer(out)
    w.writerow(['Room','Guest','Phone','Check-in','Check-out','Nights','Price/Night','Total','Payment','Status','Notes','Booked At','Checked Out'])
    for r in rows:
        w.writerow([r['room_number'],r['guest_name'],r['phone'],r['checkin_date'],r['checkout_date'],r['nights'],r['price_per_night'],r['total_amount'],r['payment_method'],r['status'],r['notes'],r['created_at'],r['checked_out_at']])
    out.seek(0)
    return send_file(io.BytesIO(out.getvalue().encode('utf-8-sig')), mimetype='text/csv', as_attachment=True, download_name='hotel_bookings.csv')

@socketio.on('connect')
def on_connect(): emit('connected',{'msg':'POS connected'})

init_db()

if __name__=='__main__':
    port = int(os.environ.get('PORT', 5003))
    print("\n"+"="*55)
    print("  Restaurant POS — Running!")
    print("="*55)
    print(f"  Login      -> http://127.0.0.1:{port}/login")
    print(f"  Terminal   -> http://127.0.0.1:{port}")
    print(f"  Admin      -> http://127.0.0.1:{port}/admin")
    print(f"  Dashboard  -> http://127.0.0.1:{port}/dashboard")
    print(f"  Hotel      -> http://127.0.0.1:{port}/hotel")
    print("="*55+"\n")
    socketio.run(app,host='0.0.0.0',port=port,debug=False,allow_unsafe_werkzeug=True,use_reloader=False)
