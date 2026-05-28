from dotenv import load_dotenv
load_dotenv()
import os
import secrets
import json
from datetime import datetime
from threading import Thread
from functools import wraps

import psycopg2
import psycopg2.extras
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_mail import Mail, Message

app = Flask(__name__)

# --- CLAVE SECRETA (cambia esto en producción) ---
app.secret_key = os.environ.get('SECRET_KEY', 'mochisbus-secret-key-2024-cambiar-en-produccion')

# --- CONFIGURACIÓN POSTGRESQL ---
# En PythonAnywhere usa la variable de entorno DATABASE_URL
# Localmente puedes usar: postgresql://usuario:password@localhost/mochisbus
DATABASE_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://postgres:password@localhost/mochisbus'
)

# --- CONFIGURACIÓN DEL CORREO ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'verimtds@gmail.com'
app.config['MAIL_PASSWORD'] = 'bcbinshhxvuamine'
app.config['MAIL_DEFAULT_SENDER'] = app.config['MAIL_USERNAME']

mail = Mail(app)


# =============================================
# HELPERS DE BASE DE DATOS
# =============================================

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn


def init_db():
    """Crea todas las tablas si no existen (PostgreSQL)."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            ruta_asignada TEXT,
            is_confirmed INTEGER DEFAULT 0,
            token_confirmacion TEXT,
            wallet_saldo NUMERIC(10,2) DEFAULT 0.00
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS rutas (
            id SERIAL PRIMARY KEY,
            nombre_ruta TEXT NOT NULL UNIQUE,
            descripcion TEXT,
            color_linea TEXT DEFAULT '#FF0000',
            coordenadas TEXT
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS ubicaciones (
            username TEXT PRIMARY KEY,
            ruta TEXT,
            lat REAL,
            lon REAL,
            ultima_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS wallet_transacciones (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL,
            tipo TEXT NOT NULL,          -- 'recarga', 'pago', 'devolucion'
            monto NUMERIC(10,2) NOT NULL,
            descripcion TEXT,
            referencia TEXT,             -- ID de pago externo o NFC
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    cur.close()
    conn.close()
    print("Base de datos inicializada correctamente.")


# =============================================
# DECORADORES DE AUTENTICACIÓN
# =============================================

def login_required(f):
    """Requiere que el usuario haya iniciado sesión."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Requiere que el usuario sea administrador."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login_page'))
        if not session.get('is_admin'):
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


