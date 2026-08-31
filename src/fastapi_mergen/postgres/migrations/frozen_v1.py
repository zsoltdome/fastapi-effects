"""Immutable schema and security definitions used only by revisions 0001-0005.

Do not update these definitions when runtime ORM models or installers change. Add a new
revision with its own frozen definitions instead.
"""

import re
from dataclasses import dataclass
from typing import Any

SCHEMA_V1 = "fastapi_mergen"
TENANT_EXPRESSION_V1 = "tenant_id = nullif(current_setting('mergen.tenant_id', true), '')::uuid"
_ROLE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


@dataclass(frozen=True, slots=True)
class RoleNamesV1:
    migration: str
    application: str
    relay: str


def role_names_v1(config: Any) -> RoleNamesV1:
    configured = config.attributes.get("runtime_roles")
    if configured is None:
        result = RoleNamesV1("mergen_migration", "mergen_app", "mergen_relay")
    else:
        try:
            result = RoleNamesV1(
                migration=configured.migration,
                application=configured.application,
                relay=configured.relay,
            )
        except (AttributeError, TypeError) as exc:
            raise TypeError("runtime_roles must provide migration/application/relay") from exc
    if any(
        _ROLE.fullmatch(role) is None
        for role in (result.migration, result.application, result.relay)
    ):
        raise TypeError("runtime_roles contains an invalid PostgreSQL identifier")
    if len({result.migration, result.application, result.relay}) != 3:
        raise TypeError("runtime_roles values must be distinct")
    return result


def create_role_sql_v1(role: str) -> str:
    if _ROLE.fullmatch(role) is None:
        raise TypeError("runtime role is invalid")
    return (
        "DO $role$ BEGIN "
        f"IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN "
        f"CREATE ROLE {role} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
        "NOINHERIT NOBYPASSRLS; END IF; END $role$"
    )


