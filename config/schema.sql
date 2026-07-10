-- ============================================================
-- DJ Set Curator — Schema Supabase
-- Execute no SQL Editor do seu projeto Supabase
-- ============================================================

-- 1. Gêneros configuráveis
CREATE TABLE IF NOT EXISTS genres (
    id          SERIAL PRIMARY KEY,
    slug        TEXT UNIQUE NOT NULL,   -- ex: 'goa-psy-trance'
    name        TEXT NOT NULL,          -- ex: 'Goa / Psy-Trance'
    active      BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Sets coletados do 1001tracklists
CREATE TABLE IF NOT EXISTS sets (
    id              SERIAL PRIMARY KEY,
    external_id     TEXT UNIQUE NOT NULL,  -- slug da URL ex: '2tlglsf9'
    url             TEXT UNIQUE NOT NULL,
    dj_name         TEXT,
    set_title       TEXT,
    genre_id        INTEGER REFERENCES genres(id),
    set_date        DATE,
    track_count     INTEGER,
    collected_at    TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Tracks com dados acústicos
CREATE TABLE IF NOT EXISTS tracks (
    id              SERIAL PRIMARY KEY,
    artist          TEXT NOT NULL,
    title           TEXT NOT NULL,
    spotify_id      TEXT,               -- null se não encontrado
    bpm             FLOAT,
    camelot_key     TEXT,               -- ex: '9A', '11B'
    energy          FLOAT,              -- 0.0 a 1.0
    danceability    FLOAT,              -- 0.0 a 1.0
    source          TEXT DEFAULT 'unknown', -- spotify | tunebat | manual | unknown
    confidence      TEXT DEFAULT 'low',     -- high | medium | low
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(artist, title)
);

-- 4. Grafo de transições (coração do sistema)
CREATE TABLE IF NOT EXISTS transitions (
    id              SERIAL PRIMARY KEY,
    set_id          INTEGER REFERENCES sets(id) ON DELETE CASCADE,
    genre_id        INTEGER REFERENCES genres(id),
    track_from_id   INTEGER REFERENCES tracks(id),
    track_to_id     INTEGER REFERENCES tracks(id),
    position_from   INTEGER,            -- posição no set original
    position_to     INTEGER,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Listas do usuário
CREATE TABLE IF NOT EXISTS user_lists (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    genre_id    INTEGER REFERENCES genres(id),
    spotify_url TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 6. Tracks de cada lista
CREATE TABLE IF NOT EXISTS user_list_tracks (
    id              SERIAL PRIMARY KEY,
    list_id         INTEGER REFERENCES user_lists(id) ON DELETE CASCADE,
    track_id        INTEGER REFERENCES tracks(id),
    manual_input    TEXT,               -- texto original se track manual
    order_hint      INTEGER,            -- posição sugerida pelo usuário (opcional)
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 7. Sets propostos pelo motor
CREATE TABLE IF NOT EXISTS proposed_sets (
    id              SERIAL PRIMARY KEY,
    user_list_id    INTEGER REFERENCES user_lists(id),
    genre_id        INTEGER REFERENCES genres(id),
    approved        BOOLEAN,            -- null=não avaliado, true=aprovado, false=rejeitado
    raw_output      TEXT,               -- output completo do Gemini
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 8. Tracks de cada set proposto
CREATE TABLE IF NOT EXISTS proposed_set_tracks (
    id                  SERIAL PRIMARY KEY,
    proposed_set_id     INTEGER REFERENCES proposed_sets(id) ON DELETE CASCADE,
    position            INTEGER NOT NULL,
    track_id            INTEGER REFERENCES tracks(id),
    is_suggestion       BOOLEAN DEFAULT FALSE,  -- veio do grafo, não da lista
    confidence          TEXT,
    transition_score    FLOAT,
    transition_note     TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- 9. Pedidos de carga (jobs) — criados pela app Vercel, processados server-side
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

-- ============================================================
CREATE INDEX IF NOT EXISTS idx_transitions_from     ON transitions(track_from_id, genre_id);
CREATE INDEX IF NOT EXISTS idx_transitions_to       ON transitions(track_to_id, genre_id);
CREATE INDEX IF NOT EXISTS idx_transitions_genre    ON transitions(genre_id);
CREATE INDEX IF NOT EXISTS idx_sets_genre           ON sets(genre_id);
CREATE INDEX IF NOT EXISTS idx_tracks_spotify       ON tracks(spotify_id);
CREATE INDEX IF NOT EXISTS idx_tracks_artist_title  ON tracks(artist, title);

-- ============================================================
-- Dados iniciais: gêneros do 1001tracklists
-- ============================================================
INSERT INTO genres (slug, name, active) VALUES
    ('goa-psy-trance',          'Goa / Psy-Trance',             TRUE),
    ('techno',                   'Techno',                       TRUE),
    ('tech-house',               'Tech House',                   TRUE),
    ('house',                    'House',                        TRUE),
    ('deep-house',               'Deep House',                   TRUE),
    ('progressive-house',        'Progressive House',            TRUE),
    ('melodic-house-techno',     'Melodic House / Techno',       TRUE),
    ('minimal-deep-tech',        'Minimal / Deep Tech',          TRUE),
    ('trance',                   'Trance',                       TRUE),
    ('drum-bass',                'Drum & Bass',                  TRUE),
    ('dubstep',                  'Dubstep',                      TRUE),
    ('hard-dance',               'Hard Dance',                   TRUE),
    ('bass-house',               'Bass House',                   TRUE),
    ('breaks',                   'Breaks',                       TRUE),
    ('afro-house',               'Afro House',                   TRUE),
    ('indie-dance',              'Indie Dance',                  TRUE),
    ('electronica',              'Electronica',                  TRUE),
    ('organic-house-downtempo',  'Organic House / Downtempo',    TRUE),
    ('mainstage',                'Mainstage',                    TRUE)
ON CONFLICT (slug) DO NOTHING;
