-- =====================================================
-- TSun Token Fetcher - Neon Database Schema
-- =====================================================
-- This schema creates tables for storing execution history
-- Run this script in your Neon PostgreSQL database console
-- =====================================================

-- =====================================================
-- Table: runs
-- Stores metadata for each execution run
-- =====================================================
CREATE TABLE IF NOT EXISTS runs (
    id SERIAL PRIMARY KEY,
    run_number INT NOT NULL,                    -- Sequential run number (e.g., #1, #2, #3)
    started_at TIMESTAMP NOT NULL,              -- When the run started
    completed_at TIMESTAMP,                     -- When the run completed (NULL if still running)
    total_duration_seconds FLOAT,               -- Total duration of the run in seconds
    status VARCHAR(20) DEFAULT 'running',       -- Status: 'running', 'completed', 'timeout', 'error'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for efficient history queries (sorted by most recent first)
CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at DESC);

-- Index for querying runs by status
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);

-- =====================================================
-- Table: region_results
-- Stores per-region results for each run
-- =====================================================
CREATE TABLE IF NOT EXISTS region_results (
    id SERIAL PRIMARY KEY,
    run_id INT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,  -- Foreign key to runs table
    region VARCHAR(10) NOT NULL,                -- Region code (e.g., 'BD', 'IND', 'PK')
    total_accounts INT NOT NULL,                -- Total number of accounts processed
    success_count INT NOT NULL,                 -- Number of successful token fetches
    failed_count INT NOT NULL,                  -- Number of failed attempts
    timed_out_count INT DEFAULT 0,              -- Number of timed-out requests
    success_rate FLOAT NOT NULL,                -- Success percentage (0-100)
    duration_seconds FLOAT NOT NULL,            -- Duration for this region in seconds
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for efficient join operations when fetching run history
CREATE INDEX IF NOT EXISTS idx_region_results_run_id ON region_results(run_id);

-- Index for querying results by region
CREATE INDEX IF NOT EXISTS idx_region_results_region ON region_results(region);

-- =====================================================
-- Verification Queries
-- =====================================================
-- After running this schema, verify with these queries:
--
-- 1. Check if tables were created:
--    SELECT table_name FROM information_schema.tables 
--    WHERE table_schema = 'public' AND table_name IN ('runs', 'region_results');
--
-- 2. Check if indexes were created:
--    SELECT indexname FROM pg_indexes 
--    WHERE tablename IN ('runs', 'region_results');
--
-- 3. View table structures:
--    \d runs
--    \d region_results
--
-- =====================================================

-- =====================================================
-- Sample Data (Optional - for testing)
-- =====================================================
-- Uncomment to insert test data:
/*
INSERT INTO runs (run_number, started_at, completed_at, total_duration_seconds, status)
VALUES (1, NOW() - INTERVAL '1 hour', NOW() - INTERVAL '56 minutes', 240, 'completed');

INSERT INTO region_results (run_id, region, total_accounts, success_count, failed_count, timed_out_count, success_rate, duration_seconds)
VALUES 
    (1, 'BD', 139, 139, 0, 0, 100.0, 80),
    (1, 'IND', 99, 99, 0, 0, 100.0, 75),
    (1, 'PK', 1000, 966, 34, 0, 96.6, 85);
*/

-- =====================================================
-- Cleanup Queries (Use with caution!)
-- =====================================================
-- To reset the database:
-- DROP TABLE IF EXISTS region_results CASCADE;
-- DROP TABLE IF EXISTS runs CASCADE;
-- =====================================================