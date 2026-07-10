"""
Módulo 1: Coletor 1001tracklists
---------------------------------
Usa async_playwright (compatível com Jupyter e GitHub Actions).
Todas as funções públicas são corrotinas — use `await` para chamá-las.

Uso no Jupyter:
    results = await collector.collect_genre('goa-psy-trance', max_sets=100)

Uso em script normal:
    import asyncio
    results = asyncio.run(collector.collect_genre('goa-psy-trance', max_sets=100))
"""

import re
import asyncio
import logging
import random
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

logger = logging.getLogger(__name__)

BASE_URL  = "https://www.1001tracklists.com"
MIN_DELAY = 3.0
MAX_DELAY = 6.0


class Collector:
    def __init__(self, supabase_client):
        self.sb = supabase_client

    # ------------------------------------------------------------------
    # PÚBLICO
    # ------------------------------------------------------------------

    async def collect_genre(self, genre_slug: str, max_sets: int = 200) -> dict:
        """Coleta sets de um gênero e persiste no Supabase."""
        genre = self._get_genre(genre_slug)
        if not genre:
            raise ValueError(f"Gênero '{genre_slug}' não encontrado na tabela genres.")

        logger.info(f"[{genre_slug}] Iniciando coleta (max={max_sets})")
        stats = {"collected": 0, "skipped": 0, "errors": 0}

        set_urls = await self._get_set_urls(genre_slug, max_sets)
        logger.info(f"[{genre_slug}] {len(set_urls)} URLs encontradas")

        for url in set_urls:
            if stats["collected"] >= max_sets:
                break
            result = await self._process_set(url, genre)
            stats[result] += 1
            await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

        logger.info(f"[{genre_slug}] Concluído: {stats}")
        return stats

    async def _get_set_urls(self, genre_slug: str, max_sets: int) -> list:
        """Coleta URLs de sets na página de gênero (scroll infinito)."""
        genre_url = f"{BASE_URL}/genre/{genre_slug}/index.html"
        urls = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            try:
                await page.goto(genre_url, timeout=30000)
                await page.wait_for_load_state("networkidle", timeout=15000)

                last_count  = 0
                max_scrolls = max(10, max_sets // 15)

                for _ in range(max_scrolls):
                    html  = await page.content()
                    soup  = BeautifulSoup(html, "html.parser")
                    links = self._extract_set_links(soup)
                    urls  = list(dict.fromkeys(links))

                    if len(urls) == last_count:
                        break
                    last_count = len(urls)

                    if len(urls) >= max_sets:
                        break

                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(2.5)

            except PWTimeout:
                logger.warning(f"Timeout na página de gênero: {genre_url}")
            finally:
                await browser.close()

        return urls[:max_sets]

    async def _scrape_set(self, url: str) -> Optional[dict]:
        """Scraping de um set individual. Retorna dict com tracks."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page    = await browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            try:
                await page.goto(url, timeout=30000)
                await page.wait_for_load_state("networkidle", timeout=15000)
                html = await page.content()
            except PWTimeout:
                logger.warning(f"Timeout: {url}")
                return None
            finally:
                await browser.close()

        return self._parse_set_html(html)

    # ------------------------------------------------------------------
    # PARSING
    # ------------------------------------------------------------------

    def _extract_set_links(self, soup: BeautifulSoup) -> list:
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.match(r"^/tracklist/[a-z0-9]+/", href):
                full_url = BASE_URL + href
                full_url = full_url.split("?")[0].split("#")[0]
                if full_url not in links:
                    links.append(full_url)
        return links

    def _parse_set_html(self, html: str) -> Optional[dict]:
        soup = BeautifulSoup(html, "html.parser")

        dj_name   = None
        set_title = None
        set_date  = None

        h1 = soup.find("h1")
        if h1:
            dj_name = h1.get_text(strip=True)

        title_tag = soup.find("title")
        if title_tag:
            set_title = title_tag.get_text(strip=True)

        date_elem = soup.find(class_=re.compile(r"date|tgDate", re.I))
        if date_elem:
            set_date = self._parse_date(date_elem.get_text(strip=True))

        tracks = self._extract_tracks(soup)
        if not tracks:
            return None

        return {
            "dj_name":   dj_name,
            "set_title": set_title,
            "set_date":  set_date,
            "tracks":    tracks,
        }

    def _extract_tracks(self, soup: BeautifulSoup) -> list:
        tracks   = []
        position = 1

        items = (
            soup.find_all(class_="tlpItem")
            or soup.find_all(class_=re.compile(r"trackItem|tlpItem"))
        )

        for item in items:
            track_format = item.find(class_="trackFormat")
            if not track_format:
                continue

            text = track_format.get_text(" ", strip=True)

            if "ID - ID" in text or text.strip() == "ID":
                position += 1
                continue

            artist, title = self._split_artist_title(text)
            if not artist or not title:
                position += 1
                continue

            timestamp = None
            ts_elem = item.find(class_=re.compile(r"timestamp|tgHid|cueTime"))
            if ts_elem:
                timestamp = ts_elem.get_text(strip=True)

            tracks.append({
                "position":  position,
                "artist":    artist.strip(),
                "title":     title.strip(),
                "timestamp": timestamp,
            })
            position += 1

        return tracks

    def _split_artist_title(self, text: str):
        text = re.sub(r"\s+", " ", text).strip()
        if " - " in text:
            parts = text.split(" - ", 1)
            return parts[0].strip(), parts[1].strip()
        return "", ""

    # ------------------------------------------------------------------
    # PERSISTÊNCIA
    # ------------------------------------------------------------------

    async def _process_set(self, url: str, genre: dict) -> str:
        external_id = self._extract_external_id(url)
        exists = (
            self.sb.table("sets")
            .select("id")
            .eq("external_id", external_id)
            .execute()
            .data
        )
        if exists:
            logger.debug(f"Skipping (já existe): {external_id}")
            return "skipped"

        try:
            set_data = await self._scrape_set(url)
            if not set_data or not set_data.get("tracks"):
                return "errors"

            set_id = self._save_set(set_data, genre, url, external_id)
            if set_id:
                logger.info(
                    f"Coletado: {set_data.get('dj_name')} "
                    f"— {len(set_data['tracks'])} tracks"
                )
                return "collected"
            return "errors"

        except Exception as e:
            logger.error(f"Erro em {url}: {e}")
            return "errors"

    def _save_set(self, set_data: dict, genre: dict, url: str, external_id: str) -> Optional[int]:
        try:
            set_row = (
                self.sb.table("sets")
                .insert({
                    "external_id": external_id,
                    "url":         url,
                    "dj_name":     set_data.get("dj_name"),
                    "set_title":   set_data.get("set_title"),
                    "genre_id":    genre["id"],
                    "set_date":    set_data.get("set_date"),
                    "track_count": len(set_data["tracks"]),
                })
                .execute()
                .data[0]
            )
            set_id = set_row["id"]

            track_ids = [
                self._upsert_track(t["artist"], t["title"])
                for t in set_data["tracks"]
            ]

            transitions = [
                {
                    "set_id":        set_id,
                    "genre_id":      genre["id"],
                    "track_from_id": track_ids[i],
                    "track_to_id":   track_ids[i + 1],
                    "position_from": i + 1,
                    "position_to":   i + 2,
                }
                for i in range(len(track_ids) - 1)
                if track_ids[i] and track_ids[i + 1]
            ]

            if transitions:
                self.sb.table("transitions").insert(transitions).execute()

            return set_id

        except Exception as e:
            logger.error(f"Erro ao salvar set {external_id}: {e}")
            return None

    def _upsert_track(self, artist: str, title: str) -> Optional[int]:
        try:
            existing = (
                self.sb.table("tracks")
                .select("id")
                .eq("artist", artist)
                .eq("title", title)
                .execute()
                .data
            )
            if existing:
                return existing[0]["id"]

            new = (
                self.sb.table("tracks")
                .insert({"artist": artist, "title": title})
                .execute()
                .data[0]
            )
            return new["id"]

        except Exception as e:
            logger.error(f"Erro ao upsert track '{artist} - {title}': {e}")
            return None

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _get_genre(self, slug: str) -> Optional[dict]:
        result = (
            self.sb.table("genres").select("*").eq("slug", slug).execute().data
        )
        return result[0] if result else None

    def _extract_external_id(self, url: str) -> str:
        match = re.search(r"/tracklist/([a-z0-9]+)/", url)
        return match.group(1) if match else url

    def _parse_date(self, date_text: str) -> Optional[str]:
        for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%B %d, %Y", "%d %B %Y"]:
            try:
                return datetime.strptime(date_text.strip(), fmt).date().isoformat()
            except ValueError:
                continue
        return None
