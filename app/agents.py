"""
Agent Integration Module - Orchestrates multi-agent system.

This module coordinates:
- Patterns Analyst (risk detection)
- Safety Auditor (final gate)
- Audit logging (immutable trail)

All agent decisions are logged to audit_log table.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import List, Literal, Optional

from sqlalchemy import insert

from app.database import audit_log_table, engine, signals_table
from app.patterns_analyst import CheckInData, PatternsAnalyst
from app.safety_auditor import SafetyAuditor, SafetyAuditResult


class AgentOrchestrator:
    """
    Orchestrates multi-agent system with audit logging.

    Flow:
    1. Patterns Analyst analyzes check-in history
    2. Safety Auditor reviews any member-facing output
    3. All decisions logged to audit_log
    """

    def __init__(self):
        self.patterns_analyst = PatternsAnalyst()
        self.safety_auditor = SafetyAuditor()

    def analyze_check_in(
        self,
        user_id: str,
        checkin_history: List[CheckInData],
    ) -> dict:
        """
        Run Patterns Analyst on check-in history.

        Returns structured analysis with signals and reason codes.
        Logs decision to audit_log.
        """
        analysis = self.patterns_analyst.analyze(user_id, checkin_history)

        self._log_audit(
            agent="patterns_analyst",
            decision=analysis.risk_band.upper(),
            user_id=user_id,
            input_refs={"checkins_count": len(checkin_history)},
            rules_fired=analysis.reason_codes,
            outputs={
                "risk_band": analysis.risk_band,
                "score": analysis.score,
                "confidence": analysis.confidence,
                "signals_count": len(analysis.signals),
            },
        )

        if analysis.signals:
            self._store_signals(user_id, analysis.signals)

        return {
            "risk_band": analysis.risk_band,
            "score": analysis.score,
            "signals": [
                {
                    "type": s.signal_type,
                    "window": s.window,
                    "value": s.value,
                    "baseline": s.baseline,
                    "deviation": s.deviation,
                    "confidence": s.confidence,
                }
                for s in analysis.signals
            ],
            "reason_codes": analysis.reason_codes,
            "confidence": analysis.confidence,
            "metadata": analysis.metadata,
        }

    def audit_message(
        self,
        content: str,
        content_type: Literal["member_message", "clinician_briefing", "family_update"],
        user_id: str,
        consent_scope: Optional[dict] = None,
    ) -> SafetyAuditResult:
        """
        Run Safety Auditor on outbound message.

        Returns audit result with APPROVED/BLOCKED decision.
        Logs decision to audit_log.
        """
        result = self.safety_auditor.audit(content, content_type, user_id, consent_scope)

        self._log_audit(
            agent="safety_auditor",
            decision=result.decision,
            user_id=user_id,
            input_refs={"content_type": content_type, "content_length": len(content)},
            rules_fired=result.policy_rules_triggered,
            outputs={
                "decision": result.decision,
                "redactions_count": len(result.redactions),
                "consent_verdict": result.consent_verdict,
                "escalation_required": result.escalation_required,
            },
            metadata=result.audit_metadata,
        )

        return result

    def _log_audit(
        self,
        agent: str,
        decision: str,
        user_id: str,
        input_refs: dict,
        rules_fired: List[str],
        outputs: dict,
        metadata: Optional[dict] = None,
    ) -> None:
        """Log agent decision to immutable audit_log table."""
        user_id_hash = hashlib.sha256(user_id.encode("utf-8")).hexdigest()

        stmt = insert(audit_log_table).values(
            agent=agent,
            decision=decision,
            user_id_hash=user_id_hash,
            input_refs=json.dumps(input_refs),
            rules_fired=json.dumps(rules_fired),
            outputs=json.dumps(outputs),
            metadata=json.dumps(metadata) if metadata else None,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        with engine.connect() as conn:
            conn.execute(stmt)
            conn.commit()

    def _store_signals(self, user_id: str, signals: list) -> None:
        """Store detected signals in signals table."""
        for signal in signals:
            stmt = insert(signals_table).values(
                user_id=user_id,
                signal_type=signal.signal_type,
                window=signal.window,
                value=signal.value,
                baseline=signal.baseline,
                deviation=signal.deviation,
                confidence=signal.confidence,
                reason_codes=json.dumps([]),  # Will be populated by reason code generation
                created_at=datetime.now(timezone.utc).isoformat(),
            )

            with engine.connect() as conn:
                conn.execute(stmt)
                conn.commit()
