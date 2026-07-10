-- ============================================================
-- Criar a tabela `jobs` (pedidos de carga do Spotify)
-- Cole isto na Supabase SQL Editor (https://app.supabase.com/project/<teu>/sql)
-- uma única vez. A app usa-a para carga automática de sets via Spotify API.
-- ============================================================
CREATE TABLE IF NOT EXISTS jobs (
    id            SERIAL PRIMARY KEY,
    genre_slug   TEXT NOT NULL,
    max_sets      INTEGER NOT NULL DEFAULT 10,
    status        TEXT DEFAULT 'running',   -- running | done | error
    progress      JSONB,                     -- {playlists:[ids], idx, sets_done}
    stats         JSONB,
    error_detail  TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