CORE_TABLE_NAMES_V1 = ("schema_revision", "events", "deliveries", "attempts")
CORE_DDL_V1 = (
    """
    CREATE TABLE fastapi_mergen.schema_revision (
        component VARCHAR(128) NOT NULL,
        revision INTEGER NOT NULL,
        installed_at TIMESTAMP WITH TIME ZONE NOT NULL,
        CONSTRAINT pk_schema_revision PRIMARY KEY (component),
        CONSTRAINT ck_schema_revision_revision_nonnegative CHECK (revision >= 0)
    )
    """,
    """
    CREATE TABLE fastapi_mergen.events (
        tenant_id UUID NOT NULL, event_id UUID NOT NULL,
        event_type VARCHAR(128) NOT NULL, event_version INTEGER NOT NULL,
        canonical_version INTEGER NOT NULL, payload JSONB NOT NULL,
        payload_canonical BYTEA NOT NULL, payload_sha256 BYTEA NOT NULL,
        principal JSONB NOT NULL, occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL, correlation_id UUID,
        causation_id UUID, traceparent VARCHAR(256), tracestate VARCHAR(512),
        dedupe_namespace VARCHAR(128), dedupe_key VARCHAR(512),
        CONSTRAINT pk_events PRIMARY KEY (tenant_id, event_id),
        CONSTRAINT uq_events_tenant_id_event_id UNIQUE (tenant_id, event_id),
        CONSTRAINT ck_events_event_version_positive CHECK (event_version > 0),
        CONSTRAINT ck_events_canonical_version_positive CHECK (canonical_version > 0),
        CONSTRAINT ck_events_payload_sha256_size CHECK (octet_length(payload_sha256) = 32),
        CONSTRAINT ck_events_dedupe_fields_paired
            CHECK ((dedupe_namespace IS NULL) = (dedupe_key IS NULL))
    )
    """,
    "CREATE INDEX ix_events_tenant_created ON fastapi_mergen.events (tenant_id, created_at)",
    """
    CREATE UNIQUE INDEX uq_events_tenant_dedupe
    ON fastapi_mergen.events (tenant_id, dedupe_namespace, dedupe_key)
    WHERE dedupe_namespace IS NOT NULL
    """,
    """
    CREATE TABLE fastapi_mergen.deliveries (
        tenant_id UUID NOT NULL, delivery_id UUID NOT NULL, event_id UUID NOT NULL,
        route_key VARCHAR(128) NOT NULL, route_version INTEGER NOT NULL,
        destination_kind VARCHAR(128) NOT NULL, destination_key VARCHAR(128) NOT NULL,
        route_snapshot JSONB NOT NULL, route_snapshot_bytes BYTEA NOT NULL,
        state VARCHAR(32) NOT NULL, attempts_started INTEGER NOT NULL,
        next_attempt_at TIMESTAMP WITH TIME ZONE NOT NULL, lease_token UUID,
        lease_expires_at TIMESTAMP WITH TIME ZONE, replay_of UUID,
        replay_actor VARCHAR(512), replay_reason VARCHAR(128),
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
        CONSTRAINT pk_deliveries PRIMARY KEY (tenant_id, delivery_id),
        CONSTRAINT fk_deliveries_tenant_id_event_id_events
            FOREIGN KEY(tenant_id, event_id)
            REFERENCES fastapi_mergen.events (tenant_id, event_id) ON DELETE RESTRICT,
        CONSTRAINT fk_deliveries_tenant_id_replay_of_deliveries
            FOREIGN KEY(tenant_id, replay_of)
            REFERENCES fastapi_mergen.deliveries (tenant_id, delivery_id) ON DELETE RESTRICT,
        CONSTRAINT uq_deliveries_tenant_id_delivery_id UNIQUE (tenant_id, delivery_id),
        CONSTRAINT ck_deliveries_route_version_positive CHECK (route_version > 0),
        CONSTRAINT ck_deliveries_attempts_started_nonnegative CHECK (attempts_started >= 0),
        CONSTRAINT ck_deliveries_delivery_state
            CHECK (state IN ('pending','leased','retry_wait','succeeded','dead')),
        CONSTRAINT ck_deliveries_delivery_lease_coherent
            CHECK ((state = 'leased') =
                (lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)),
        CONSTRAINT ck_deliveries_delivery_replay_audit_coherent CHECK (
            (replay_of IS NULL AND replay_actor IS NULL AND replay_reason IS NULL) OR
            (replay_of IS NOT NULL AND replay_actor IS NOT NULL AND replay_reason IS NOT NULL)
        )
    )
    """,
    """
    CREATE INDEX ix_deliveries_claim
    ON fastapi_mergen.deliveries (state, next_attempt_at, tenant_id, created_at)
    """,
    """
    CREATE UNIQUE INDEX uq_deliveries_original_route
    ON fastapi_mergen.deliveries
        (tenant_id, event_id, route_key, route_version, destination_kind, destination_key)
    WHERE replay_of IS NULL
    """,
    """
    CREATE TABLE fastapi_mergen.attempts (
        tenant_id UUID NOT NULL, attempt_id UUID NOT NULL, delivery_id UUID NOT NULL,
        attempt_number INTEGER NOT NULL, lease_token UUID NOT NULL,
        outcome VARCHAR(32) NOT NULL, started_at TIMESTAMP WITH TIME ZONE NOT NULL,
        finished_at TIMESTAMP WITH TIME ZONE, failure_code VARCHAR(128),
        failure_summary TEXT,
        CONSTRAINT pk_attempts PRIMARY KEY (tenant_id, attempt_id),
        CONSTRAINT fk_attempts_tenant_id_delivery_id_deliveries
            FOREIGN KEY(tenant_id, delivery_id)
            REFERENCES fastapi_mergen.deliveries (tenant_id, delivery_id) ON DELETE CASCADE,
        CONSTRAINT uq_attempts_tenant_id_delivery_id_attempt_number
            UNIQUE (tenant_id, delivery_id, attempt_number),
        CONSTRAINT ck_attempts_attempt_number_positive CHECK (attempt_number > 0),
        CONSTRAINT ck_attempts_attempt_outcome
            CHECK (outcome IN (
                'started','succeeded','retryable','terminal','abandoned','lease_lost'
            )),
        CONSTRAINT ck_attempts_attempt_finish_coherent CHECK (
            (outcome = 'started' AND finished_at IS NULL) OR
            (outcome <> 'started' AND finished_at IS NOT NULL)
        ),
        CONSTRAINT ck_attempts_attempt_failure_coherent CHECK (
            (outcome IN ('started','succeeded') AND failure_code IS NULL
                AND failure_summary IS NULL) OR
            (outcome NOT IN ('started','succeeded') AND failure_code IS NOT NULL
                AND failure_summary IS NOT NULL)
        )
    )
    """,
    """
    CREATE INDEX ix_attempts_delivery
    ON fastapi_mergen.attempts (tenant_id, delivery_id, started_at)
    """,
)


