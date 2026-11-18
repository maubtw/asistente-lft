CREATE EXTENSION IF NOT EXISTS vector;

-- Un registro por chunk. Con chunking por artículo, chunk = artículo.
-- `estrategia` permite guardar varias estrategias de chunking y compararlas en la evaluación.
CREATE TABLE IF NOT EXISTS articulos (
    id              SERIAL PRIMARY KEY,
    estrategia      TEXT NOT NULL DEFAULT 'by_article',   -- 'by_article' | 'fixed_chunks'
    ley             TEXT NOT NULL DEFAULT 'LFT',
    articulo        TEXT,                                 -- '76', '39-A', '3 Bis' (NULL en chunks fijos que crucen artículos)
    articulos_en_chunk TEXT[] DEFAULT '{}',               -- para chunks fijos: qué artículos contiene
    titulo          TEXT,
    capitulo        TEXT,
    texto           TEXT NOT NULL,
    referencias     TEXT[] DEFAULT '{}',
    derogado        BOOLEAN DEFAULT FALSE,
    es_transitorio  BOOLEAN DEFAULT FALSE,
    fecha_reforma   DATE,
    embedding       vector(1024),                          -- bge-m3; cambia si cambias de modelo
    tsv             tsvector GENERATED ALWAYS AS (to_tsvector('spanish', coalesce(texto, ''))) STORED
);

CREATE INDEX IF NOT EXISTS idx_articulos_embedding ON articulos USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_articulos_tsv ON articulos USING gin (tsv);
CREATE INDEX IF NOT EXISTS idx_articulos_lookup ON articulos (estrategia, ley, articulo);
