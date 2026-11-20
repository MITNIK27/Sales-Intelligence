-- Phase 8a: a least-privilege login for the API and the worker.
--
-- Two roles:
--   * the schema owner (locally `sales_intel`) runs migrations and maintenance scripts
--     (MIGRATION_DATABASE_URL, and DATABASE_URL while running scripts/reset_test_data.py);
--   * `sales_intel_app` is what the running app uses (DATABASE_URL): it can read and write rows,
--     but cannot create, alter, drop or truncate anything.
--
-- Run it as the schema owner, against the database it should grant on. Safe to run again (for
-- example after a password change). Locally, from the repo root, in Command Prompt:
--   docker exec -i infra-postgres-pgvector-1 psql -U sales_intel -d sales_intel ^
--       -v app_password="choose-a-password" < infra\db\create_app_role.sql
-- Then set DATABASE_URL to postgresql+asyncpg://sales_intel_app:<password>@localhost:5435/sales_intel
-- and MIGRATION_DATABASE_URL to the owner's URL.

\set ON_ERROR_STOP on

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sales_intel_app') THEN
        CREATE ROLE sales_intel_app LOGIN;
    END IF;
END $$;

ALTER ROLE sales_intel_app WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'app_password';

GRANT CONNECT ON DATABASE :"DBNAME" TO sales_intel_app;
GRANT USAGE ON SCHEMA public TO sales_intel_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- Everything that exists now...
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO sales_intel_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sales_intel_app;

-- ...and every table or sequence the owner's migrations create later.
ALTER DEFAULT PRIVILEGES FOR ROLE :"USER" IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sales_intel_app;
ALTER DEFAULT PRIVILEGES FOR ROLE :"USER" IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO sales_intel_app;
