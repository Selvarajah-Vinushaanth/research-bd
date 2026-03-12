-- ============================================
-- Database Initialization Script
-- AI Research Assistant
-- ============================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create custom functions

-- Function: cosine distance search
CREATE OR REPLACE FUNCTION match_chunks(
    query_embedding vector(384),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 10,
    filter_paper_id text DEFAULT NULL
)
RETURNS TABLE (
    id text,
    paper_id text,
    content text,
    chunk_index int,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        pc.id,
        pc.paper_id,
        pc.content,
        pc."chunkIndex",
        1 - (pc.embedding <=> query_embedding) AS similarity
    FROM "PaperChunk" pc
    WHERE
        pc.embedding IS NOT NULL
        AND (filter_paper_id IS NULL OR pc.paper_id = filter_paper_id)
        AND 1 - (pc.embedding <=> query_embedding) > match_threshold
    ORDER BY pc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Function: find related papers by average chunk similarity
CREATE OR REPLACE FUNCTION find_related_papers(
    source_paper_id text,
    match_count int DEFAULT 5
)
RETURNS TABLE (
    paper_id text,
    title text,
    similarity float
)
LANGUAGE plpgsql
AS $$
DECLARE
    avg_embedding vector(384);
BEGIN
    -- Compute average embedding for the source paper
    SELECT AVG(pc.embedding) INTO avg_embedding
    FROM "PaperChunk" pc
    WHERE pc.paper_id = source_paper_id AND pc.embedding IS NOT NULL;

    IF avg_embedding IS NULL THEN
        RETURN;
    END IF;

    RETURN QUERY
    SELECT
        p.id AS paper_id,
        p.title,
        1 - (AVG(pc.embedding) <=> avg_embedding) AS similarity
    FROM "Paper" p
    JOIN "PaperChunk" pc ON pc.paper_id = p.id
    WHERE
        p.id != source_paper_id
        AND pc.embedding IS NOT NULL
    GROUP BY p.id, p.title
    ORDER BY AVG(pc.embedding) <=> avg_embedding
    LIMIT match_count;
END;
$$;

-- Create indexes for performance (supplement Prisma-managed indexes)
-- These are vector-specific indexes that Prisma doesn't natively support

-- IVFFlat index for approximate nearest neighbour search on chunk embeddings
-- Lists = sqrt(number_of_rows), start with 100 and adjust
-- Note: This index is created after data is loaded for best performance
-- Run this after initial data population:
-- CREATE INDEX IF NOT EXISTS idx_chunk_embedding_ivfflat
--     ON "PaperChunk"
--     USING ivfflat (embedding vector_cosine_ops)
--     WITH (lists = 100);

-- HNSW index (alternative, better recall, more memory)
CREATE INDEX IF NOT EXISTS idx_chunk_embedding_hnsw
    ON "PaperChunk"
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Trigram indexes for full-text search
CREATE INDEX IF NOT EXISTS idx_paper_title_trgm
    ON "Paper"
    USING gin (title gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_paper_abstract_trgm
    ON "Paper"
    USING gin (abstract gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_chunk_content_trgm
    ON "PaperChunk"
    USING gin (content gin_trgm_ops);

-- Full-text search index
CREATE INDEX IF NOT EXISTS idx_paper_fts
    ON "Paper"
    USING gin (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(abstract, '')));

-- Composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_paper_user_status
    ON "Paper" ("userId", status);

CREATE INDEX IF NOT EXISTS idx_paper_user_created
    ON "Paper" ("userId", "createdAt" DESC);

CREATE INDEX IF NOT EXISTS idx_chunk_paper_index
    ON "PaperChunk" (paper_id, "chunkIndex");

CREATE INDEX IF NOT EXISTS idx_chat_message_session_created
    ON "ChatMessage" ("sessionId", "createdAt");

CREATE INDEX IF NOT EXISTS idx_activity_user_created
    ON "ActivityLog" ("userId", "createdAt" DESC);

-- Materialized view for paper statistics (refresh periodically)
CREATE MATERIALIZED VIEW IF NOT EXISTS paper_stats AS
SELECT
    p."userId",
    COUNT(DISTINCT p.id) AS total_papers,
    COUNT(DISTINCT CASE WHEN p.status = 'COMPLETED' THEN p.id END) AS processed_papers,
    COUNT(DISTINCT cs.id) AS total_sessions,
    COUNT(DISTINCT rn.id) AS total_notes,
    COUNT(DISTINCT c.id) AS total_collections,
    MAX(p."createdAt") AS last_upload
FROM "Paper" p
LEFT JOIN "ChatSession" cs ON cs."userId" = p."userId"
LEFT JOIN "ResearchNote" rn ON rn."userId" = p."userId"
LEFT JOIN "Collection" c ON c."userId" = p."userId"
GROUP BY p."userId";

CREATE UNIQUE INDEX IF NOT EXISTS idx_paper_stats_user ON paper_stats ("userId");

-- Function to refresh materialized views
CREATE OR REPLACE FUNCTION refresh_paper_stats()
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY paper_stats;
END;
$$;

-- Grant necessary permissions (adjust role name as needed)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO app_user;

RAISE NOTICE 'Database initialization completed successfully.';