def chofer_required(f):
    """Requiere que el usuario sea chofer (tenga ruta asignada)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login_page'))
        if not session.get('ruta_asignada'):
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


# =============================================
# CORREO ASYNC
# =============================================

def enviar_correo_async(app_ctx, msg):
    with app_ctx.app_context():
        try:
            mail.send(msg)
        except Exception as e:
            print(f"Error correo: {e}")


# =============================================
# VISTAS HTML (protegidas)
# =============================================

@app.route('/')
def login_page():
    if 'username' in session:
        if session.get('is_admin'):
            return redirect(url_for('admin_panel'))
        elif session.get('ruta_asignada'):
            return redirect(url_for('soy_chofer'))
        else:
            return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route('/register_page')
def register_page():
    return render_template('register.html')


@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html',
                           username=session['username'],
                           role=session.get('role', 'Pasajero'))


@app.route('/admin_panel')
@admin_required
def admin_panel():
    return render_template('admin_panel.html',
                           username=session['username'])


@app.route('/soy_chofer')
@chofer_required
def soy_chofer():
    return render_template('chofer.html',
                           username=session['username'],
                           ruta=session.get('ruta_asignada', ''))


@app.route('/wallet')
@login_required
def wallet_page():
    return render_template('wallet.html',
                           username=session['username'],
                           role=session.get('role', 'Pasajero'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))


# =============================================
# API - AUTH
# =============================================

@app.route('/api/login', methods=['POST'])
def login_user():
    data = request.json
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('SELECT * FROM users WHERE username = %s AND password = %s',
                (data['username'], data['password']))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user:
        return jsonify({'success': False, 'message': 'Usuario o contraseña incorrectos.'})
    if user['is_confirmed'] == 0:
        return jsonify({'success': False, 'message': 'Correo no confirmado. Revisa tu bandeja.'})

    # Guardar sesión en el servidor
    session['username'] = user['username']
    session['is_admin'] = bool(user['is_admin'])
    session['ruta_asignada'] = user['ruta_asignada']

    if user['is_admin']:
        session['role'] = 'Administrador'
    elif user['ruta_asignada']:
        session['role'] = 'Conductor'
    else:
        session['role'] = 'Pasajero'

    return jsonify({
        'success': True,
        'is_admin': bool(user['is_admin']),
        'ruta_asignada': user['ruta_asignada'],
        'role': session['role']
    })


@app.route('/api/register', methods=['POST'])
def register_user():
    data = request.json
    token = secrets.token_urlsafe(16)
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            'INSERT INTO users (username, email, password, token_confirmacion) VALUES (%s, %s, %s, %s)',
            (data['username'], data['email'], data['password'], token)
        )
        conn.commit()
        cur.close()
        conn.close()

        link = url_for('confirmar_correo', token=token, _external=True)
        msg = Message('Confirma tu cuenta en MochisBus', recipients=[data['email']])
        msg.body = f'Hola {data["username"]},\n\nActiva tu cuenta aquí: {link}\n\nSi no creaste esta cuenta, ignora este correo.'
        Thread(target=enviar_correo_async, args=(app, msg)).start()
        return jsonify({'success': True, 'message': 'Cuenta creada. Revisa tu correo para confirmar.'})
    except psycopg2.errors.UniqueViolation:
        return jsonify({'success': False, 'message': 'El usuario o correo ya existe.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/confirmar/<token>')
def confirmar_correo(token):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('SELECT * FROM users WHERE token_confirmacion = %s', (token,))
    user = cur.fetchone()
    if user:
        cur.execute('UPDATE users SET is_confirmed = 1, token_confirmacion = NULL WHERE id = %s', (user['id'],))
        conn.commit()
        cur.close()
        conn.close()
        return render_template('confirmado.html')
    cur.close()
    conn.close()
    return "Token inválido o ya utilizado.", 400


# =============================================
# API - ADMIN - RUTAS
# =============================================

@app.route('/api/admin/crear_ruta', methods=['POST'])
@admin_required
def admin_crear_ruta():
    data = request.json
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            'INSERT INTO rutas (nombre_ruta, descripcion, color_linea, coordenadas) VALUES (%s, %s, %s, %s)',
            (data['nombre'], data['descripcion'], data['color'], json.dumps(data['coordenadas']))
        )
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True, 'message': 'Ruta creada correctamente.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/admin/editar_ruta', methods=['POST'])
@admin_required
def admin_editar_ruta():
    data = request.json
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        if data.get('coordenadas'):
            cur.execute(
                'UPDATE rutas SET nombre_ruta=%s, descripcion=%s, color_linea=%s, coordenadas=%s WHERE id=%s',
                (data['nombre'], data['descripcion'], data['color'], json.dumps(data['coordenadas']), data['id'])
            )
        else:
            cur.execute(
                'UPDATE rutas SET nombre_ruta=%s, descripcion=%s, color_linea=%s WHERE id=%s',
                (data['nombre'], data['descripcion'], data['color'], data['id'])
            )
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True, 'message': 'Ruta actualizada.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/admin/borrar_ruta', methods=['POST'])
@admin_required
def admin_borrar_ruta():
    data = request.json
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('DELETE FROM rutas WHERE id = %s', (data['id'],))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/admin/get_rutas', methods=['GET'])
def admin_get_rutas():
    """Pública: pasajeros también la necesitan para ver rutas."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('SELECT * FROM rutas')
    rutas = cur.fetchall()
    cur.close()
    conn.close()
    lista = []
    for r in rutas:
        try:
            coords = json.loads(r['coordenadas']) if r['coordenadas'] else []
        except Exception:
            coords = []
        lista.append({
            'id': r['id'],
            'nombre': r['nombre_ruta'],
            'descripcion': r['descripcion'],
            'color': r['color_linea'],
            'coordenadas': coords
        })
    return jsonify(lista)


@app.route('/api/admin/buscar_usuarios', methods=['POST'])
@admin_required
def admin_buscar_usuarios():
    busqueda = request.json.get('query', '')
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id, username, email, ruta_asignada FROM users WHERE username ILIKE %s",
                ('%' + busqueda + '%',))
    usuarios = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([dict(u) for u in usuarios])


@app.route('/api/admin/asignar_chofer', methods=['POST'])
@admin_required
def admin_asignar_chofer():
    data = request.json
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        ruta = data['ruta'] if data['ruta'] != "" else None
        cur.execute('UPDATE users SET ruta_asignada = %s WHERE id = %s', (ruta, data['user_id']))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


# =============================================
# API - GEOLOCALIZACIÓN
# =============================================

@app.route('/api/obtener_choferes', methods=['GET'])
def obtener_choferes():
    ruta = request.args.get('ruta')
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("DELETE FROM ubicaciones WHERE ultima_actualizacion < NOW() - INTERVAL '2 minutes'")
        conn.commit()
        if ruta:
            cur.execute('SELECT username, lat, lon FROM ubicaciones WHERE ruta = %s', (ruta,))
            choferes = cur.fetchall()
        else:
            choferes = []
        return jsonify([{'username': c['username'], 'lat': c['lat'], 'lon': c['lon']} for c in choferes])
    finally:
        cur.close()
        conn.close()


@app.route('/api/actualizar_ubicacion', methods=['POST'])
def actualizar_ubicacion():
    data = request.json
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        if data['activo']:
            cur.execute(
                '''INSERT INTO ubicaciones (username, ruta, lat, lon, ultima_actualizacion)
                   VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                   ON CONFLICT (username) DO UPDATE
                   SET ruta=%s, lat=%s, lon=%s, ultima_actualizacion=CURRENT_TIMESTAMP''',
                (data['username'], data['ruta'], data['lat'], data['lon'],
                 data['ruta'], data['lat'], data['lon'])
            )
        else:
            cur.execute('DELETE FROM ubicaciones WHERE username = %s', (data['username'],))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
    finally:
        cur.close()
        conn.close()


