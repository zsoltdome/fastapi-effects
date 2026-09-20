\set ON_ERROR_STOP on

SELECT 'CREATE ROLE fastapi_effects_migration LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fastapi_effects_migration') \gexec
SELECT 'CREATE ROLE fastapi_effects_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fastapi_effects_app') \gexec
SELECT 'CREATE ROLE fastapi_effects_relay LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fastapi_effects_relay') \gexec

ALTER ROLE fastapi_effects_migration PASSWORD :'migration_password';
ALTER ROLE fastapi_effects_app PASSWORD :'application_password';
ALTER ROLE fastapi_effects_relay PASSWORD :'relay_password';
GRANT CONNECT ON DATABASE fastapi_effects TO fastapi_effects_migration, fastapi_effects_app, fastapi_effects_relay;
GRANT CREATE ON DATABASE fastapi_effects TO fastapi_effects_migration;
