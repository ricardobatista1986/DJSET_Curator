#!/usr/bin/env python3
"""
DJ Set Curator — Servidor web (produto)
========================================
Backend Flask que orquestra os módulos reais do projeto
(Collector, Graph, Enricher, Curator) e serve uma UI HTML única.

Como correr (na tua máquina, com rede + chaves válidas):
    cd ~/djset-curator-v3/djset-curator
    . .venv/bin/activate
    pip install flask
    python app.py
Depois abre http://localhost:5000

O servidor:
  - serve a UI (index.html)
  - expõe endpoints REST que ligam ao teu Supabase real
  - a coleta do 1001tracklists roda em background (podes acompanhar o progresso)
"""
import os
import sys
import json
import time
import threading
import logging
from datetime import datetime
from functools import wraps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(".env")

from flask import (Flask, request, jsonify, send_from_directory,
                   session, redirect, render_template_string)
from supabase import create_client

from src.graph.graph import Graph
from src.enricher.enricher import Enricher
from src.curator.curator import Curator
from src.llm.llm import LLMProvider
from src.spotify_oauth import (authorize_url, exchange_code, get_valid_token,
                               tracks_from_playlist_with_token)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("djset-web")

app = Flask(__name__, static_folder="web", template_folder="web")
app.secret_key = os.environ.get("APP_PASSWORD", "djset-secret-change-me")

URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
GEMINI = os.environ.get("GEMINI_API_KEY")
SPOT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOT_SEC = os.environ.get("SPOTIFY_CLIENT_SECRET")

APP_USER = os.environ.get("APP_USER", "admin")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "admin")

sb = create_client(URL, KEY)
enricher = Enricher(sb, SPOT_ID, SPOT_SEC)
graph = Graph(sb)
curator = Curator(sb, enricher, graph, gemini_api_key=GEMINI, llm_provider=LLMProvider())


# ---- autenticação simples (tu + quem souberes a senha) ----
def login_required(f):
    @wraps(f)
    def wrapped(*a, **k):
        if not session.get("auth"):
            # para pedidos de API, devolve 401; para página, redireciona p/ login
            if request.path.startswith("/api/"):
                return jsonify({"error": "nao autenticado"}), 401
            return redirect("/login")
        return f(*a, **k)
    return wrapped


LOGIN_HTML = """<!doctype html><html lang=pt-BR><head><meta charset=utf-8>
<title>DJ Set Curator — Login</title>
<link href=https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css rel=stylesheet></head>
<body class="bg-dark text-light"><div class=container style="max-width:420px;margin-top:12vh">
<h3 class=mb-3>🎧 DJ Set Curator</h3>
{% if erro %}<div class="alert alert-danger">{{erro}}</div>{% endif %}
<form method=post><div class=mb-2><input name=user class=form-control placeholder=Email value="{{user}}"></div>
<div class=mb-3><input name=pw type=password class=form-control placeholder=Senha></div>
<button class="btn btn-primary w-100">Entrar</button></form></div></body></html>"""


@app.route("/login", methods=["GET", "POST"])
def login():
    erro = None
    user = ""
    if request.method == "POST":
        user = request.form.get("user", "")
        pw = request.form.get("pw", "")
        if user == APP_USER and pw == APP_PASSWORD:
            session["auth"] = True
            return redirect("/")
        erro = "Credenciais inválidas."
    return render_template_string(LOGIN_HTML, erro=erro, user=user)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---- estado de coleta em background ----
_collect_state = {"running": False, "genre": None, "stats": None,
                  "started_at": None, "done_at": None, "error": None}
_collect_lock = threading.Lock()

# =====================================================================
# UI
# =====================================================================
@app.route("/")
@login_required
def index():
    return send_from_directory("web", "index.html")

@app.route("/web/<path:p>")
@login_required
def web_static(p):
    return send_from_directory("web", p)