WEBHOOK_TABLE_NAMES_V1 = (
    "webhook_secret_sets",
    "webhook_subscriptions",
    "webhook_secret_versions",
    "webhook_subscription_versions",
    "webhook_audit",
)
WEBHOOK_DDL_V1 = (
    """
    CREATE TABLE fastapi_mergen.webhook_secret_sets (
        tenant_id UUID NOT NULL, secret_set_id UUID NOT NULL, revision INTEGER NOT NULL,
        created_by VARCHAR(512) NOT NULL, created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
        CONSTRAINT pk_webhook_secret_sets PRIMARY KEY (tenant_id, secret_set_id),
        CONSTRAINT uq_webhook_secret_sets_tenant_id_secret_set_id
            UNIQUE (tenant_id, secret_set_id),
        CONSTRAINT ck_webhook_secret_sets_webhook_secret_set_revision_positive
            CHECK (revision > 0)
    )
    """,
    """
    CREATE TABLE fastapi_mergen.webhook_subscriptions (
        tenant_id UUID NOT NULL, subscription_id UUID NOT NULL,
        current_version INTEGER NOT NULL, revision INTEGER NOT NULL,
        state VARCHAR(32) NOT NULL, failure_streak INTEGER NOT NULL,
        auto_pause_threshold INTEGER NOT NULL, created_by VARCHAR(512) NOT NULL,
        updated_by VARCHAR(512) NOT NULL, created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
        CONSTRAINT pk_webhook_subscriptions PRIMARY KEY (tenant_id, subscription_id),
        CONSTRAINT uq_webhook_subscriptions_tenant_id_subscription_id
            UNIQUE (tenant_id, subscription_id),
        CONSTRAINT ck_webhook_subscriptions_webhook_subscription_version_positive
            CHECK (current_version > 0),
        CONSTRAINT ck_webhook_subscriptions_webhook_subscription_revision_positive
            CHECK (revision > 0),
        CONSTRAINT ck_webhook_subscriptions_webhook_subscription_state
            CHECK (state IN ('active','paused','disabled')),
        CONSTRAINT ck_webhook_subscriptions_webhook_failure_streak_nonnegative
            CHECK (failure_streak >= 0),
        CONSTRAINT ck_webhook_subscriptions_webhook_pause_threshold_positive
            CHECK (auto_pause_threshold > 0)
    )
    """,
    """
    CREATE INDEX ix_webhook_subscriptions_tenant_state
    ON fastapi_mergen.webhook_subscriptions (tenant_id, state)
    """,
    """
    CREATE TABLE fastapi_mergen.webhook_secret_versions (
        tenant_id UUID NOT NULL, secret_set_id UUID NOT NULL,
        secret_version INTEGER NOT NULL, key_id VARCHAR(128) NOT NULL,
        nonce BYTEA NOT NULL, ciphertext BYTEA NOT NULL, state VARCHAR(32) NOT NULL,
        retiring_until TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        revoked_at TIMESTAMP WITH TIME ZONE,
        CONSTRAINT pk_webhook_secret_versions
            PRIMARY KEY (tenant_id, secret_set_id, secret_version),
        CONSTRAINT fk_webhook_secret_versions_tenant_id_secret_set_id_webh_2a09
            FOREIGN KEY(tenant_id, secret_set_id)
            REFERENCES fastapi_mergen.webhook_secret_sets (tenant_id, secret_set_id)
            ON DELETE CASCADE,
        CONSTRAINT ck_webhook_secret_versions_webhook_secret_version_positive
            CHECK (secret_version > 0),
        CONSTRAINT ck_webhook_secret_versions_webhook_secret_state
            CHECK (state IN ('active','retiring','revoked')),
        CONSTRAINT ck_webhook_secret_versions_webhook_secret_nonce_size
            CHECK (octet_length(nonce) = 12),
        CONSTRAINT ck_webhook_secret_versions_webhook_secret_ciphertext_size
            CHECK (octet_length(ciphertext) >= 16),
        CONSTRAINT ck_webhook_secret_versions_webhook_secret_retirement_coherent CHECK (
            (state = 'retiring' AND retiring_until IS NOT NULL) OR
            (state <> 'retiring' AND retiring_until IS NULL)
        )
    )
    """,
    """
    CREATE INDEX ix_webhook_secret_versions_eligible
    ON fastapi_mergen.webhook_secret_versions (tenant_id, secret_set_id, state)
    """,
    """
    CREATE TABLE fastapi_mergen.webhook_subscription_versions (
        tenant_id UUID NOT NULL, subscription_id UUID NOT NULL, version INTEGER NOT NULL,
        exact_event_types JSONB NOT NULL, endpoint_url TEXT NOT NULL,
        retry_policy JSONB NOT NULL, secret_set_id UUID NOT NULL,
        created_by VARCHAR(512) NOT NULL, created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        CONSTRAINT pk_webhook_subscription_versions
            PRIMARY KEY (tenant_id, subscription_id, version),
        CONSTRAINT fk_webhook_subscription_versions_tenant_id_subscription_8717
            FOREIGN KEY(tenant_id, subscription_id)
            REFERENCES fastapi_mergen.webhook_subscriptions (tenant_id, subscription_id)
            ON DELETE CASCADE,
        CONSTRAINT fk_webhook_subscription_versions_tenant_id_secret_set_i_6db1
            FOREIGN KEY(tenant_id, secret_set_id)
            REFERENCES fastapi_mergen.webhook_secret_sets (tenant_id, secret_set_id)
            ON DELETE RESTRICT,
        CONSTRAINT ck_webhook_subscription_versions_webhook_subscription_h_7cf1
            CHECK (version > 0)
    )
    """,
    """
    CREATE INDEX ix_webhook_subscription_versions_events
    ON fastapi_mergen.webhook_subscription_versions USING gin (exact_event_types)
    """,
    """
    CREATE TABLE fastapi_mergen.webhook_audit (
        tenant_id UUID NOT NULL, audit_id UUID NOT NULL,
        subject_id VARCHAR(512) NOT NULL, action VARCHAR(128) NOT NULL,
        target_kind VARCHAR(64) NOT NULL, target_id UUID NOT NULL,
        details JSONB NOT NULL, occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
        CONSTRAINT pk_webhook_audit PRIMARY KEY (tenant_id, audit_id)
    )
    """,
    """
    CREATE INDEX ix_webhook_audit_tenant_occurred
    ON fastapi_mergen.webhook_audit (tenant_id, occurred_at)
    """,
)


