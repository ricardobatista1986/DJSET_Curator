#!/usr/bin/env python3
"""
worker.py — Worker de carga do 1001tracklists (CORRE NA TUA MÁQUINA)

O botão "Gerar carga" na app Vercel cria um job na tabela `jobs` do Supabase.
Este worker fica a correr em background na tua máquina (onde tens Chrome + IP
residencial, que o 1001tracklists aceita). Ele:
  1. cria a tabela `jobs` se não existir (precisa de DATABASE_URL)
  2. vigia a tabela `jobs` por pedidos com status='pending'
  3. quando aparece um, marca 'running', corre o Collector (extrai sets reais
     de DJs do 1001tracklists) e grava sets+transições no Supabase
  4. marca 'done' (ou 'error') e atualiza o progresso

Uso:
    cd ~/djset-curator-v3/djset-curator
    . .venv/bin/activate
    python worker.py
    # deixa a correr. Clica em "Gerar carga" na app quando quiseres carregar.

Pré-requisito (1x): tens de ter o Chrome do Playwright instalado:
    playwright install chromium

E, para o worker criar a tabela jobs sozinho, adiciona ao teu .env:
    DATABASE_URL=postgresql://postgres:<tua-senha>@db.<ref>.supabase.co:5432/postgres
(Encontras em Supabase → Settings → Database → Connection string. Se não quiseres
pôr isto, corre o SQL em config/schema.sql na Supabase SQL Editor uma vez.)
"""
import os
import sys
import time
import asyncio
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [worker] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("worker")

POLL_SECONDS = 15


def ensure_jobs_table():
    """Cria a tabela jobs se não existir (precisa DATABASE_URL)."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        logger.warning("DATABASE_URL não definido — não consigo criar a tabela jobs automaticamente.")
        logger.warning("Corre o SQL em config/schema.sql na Supabase SQL Editor (1x).")
        return
    try:
        import psycopg2
        conn = psycopg2.connect(url, connect_timeout=10)
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id          SERIAL PRIMARY KEY,
            genre_slug TEXT NOT NULL,
            max_sets    INTEGER NOT NULL DEFAULT 50,
            status      TEXT DEFAULT 'pending',
            stats       JSONB,
            error_detail TEXT,
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            updated_at  TIMESTAMPTZ DEFAULT NOW()
        );
        """)
        conn.commit()
        cur.close(); conn.close()
        logger.info("Tabela jobs OK (criada ou já existente).")
    except Exception as e:
        logger.error(f"Não consegui criar a tabela jobs: {e}")


def run_job(sb, job: dict):
    from src.collector.collector import Collector
    genre = job["genre_slug"]
    max_sets = job["max_sets"]
    logger.info(f"Job #{job['id']}: a extrair género '{genre}' (max {max_sets})")
    collector = Collector(sb)
    try:
        stats = asyncio.run(collector.collect_genre(genre, max_sets))
        if not stats.get("collected"):
            logger.warning(
                f"Job #{job['id']}: 0 sets recolhidos. Se estás a correr isto no teu PC "
                f"com Chrome+IP residencial e mesmo assim vem 0, o 1001tracklists pode estar "
                f"a bloquear (Cloudflare). Verifica a tua ligação/Chrome e tenta de novo."
            )
        sb.table("jobs").update({
            "status": "done", "stats": stats, "updated_at": "now()"
        }).eq("id", job["id"]).execute()
        logger.info(f"Job #{job['id']} CONCLUÍDO: {stats}")
    except Exception as e:
        logger.exception(f"Job #{job['id']} falhou")
        sb.table("jobs").update({
            "status": "error", "error_detail": str(e), "updated_at": "now()"
        }).eq("id", job["id"]).execute()


def main():
    from supabase import create_client
    URL = os.environ.get("SUPABASE_URL"); KEY = os.environ.get("SUPABASE_KEY")
    if not URL or not KEY:
        logger.error("SUPABASE_URL/KEY em falta no .env"); sys.exit(1)
    sb = create_client(URL, KEY)
    ensure_jobs_table()

    logger.info(f"Worker a vigiar a tabela jobs (cada {POLL_SECONDS}s). Ctrl+C para parar.")
    while True:
        try:
            rows = sb.table("jobs").select("*").eq("status", "pending").order("id").limit(1).execute().data
            if rows:
                job = rows[0]
                sb.table("jobs").update({"status": "running", "updated_at": "now()"}).eq("id", job["id"]).execute()
                run_job(sb, job)
            else:
                time.sleep(POLL_SECONDS)
        except KeyboardInterrupt:
            logger.info("Worker parado."); break
        except Exception as e:
            logger.error(f"Erro no loop: {e}")
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