# =============================================
# API - FEEDBACK
# =============================================

@app.route('/api/enviar_feedback', methods=['POST'])
def enviar_feedback():
    data = request.json
    usuario = data.get('usuario', 'Anónimo')
    mensaje = data.get('mensaje', '')
    msg = Message(f'Reporte MochisBus: {usuario}', recipients=[app.config['MAIL_USERNAME']])
    msg.body = f"Usuario: {usuario}\n\n{mensaje}"
    Thread(target=enviar_correo_async, args=(app, msg)).start()
    return jsonify({'success': True})


# =============================================
# API - WALLET
# =============================================

@app.route('/api/wallet/saldo', methods=['GET'])
@login_required
def wallet_saldo():
    username = session['username']
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('SELECT wallet_saldo FROM users WHERE username = %s', (username,))
    user = cur.fetchone()
    cur.execute(
        'SELECT * FROM wallet_transacciones WHERE username = %s ORDER BY fecha DESC LIMIT 10',
        (username,)
    )
    transacciones = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({
        'success': True,
        'saldo': float(user['wallet_saldo']) if user else 0.0,
        'transacciones': [dict(t) for t in transacciones]
    })


@app.route('/api/wallet/recargar', methods=['POST'])
@login_required
def wallet_recargar():
    """Simula una recarga de saldo (sandbox)."""
    data = request.json
    monto = float(data.get('monto', 0))
    metodo = data.get('metodo', 'simulado')

    if monto <= 0 or monto > 5000:
        return jsonify({'success': False, 'message': 'Monto inválido. Máximo $5,000 MXN.'})

    username = session['username']
    referencia = secrets.token_hex(8).upper()

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('UPDATE users SET wallet_saldo = wallet_saldo + %s WHERE username = %s',
                    (monto, username))
        cur.execute(
            '''INSERT INTO wallet_transacciones (username, tipo, monto, descripcion, referencia)
               VALUES (%s, %s, %s, %s, %s)''',
            (username, 'recarga', monto, f'Recarga vía {metodo}', referencia)
        )
        conn.commit()
        cur.execute('SELECT wallet_saldo FROM users WHERE username = %s', (username,))
        nuevo_saldo = cur.fetchone()[0]
        return jsonify({
            'success': True,
            'message': f'Recarga de ${monto:.2f} exitosa.',
            'nuevo_saldo': float(nuevo_saldo),
            'referencia': referencia
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        cur.close()
        conn.close()


@app.route('/api/wallet/pagar_nfc', methods=['POST'])
@login_required
def wallet_pagar_nfc():
    """Procesa el pago NFC al abordar el camión."""
    data = request.json
    tarifa = float(data.get('tarifa', 12.00))  # Tarifa por defecto $12 MXN
    ruta = data.get('ruta', 'Desconocida')
    nfc_ref = data.get('nfc_ref', secrets.token_hex(6).upper())

    username = session['username']
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute('SELECT wallet_saldo FROM users WHERE username = %s', (username,))
        user = cur.fetchone()
        saldo_actual = float(user['wallet_saldo'])

        if saldo_actual < tarifa:
            return jsonify({
                'success': False,
                'message': f'Saldo insuficiente. Tienes ${saldo_actual:.2f} y la tarifa es ${tarifa:.2f}.'
            })

        cur2 = conn.cursor()
        cur2.execute('UPDATE users SET wallet_saldo = wallet_saldo - %s WHERE username = %s',
                     (tarifa, username))
        cur2.execute(
            '''INSERT INTO wallet_transacciones (username, tipo, monto, descripcion, referencia)
               VALUES (%s, %s, %s, %s, %s)''',
            (username, 'pago', tarifa, f'Pago NFC - Ruta {ruta}', nfc_ref)
        )
        conn.commit()

        cur2.execute('SELECT wallet_saldo FROM users WHERE username = %s', (username,))
        nuevo_saldo = cur2.fetchone()[0]
        cur2.close()
        return jsonify({
            'success': True,
            'message': f'Pago de ${tarifa:.2f} procesado.',
            'nuevo_saldo': float(nuevo_saldo),
            'referencia': nfc_ref
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        cur.close()
        conn.close()


# =============================================
# API - INFO SESIÓN (para JS en frontend)
# =============================================

@app.route('/api/session_info', methods=['GET'])
def session_info():
    """Devuelve info de sesión para el JS del frontend."""
    if 'username' not in session:
        return jsonify({'logged_in': False})
    return jsonify({
        'logged_in': True,
        'username': session['username'],
        'role': session.get('role', 'Pasajero'),
        'is_admin': session.get('is_admin', False),
        'ruta_asignada': session.get('ruta_asignada')
    })


# =============================================
# MAIN
# =============================================

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', debug=True, port=5000)