-- ============================================================
-- Criar a tabela `jobs` (pedidos de carga do 1001tracklists)
-- Cole isto na Supabase SQL Editor (https://app.supotify.com/project/<teu>/sql)
-- uma única vez. O worker (python worker.py) e a app usam-na.
-- ============================================================
CREATE TABLE IF NOT EXISTS jobs (
    id            SERIAL PRIMARY KEY,
    genre_slug   TEXT NOT NULL,
    max_sets      INTEGER NOT NULL DEFAULT 50,
    status        TEXT DEFAULT 'pending',   -- pending | running | done | error
    stats         JSONB,
    error_detail  TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