# =====================================================================
# API
# =====================================================================
@app.route("/api/genres")
@login_required
def api_genres():
    try:
        rows = sb.table("genres").select("slug,name,active").eq("active", True).execute().data
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/stats")
@login_required
def api_stats():
    try:
        s = graph.get_genre_stats(None)
        return jsonify(s)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

import src.load_spotify as load_spotify

@app.route("/api/collect/job", methods=["POST"])
@login_required
def api_collect_job():
    """Cria um pedido de carga e processa o 1º lote (server-side, Spotify API).
    Processamento é resumável: cada chamada a /api/collect/step faz o próximo
    lote (uma playlist) para caber no timeout de 60s da Vercel."""
    data = request.get_json(silent=True) or {}
    genre = data.get("genre")
    max_sets = int(data.get("max_sets", 10))
    if not genre:
        return jsonify({"error": "genre obrigatório"}), 400
    try:
        row = sb.table("jobs").insert({
            "genre_slug": genre, "max_sets": max_sets,
            "status": "running",
            "progress": {"playlists": None, "idx": 0, "sets_done": 0},
        }).execute().data[0]
        # processa o primeiro lote já na resposta
        result = step_collect_job(row["id"])
        return jsonify({"ok": True, "job_id": row["id"], "result": result})
    except Exception as e:
        return jsonify({"error": f"não consegui criar o job (tabela jobs existe?): {e}"}), 500


def step_collect_job(job_id):
    """Processa o próximo lote (uma playlist) de um job. Retorna estado.
    Usa o token OAuth do Spotify da SESSÃO do utilizador (não Client Credentials,
    porque ler tracks de playlists exige token de user). Cada chamada vem com o
    session cookie, por isso get_valid_token(session) funciona em cada passo."""
    job = sb.table("jobs").select("*").eq("id", job_id).execute().data[0]
    if job["status"] in ("done", "error"):
        return {"status": job["status"]}
    token = get_valid_token(session)
    if not token:
        return _finish_job(job_id, error="Spotify não ligado. Clica em 'Conectar Spotify' (em cima) e volta a gerar a carga.")
    genre_slug = job["genre_slug"]
    max_sets = job["max_sets"]
    progress = job.get("progress") or {"playlists": None, "idx": 0, "sets_done": 0}
    genre = sb.table("genres").select("*").eq("slug", genre_slug).limit(1).execute().data
    if not genre:
        return _finish_job(job_id, error=f"género '{genre_slug}' não existe")
    genre = genre[0]

    # 1) descobrir playlists (1x) se ainda não tivermos
    if not progress.get("playlists"):
        pls = load_spotify.find_genre_playlists(token, genre["name"], limit=min(max_sets, 10))
        progress["playlists"] = [p["id"] for p in pls]
        progress["idx"] = 0
        if not pls:
            return _finish_job(job_id, stats={"collected": 0, "skipped": 0, "errors": 0})

    # 2) processar a próxima playlist
    idx = progress["idx"]
    playlists = progress["playlists"]
    if idx >= len(playlists):
        return _finish_job(job_id, stats=progress.get("_stats", {"collected": progress["sets_done"], "skipped": 0, "errors": 0}))

    pid = playlists[idx]
    try:
        res = load_spotify.process_playlist(sb, token, pid, genre["id"], max_tracks=60)
        if res.get("status") == "ok":
            progress["sets_done"] = progress.get("sets_done", 0) + 1
        elif res.get("status") == "skip":
            logger.info(f"playlist {pid} ignorada: {res.get('reason')}")
    except Exception as e:
        logger.warning(f"playlist {pid} falhou: {e}")
    progress["idx"] = idx + 1
    done = progress["idx"] >= len(playlists)
    sb.table("jobs").update({
        "progress": progress, "updated_at": "now()",
        "status": "done" if done else "running",
    }).eq("id", job_id).execute()
    if done:
        return _finish_job(job_id, stats={"collected": progress["sets_done"], "skipped": 0, "errors": 0}, already_updated=True)
    return {"status": "running", "progress": progress, "sets_done": progress["sets_done"]}


