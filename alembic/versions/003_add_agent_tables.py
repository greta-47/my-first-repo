"""Add agent system tables

Revision ID: 003
Revises: 002
Create Date: 2025-10-16

"""

import sqlalchemy as sa

from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consent_scopes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("scope_type", sa.String(), nullable=False),  # clinician, family, etc.
        sa.Column("permissions", sa.Text(), nullable=False),  # JSON list of permissions
        sa.Column("status", sa.String(), nullable=False),  # active, revoked
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.email"], ondelete="CASCADE"),
    )
    op.create_index("ix_consent_scopes_user_id", "consent_scopes", ["user_id"])
    op.create_index("ix_consent_scopes_status", "consent_scopes", ["status"])

    op.create_table(
        "signals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("signal_type", sa.String(), nullable=False),  # sleep_low, isolation_up, etc.
        sa.Column("window", sa.String(), nullable=False),  # 3day, 14day, 30day
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("baseline", sa.Float(), nullable=True),
        sa.Column("deviation", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("reason_codes", sa.Text(), nullable=False),  # JSON list
        sa.Column("created_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_signals_user_id", "signals", ["user_id"])
    op.create_index("ix_signals_created_at", "signals", ["created_at"])
    op.create_index("ix_signals_signal_type", "signals", ["signal_type"])

    op.create_table(
        "plan_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("template_key", sa.String(), nullable=False),  # peer_support_sms, etc.
        sa.Column("phase", sa.String(), nullable=False),  # week1, week2, etc.
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("tasks", sa.Text(), nullable=False),  # JSON list of tasks
        sa.Column("kpis", sa.Text(), nullable=False),  # JSON list of KPIs
        sa.Column("trigger_conditions", sa.Text(), nullable=True),  # JSON conditions
        sa.Column("reading_level", sa.Integer(), nullable=False),  # 6-8
        sa.Column("evidence_refs", sa.Text(), nullable=True),  # JSON list of citations
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_key"),
    )
    op.create_index("ix_plan_templates_template_key", "plan_templates", ["template_key"])

    op.create_table(
        "recovery_plans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("phase", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),  # active, completed, paused
        sa.Column("goals", sa.Text(), nullable=False),  # JSON list
        sa.Column("tasks", sa.Text(), nullable=False),  # JSON list
        sa.Column("kpis", sa.Text(), nullable=False),  # JSON dict
        sa.Column("review_date", sa.String(), nullable=False),
        sa.Column("fallback_plan", sa.Text(), nullable=True),  # JSON
        sa.Column("reason_codes", sa.Text(), nullable=False),  # JSON list
        sa.Column("adaptations_applied", sa.Text(), nullable=True),  # JSON list
        sa.Column("consent_scope_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["template_id"], ["plan_templates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["consent_scope_id"], ["consent_scopes.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_recovery_plans_user_id", "recovery_plans", ["user_id"])
    op.create_index("ix_recovery_plans_status", "recovery_plans", ["status"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agent", sa.String(), nullable=False),  # patterns_analyst, safety_auditor, etc.
        sa.Column("decision", sa.String(), nullable=False),  # APPROVED, BLOCKED, etc.
        sa.Column("user_id_hash", sa.String(), nullable=False),  # SHA256 hash
        sa.Column("input_refs", sa.Text(), nullable=False),  # JSON with hashed references
        sa.Column("rules_fired", sa.Text(), nullable=False),  # JSON list
        sa.Column("outputs", sa.Text(), nullable=False),  # JSON
        sa.Column("metadata", sa.Text(), nullable=True),  # JSON
        sa.Column("created_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_agent", "audit_log", ["agent"])
    op.create_index("ix_audit_log_decision", "audit_log", ["decision"])
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])
    op.create_index("ix_audit_log_user_id_hash", "audit_log", ["user_id_hash"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_user_id_hash", table_name="audit_log")
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
    op.drop_index("ix_audit_log_decision", table_name="audit_log")
    op.drop_index("ix_audit_log_agent", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index("ix_recovery_plans_status", table_name="recovery_plans")
    op.drop_index("ix_recovery_plans_user_id", table_name="recovery_plans")
    op.drop_table("recovery_plans")

    op.drop_index("ix_plan_templates_template_key", table_name="plan_templates")
    op.drop_table("plan_templates")

    op.drop_index("ix_signals_signal_type", table_name="signals")
    op.drop_index("ix_signals_created_at", table_name="signals")
    op.drop_index("ix_signals_user_id", table_name="signals")
    op.drop_table("signals")

    op.drop_index("ix_consent_scopes_status", table_name="consent_scopes")
    op.drop_index("ix_consent_scopes_user_id", table_name="consent_scopes")
    op.drop_table("consent_scopes")
