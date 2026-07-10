#!/usr/bin/env python3
"""setup_db.py — cria a tabela `jobs` no teu Supabase (1x).
Precisa de DATABASE_URL no .env (Supabase → Settings → Database → Connection string).
Uso: python setup_db.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(".env")

url = os.environ.get("DATABASE_URL")
if not url:
    print("❌ DATABASE_URL em falta no .env.")
    print("Vai a Supabase → Settings → Database → Connection string e copia a linha")
    print("postgresql://postgres:****@db.<ref>.supabase.co:5432/postgres")
    print("Cola no .env e corre de novo. (Ou corre config/create_jobs_table.sql na SQL Editor.)")
    sys.exit(1)

try:
    import psycopg2
    conn = psycopg2.connect(url, connect_timeout=15)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        id            SERIAL PRIMARY KEY,
        genre_slug   TEXT NOT NULL,
        max_sets      INTEGER NOT NULL DEFAULT 50,
        status        TEXT DEFAULT 'pending',
        stats         JSONB,
        error_detail  TEXT,
        created_at    TIMESTAMPTZ DEFAULT NOW(),
        updated_at    TIMESTAMPTZ DEFAULT NOW()
    );
    """)
    conn.commit(); cur.close(); conn.close()
    print("✅ Tabela jobs criada (ou já existia). Worker pronto a usar.")
except Exception as e:
    print("❌ Erro ao criar tabela:", e)
    sys.exit(1)
