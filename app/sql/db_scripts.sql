-- Table: public.users

-- DROP TABLE IF EXISTS public.users;

-- CREATE TABLE IF NOT EXISTS public.users
-- (
--     id integer NOT NULL DEFAULT nextval('users_id_seq'::regclass),
--     email character varying(255) COLLATE pg_catalog."default",
--     hashed_password character varying(255) COLLATE pg_catalog."default",
--     is_active boolean,
--     otp_secret character varying(255) COLLATE pg_catalog."default",
--     otp_created_at timestamp with time zone,
--     CONSTRAINT users_pkey PRIMARY KEY (id),
--     CONSTRAINT users_email_key UNIQUE (email)
-- )

-- CREATE TABLE IF NOT EXISTS public.users
-- (
--     id UUID NOT NULL,
--     email VARCHAR,
--     hashed_password VARCHAR,
--     is_active BOOLEAN,
--     otp_secret VARCHAR,
--     otp_created_at TIMESTAMPTZ DEFAULT now(),
--     first_name VARCHAR(255),
--     last_name VARCHAR(255),
--     CONSTRAINT users_pkey PRIMARY KEY (id)
-- );
 
-- CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email
--     ON public.users (email);
 
-- CREATE INDEX IF NOT EXISTS ix_users_id
--     ON public.users (id);

CREATE TABLE threads (
    thread_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    thread_name VARCHAR(255) NOT NULL,
    conversation_ids UUID[] NOT NULL DEFAULT '{}'
);

CREATE TABLE conversations (
    conversation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id UUID NOT NULL REFERENCES threads(thread_id),
    version INT NOT NULL,
    diagram_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_thread_version UNIQUE (thread_id, version)
);