TASKIQ_TABLE_NAMES_V1 = ("taskiq_handoffs",)
TASKIQ_DDL_V1 = (
    """
    CREATE TABLE fastapi_mergen.taskiq_handoffs (
        tenant_id UUID NOT NULL, handoff_id UUID NOT NULL, delivery_id UUID NOT NULL,
        attempt_id UUID NOT NULL, task_id VARCHAR(128) NOT NULL,
        handoff_token UUID NOT NULL, state VARCHAR(32) NOT NULL,
        principal JSONB NOT NULL, route_snapshot JSONB NOT NULL,
        route_snapshot_bytes BYTEA NOT NULL, event_metadata JSONB NOT NULL,
        execution_token UUID, execution_deadline TIMESTAMP WITH TIME ZONE,
        execution_count INTEGER NOT NULL, prepared_at TIMESTAMP WITH TIME ZONE NOT NULL,
        enqueued_at TIMESTAMP WITH TIME ZONE, started_at TIMESTAMP WITH TIME ZONE,
        finished_at TIMESTAMP WITH TIME ZONE,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
        failure_code VARCHAR(128), failure_summary TEXT,
        CONSTRAINT pk_taskiq_handoffs PRIMARY KEY (tenant_id, handoff_id),
        CONSTRAINT fk_taskiq_handoffs_tenant_id_delivery_id_deliveries
            FOREIGN KEY(tenant_id, delivery_id)
            REFERENCES fastapi_mergen.deliveries (tenant_id, delivery_id) ON DELETE CASCADE,
        CONSTRAINT fk_taskiq_handoffs_tenant_id_attempt_id_attempts
            FOREIGN KEY(tenant_id, attempt_id)
            REFERENCES fastapi_mergen.attempts (tenant_id, attempt_id) ON DELETE CASCADE,
        CONSTRAINT uq_taskiq_handoffs_tenant_id_delivery_id_attempt_id
            UNIQUE (tenant_id, delivery_id, attempt_id),
        CONSTRAINT uq_taskiq_handoffs_task_id UNIQUE (task_id),
        CONSTRAINT ck_taskiq_handoffs_taskiq_handoff_state
            CHECK (state IN ('prepared','enqueued','executing','succeeded','retry_wait','dead')),
        CONSTRAINT ck_taskiq_handoffs_taskiq_execution_count_nonnegative
            CHECK (execution_count >= 0),
        CONSTRAINT ck_taskiq_handoffs_taskiq_execution_coherent CHECK (
            (state = 'executing') =
            (execution_token IS NOT NULL AND execution_deadline IS NOT NULL)
        ),
        CONSTRAINT ck_taskiq_handoffs_taskiq_enqueue_coherent CHECK (
            (state = 'prepared' AND enqueued_at IS NULL) OR
            (state IN ('enqueued','executing','succeeded') AND enqueued_at IS NOT NULL) OR
            state IN ('retry_wait','dead')
        ),
        CONSTRAINT ck_taskiq_handoffs_taskiq_finish_coherent CHECK (
            (state IN ('succeeded','retry_wait','dead') AND finished_at IS NOT NULL) OR
            (state NOT IN ('succeeded','retry_wait','dead') AND finished_at IS NULL)
        ),
        CONSTRAINT ck_taskiq_handoffs_taskiq_failure_coherent CHECK (
            (state IN ('retry_wait','dead') AND failure_code IS NOT NULL
                AND failure_summary IS NOT NULL) OR
            (state NOT IN ('retry_wait','dead') AND failure_code IS NULL
                AND failure_summary IS NULL)
        )
    )
    """,
    """
    CREATE INDEX ix_taskiq_handoffs_recovery
    ON fastapi_mergen.taskiq_handoffs (state, execution_deadline, updated_at)
    """,
)


