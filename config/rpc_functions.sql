-- ============================================================
-- Funções RPC para o Grafo de Transições
-- Execute no SQL Editor do Supabase APÓS o schema.sql
-- ============================================================

-- Função: top N sucessores de uma track em um gênero
CREATE OR REPLACE FUNCTION get_successors(
    p_track_id  INTEGER,
    p_genre_id  INTEGER,
    p_top_n     INTEGER DEFAULT 15
)
RETURNS TABLE (
    id           INTEGER,
    artist       TEXT,
    title        TEXT,
    bpm          FLOAT,
    camelot_key  TEXT,
    energy       FLOAT,
    danceability FLOAT,
    spotify_id   TEXT,
    confidence   TEXT,
    count        BIGINT
)
LANGUAGE sql STABLE AS $$
    SELECT
        t.id,
        t.artist,
        t.title,
        t.bpm,
        t.camelot_key,
        t.energy,
        t.danceability,
        t.spotify_id,
        t.confidence,
        COUNT(*) AS count
    FROM transitions tr
    JOIN tracks t ON t.id = tr.track_to_id
    WHERE tr.track_from_id = p_track_id
      AND tr.genre_id = p_genre_id
    GROUP BY t.id, t.artist, t.title, t.bpm, t.camelot_key,
             t.energy, t.danceability, t.spotify_id, t.confidence
    ORDER BY count DESC
    LIMIT p_top_n;
$$;

-- Função: top N predecessores de uma track em um gênero
CREATE OR REPLACE FUNCTION get_predecessors(
    p_track_id  INTEGER,
    p_genre_id  INTEGER,
    p_top_n     INTEGER DEFAULT 15
)
RETURNS TABLE (
    id           INTEGER,
    artist       TEXT,
    title        TEXT,
    bpm          FLOAT,
    camelot_key  TEXT,
    energy       FLOAT,
    danceability FLOAT,
    spotify_id   TEXT,
    confidence   TEXT,
    count        BIGINT
)
LANGUAGE sql STABLE AS $$
    SELECT
        t.id,
        t.artist,
        t.title,
        t.bpm,
        t.camelot_key,
        t.energy,
        t.danceability,
        t.spotify_id,
        t.confidence,
        COUNT(*) AS count
    FROM transitions tr
    JOIN tracks t ON t.id = tr.track_from_id
    WHERE tr.track_to_id = p_track_id
      AND tr.genre_id = p_genre_id
    GROUP BY t.id, t.artist, t.title, t.bpm, t.camelot_key,
             t.energy, t.danceability, t.spotify_id, t.confidence
    ORDER BY count DESC
    LIMIT p_top_n;
$$;

-- Função: estatísticas de posição típica de uma track
CREATE OR REPLACE FUNCTION get_track_position_stats(
    p_track_id INTEGER,
    p_genre_id INTEGER DEFAULT NULL
)
RETURNS TABLE (
    avg_position_pct FLOAT,
    appearances      BIGINT
)
LANGUAGE sql STABLE AS $$
    SELECT
        AVG(tr.position_from::FLOAT / NULLIF(s.track_count, 0)) AS avg_position_pct,
        COUNT(*)                                                  AS appearances
    FROM transitions tr
    JOIN sets s ON s.id = tr.set_id
    WHERE tr.track_from_id = p_track_id
      AND (p_genre_id IS NULL OR tr.genre_id = p_genre_id)
      AND s.track_count > 0;
$$;
