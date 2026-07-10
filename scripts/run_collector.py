"""Script de coleta para GitHub Actions."""
import os, sys, logging, asyncio

from supabase import create_client
from src.collector.collector import Collector

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main():
    sb         = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    collector  = Collector(sb)
    genre_slug = os.environ.get("GENRE_SLUG", "").strip()
    max_sets   = int(os.environ.get("MAX_SETS", "200"))

    if genre_slug:
        genres = [genre_slug]
    else:
        genres = [g["slug"] for g in
                  sb.table("genres").select("slug").eq("active", True).execute().data]

    logger.info(f"Generos: {genres} | Max/genero: {max_sets}")
    total = {"collected": 0, "skipped": 0, "errors": 0}

    for slug in genres:
        try:
            stats = await collector.collect_genre(slug, max_sets=max_sets)
            for k in total:
                total[k] += stats.get(k, 0)
        except Exception as e:
            logger.error(f"Falha em {slug}: {e}")
            total["errors"] += 1

    logger.info(f"TOTAL: {total}")
    attempts = total["collected"] + total["errors"]
    if attempts > 0 and total["errors"] / attempts > 0.5:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