COMMAND_TABLE_NAMES_V1 = ("commands",)
COMMAND_DDL_V1 = (
    """
    CREATE TABLE fastapi_mergen.commands (
        tenant_id UUID NOT NULL, command_id UUID NOT NULL,
        route_id VARCHAR(128) NOT NULL, method VARCHAR(16) NOT NULL,
        key_digest BYTEA NOT NULL, generation INTEGER NOT NULL,
        is_current BOOLEAN NOT NULL, subject_id VARCHAR(512) NOT NULL,
        fingerprint_version INTEGER NOT NULL, fingerprint BYTEA NOT NULL,
        state VARCHAR(32) NOT NULL, response_status INTEGER,
        response_headers JSONB, response_body BYTEA, response_media_type VARCHAR(128),
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
        expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
        completed_at TIMESTAMP WITH TIME ZONE, superseded_at TIMESTAMP WITH TIME ZONE,
        CONSTRAINT pk_commands PRIMARY KEY (tenant_id, command_id),
        CONSTRAINT uq_commands_tenant_id_route_id_method_key_digest_generation
            UNIQUE (tenant_id, route_id, method, key_digest, generation),
        CONSTRAINT ck_commands_command_key_digest_size
            CHECK (octet_length(key_digest) = 32),
        CONSTRAINT ck_commands_command_fingerprint_size
            CHECK (octet_length(fingerprint) = 32),
        CONSTRAINT ck_commands_command_generation_positive CHECK (generation > 0),
        CONSTRAINT ck_commands_command_fingerprint_version_positive
            CHECK (fingerprint_version > 0),
        CONSTRAINT ck_commands_command_expiry_after_creation CHECK (expires_at > created_at),
        CONSTRAINT ck_commands_command_update_after_creation CHECK (updated_at >= created_at),
        CONSTRAINT ck_commands_command_response_status
            CHECK (response_status IS NULL OR response_status BETWEEN 200 AND 599),
        CONSTRAINT ck_commands_command_completion_after_creation
            CHECK (completed_at IS NULL OR completed_at >= created_at),
        CONSTRAINT ck_commands_command_supersession_after_creation
            CHECK (superseded_at IS NULL OR superseded_at >= created_at),
        CONSTRAINT ck_commands_command_response_body_bounded
            CHECK (response_body IS NULL OR octet_length(response_body) <= 262144),
        CONSTRAINT ck_commands_command_response_headers_object
            CHECK (response_headers IS NULL OR jsonb_typeof(response_headers) = 'object'),
        CONSTRAINT ck_commands_command_response_media_type CHECK (
            response_media_type IS NULL OR
            response_media_type IN ('application/json','application/problem+json','text/plain')
        ),
        CONSTRAINT ck_commands_command_state
            CHECK (state IN ('in_progress','completed','superseded')),
        CONSTRAINT ck_commands_command_supersession_coherent CHECK (
            (state = 'superseded') = (is_current = false AND superseded_at IS NOT NULL)
        ),
        CONSTRAINT ck_commands_command_response_coherent CHECK (
            (state = 'completed' AND completed_at IS NOT NULL
                AND response_status IS NOT NULL AND response_headers IS NOT NULL
                AND response_body IS NOT NULL AND response_media_type IS NOT NULL) OR
            (state = 'in_progress' AND completed_at IS NULL
                AND response_status IS NULL AND response_headers IS NULL
                AND response_body IS NULL AND response_media_type IS NULL) OR
            state = 'superseded'
        )
    )
    """,
    "CREATE INDEX ix_commands_retention ON fastapi_mergen.commands (state, updated_at)",
    """
    CREATE UNIQUE INDEX uq_commands_current_identity
    ON fastapi_mergen.commands (tenant_id, route_id, method, key_digest)
    WHERE is_current = true
    """,
)


def core_rls_sql_v1(roles: RoleNamesV1) -> tuple[str, ...]:
    statements: list[str] = []
    for table in ("events", "deliveries", "attempts"):
        qualified = f"{SCHEMA_V1}.{table}"
        statements.extend(
            (
                f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY",
                f"ALTER TABLE {qualified} FORCE ROW LEVEL SECURITY",
                f"DROP POLICY IF EXISTS {table}_application_tenant ON {qualified}",
                f"CREATE POLICY {table}_application_tenant ON {qualified} "
                f"FOR ALL TO {roles.application} USING ({TENANT_EXPRESSION_V1}) "
                f"WITH CHECK ({TENANT_EXPRESSION_V1})",
                f"DROP POLICY IF EXISTS {table}_migration_control ON {qualified}",
                f"CREATE POLICY {table}_migration_control ON {qualified} "
                f"FOR ALL TO {roles.migration} USING (true) WITH CHECK (true)",
            )
        )
    statements.extend(
        (
            f"DROP POLICY IF EXISTS events_relay_read ON {SCHEMA_V1}.events",
            f"CREATE POLICY events_relay_read ON {SCHEMA_V1}.events "
            f"FOR SELECT TO {roles.relay} USING (true)",
            f"DROP POLICY IF EXISTS deliveries_relay_control ON {SCHEMA_V1}.deliveries",
            f"CREATE POLICY deliveries_relay_control ON {SCHEMA_V1}.deliveries "
            f"FOR ALL TO {roles.relay} USING (true) WITH CHECK (true)",
            f"DROP POLICY IF EXISTS attempts_relay_control ON {SCHEMA_V1}.attempts",
            f"CREATE POLICY attempts_relay_control ON {SCHEMA_V1}.attempts "
            f"FOR ALL TO {roles.relay} USING (true) WITH CHECK (true)",
        )
    )
    return tuple(statements)


