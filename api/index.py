"""Entrypoint para Vercel.
O Vercel Python runtime importa o WSGI `app` a partir de app.py (raiz do repo)."""
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import app  # noqa: E402

# Vercel espera o objeto WSGI chamado `app` — já o temos.
