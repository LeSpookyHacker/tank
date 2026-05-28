"""SQLite persistence for Tank.

Single global connection guarded by a `threading.Lock` for write safety.
WAL mode permits concurrent readers while a writer holds the lock.
Schema is initialized on first connection via `CREATE TABLE IF NOT EXISTS`.

Path defaults to `~/.tank/db.sqlite`; override with `TANK_DB_PATH`.

The full data model is documented in the architecture plan. Key invariants:
- `chunks.text_redacted` is what's sent to Claude; `chunks.text_original`
  never leaves the machine and exists only for local rehydration.
- `redaction_map.original_text` is cleartext EXCEPT for category='secret_token'
  where it is overwritten with a SHA-256 hash at insert time (one-way).
- All entities and relationships carry a `provenance` ∈ {source, inferred,
  claim, user} that drives the trust badge in the UI.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path

LOCK = threading.Lock()
_CONN: sqlite3.Connection | None = None


def db_path() -> Path:
    raw = os.environ.get("TANK_DB_PATH", "").strip()
    p = Path(raw).expanduser() if raw else Path.home() / ".tank" / "db.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def get_conn() -> sqlite3.Connection:
    global _CONN
    if _CONN is None:
        _CONN = sqlite3.connect(
            db_path(), check_same_thread=False, isolation_level=None,
        )
        _CONN.row_factory = sqlite3.Row
        _CONN.execute("PRAGMA journal_mode=WAL")
        _CONN.execute("PRAGMA foreign_keys=ON")
        _load_extensions(_CONN)
        _init_schema(_CONN)
    return _CONN


def _load_extensions(conn: sqlite3.Connection) -> None:
    """Load sqlite-vec for the chunks_vec virtual table.

    If sqlite-vec is unavailable (e.g. during initial setup or on a system
    where extension loading is disabled), we degrade to keyword-only search
    via FTS5. Vector search will raise at query time.
    """
    try:
        import sqlite_vec
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
    except Exception:
        # Logged at first query attempt; non-fatal at boot.
        pass


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        -- ----- documents: raw ingested artifacts -----
        CREATE TABLE IF NOT EXISTS documents (
            id           TEXT PRIMARY KEY,
            kind         TEXT NOT NULL,
            source_path  TEXT NOT NULL,
            title        TEXT,
            sha256       TEXT NOT NULL,
            size_bytes   INTEGER,
            category     TEXT NOT NULL,
            meta_json    TEXT NOT NULL DEFAULT '{}',
            ingested_at  REAL NOT NULL,
            status       TEXT NOT NULL DEFAULT 'pending'
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_sha ON documents(sha256);
        CREATE INDEX IF NOT EXISTS idx_documents_category ON documents(category);
        CREATE INDEX IF NOT EXISTS idx_documents_ingested_at ON documents(ingested_at);

        -- ----- chunks: post-split, post-redaction units -----
        CREATE TABLE IF NOT EXISTS chunks (
            id            TEXT PRIMARY KEY,
            document_id   TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            ordinal       INTEGER NOT NULL,
            text_redacted TEXT NOT NULL,
            text_original TEXT NOT NULL,
            token_count   INTEGER NOT NULL,
            section_path  TEXT,
            meta_json     TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id, ordinal);

        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            chunk_id UNINDEXED,
            text_redacted,
            section_path,
            content=''
        );

        -- ----- entities: typed graph nodes -----
        CREATE TABLE IF NOT EXISTS entities (
            id              TEXT PRIMARY KEY,
            type            TEXT NOT NULL,
            name            TEXT NOT NULL,
            name_normalized TEXT NOT NULL,
            description     TEXT,
            attrs_json      TEXT NOT NULL DEFAULT '{}',
            confidence      REAL NOT NULL DEFAULT 1.0,
            provenance      TEXT NOT NULL DEFAULT 'inferred',
            first_seen_doc  TEXT REFERENCES documents(id),
            created_at      REAL NOT NULL,
            updated_at      REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_entities_type_name
            ON entities(type, name_normalized);
        CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);

        CREATE TABLE IF NOT EXISTS entity_chunks (
            entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            chunk_id  TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
            PRIMARY KEY (entity_id, chunk_id)
        );
        CREATE INDEX IF NOT EXISTS idx_entity_chunks_chunk
            ON entity_chunks(chunk_id);

        -- ----- relationships: typed graph edges -----
        CREATE TABLE IF NOT EXISTS relationships (
            id              TEXT PRIMARY KEY,
            src_id          TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            dst_id          TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            kind            TEXT NOT NULL,
            attrs_json      TEXT NOT NULL DEFAULT '{}',
            confidence      REAL NOT NULL DEFAULT 1.0,
            provenance      TEXT NOT NULL DEFAULT 'inferred',
            first_seen_doc  TEXT REFERENCES documents(id),
            created_at      REAL NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_rel_dedup
            ON relationships(src_id, dst_id, kind);
        CREATE INDEX IF NOT EXISTS idx_rel_src ON relationships(src_id, kind);
        CREATE INDEX IF NOT EXISTS idx_rel_dst ON relationships(dst_id, kind);
        CREATE INDEX IF NOT EXISTS idx_rel_kind ON relationships(kind);

        -- ----- redaction (never leaves machine) -----
        CREATE TABLE IF NOT EXISTS redaction_map (
            placeholder       TEXT PRIMARY KEY,
            category          TEXT NOT NULL,
            sha256            TEXT NOT NULL,
            original_text     TEXT NOT NULL,
            first_seen_at     REAL NOT NULL,
            occurrence_count  INTEGER NOT NULL DEFAULT 1
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_redaction_sha_cat
            ON redaction_map(sha256, category);
        CREATE INDEX IF NOT EXISTS idx_redaction_category
            ON redaction_map(category);

        CREATE TABLE IF NOT EXISTS redaction_rules (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            category        TEXT NOT NULL,
            enabled         INTEGER NOT NULL DEFAULT 1,
            pattern         TEXT,
            placeholder_fmt TEXT,
            description     TEXT,
            created_at      REAL NOT NULL
        );

        -- ----- chat -----
        CREATE TABLE IF NOT EXISTS conversations (
            id          TEXT PRIMARY KEY,
            title       TEXT,
            role_mode   TEXT NOT NULL,
            model       TEXT NOT NULL,
            scope_json  TEXT NOT NULL DEFAULT '{}',
            created_at  REAL NOT NULL,
            updated_at  REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_conv_updated ON conversations(updated_at);

        CREATE TABLE IF NOT EXISTS messages (
            id              TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            ordinal         INTEGER NOT NULL,
            role            TEXT NOT NULL,
            content_json    TEXT NOT NULL,
            redacted_view   TEXT,
            display_view    TEXT,
            tokens_in       INTEGER,
            tokens_out      INTEGER,
            cache_read_in   INTEGER,
            cache_create_in INTEGER,
            citations_json  TEXT NOT NULL DEFAULT '[]',
            created_at      REAL NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_conv_ord
            ON messages(conversation_id, ordinal);

        -- ----- reports -----
        CREATE TABLE IF NOT EXISTS reports (
            id                  TEXT PRIMARY KEY,
            kind                TEXT NOT NULL,
            scope_json          TEXT NOT NULL DEFAULT '{}',
            role_mode           TEXT NOT NULL,
            model               TEXT NOT NULL,
            title               TEXT NOT NULL,
            content_md          TEXT NOT NULL,
            content_md_redacted TEXT NOT NULL,
            tokens_in           INTEGER,
            tokens_out          INTEGER,
            cache_read_in       INTEGER,
            cache_create_in     INTEGER,
            created_at          REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_reports_kind_created
            ON reports(kind, created_at);

        -- ----- dfd_analyses: DFD threat models -----
        CREATE TABLE IF NOT EXISTS dfd_analyses (
            id              TEXT PRIMARY KEY,
            diagram_hash    TEXT NOT NULL UNIQUE,
            mermaid_src     TEXT,
            analysis_json   TEXT NOT NULL,
            tokens_in       INTEGER,
            tokens_out      INTEGER,
            created_at      REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_dfd_hash
            ON dfd_analyses(diagram_hash);
        CREATE INDEX IF NOT EXISTS idx_dfd_created
            ON dfd_analyses(created_at);

        -- ----- api_calls: catch-all token ledger for all Claude call sites -----
        CREATE TABLE IF NOT EXISTS api_calls (
            id              TEXT PRIMARY KEY,
            call_site       TEXT NOT NULL,
            model           TEXT NOT NULL,
            tokens_in       INTEGER NOT NULL DEFAULT 0,
            tokens_out      INTEGER NOT NULL DEFAULT 0,
            cache_read_in   INTEGER NOT NULL DEFAULT 0,
            cache_create_in INTEGER NOT NULL DEFAULT 0,
            created_at      REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_api_calls_created
            ON api_calls(created_at);

        -- ----- partner-mode state -----
        CREATE TABLE IF NOT EXISTS nudges (
            id            TEXT PRIMARY KEY,
            kind          TEXT NOT NULL,
            title         TEXT NOT NULL,
            body          TEXT NOT NULL,
            payload_json  TEXT NOT NULL DEFAULT '{}',
            priority      INTEGER NOT NULL DEFAULT 50,
            status        TEXT NOT NULL DEFAULT 'open',
            snoozed_until REAL,
            created_at    REAL NOT NULL,
            updated_at    REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_nudges_status_priority
            ON nudges(status, priority DESC);

        CREATE TABLE IF NOT EXISTS notes (
            id                      TEXT PRIMARY KEY,
            body                    TEXT NOT NULL,
            body_redacted           TEXT NOT NULL,
            meeting_with_entity_id  TEXT REFERENCES entities(id),
            extracted_json          TEXT NOT NULL DEFAULT '{}',
            confirmed               INTEGER NOT NULL DEFAULT 0,
            created_at              REAL NOT NULL
        );

        -- ----- single-row app state -----
        CREATE TABLE IF NOT EXISTS app_state (
            id               INTEGER PRIMARY KEY CHECK (id = 1),
            role_mode        TEXT NOT NULL DEFAULT 'both',
            internal_tld     TEXT,
            user_scope_json  TEXT NOT NULL DEFAULT '{}',
            digest_time      TEXT NOT NULL DEFAULT '08:00',
            reflection_day   TEXT NOT NULL DEFAULT 'fri',
            onboarded        INTEGER NOT NULL DEFAULT 0,
            updated_at       REAL NOT NULL
        );

        -- ----- daily-use tables (Phase 8) -----

        CREATE TABLE IF NOT EXISTS journal_entries (
            id              TEXT PRIMARY KEY,
            body            TEXT NOT NULL,
            body_redacted   TEXT NOT NULL,
            date_label      TEXT NOT NULL,         -- YYYY-MM-DD (local)
            tenure_day      INTEGER NOT NULL,
            extracted_json  TEXT NOT NULL DEFAULT '{}',
            created_at      REAL NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_journal_date
            ON journal_entries(date_label);

        CREATE TABLE IF NOT EXISTS followups (
            id                  TEXT PRIMARY KEY,
            title               TEXT NOT NULL,
            body                TEXT,
            status              TEXT NOT NULL DEFAULT 'open',
            due_at              REAL,
            source_kind         TEXT NOT NULL,
            source_id           TEXT,
            related_entity_id   TEXT REFERENCES entities(id),
            created_at          REAL NOT NULL,
            updated_at          REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_followups_status_due
            ON followups(status, due_at);

        CREATE TABLE IF NOT EXISTS report_subscriptions (
            id              TEXT PRIMARY KEY,
            kind            TEXT NOT NULL,
            scope_json      TEXT NOT NULL DEFAULT '{}',
            role_mode       TEXT NOT NULL,
            cadence         TEXT NOT NULL,         -- daily|weekly|monthly|quarterly
            last_run_at     REAL,
            last_report_id  TEXT REFERENCES reports(id),
            enabled         INTEGER NOT NULL DEFAULT 1,
            created_at      REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS usage_events (
            id               TEXT PRIMARY KEY,
            kind             TEXT NOT NULL,
            entity_id        TEXT REFERENCES entities(id),
            chunk_id         TEXT REFERENCES chunks(id),
            conversation_id  TEXT REFERENCES conversations(id),
            report_id        TEXT REFERENCES reports(id),
            created_at       REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_usage_entity
            ON usage_events(entity_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_usage_kind_time
            ON usage_events(kind, created_at);

        CREATE TABLE IF NOT EXISTS watchers (
            id            TEXT PRIMARY KEY,
            kind          TEXT NOT NULL,           -- folder|ics_url|cve_feed|github_repo
            target        TEXT NOT NULL,
            category      TEXT,
            config_json   TEXT NOT NULL DEFAULT '{}',
            last_scan_at  REAL,
            enabled       INTEGER NOT NULL DEFAULT 1,
            created_at    REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS meetings (
            id            TEXT PRIMARY KEY,
            external_id   TEXT,
            title         TEXT NOT NULL,
            starts_at     REAL NOT NULL,
            ends_at       REAL,
            attendees_json TEXT NOT NULL DEFAULT '[]',
            source        TEXT NOT NULL DEFAULT 'manual',  -- manual|ics
            created_at    REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_meetings_starts ON meetings(starts_at);

        -- ----- Phase 12: living threat models + decisions log -----

        CREATE TABLE IF NOT EXISTS threat_models (
            id                  TEXT PRIMARY KEY,
            service_entity_id   TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            version             INTEGER NOT NULL,
            title               TEXT NOT NULL,
            body_md             TEXT NOT NULL,
            body_md_redacted    TEXT NOT NULL,
            threats_json        TEXT NOT NULL,         -- frozen STRIDEThreat[] at gen time
            arch_snapshot_hash  TEXT NOT NULL,
            generated_at        REAL NOT NULL,
            confirmed_by_user   INTEGER NOT NULL DEFAULT 0
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_tm_service_ver
            ON threat_models(service_entity_id, version);
        CREATE INDEX IF NOT EXISTS idx_tm_generated_at
            ON threat_models(generated_at);

        CREATE TABLE IF NOT EXISTS decisions (
            id                TEXT PRIMARY KEY,
            title             TEXT NOT NULL,
            body_md           TEXT NOT NULL,
            body_md_redacted  TEXT NOT NULL,
            kind              TEXT NOT NULL,
              -- design_choice|accepted_risk|deferred_fix|security_invariant
            status            TEXT NOT NULL DEFAULT 'open',
              -- open|withdrawn|expired|reaffirmed
            scope_entity_ids  TEXT NOT NULL DEFAULT '[]',
            rationale         TEXT,
            expires_at        REAL,
            owner_entity_id   TEXT REFERENCES entities(id),
            source            TEXT NOT NULL,
              -- manual|extracted|postmortem|design_review
            source_doc_id     TEXT REFERENCES documents(id),
            created_at        REAL NOT NULL,
            updated_at        REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_decisions_kind_status
            ON decisions(kind, status);
        CREATE INDEX IF NOT EXISTS idx_decisions_expires
            ON decisions(expires_at);
        CREATE INDEX IF NOT EXISTS idx_decisions_source
            ON decisions(source);

        -- ----- Phase 13: workstream artifacts -----

        CREATE TABLE IF NOT EXISTS design_reviews (
            id                TEXT PRIMARY KEY,
            title             TEXT NOT NULL,
            status            TEXT NOT NULL DEFAULT 'intake',
              -- intake|reviewing|approved|rejected|withdrawn
            requester         TEXT,
            scope_entity_ids  TEXT NOT NULL DEFAULT '[]',
            body_md           TEXT NOT NULL,
            body_md_redacted  TEXT NOT NULL,
            checklist_json    TEXT NOT NULL DEFAULT '[]',
            decisions_json    TEXT NOT NULL DEFAULT '[]',
            created_at        REAL NOT NULL,
            updated_at        REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_dr_status_created
            ON design_reviews(status, created_at);

        CREATE TABLE IF NOT EXISTS postmortems_drafts (
            id                  TEXT PRIMARY KEY,
            title               TEXT NOT NULL,
            incident_date       REAL,
            severity            TEXT,                  -- sev1|sev2|sev3
            status              TEXT NOT NULL DEFAULT 'draft',
              -- draft|published|withdrawn
            fields_json         TEXT NOT NULL,
              -- {summary,timeline,what_failed,why,contributing,mitigations,action_items}
            body_md             TEXT,
            body_md_redacted    TEXT,
            services_affected   TEXT NOT NULL DEFAULT '[]',
            created_at          REAL NOT NULL,
            updated_at          REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_pm_status_created
            ON postmortems_drafts(status, created_at);

        CREATE TABLE IF NOT EXISTS tabletops (
            id                TEXT PRIMARY KEY,
            scenario_md       TEXT NOT NULL,
            scope_service_id  TEXT REFERENCES entities(id),
            threat_kind       TEXT,
            injects_json      TEXT NOT NULL DEFAULT '[]',
            participants      TEXT,
            ran_at            REAL,
            lessons_md        TEXT,
            created_at        REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_tt_created
            ON tabletops(created_at);

        -- ----- Phase 14: coverage + visibility -----

        CREATE TABLE IF NOT EXISTS attack_surface_snapshots (
            id              TEXT PRIMARY KEY,
            snapshot_at     REAL NOT NULL,
            endpoints_json  TEXT NOT NULL,
            summary_md      TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ass_snapshot_at
            ON attack_surface_snapshots(snapshot_at);

        CREATE TABLE IF NOT EXISTS compliance_evidence (
            control_id     TEXT NOT NULL,
            evidence_kind  TEXT NOT NULL,
              -- document|decision|policy|runbook|threat_model
            evidence_id    TEXT NOT NULL,
            confidence     REAL NOT NULL DEFAULT 1.0,
            captured_at    REAL NOT NULL,
            PRIMARY KEY (control_id, evidence_kind, evidence_id)
        );
        CREATE INDEX IF NOT EXISTS idx_ce_control
            ON compliance_evidence(control_id);

        -- ----- Phase 15: lessons + glossary + ownership -----

        CREATE TABLE IF NOT EXISTS lessons (
            id                TEXT PRIMARY KEY,
            title             TEXT NOT NULL,
            body_md           TEXT NOT NULL,
            body_md_redacted  TEXT NOT NULL,
            source_kind       TEXT NOT NULL,
              -- postmortem|design_review|tabletop|incident|user
            source_id         TEXT NOT NULL,
            tags              TEXT NOT NULL DEFAULT '[]',
            scope_entity_ids  TEXT NOT NULL DEFAULT '[]',
            captured_at       REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_lessons_captured
            ON lessons(captured_at);
        CREATE INDEX IF NOT EXISTS idx_lessons_source
            ON lessons(source_kind, source_id);

        CREATE TABLE IF NOT EXISTS glossary (
            id                  TEXT PRIMARY KEY,
            term                TEXT NOT NULL,
            term_normalized     TEXT NOT NULL,
            definition          TEXT NOT NULL,
            aliases             TEXT NOT NULL DEFAULT '[]',
            confirmed           INTEGER NOT NULL DEFAULT 0,
            first_seen_doc_id   TEXT REFERENCES documents(id),
            occurrences         INTEGER NOT NULL DEFAULT 1,
            updated_at          REAL NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_glossary_term
            ON glossary(term_normalized);

        CREATE TABLE IF NOT EXISTS owned_entities (
            user_id    INTEGER NOT NULL DEFAULT 1,
            entity_id  TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            role       TEXT NOT NULL,    -- owner|reviewer|consulted|informed
            set_at     REAL NOT NULL,
            PRIMARY KEY (user_id, entity_id)
        );

        -- ----- Redesign: org / team / project hierarchy -----

        CREATE TABLE IF NOT EXISTS organizations (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            description TEXT,
            industry    TEXT,
            created_at  INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS teams (
            id          TEXT PRIMARY KEY,
            org_id      TEXT NOT NULL REFERENCES organizations(id),
            name        TEXT NOT NULL,
            description TEXT,
            color       TEXT NOT NULL DEFAULT '#6c5ce7',
            icon        TEXT NOT NULL DEFAULT '🛡️',
            status      TEXT NOT NULL DEFAULT 'active',
            created_at  INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_teams_org ON teams(org_id);
        CREATE INDEX IF NOT EXISTS idx_teams_status ON teams(status);

        -- ----- Phase 16: project compartmentalization -----

        CREATE TABLE IF NOT EXISTS projects (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            description TEXT,
            emoji       TEXT NOT NULL DEFAULT '🔐',
            created_at  REAL NOT NULL
        );

        -- ----- Redesign: first-hire intake + security program building -----

        CREATE TABLE IF NOT EXISTS intake_interview (
            id           TEXT PRIMARY KEY,
            created_at   REAL NOT NULL,
            completed_at REAL,
            answers      TEXT NOT NULL DEFAULT '{}',
            kb_seeded    INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS asset_inventory (
            id                  TEXT PRIMARY KEY,
            created_at          REAL NOT NULL,
            updated_at          REAL NOT NULL,
            capability_category TEXT NOT NULL,
            tool_name           TEXT,
            deployment_status   TEXT NOT NULL DEFAULT 'none',
            coverage_notes      TEXT,
            known_gaps          TEXT,
            project_id          TEXT REFERENCES projects(id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_asset_inv_category
            ON asset_inventory(capability_category);

        CREATE TABLE IF NOT EXISTS ninety_day_plan (
            id           TEXT PRIMARY KEY,
            created_at   REAL NOT NULL,
            generated_at REAL NOT NULL,
            items        TEXT NOT NULL DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS policy_artifact (
            id                  TEXT PRIMARY KEY,
            kind                TEXT NOT NULL,
            created_at          REAL NOT NULL,
            updated_at          REAL NOT NULL,
            content_md          TEXT NOT NULL DEFAULT '',
            content_md_redacted TEXT NOT NULL DEFAULT '',
            status              TEXT NOT NULL DEFAULT 'draft',
            linked_decision_ids TEXT NOT NULL DEFAULT '[]',
            version             INTEGER NOT NULL DEFAULT 1,
            project_id          TEXT REFERENCES projects(id)
        );
        CREATE INDEX IF NOT EXISTS idx_policy_artifact_kind
            ON policy_artifact(kind, updated_at);

        -- ----- Ops: scheduler durability + backup ledger -----

        -- Last-fired markers for the cron-ish scheduler. Replaces the
        -- previous in-memory _LAST_FIRED dict so restarts don't double-
        -- fire (or skip) daily jobs.
        CREATE TABLE IF NOT EXISTS scheduler_state (
            job_name      TEXT PRIMARY KEY,   -- digest|reflection|journal_prompt|auto_briefs|attack_surface_snapshot|weekly_backup
            last_fired_at REAL NOT NULL,
            last_label    TEXT NOT NULL       -- YYYY-MM-DD (local) or YYYY-Www for weekly jobs
        );

        -- Backup ledger so we can prune old files when retention overflows.
        CREATE TABLE IF NOT EXISTS backup_log (
            id          TEXT PRIMARY KEY,
            path        TEXT NOT NULL,
            size_bytes  INTEGER,
            created_at  REAL NOT NULL,
            status      TEXT NOT NULL DEFAULT 'ok'  -- ok|failed
        );
        CREATE INDEX IF NOT EXISTS idx_backup_log_created
            ON backup_log(created_at);
        """
    )
    _migrate_app_state_columns(conn)
    _migrate_project_columns(conn)
    _migrate_project_fields(conn)
    _migrate_reports_cache_columns(conn)
    _seed_default_project(conn)
    _migrate_unscoped_data(conn)
    _migrate_projects_team_fields(conn)
    _seed_org_team(conn)
    _migrate_dfd_columns(conn)
    _migrate_risk_register(conn)
    _migrate_ir_runbooks(conn)
    _init_vec_table(conn)
    # Redesign migrations
    _migrate_intake_fields(conn)
    _migrate_conversation_mode(conn)
    _migrate_project_starter_template(conn)
    _migrate_vulnerability_triage(conn)
    _migrate_decisions_founding(conn)


