CREATE EXTENSION IF NOT EXISTS pgcrypto;

DROP TABLE IF EXISTS conversations;
DROP TABLE IF EXISTS threads;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    email VARCHAR(255),
    hashed_password VARCHAR(255),
    is_active BOOLEAN DEFAULT FALSE,
    otp_secret VARCHAR(255),
    otp_created_at TIMESTAMPTZ DEFAULT NOW(),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    CONSTRAINT users_pkey PRIMARY KEY (id),
    CONSTRAINT users_email_key UNIQUE (email)
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email
    ON users (email);

CREATE INDEX IF NOT EXISTS ix_users_id
    ON users (id);

CREATE TABLE threads (
    thread_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    thread_name VARCHAR(255) NOT NULL,
    conversation_ids UUID[] NOT NULL DEFAULT '{}'::UUID[],
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE conversations (
    conversation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id UUID NOT NULL REFERENCES threads(thread_id),
    version INT NOT NULL,
    diagram_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_thread_version UNIQUE (thread_id, version)
);