def webhook_rls_sql_v1(roles: RoleNamesV1) -> tuple[str, ...]:
    statements: list[str] = []
    for table in WEBHOOK_TABLE_NAMES_V1:
        qualified = f"{SCHEMA_V1}.{table}"
        statements.extend(
            (
                f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY",
                f"ALTER TABLE {qualified} FORCE ROW LEVEL SECURITY",
                f"DROP POLICY IF EXISTS {table}_application_tenant ON {qualified}",
                f"CREATE POLICY {table}_application_tenant ON {qualified} "
                f"FOR ALL TO {roles.application} USING ({TENANT_EXPRESSION_V1}) "
                f"WITH CHECK ({TENANT_EXPRESSION_V1})",
                f"DROP POLICY IF EXISTS {table}_migration_control ON {qualified}",
                f"CREATE POLICY {table}_migration_control ON {qualified} "
                f"FOR ALL TO {roles.migration} USING (true) WITH CHECK (true)",
            )
        )
    for table in WEBHOOK_TABLE_NAMES_V1[:-1]:
        qualified = f"{SCHEMA_V1}.{table}"
        statements.extend(
            (
                f"DROP POLICY IF EXISTS {table}_relay_read ON {qualified}",
                f"CREATE POLICY {table}_relay_read ON {qualified} "
                f"FOR SELECT TO {roles.relay} USING (true)",
            )
        )
    statements.extend(
        (
            f"DROP POLICY IF EXISTS webhook_subscriptions_relay_health "
            f"ON {SCHEMA_V1}.webhook_subscriptions",
            f"CREATE POLICY webhook_subscriptions_relay_health "
            f"ON {SCHEMA_V1}.webhook_subscriptions FOR UPDATE TO {roles.relay} "
            "USING (true) WITH CHECK (true)",
            f"DROP POLICY IF EXISTS webhook_audit_relay_append ON {SCHEMA_V1}.webhook_audit",
            f"CREATE POLICY webhook_audit_relay_append ON {SCHEMA_V1}.webhook_audit "
            f"FOR INSERT TO {roles.relay} WITH CHECK (true)",
        )
    )
    return tuple(statements)


def webhook_grant_sql_v1(roles: RoleNamesV1) -> tuple[str, ...]:
    return (
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA_V1}.webhook_subscriptions, "
        f"{SCHEMA_V1}.webhook_secret_sets, {SCHEMA_V1}.webhook_secret_versions, "
        f"{SCHEMA_V1}.webhook_subscription_versions TO {roles.application}",
        f"GRANT SELECT, INSERT ON {SCHEMA_V1}.webhook_audit TO {roles.application}",
        f"GRANT SELECT ON {SCHEMA_V1}.webhook_secret_sets, "
        f"{SCHEMA_V1}.webhook_secret_versions, {SCHEMA_V1}.webhook_subscription_versions "
        f"TO {roles.relay}",
        f"GRANT SELECT, UPDATE ON {SCHEMA_V1}.webhook_subscriptions TO {roles.relay}",
        f"GRANT INSERT ON {SCHEMA_V1}.webhook_audit TO {roles.relay}",
    )


def executor_schema_sql_v1(roles: RoleNamesV1) -> tuple[str, ...]:
    qualified = f"{SCHEMA_V1}.taskiq_handoffs"
    return (
        f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {qualified} FORCE ROW LEVEL SECURITY",
        f"DROP POLICY IF EXISTS taskiq_handoffs_application_tenant ON {qualified}",
        f"CREATE POLICY taskiq_handoffs_application_tenant ON {qualified} "
        f"FOR SELECT TO {roles.application} USING ({TENANT_EXPRESSION_V1})",
        f"DROP POLICY IF EXISTS taskiq_handoffs_relay_control ON {qualified}",
        f"CREATE POLICY taskiq_handoffs_relay_control ON {qualified} "
        f"FOR ALL TO {roles.relay} USING (true) WITH CHECK (true)",
        f"DROP POLICY IF EXISTS taskiq_handoffs_migration_control ON {qualified}",
        f"CREATE POLICY taskiq_handoffs_migration_control ON {qualified} "
        f"FOR ALL TO {roles.migration} USING (true) WITH CHECK (true)",
        f"GRANT SELECT ON {qualified} TO {roles.application}",
        f"GRANT SELECT, INSERT, UPDATE ON {qualified} TO {roles.relay}",
    )


