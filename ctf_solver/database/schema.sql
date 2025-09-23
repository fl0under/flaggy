CREATE TABLE challenges (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    binary_path TEXT NOT NULL,
    flag_format TEXT DEFAULT 'picoCTF{.*}',
    description TEXT,
    category TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE attempts (
    id SERIAL PRIMARY KEY,
    challenge_id INT REFERENCES challenges(id),
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    flag TEXT,
    total_steps INT DEFAULT 0,
    container_name TEXT,
    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    error_message TEXT
);

CREATE TABLE steps (
    id SERIAL PRIMARY KEY,
    attempt_id INT REFERENCES attempts(id),
    step_num INT NOT NULL,
    action JSONB NOT NULL,
    output BYTEA,  -- Changed to BYTEA for binary-safe storage
    exit_code INT,
    tool TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    execution_time_ms INT
);

-- Indexes
CREATE INDEX idx_attempts_status ON attempts(status);
CREATE INDEX idx_attempts_challenge ON attempts(challenge_id);
CREATE INDEX idx_steps_attempt ON steps(attempt_id);
CREATE INDEX idx_steps_step_num ON steps(attempt_id, step_num);

-- Add unique constraint to prevent duplicate step numbers per attempt
CREATE UNIQUE INDEX idx_steps_unique ON steps(attempt_id, step_num);


