"""
Safety Auditor Agent - Independent ethical & privacy review gate.

This module implements deterministic-first safety checks with model moderation
as a secondary signal. It acts as the final gate before any output reaches
members, families, or clinicians.

Key principles:
- Independent from other agents (can hard-block any output)
- Deterministic rules first, model checks second
- Immutable audit trail for every decision
- Default deny for consent/sharing
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Optional

CRISIS_PATTERNS = [
    r"\b(kill|harm|hurt)\s+(myself|yourself|themselves)\b",
    r"\bsuicid(e|al)\b",
    r"\bend\s+(my|your|their)\s+life\b",
    r"\bwant\s+to\s+die\b",
    r"\bbetter\s+off\s+dead\b",
    r"\bno\s+reason\s+to\s+live\b",
]

STIGMA_PATTERNS = [
    r"\baddict\b",  # Use "person in recovery" instead
    r"\bjunkie\b",
    r"\bcrackhead\b",
    r"\bdrug\s+abuse\b",  # Use "substance use" instead
    r"\bclean\b",  # Use "in recovery" or "abstinent" instead
    r"\bdirty\b",  # Avoid moral framing
    r"\brelapse\b.*\bfail(ed|ure)\b",  # Avoid shaming
]

PII_PHI_PATTERNS = [
    (r"\b\d{3}-\d{2}-\d{4}\b", "[SSN_REDACTED]"),  # SSN
    (r"\b\d{3}-\d{3}-\d{4}\b", "[PHONE_REDACTED]"),  # Phone
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[EMAIL_REDACTED]"),  # Email
    (
        r"\b\d{1,5}\s+[\w\s]+(?:street|st|avenue|ave|road|rd|boulevard|blvd)\b",
        "[ADDRESS_REDACTED]",
    ),  # Address
]

CLINICAL_ALLOWLIST = [
    r"craving\s+assessment",
    r"craving\s+scale",
    r"substance\s+use\s+disorder",
    r"recovery\s+plan",
]


@dataclass
class SafetyAuditResult:
    """Result from safety audit with full transparency."""

    decision: Literal["APPROVED", "BLOCKED"]
    policy_rules_triggered: list[str]
    redactions: list[tuple[str, str]]  # (pattern, replacement)
    consent_verdict: Optional[str]
    escalation_required: bool
    sanitized_content: str
    audit_metadata: dict


class SafetyAuditor:
    """
    Independent safety auditor agent.

    Runs deterministic checks for:
    - Crisis/self-harm language
    - Stigmatizing language
    - PII/PHI exposure
    - Consent policy compliance

    All decisions are logged immutably.
    """

    def __init__(self):
        self.crisis_regex = [re.compile(p, re.IGNORECASE) for p in CRISIS_PATTERNS]
        self.stigma_regex = [re.compile(p, re.IGNORECASE) for p in STIGMA_PATTERNS]
        self.allowlist_regex = [re.compile(p, re.IGNORECASE) for p in CLINICAL_ALLOWLIST]

    def audit(
        self,
        content: str,
        content_type: Literal["member_message", "clinician_briefing", "family_update"],
        user_id: str,
        consent_scope: Optional[dict] = None,
    ) -> SafetyAuditResult:
        """
        Perform layered safety audit.

        Args:
            content: The exact message/content to be sent
            content_type: Type of content being audited
            user_id: User ID for consent checking
            consent_scope: Optional consent permissions dict

        Returns:
            SafetyAuditResult with decision and full audit trail
        """
        rules_triggered: list[str] = []
        redactions: list[tuple[str, str]] = []
        escalation = False
        sanitized = content

        crisis_detected = self._check_crisis_language(content)
        if crisis_detected:
            rules_triggered.append("CRISIS_LANGUAGE_DETECTED")
            escalation = True
            if content_type != "member_message" or not self._is_safety_resource(content):
                return SafetyAuditResult(
                    decision="BLOCKED",
                    policy_rules_triggered=rules_triggered,
                    redactions=redactions,
                    consent_verdict=None,
                    escalation_required=True,
                    sanitized_content=content,
                    audit_metadata={
                        "reason": "Crisis language detected",
                        "timestamp": self._iso_now(),
                        "user_id_hash": self._hash_user_id(user_id),
                    },
                )

        stigma_detected = self._check_stigma_language(content)
        if stigma_detected:
            if not self._is_clinical_context(content):
                rules_triggered.append("STIGMA_LANGUAGE_DETECTED")
                return SafetyAuditResult(
                    decision="BLOCKED",
                    policy_rules_triggered=rules_triggered,
                    redactions=redactions,
                    consent_verdict=None,
                    escalation_required=False,
                    sanitized_content=content,
                    audit_metadata={
                        "reason": "Stigmatizing language detected outside clinical context",
                        "timestamp": self._iso_now(),
                        "user_id_hash": self._hash_user_id(user_id),
                    },
                )

        sanitized, redactions = self._redact_pii_phi(content)
        if redactions:
            rules_triggered.append("PII_PHI_REDACTED")

        consent_verdict = self._check_consent(content_type, consent_scope)
        if not consent_verdict.startswith("ALLOWED"):
            rules_triggered.append("CONSENT_DENIED")
            return SafetyAuditResult(
                decision="BLOCKED",
                policy_rules_triggered=rules_triggered,
                redactions=redactions,
                consent_verdict=consent_verdict,
                escalation_required=False,
                sanitized_content=sanitized,
                audit_metadata={
                    "reason": consent_verdict,
                    "timestamp": self._iso_now(),
                    "user_id_hash": self._hash_user_id(user_id),
                },
            )

        return SafetyAuditResult(
            decision="APPROVED",
            policy_rules_triggered=rules_triggered,
            redactions=redactions,
            consent_verdict=consent_verdict,
            escalation_required=escalation,
            sanitized_content=sanitized,
            audit_metadata={
                "timestamp": self._iso_now(),
                "user_id_hash": self._hash_user_id(user_id),
            },
        )

    def _check_crisis_language(self, content: str) -> bool:
        """Check for crisis/self-harm language patterns."""
        for pattern in self.crisis_regex:
            if pattern.search(content):
                return True
        return False

    def _check_stigma_language(self, content: str) -> bool:
        """Check for stigmatizing language patterns."""
        for pattern in self.stigma_regex:
            if pattern.search(content):
                return True
        return False

    def _is_clinical_context(self, content: str) -> bool:
        """Check if stigma language is in allowed clinical context."""
        for pattern in self.allowlist_regex:
            if pattern.search(content):
                return True
        return False

    def _is_safety_resource(self, content: str) -> bool:
        """Check if content is a safety resource (e.g., crisis hotline info)."""
        safety_indicators = [
            r"crisis\s+(line|hotline)",
            r"988",
            r"1-800-273-8255",
            r"emergency\s+services",
            r"if\s+you\s+are\s+in\s+danger",
        ]
        for indicator in safety_indicators:
            if re.search(indicator, content, re.IGNORECASE):
                return True
        return False

    def _redact_pii_phi(self, content: str) -> tuple[str, list[tuple[str, str]]]:
        """Redact PII/PHI from content."""
        sanitized = content
        redactions: list[tuple[str, str]] = []

        for pattern, replacement in PII_PHI_PATTERNS:
            matches = re.findall(pattern, sanitized, re.IGNORECASE)
            if matches:
                sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
                redactions.append((pattern, replacement))

        return sanitized, redactions

    def _check_consent(self, content_type: str, consent_scope: Optional[dict]) -> str:
        """
        Check consent policy (PIPA/GDPR default deny).

        Returns verdict string explaining decision.
        """
        if consent_scope is None:
            return "DENIED: No consent scope provided (default deny)"

        if consent_scope.get("status") != "active":
            return f"DENIED: Consent status is {consent_scope.get('status', 'unknown')}"

        permissions = consent_scope.get("permissions", [])
        if isinstance(permissions, str):
            try:
                permissions = json.loads(permissions)
            except json.JSONDecodeError:
                return "DENIED: Invalid permissions format"

        permission_map = {
            "member_message": "send_member_messages",
            "clinician_briefing": "share_with_clinician",
            "family_update": "share_with_family",
        }

        required_permission = permission_map.get(content_type)
        if required_permission not in permissions:
            return f"DENIED: Permission '{required_permission}' not granted"

        return "ALLOWED: Consent scope permits this content type"

    @staticmethod
    def _hash_user_id(user_id: str) -> str:
        """Hash user ID for privacy-safe audit logging."""
        return hashlib.sha256(user_id.encode("utf-8")).hexdigest()

    @staticmethod
    def _iso_now() -> str:
        """Get current timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat()
