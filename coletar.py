#!/usr/bin/env python3
"""
coletar.py — Recolha local do 1001tracklists para o DJ Set Curator
===============================================================

CORRE NA TUA MÁQUINA (não na Vercel): o 1001tracklists bloqueia
datacenters (Cloudflare). Com o teu IP residencial + Chrome instalado,
funciona. Os dados vão para o teu Supabase e aparecem na app Vercel.

Pré-requisitos (uma vez):
    cd ~/djset-curator-v3/djset-curator
    python -m venv .venv && . .venv/bin/activate
    pip install -r requirements.txt
    playwright install chromium

Uso:
    python coletar.py --genre goa-psy-trance --max 50
    python coletar.py --genre techno --max 200 --delay 4
    python coletar.py --all            # todos os géneros ativos, 50 cada

O script respeita o delay entre sets (3–6s por omissão) para não
sobrecarregar o site. Podes interromper (Ctrl+C) a qualquer altura;
o que já foi gravado no Supabase fica lá.
"""
import os
import sys
import asyncio
import argparse
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(".env")

from supabase import create_client
from src.collector.collector import Collector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("coletar")


def main():
    ap = argparse.ArgumentParser(description="Recolha local 1001tracklists → Supabase")
    ap.add_argument("--genre", help="slug do género (ex: goa-psy-trance)")
    ap.add_argument("--max", type=int, default=50, help="máx. sets por género")
    ap.add_argument("--delay", type=float, default=4.5, help="delay médio entre sets (s)")
    ap.add_argument("--all", action="store_true", help="todos os géneros ativos")
    args = ap.parse_args()

    if not args.genre and not args.all:
        ap.error("usa --genre <slug> ou --all")

    URL = os.environ.get("SUPABASE_URL")
    KEY = os.environ.get("SUPABASE_KEY")
    if not URL or not KEY:
        logger.error("SUPABASE_URL / SUPABASE_KEY em falta no .env")
        sys.exit(1)

    sb = create_client(URL, KEY)
    collector = Collector(sb)

    # override do delay se pedido
    if args.delay:
        import src.collector.collector as cc
        cc.MIN_DELAY = max(1.0, args.delay - 1.5)
        cc.MAX_DELAY = args.delay + 1.5

    async def run():
        if args.all:
            genres = sb.table("genres").select("slug").eq("active", True).execute().data
            slugs = [g["slug"] for g in genres]
            logger.info(f"{len(slugs)} géneros ativos")
        else:
            slugs = [args.genre]

        total = 0
        for slug in slugs:
            logger.info(f"=== Género: {slug} (max {args.max}) ===")
            try:
                stats = await collector.collect_genre(slug, max_sets=args.max)
                logger.info(f"{slug} concluído: {stats}")
                total += stats.get("collected", 0)
            except Exception as e:
                logger.error(f"{slug} falhou: {e}")
            # pausa entre géneros
            await asyncio.sleep(5)
        logger.info(f"RECOLHA TOTAL: {total} sets gravados no Supabase.")

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.warning("Interrompido pelo utilizador. Dados já gravados ficam no Supabase.")


if __name__ == "__main__":
    main()
