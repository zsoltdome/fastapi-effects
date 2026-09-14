\set ON_ERROR_STOP on

SELECT 'CREATE ROLE mergen_migration LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mergen_migration') \gexec
SELECT 'CREATE ROLE mergen_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mergen_app') \gexec
SELECT 'CREATE ROLE mergen_relay LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mergen_relay') \gexec

ALTER ROLE mergen_migration PASSWORD :'migration_password';
ALTER ROLE mergen_app PASSWORD :'application_password';
ALTER ROLE mergen_relay PASSWORD :'relay_password';
GRANT CONNECT ON DATABASE mergen TO mergen_migration, mergen_app, mergen_relay;
GRANT CREATE ON DATABASE mergen TO mergen_migration;
