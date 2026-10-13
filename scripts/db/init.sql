-- Local/dev database provisioning. Idempotent; run as a superuser:
--   psql -v ON_ERROR_STOP=1 -d postgres -f scripts/db/init.sql
-- Also mounted into the optional docker-compose Postgres as an init script.
--
-- Roles (see docs/local-setup.md):
--   vp_migrator  owns the databases and every table; runs Alembic. Table owners bypass RLS
--                unless the table uses FORCE ROW LEVEL SECURITY, so the app never uses this role.
--   vp_app       what the API and workers connect as. Not superuser, not owner, NOBYPASSRLS,
--                no DDL. Only gets DML on tables vp_migrator creates.
--   vp_resolver  NOLOGIN, BYPASSRLS. Owns only the SECURITY DEFINER resolver functions that map
--                one key (dialed number, webhook token) to an org_id (decision 0005). Nobody can
--                log in as it; vp_migrator may SET ROLE to it only to assign function ownership.
-- Passwords below are for local development only. Real environments use the secrets manager.

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'vp_migrator') THEN
    CREATE ROLE vp_migrator;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'vp_app') THEN
    CREATE ROLE vp_app;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'vp_resolver') THEN
    CREATE ROLE vp_resolver;
  END IF;
END
$$;

ALTER ROLE vp_migrator WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  PASSWORD 'vp_migrator_local_dev';
ALTER ROLE vp_app WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT
  PASSWORD 'vp_app_local_dev';
ALTER ROLE vp_resolver WITH NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS
  PASSWORD NULL;
-- ALTER FUNCTION ... OWNER TO vp_resolver requires vp_migrator to be able to SET ROLE vp_resolver.
-- INHERIT FALSE: vp_migrator does not get vp_resolver's privileges implicitly (and BYPASSRLS is
-- never inherited). vp_app is never granted vp_resolver.
GRANT vp_resolver TO vp_migrator WITH INHERIT FALSE, SET TRUE;

SELECT format('CREATE DATABASE %I OWNER vp_migrator', db)
FROM unnest(ARRAY['vp_dev', 'vp_test']) AS db
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = db)
\gexec

-- Per-database privileges. Repeated for each database (psql has no loops over \c).
\c vp_dev
ALTER DATABASE vp_dev OWNER TO vp_migrator;
REVOKE ALL ON DATABASE vp_dev FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE vp_dev TO vp_app;
-- CREATE: Postgres requires it of a function's new owner (ALTER FUNCTION ... OWNER TO).
GRANT USAGE, CREATE ON SCHEMA public TO vp_resolver;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO vp_app;
ALTER DEFAULT PRIVILEGES FOR ROLE vp_migrator IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO vp_app;
ALTER DEFAULT PRIVILEGES FOR ROLE vp_migrator IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO vp_app;

\c vp_test
ALTER DATABASE vp_test OWNER TO vp_migrator;
REVOKE ALL ON DATABASE vp_test FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE vp_test TO vp_app;
-- CREATE: Postgres requires it of a function's new owner (ALTER FUNCTION ... OWNER TO).
GRANT USAGE, CREATE ON SCHEMA public TO vp_resolver;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO vp_app;
ALTER DEFAULT PRIVILEGES FOR ROLE vp_migrator IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO vp_app;
ALTER DEFAULT PRIVILEGES FOR ROLE vp_migrator IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO vp_app;