def _finish_job(job_id, stats=None, error=None, already_updated=False):
    if not already_updated:
        sb.table("jobs").update({
            "status": "error" if error else "done",
            "stats": stats, "error_detail": error, "updated_at": "now()",
        }).eq("id", job_id).execute()
    return {"status": "error" if error else "done", "stats": stats, "error_detail": error}


@app.route("/api/collect/step", methods=["POST"])
@login_required
def api_collect_step():
    """Processa o próximo lote do job mais recente (chamado pelo polling da UI)."""
    try:
        rows = sb.table("jobs").select("*").order("id", desc=True).limit(1).execute().data
        if not rows:
            return jsonify({"error": "sem jobs"}), 404
        result = step_collect_job(rows[0]["id"])
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/collect/job/status")
@login_required
def api_collect_job_status():
    try:
        rows = sb.table("jobs").select("*").order("id", desc=True).limit(1).execute().data
        if not rows:
            return jsonify({})
        j = rows[0]
        return jsonify({"id": j["id"], "status": j["status"], "stats": j.get("stats"),
                        "progress": j.get("progress"),
                        "error_detail": j.get("error_detail"),
                        "genre": j["genre_slug"], "created_at": str(j["created_at"])})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/build", methods=["POST"])
@login_required
def api_build():
    data = request.get_json(silent=True) or {}
    raw = data.get("tracks", "")
    genre = data.get("genre")
    name = data.get("name", "Meu Set")
    spotify_url = (data.get("spotify_url") or "").strip()
    if not genre:
        return jsonify({"error": "genre obrigatório"}), 400
    tracks = [line.strip() for line in raw.splitlines() if line.strip()]
    if spotify_url:
        try:
            token = get_valid_token(session)
            if token:
                pl = tracks_from_playlist_with_token(token, spotify_url)
            else:
                # tenta Client Credentials (só playlists públicas muito raras)
                try:
                    pl = enricher.tracks_from_playlist(spotify_url)
                except Exception as e2:
                    raise Exception(
                        "não consegui ler a playlist. Se forcurada do Spotify ou de "
                        "outro utilizador, a app tem de estar em 'Extended Quota Mode' "
                        "(Dashboard Spotify > Settings > desmarcar Development Mode). "
                        "Ou usa uma playlist SUA. Erro original: " + str(e2))
            tracks = pl + tracks  # playlist primeiro, depois manuais
        except Exception as e:
            return jsonify({"error": f"Playlist Spotify: {e}"}), 400
    if not tracks:
        return jsonify({"error": "coloca tracks ou um link de playlist Spotify"}), 400
    try:
        result = curator.build_set(tracks, genre, list_name=name, save_to_db=True)
        return jsonify({
            "output_text": result["output_text"],
            "proposed_set_id": result["proposed_set_id"],
            "suggestions": result["suggestions"],
            "tracks_enriched": [
                {k: t.get(k) for k in ("artist", "title", "bpm", "camelot_key",
                                       "energy", "confidence", "typical_zone")}
                for t in result["tracks_enriched"]
            ],
        })
    except Exception as e:
        logger.exception("build falhou")
        return jsonify({"error": str(e)}), 500

@app.route("/api/proposed")
@login_required
def api_proposed():
    try:
        rows = sb.table("proposed_sets").select(
            "id,created_at,genre_id,raw_output,user_lists(name)"
        ).order("created_at", desc=True).limit(50).execute().data
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/proposed/<int:pid>")
@login_required
def api_proposed_detail(pid):
    try:
        r = sb.table("proposed_sets").select("*").eq("id", pid).execute().data
        if not r:
            return jsonify({"error": "não encontrado"}), 404
        tracks = sb.table("proposed_set_tracks").select(
            "position,track_id,is_suggestion,confidence"
        ).eq("proposed_set_id", pid).order("position").execute().data
        return jsonify({"set": r[0], "tracks": tracks})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/who")