def command_trigger_sql_v1() -> tuple[str, ...]:
    qualified = f"{SCHEMA_V1}.commands"
    function = f"{SCHEMA_V1}.guard_command_mutation"
    return (
        f"""
        CREATE OR REPLACE FUNCTION {function}() RETURNS trigger
        LANGUAGE plpgsql AS $guard$
        BEGIN
            IF ROW(
                NEW.tenant_id, NEW.command_id, NEW.route_id, NEW.method,
                NEW.key_digest, NEW.generation, NEW.subject_id,
                NEW.fingerprint_version, NEW.fingerprint, NEW.created_at, NEW.expires_at
            ) IS DISTINCT FROM ROW(
                OLD.tenant_id, OLD.command_id, OLD.route_id, OLD.method,
                OLD.key_digest, OLD.generation, OLD.subject_id,
                OLD.fingerprint_version, OLD.fingerprint, OLD.created_at, OLD.expires_at
            ) THEN
                RAISE EXCEPTION 'command immutable fields cannot change'
                    USING ERRCODE = 'check_violation';
            END IF;
            IF NOT (
                NEW.state = OLD.state OR
                (OLD.state = 'in_progress' AND NEW.state IN ('completed', 'superseded')) OR
                (OLD.state = 'completed' AND NEW.state = 'superseded')
            ) THEN
                RAISE EXCEPTION 'illegal command state transition'
                    USING ERRCODE = 'check_violation';
            END IF;
            IF OLD.state = 'superseded' AND NEW IS DISTINCT FROM OLD THEN
                RAISE EXCEPTION 'superseded command history is immutable'
                    USING ERRCODE = 'check_violation';
            END IF;
            IF OLD.state = 'completed' AND ROW(
                NEW.response_status, NEW.response_headers, NEW.response_body,
                NEW.response_media_type, NEW.completed_at
            ) IS DISTINCT FROM ROW(
                OLD.response_status, OLD.response_headers, OLD.response_body,
                OLD.response_media_type, OLD.completed_at
            ) THEN
                RAISE EXCEPTION 'completed command response is immutable'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END
        $guard$
        """,
        f"DROP TRIGGER IF EXISTS guard_command_mutation ON {qualified}",
        f"CREATE TRIGGER guard_command_mutation BEFORE UPDATE ON {qualified} "
        f"FOR EACH ROW EXECUTE FUNCTION {function}()",
    )


def command_schema_sql_v1(roles: RoleNamesV1) -> tuple[str, ...]:
    qualified = f"{SCHEMA_V1}.commands"
    return (
        f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {qualified} FORCE ROW LEVEL SECURITY",
        f"DROP POLICY IF EXISTS commands_application_tenant ON {qualified}",
        f"CREATE POLICY commands_application_tenant ON {qualified} "
        f"FOR ALL TO {roles.application} USING ({TENANT_EXPRESSION_V1}) "
        f"WITH CHECK ({TENANT_EXPRESSION_V1})",
        f"DROP POLICY IF EXISTS commands_relay_read ON {qualified}",
        f"CREATE POLICY commands_relay_read ON {qualified} "
        f"FOR SELECT TO {roles.relay} USING (true)",
        f"DROP POLICY IF EXISTS commands_relay_delete ON {qualified}",
        f"CREATE POLICY commands_relay_delete ON {qualified} "
        f"FOR DELETE TO {roles.relay} USING (true)",
        f"DROP POLICY IF EXISTS commands_migration_control ON {qualified}",
        f"CREATE POLICY commands_migration_control ON {qualified} "
        f"FOR ALL TO {roles.migration} USING (true) WITH CHECK (true)",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {qualified} TO {roles.application}",
        f"""
        CREATE OR REPLACE FUNCTION {SCHEMA_V1}.prune_commands(
            cutoff timestamp with time zone, requested_batch integer
        ) RETURNS bigint
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, {SCHEMA_V1}
        AS $prune$
        DECLARE deleted_count bigint;
        BEGIN
            IF requested_batch < 1 OR requested_batch > 10000 THEN
                RAISE EXCEPTION 'command pruning batch size is invalid'
                    USING ERRCODE = 'invalid_parameter_value';
            END IF;
            WITH locked AS (
                SELECT ctid FROM {qualified}
                WHERE state IN ('completed', 'superseded') AND expires_at <= cutoff
                ORDER BY expires_at, command_id
                LIMIT requested_batch FOR UPDATE SKIP LOCKED
            ), deleted AS (
                DELETE FROM {qualified}
                WHERE ctid IN (SELECT ctid FROM locked)
                RETURNING 1
            )
            SELECT count(*) INTO deleted_count FROM deleted;
            RETURN deleted_count;
        END
        $prune$
        """,
        f"REVOKE ALL ON FUNCTION {SCHEMA_V1}.prune_commands"
        "(timestamp with time zone, integer) FROM PUBLIC",
        f"GRANT EXECUTE ON FUNCTION {SCHEMA_V1}.prune_commands"
        f"(timestamp with time zone, integer) TO {roles.relay}",
    )


