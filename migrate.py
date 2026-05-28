"""
migrate_sqlite_to_postgres.py
==============================
Migra los datos existentes de SQLite → PostgreSQL.
Corre este script UNA SOLA VEZ después de configurar la DB.

Uso:
    python migrate_sqlite_to_postgres.py

Asegúrate de tener DATABASE_URL en tu entorno o ajusta la variable
POSTGRES_URL abajo antes de correr.
"""

import sqlite3
import os
import json
import psycopg2
import psycopg2.extras

SQLITE_FILE = os.path.join(os.path.dirname(__file__), 'database.db')

# Ajusta esto con tus datos de PostgreSQL
POSTGRES_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://postgres:1234@localhost/mochisbus'
)


def get_sqlite():
    conn = sqlite3.connect(SQLITE_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def get_postgres():
    conn = psycopg2.connect(POSTGRES_URL)
    return conn


def crear_tablas_postgres(pg):
    cur = pg.cursor()

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
            tipo TEXT NOT NULL,
            monto NUMERIC(10,2) NOT NULL,
            descripcion TEXT,
            referencia TEXT,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    pg.commit()
    cur.close()
    print("✅ Tablas creadas en PostgreSQL.")


def migrar_usuarios(sq, pg):
    cur_sq = sq.cursor()
    cur_pg = pg.cursor()
    cur_sq.execute("SELECT * FROM users")
    rows = cur_sq.fetchall()
    count = 0
    for row in rows:
        try:
            cur_pg.execute('''
                INSERT INTO users (id, username, email, password, is_admin, ruta_asignada, is_confirmed, token_confirmacion, wallet_saldo)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0.00)
                ON CONFLICT (username) DO NOTHING
            ''', (row['id'], row['username'], row['email'], row['password'],
                  row['is_admin'], row['ruta_asignada'], row['is_confirmed'], row['token_confirmacion']))
            count += 1
        except Exception as e:
            print(f"  ⚠️  Usuario {row['username']}: {e}")
    pg.commit()
    # Resetear la secuencia del serial
    cur_pg.execute("SELECT setval('users_id_seq', (SELECT MAX(id) FROM users))")
    pg.commit()
    cur_sq.close()
    cur_pg.close()
    print(f"✅ Usuarios migrados: {count}")


def migrar_rutas(sq, pg):
    cur_sq = sq.cursor()
    cur_pg = pg.cursor()
    cur_sq.execute("SELECT * FROM rutas")
    rows = cur_sq.fetchall()
    count = 0
    for row in rows:
        try:
            cur_pg.execute('''
                INSERT INTO rutas (id, nombre_ruta, descripcion, color_linea, coordenadas)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (nombre_ruta) DO NOTHING
            ''', (row['id'], row['nombre_ruta'], row['descripcion'], row['color_linea'], row['coordenadas']))
            count += 1
        except Exception as e:
            print(f"  ⚠️  Ruta {row['nombre_ruta']}: {e}")
    pg.commit()
    cur_pg.execute("SELECT setval('rutas_id_seq', (SELECT MAX(id) FROM rutas))")
    pg.commit()
    cur_sq.close()
    cur_pg.close()
    print(f"✅ Rutas migradas: {count}")


def migrar_ubicaciones(sq, pg):
    """Las ubicaciones son efímeras, solo migramos si hay datos."""
    cur_sq = sq.cursor()
    cur_pg = pg.cursor()
    cur_sq.execute("SELECT * FROM ubicaciones")
    rows = cur_sq.fetchall()
    count = 0
    for row in rows:
        try:
            cur_pg.execute('''
                INSERT INTO ubicaciones (username, ruta, lat, lon)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (username) DO NOTHING
            ''', (row['username'], row['ruta'], row['lat'], row['lon']))
            count += 1
        except Exception as e:
            print(f"  ⚠️  Ubicación {row['username']}: {e}")
    pg.commit()
    cur_sq.close()
    cur_pg.close()
    print(f"✅ Ubicaciones migradas: {count}")


if __name__ == '__main__':
    print("\n🚀 Iniciando migración SQLite → PostgreSQL\n")
    print(f"   SQLite:     {SQLITE_FILE}")
    print(f"   PostgreSQL: {POSTGRES_URL[:40]}...\n")

    if not os.path.exists(SQLITE_FILE):
        print("❌ No se encontró database.db. Verifica la ruta.")
        exit(1)

    sq = get_sqlite()
    pg = get_postgres()

    crear_tablas_postgres(pg)
    migrar_usuarios(sq, pg)
    migrar_rutas(sq, pg)
    migrar_ubicaciones(sq, pg)

    sq.close()
    pg.close()

    print("\n✅ Migración completada.")
    print("   Recuerda ajustar DATABASE_URL en tu entorno antes de correr app.py\n")