@login_required
def api_who():
    return jsonify({"user": APP_USER, "llm": os.environ.get("LLM_PROVIDER", "groq")})


@app.route("/api/graph")
@login_required
def api_graph():
    """Nós de maior grau (mais conectados) num género — para explorar."""
    genre = request.args.get("genre")
    try:
        g = graph.get_top_nodes(genre_id=int(genre) if genre else None, limit=30)
        return jsonify(g)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/graph/edges")
@login_required
def api_graph_edges():
    """Arestas do grafo (para visualização de rede)."""
    genre = request.args.get("genre")
    try:
        q = sb.table("transitions").select(
            "track_from_id,track_to_id,genre_id")
        if genre:
            q = q.eq("genre_id", int(genre))
        rows = q.limit(2000).execute().data
        # reduz à maior componente conexa (top N nós por grau)
        from collections import Counter
        deg = Counter()
        for r in rows:
            deg[r["track_from_id"]] += 1
            deg[r["track_to_id"]] += 1
        top = set([n for n, _ in deg.most_common(40)])
        edges = [{"from": r["track_from_id"], "to": r["track_to_id"]}
                 for r in rows
                 if r["track_from_id"] in top and r["track_to_id"] in top]
        # labels dos nós
        nodes = {}
        for tid in top:
            t = graph.get_track_data(tid)
            if t:
                nodes[tid] = f"{t['artist']} - {t['title']}"
        return jsonify({"nodes": nodes, "edges": edges})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/set/<int:pid>/reorder", methods=["POST"])
@login_required
def api_set_reorder(pid):
    """Reordena/apaga faixas de um set proposto.
    body: {"order": [track_id, ...]}  (omitir = apagar; null = manter)"""
    data = request.get_json(silent=True) or {}
    order = data.get("order")  # lista de track_id na nova ordem
    try:
        # apaga as tracks atuais e re-insere na nova ordem
        sb.table("proposed_set_tracks").delete().eq("proposed_set_id", pid).execute()
        if order:
            rows = [{"proposed_set_id": pid, "position": i + 1,
                     "track_id": tid, "is_suggestion": False, "confidence": "high"}
                    for i, tid in enumerate(order)]
            sb.table("proposed_set_tracks").insert(rows).execute()
        return jsonify({"ok": True, "count": len(order) if order else 0})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/set/<int:pid>/output", methods=["POST"])
@login_required
def api_set_output(pid):
    """Atualiza o texto da tracklist (raw_output) após edição manual."""
    data = request.get_json(silent=True) or {}
    out = data.get("output", "")
    try:
        sb.table("proposed_sets").update({"raw_output": out}).eq("id", pid).execute()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---- Spotify OAuth (leitura de playlists do user) ----
@app.route("/api/spotify/login")
@login_required
def api_spotify_login():
    import secrets
    state = secrets.token_urlsafe(16)
    session["spotify_state"] = state
    return jsonify({"url": authorize_url(state)})


@app.route("/api/spotify/callback")
def api_spotify_callback():
    code = request.args.get("code")
    state = request.args.get("state")
    if not code:
        return redirect("/login")
    if state != session.get("spotify_state"):
        return redirect("/?spotify=erro")
    try:
        tok = exchange_code(code)
        tok["expires_at"] = int(time.time()) + tok.get("expires_in", 3600)
        session["spotify_token"] = tok
    except Exception as e:
        logger.error(f"spotify callback erro: {e}")
    return redirect("/?spotify=ok")


@app.route("/api/spotify/status")
@login_required
def api_spotify_status():
    t = get_valid_token(session)
    return jsonify({"connected": bool(t)})



# =====================================================================
def asyncio_run(coro):
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  DJ Set Curator → http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