def webhook_retention_sql_v1(roles: RoleNamesV1) -> tuple[str, ...]:
    signature = f"{SCHEMA_V1}.prune_webhook_history(uuid, timestamp with time zone, integer)"
    return (
        f"""
        CREATE OR REPLACE FUNCTION {SCHEMA_V1}.prune_webhook_history(
            requested_tenant uuid, cutoff timestamp with time zone, requested_batch integer
        ) RETURNS TABLE(
            attempts_deleted bigint, deliveries_deleted bigint,
            events_deleted bigint, secret_versions_deleted bigint
        )
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, {SCHEMA_V1}
        AS $retention$
        BEGIN
            IF nullif(current_setting('mergen.tenant_id', true), '')
                IS DISTINCT FROM requested_tenant::text THEN
                RAISE EXCEPTION 'webhook retention tenant context does not match'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;
            IF cutoff IS NULL OR requested_batch < 1 OR requested_batch > 10000 THEN
                RAISE EXCEPTION 'webhook retention arguments are invalid'
                    USING ERRCODE = 'invalid_parameter_value';
            END IF;
            PERFORM pg_catalog.pg_advisory_xact_lock(
                pg_catalog.hashtextextended(
                    'fastapi-mergen:webhook-retention:' || requested_tenant::text,
                    0
                )
            );
            WITH locked AS (
                SELECT a.tenant_id, a.attempt_id FROM {SCHEMA_V1}.attempts AS a
                JOIN {SCHEMA_V1}.deliveries AS d
                  ON d.tenant_id = a.tenant_id AND d.delivery_id = a.delivery_id
                WHERE a.tenant_id = requested_tenant AND a.finished_at < cutoff
                  AND d.destination_kind = 'webhook' AND d.state IN ('succeeded', 'dead')
                  AND d.updated_at < cutoff
                ORDER BY a.finished_at, a.attempt_id
                LIMIT requested_batch FOR UPDATE OF a SKIP LOCKED
            ), deleted AS (
                DELETE FROM {SCHEMA_V1}.attempts AS a USING locked
                WHERE a.tenant_id = locked.tenant_id AND a.attempt_id = locked.attempt_id
                RETURNING 1
            ) SELECT count(*) INTO attempts_deleted FROM deleted;
            WITH locked AS (
                SELECT d.tenant_id, d.delivery_id FROM {SCHEMA_V1}.deliveries AS d
                WHERE d.tenant_id = requested_tenant AND d.destination_kind = 'webhook'
                  AND d.state IN ('succeeded', 'dead') AND d.updated_at < cutoff
                  AND NOT EXISTS (
                      SELECT 1 FROM {SCHEMA_V1}.attempts AS a
                      WHERE a.tenant_id = d.tenant_id AND a.delivery_id = d.delivery_id
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM {SCHEMA_V1}.deliveries AS replay
                      WHERE replay.tenant_id = d.tenant_id
                        AND replay.replay_of = d.delivery_id
                  )
                ORDER BY d.updated_at, d.delivery_id
                LIMIT requested_batch FOR UPDATE OF d SKIP LOCKED
            ), deleted AS (
                DELETE FROM {SCHEMA_V1}.deliveries AS d USING locked
                WHERE d.tenant_id = locked.tenant_id AND d.delivery_id = locked.delivery_id
                RETURNING 1
            ) SELECT count(*) INTO deliveries_deleted FROM deleted;
            WITH locked AS (
                SELECT e.tenant_id, e.event_id FROM {SCHEMA_V1}.events AS e
                WHERE e.tenant_id = requested_tenant AND e.created_at < cutoff
                  AND NOT EXISTS (
                      SELECT 1 FROM {SCHEMA_V1}.deliveries AS d
                      WHERE d.tenant_id = e.tenant_id AND d.event_id = e.event_id
                  )
                ORDER BY e.created_at, e.event_id
                LIMIT requested_batch FOR UPDATE OF e SKIP LOCKED
            ), deleted AS (
                DELETE FROM {SCHEMA_V1}.events AS e USING locked
                WHERE e.tenant_id = locked.tenant_id AND e.event_id = locked.event_id
                RETURNING 1
            ) SELECT count(*) INTO events_deleted FROM deleted;
            WITH locked AS (
                SELECT s.tenant_id, s.secret_set_id, s.secret_version
                FROM {SCHEMA_V1}.webhook_secret_versions AS s
                WHERE s.tenant_id = requested_tenant
                  AND s.state IN ('retiring', 'revoked') AND s.created_at < cutoff
                ORDER BY s.created_at, s.secret_set_id, s.secret_version
                LIMIT requested_batch FOR UPDATE OF s SKIP LOCKED
            ), deleted AS (
                DELETE FROM {SCHEMA_V1}.webhook_secret_versions AS s USING locked
                WHERE s.tenant_id = locked.tenant_id
                  AND s.secret_set_id = locked.secret_set_id
                  AND s.secret_version = locked.secret_version
                RETURNING 1
            ) SELECT count(*) INTO secret_versions_deleted FROM deleted;
            RETURN NEXT;
        END
        $retention$
        """,
        f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC",
        f"REVOKE ALL ON FUNCTION {signature} FROM {roles.relay}",
        f"GRANT EXECUTE ON FUNCTION {signature} TO {roles.application}",
    )


__all__ = [
    "COMMAND_DDL_V1",
    "COMMAND_TABLE_NAMES_V1",
    "CORE_DDL_V1",
    "CORE_TABLE_NAMES_V1",
    "SCHEMA_V1",
    "TASKIQ_DDL_V1",
    "TASKIQ_TABLE_NAMES_V1",
    "WEBHOOK_DDL_V1",
    "WEBHOOK_TABLE_NAMES_V1",
    "command_schema_sql_v1",
    "command_trigger_sql_v1",
    "core_rls_sql_v1",
    "create_role_sql_v1",
    "executor_schema_sql_v1",
    "role_names_v1",
    "webhook_grant_sql_v1",
    "webhook_retention_sql_v1",
    "webhook_rls_sql_v1",
]