def _add_col_safe(conn: sqlite3.Connection, table: str, col_def: str) -> None:
    """Add a column to an existing table if it doesn't already exist."""
    existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    col_name = col_def.split()[0]
    if col_name not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")


def _migrate_app_state_columns(conn: sqlite3.Connection) -> None:
    """Additive migration for Phase-8+ columns on app_state."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(app_state)")}
    if "tenure_started_at" not in cols:
        conn.execute("ALTER TABLE app_state ADD COLUMN tenure_started_at REAL")
    if "last_journal_at" not in cols:
        conn.execute("ALTER TABLE app_state ADD COLUMN last_journal_at REAL")
    # Phase 15: pointer to the curated security-philosophy document.
    if "philosophy_doc_id" not in cols:
        conn.execute("ALTER TABLE app_state ADD COLUMN philosophy_doc_id TEXT")
    # Phase 16: active project context.
    if "active_project_id" not in cols:
        conn.execute("ALTER TABLE app_state ADD COLUMN active_project_id TEXT REFERENCES projects(id)")


def _migrate_reports_cache_columns(conn: sqlite3.Connection) -> None:
    """Add cache token columns to reports table (token-counter fix)."""
    _add_col_safe(conn, "reports", "cache_read_in INTEGER")
    _add_col_safe(conn, "reports", "cache_create_in INTEGER")


def _migrate_project_columns(conn: sqlite3.Connection) -> None:
    """Add project_id to key artifact tables (Phase 16)."""
    for table in ("documents", "conversations", "reports",
                  "threat_models", "design_reviews", "postmortems_drafts", "tabletops"):
        _add_col_safe(conn, table, "project_id TEXT REFERENCES projects(id)")


def _migrate_project_fields(conn: sqlite3.Connection) -> None:
    """Add color and notes to the projects table (tankinstuction Phase 1)."""
    _add_col_safe(conn, "projects", "color TEXT NOT NULL DEFAULT '#6366f1'")
    _add_col_safe(conn, "projects", "notes TEXT NOT NULL DEFAULT ''")


def _migrate_unscoped_data(conn: sqlite3.Connection) -> None:
    """Assign artifact rows with no project_id to the Default project (tankinstuction Phase 7)."""
    import logging as _logging
    _log = _logging.getLogger("tank")
    tables = ["documents", "conversations", "reports",
              "threat_models", "design_reviews", "postmortems_drafts", "tabletops"]
    for table in tables:
        try:
            count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE project_id IS NULL"
            ).fetchone()[0]
            if count:
                _log.warning("[migration] %d unscoped rows in %s → assigning to 'default'", count, table)
                conn.execute(
                    f"UPDATE {table} SET project_id='default' WHERE project_id IS NULL"
                )
        except sqlite3.OperationalError:
            pass  # table may not exist yet on first run


def _seed_default_project(conn: sqlite3.Connection) -> None:
    """Create the Default project if the projects table is empty."""
    import time as _t
    row = conn.execute("SELECT id FROM projects LIMIT 1").fetchone()
    if row:
        # Backfill color on the default project in case it predates Phase 1.
        conn.execute(
            "UPDATE projects SET color='#6366f1' WHERE id='default' AND (color IS NULL OR color='')"
        )
        return
    conn.execute(
        "INSERT INTO projects (id, name, description, emoji, color, notes, created_at) "
        "VALUES ('default', 'Default', 'Default project for all existing data.', '🔐', '#6366f1', '', ?)",
        (_t.time(),),
    )


def _migrate_projects_team_fields(conn: sqlite3.Connection) -> None:
    """Add team/org hierarchy and new display fields to projects (redesign)."""
    _add_col_safe(conn, "projects", "team_id TEXT REFERENCES teams(id)")
    _add_col_safe(conn, "projects", "org_id TEXT REFERENCES organizations(id)")
    _add_col_safe(conn, "projects", "status TEXT NOT NULL DEFAULT 'active'")
    _add_col_safe(conn, "projects", "tags TEXT NOT NULL DEFAULT '[]'")
    _add_col_safe(conn, "projects", "risk_level TEXT NOT NULL DEFAULT 'medium'")
    _add_col_safe(conn, "projects", "icon TEXT NOT NULL DEFAULT '📦'")
    _add_col_safe(conn, "projects", "last_activity_at INTEGER")


def _seed_org_team(conn: sqlite3.Connection) -> None:
    """Create default org + team and wire all existing projects to them (idempotent)."""
    import logging as _logging
    import time as _t
    import uuid as _uuid
    _log = _logging.getLogger("tank")

    # Only seed once — if orgs already exist, nothing to do.
    existing_org = conn.execute("SELECT id FROM organizations LIMIT 1").fetchone()
    if existing_org:
        # Still backfill any projects missing team_id in case migration was partial.
        default_team = conn.execute(
            "SELECT id FROM teams ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        if default_team:
            conn.execute(
                "UPDATE projects SET team_id=?, org_id=(SELECT org_id FROM teams WHERE id=?) "
                "WHERE team_id IS NULL",
                (default_team["id"], default_team["id"]),
            )
        return

    org_id = _uuid.uuid4().hex[:12]
    team_id = _uuid.uuid4().hex[:12]
    now = int(_t.time())

    conn.execute(
        "INSERT INTO organizations (id, name, description, industry, created_at) "
        "VALUES (?, 'My Organization', '', '', ?)",
        (org_id, now),
    )
    conn.execute(
        "INSERT INTO teams (id, org_id, name, description, color, icon, status, created_at) "
        "VALUES (?, ?, 'Unassigned', '', '#6c5ce7', '🛡️', 'active', ?)",
        (team_id, org_id, now),
    )
    # Assign all existing projects to the default team.
    count = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    conn.execute(
        "UPDATE projects SET team_id=?, org_id=? WHERE team_id IS NULL",
        (team_id, org_id),
    )
    # Create catch-all "Imported Data" project for orphaned artifact rows.
    tables_with_project = [
        "documents", "conversations", "reports",
        "threat_models", "design_reviews", "postmortems_drafts", "tabletops",
    ]
    orphan_total = 0
    for tbl in tables_with_project:
        try:
            n = conn.execute(
                f"SELECT COUNT(*) FROM {tbl} WHERE project_id IS NULL"
            ).fetchone()[0]
            orphan_total += n
        except sqlite3.OperationalError:
            pass

    if orphan_total:
        catch_id = "imported"
        existing = conn.execute(
            "SELECT id FROM projects WHERE id=?", (catch_id,)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO projects (id, name, description, emoji, color, notes, "
                "team_id, org_id, status, tags, risk_level, icon, created_at) "
                "VALUES (?, 'Imported Data', 'Auto-created for pre-migration data.', "
                "'📦', '#6366f1', '', ?, ?, 'active', '[]', 'medium', '📦', ?)",
                (catch_id, team_id, org_id, now),
            )
        for tbl in tables_with_project:
            try:
                conn.execute(
                    f"UPDATE {tbl} SET project_id=? WHERE project_id IS NULL",
                    (catch_id,),
                )
            except sqlite3.OperationalError:
                pass

    _log.info(
        "[TANK MIGRATION] Created org %s, team 'Unassigned' (%s), "
        "migrated %d existing projects, %d orphan artifact rows → 'Imported Data'",
        org_id, team_id, count, orphan_total,
    )


def _migrate_ir_runbooks(conn: sqlite3.Connection) -> None:
    """Create the ir_runbooks table (Gap 5)."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ir_runbooks (
            id                  TEXT PRIMARY KEY,
            service_entity_id   TEXT REFERENCES entities(id) ON DELETE SET NULL,
            threat_scenario     TEXT NOT NULL,
            severity_trigger    TEXT NOT NULL DEFAULT 'any',
            runbook_md          TEXT NOT NULL,
            runbook_md_redacted TEXT NOT NULL,
            contacts_json       TEXT NOT NULL DEFAULT '[]',
            escalation_json     TEXT NOT NULL DEFAULT '[]',
            version             INTEGER NOT NULL DEFAULT 1,
            generated_at        INTEGER NOT NULL,
            confirmed_by_user   INTEGER NOT NULL DEFAULT 0,
            tabletop_id         TEXT REFERENCES tabletops(id) ON DELETE SET NULL,
            project_id          TEXT REFERENCES projects(id)
        );
        CREATE INDEX IF NOT EXISTS idx_ir_service
            ON ir_runbooks(service_entity_id, generated_at);
        CREATE INDEX IF NOT EXISTS idx_ir_generated
            ON ir_runbooks(generated_at);
        """
    )


def _migrate_risk_register(conn: sqlite3.Connection) -> None:
    """Create risk register, vulnerabilities intake, and program snapshot tables."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS risks (
            id                   TEXT PRIMARY KEY,
            title                TEXT NOT NULL,
            description          TEXT NOT NULL,
            category             TEXT NOT NULL,
            inherent_likelihood  INTEGER NOT NULL DEFAULT 3,
            inherent_impact      INTEGER NOT NULL DEFAULT 3,
            controls_json        TEXT NOT NULL DEFAULT '[]',
            residual_likelihood  INTEGER NOT NULL DEFAULT 3,
            residual_impact      INTEGER NOT NULL DEFAULT 3,
            treatment            TEXT NOT NULL DEFAULT 'mitigate',
            treatment_rationale  TEXT,
            owner_entity_id      TEXT REFERENCES entities(id),
            status               TEXT NOT NULL DEFAULT 'open',
            review_at            INTEGER,
            scope_entity_ids     TEXT NOT NULL DEFAULT '[]',
            decision_id          TEXT REFERENCES decisions(id),
            project_id           TEXT REFERENCES projects(id),
            created_at           INTEGER NOT NULL,
            updated_at           INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_risks_status
            ON risks(status, updated_at);
        CREATE INDEX IF NOT EXISTS idx_risks_category
            ON risks(category);
        CREATE INDEX IF NOT EXISTS idx_risks_review_at
            ON risks(review_at);

        CREATE TABLE IF NOT EXISTS vulnerabilities (
            id                   TEXT PRIMARY KEY,
            cve_id               TEXT,
            title                TEXT NOT NULL,
            description          TEXT,
            cvss_score           REAL,
            cvss_vector          TEXT,
            severity             TEXT NOT NULL DEFAULT 'medium',
            status               TEXT NOT NULL DEFAULT 'open',
            source               TEXT NOT NULL DEFAULT 'manual',
            affected_service_ids TEXT NOT NULL DEFAULT '[]',
            owner_entity_id      TEXT REFERENCES entities(id),
            due_at               INTEGER,
            accepted_rationale   TEXT,
            source_doc_id        TEXT REFERENCES documents(id),
            external_ref         TEXT,
            project_id           TEXT REFERENCES projects(id),
            created_at           INTEGER NOT NULL,
            updated_at           INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_vulns_status_severity
            ON vulnerabilities(status, severity);
        CREATE INDEX IF NOT EXISTS idx_vulns_source
            ON vulnerabilities(source);
        CREATE INDEX IF NOT EXISTS idx_vulns_due_at
            ON vulnerabilities(due_at);

        CREATE TABLE IF NOT EXISTS security_program_snapshots (
            id           TEXT PRIMARY KEY,
            snapshot_at  INTEGER NOT NULL,
            metrics_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sps_snapshot_at
            ON security_program_snapshots(snapshot_at);
        """
    )


def _migrate_dfd_columns(conn: sqlite3.Connection) -> None:
    """Add input_format and project_id columns to dfd_analyses (DFD revamp)."""
    _add_col_safe(conn, "dfd_analyses", "input_format TEXT")
    _add_col_safe(conn, "dfd_analyses", "project_id TEXT")
    _add_col_safe(conn, "dfd_analyses", "cached INTEGER NOT NULL DEFAULT 0")


def _migrate_intake_fields(conn: sqlite3.Connection) -> None:
    """Add first-hire intake and org-profile fields to app_state."""
    _add_col_safe(conn, "app_state", "intake_completed INTEGER NOT NULL DEFAULT 0")
    _add_col_safe(conn, "app_state", "kb_bootstrap_stage TEXT NOT NULL DEFAULT 'none'")
    _add_col_safe(conn, "app_state", "industry TEXT")
    _add_col_safe(conn, "app_state", "customer_type TEXT")
    _add_col_safe(conn, "app_state", "approx_team_size TEXT")
    _add_col_safe(conn, "app_state", "compliance_targets TEXT NOT NULL DEFAULT '[]'")


def _migrate_conversation_mode(conn: sqlite3.Connection) -> None:
    """Add discovery mode flag to conversations."""
    _add_col_safe(conn, "conversations", "mode TEXT NOT NULL DEFAULT 'normal'")


def _migrate_project_starter_template(conn: sqlite3.Connection) -> None:
    """Mark auto-created onboarding template projects."""
    _add_col_safe(conn, "projects", "starter_template INTEGER NOT NULL DEFAULT 0")


def _migrate_vulnerability_triage(conn: sqlite3.Connection) -> None:
    """Add triage workflow fields to vulnerabilities table."""
    _add_col_safe(conn, "vulnerabilities", "triage_status TEXT NOT NULL DEFAULT 'new'")
    _add_col_safe(conn, "vulnerabilities", "assigned_to TEXT")
    _add_col_safe(conn, "vulnerabilities", "promoted_to_risk_id TEXT REFERENCES risks(id)")


def _migrate_decisions_founding(conn: sqlite3.Connection) -> None:
    """Tag decisions made in the first 90 days as founding decisions."""
    _add_col_safe(conn, "decisions", "founding_decision INTEGER NOT NULL DEFAULT 0")


def _init_vec_table(conn: sqlite3.Connection) -> None:
    """Create the sqlite-vec virtual table if the extension loaded.

    Separated from the main executescript because vec0 requires the loaded
    extension and we want a clean degradation when it's missing.
    """
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0("
            "  chunk_id TEXT PRIMARY KEY,"
            "  embedding FLOAT[384]"
            ")"
        )
    except sqlite3.OperationalError:
        # sqlite-vec not loaded; FTS5 still works for keyword-only search.
        pass
