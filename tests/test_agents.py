"""Tests for agent system (Safety Auditor and Patterns Analyst)."""

from datetime import datetime, timedelta, timezone

from app.patterns_analyst import CheckInData, PatternsAnalyst
from app.safety_auditor import SafetyAuditor


class TestSafetyAuditor:
    """Test suite for Safety Auditor agent."""

    def setup_method(self):
        """Set up test fixtures."""
        self.auditor = SafetyAuditor()

    def test_crisis_language_blocking(self):
        """Test that crisis language is blocked."""
        content = "I want to kill myself"
        result = self.auditor.audit(
            content=content,
            content_type="member_message",
            user_id="test_user",
            consent_scope={"status": "active", "permissions": ["send_member_messages"]},
        )

        assert result.decision == "BLOCKED"
        assert "CRISIS_LANGUAGE_DETECTED" in result.policy_rules_triggered
        assert result.escalation_required is True

    def test_crisis_language_safety_resource_allowed(self):
        """Test that safety resource messages with crisis language are allowed."""
        content = (
            "If you are in danger or thinking about suicide, contact BC Crisis Line: 1-800-784-2433"
        )
        result = self.auditor.audit(
            content=content,
            content_type="member_message",
            user_id="test_user",
            consent_scope={"status": "active", "permissions": ["send_member_messages"]},
        )

        assert result.decision == "APPROVED"
        assert result.escalation_required is True

    def test_stigma_language_blocking(self):
        """Test that stigmatizing language is blocked."""
        content = "You're just an addict who failed again"
        result = self.auditor.audit(
            content=content,
            content_type="member_message",
            user_id="test_user",
            consent_scope={"status": "active", "permissions": ["send_member_messages"]},
        )

        assert result.decision == "BLOCKED"
        assert "STIGMA_LANGUAGE_DETECTED" in result.policy_rules_triggered

    def test_stigma_language_clinical_context_allowed(self):
        """Test that stigma language in clinical context is allowed."""
        content = "Your substance use disorder craving assessment shows improvement"
        result = self.auditor.audit(
            content=content,
            content_type="clinician_briefing",
            user_id="test_user",
            consent_scope={"status": "active", "permissions": ["share_with_clinician"]},
        )

        assert result.decision == "APPROVED"

    def test_pii_redaction(self):
        """Test that PII is redacted from content."""
        content = "Contact me at 555-123-4567 or john@example.com"
        result = self.auditor.audit(
            content=content,
            content_type="member_message",
            user_id="test_user",
            consent_scope={"status": "active", "permissions": ["send_member_messages"]},
        )

        assert result.decision == "APPROVED"
        assert len(result.redactions) > 0
        assert (
            "[PHONE_REDACTED]" in result.sanitized_content
            or "[EMAIL_REDACTED]" in result.sanitized_content
        )

    def test_consent_check_no_scope(self):
        """Test that messages are blocked when no consent scope provided."""
        content = "This is a normal message"
        result = self.auditor.audit(
            content=content,
            content_type="family_update",
            user_id="test_user",
            consent_scope=None,
        )

        assert result.decision == "BLOCKED"
        assert "CONSENT_DENIED" in result.policy_rules_triggered
        assert "No consent scope provided" in result.consent_verdict

    def test_consent_check_inactive_status(self):
        """Test that messages are blocked when consent is inactive."""
        content = "This is a normal message"
        result = self.auditor.audit(
            content=content,
            content_type="member_message",
            user_id="test_user",
            consent_scope={"status": "revoked", "permissions": ["send_member_messages"]},
        )

        assert result.decision == "BLOCKED"
        assert result.consent_verdict.startswith("DENIED:")

    def test_consent_check_missing_permission(self):
        """Test that messages are blocked when permission not granted."""
        content = "This is a clinician briefing"
        result = self.auditor.audit(
            content=content,
            content_type="clinician_briefing",
            user_id="test_user",
            consent_scope={
                "status": "active",
                "permissions": ["send_member_messages"],
            },  # Wrong permission
        )

        assert result.decision == "BLOCKED"
        assert "Permission 'share_with_clinician' not granted" in result.consent_verdict

    def test_approved_message(self):
        """Test that clean messages with proper consent are approved."""
        content = "Your recovery progress looks positive. Keep up the good work!"
        result = self.auditor.audit(
            content=content,
            content_type="member_message",
            user_id="test_user",
            consent_scope={"status": "active", "permissions": ["send_member_messages"]},
        )

        assert result.decision == "APPROVED"
        assert result.consent_verdict.startswith("ALLOWED:")
        assert result.escalation_required is False


class TestPatternsAnalyst:
    """Test suite for Patterns Analyst agent."""

    def setup_method(self):
        """Set up test fixtures."""
        self.analyst = PatternsAnalyst()

    def _create_checkin(self, days_ago: int, **kwargs) -> CheckInData:
        """Helper to create check-in with timestamp."""
        ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
        defaults = {
            "user_id": "test_user",
            "adherence": 70,
            "mood_trend": 0,
            "cravings": 40,
            "sleep_hours": 7.0,
            "isolation": 30,
            "ts": ts,
        }
        defaults.update(kwargs)
        return CheckInData(**defaults)

    def test_insufficient_data(self):
        """Test that insufficient data state is returned for <3 check-ins."""
        history = [
            self._create_checkin(1),
            self._create_checkin(0),
        ]

        result = self.analyst.analyze("test_user", history)

        assert result.risk_band == "insufficient_data"
        assert result.score is None
        assert "INSUFFICIENT_DATA" in result.reason_codes
        assert result.confidence == 0.0

    def test_low_risk_pattern(self):
        """Test that low risk pattern is detected correctly."""
        history = [
            self._create_checkin(5, adherence=85, sleep_hours=7.5, isolation=20),
            self._create_checkin(3, adherence=80, sleep_hours=7.0, isolation=25),
            self._create_checkin(1, adherence=90, sleep_hours=8.0, isolation=15),
        ]

        result = self.analyst.analyze("test_user", history)

        assert result.risk_band == "low"
        assert result.score < 30
        assert len(result.signals) == 0  # No risk signals

    def test_sleep_disruption_signal(self):
        """Test that sleep disruption signal is detected."""
        history = [
            self._create_checkin(5, sleep_hours=7.0),
            self._create_checkin(3, sleep_hours=4.5),
            self._create_checkin(1, sleep_hours=4.0),
        ]

        result = self.analyst.analyze("test_user", history)

        sleep_signals = [s for s in result.signals if s.signal_type == "sleep_low"]
        assert len(sleep_signals) > 0
        assert "SLEEP_DISRUPTION" in result.reason_codes
        assert result.score > 0

    def test_isolation_increase_signal(self):
        """Test that isolation increase signal is detected."""
        history = [
            self._create_checkin(5, isolation=30),
            self._create_checkin(3, isolation=75),
            self._create_checkin(1, isolation=80),
        ]

        result = self.analyst.analyze("test_user", history)

        isolation_signals = [s for s in result.signals if s.signal_type == "isolation_up"]
        assert len(isolation_signals) > 0
        assert "SOCIAL_WITHDRAWAL" in result.reason_codes

    def test_adherence_decline_signal(self):
        """Test that adherence decline signal is detected."""
        history = [
            self._create_checkin(5, adherence=80),
            self._create_checkin(3, adherence=45),
            self._create_checkin(1, adherence=40),
        ]

        result = self.analyst.analyze("test_user", history)

        adherence_signals = [s for s in result.signals if s.signal_type == "adherence_low"]
        assert len(adherence_signals) > 0
        assert "ADHERENCE_DECLINE" in result.reason_codes

    def test_multiple_risk_factors(self):
        """Test that multiple risk factors trigger higher risk."""
        history = [
            self._create_checkin(5, sleep_hours=7.0, isolation=30, adherence=70),
            self._create_checkin(3, sleep_hours=4.5, isolation=75, adherence=45),
            self._create_checkin(1, sleep_hours=4.0, isolation=80, adherence=40),
        ]

        result = self.analyst.analyze("test_user", history)

        assert len(result.signals) >= 3
        assert "MULTIPLE_RISK_FACTORS" in result.reason_codes
        assert result.confidence > 0.7

    def test_baseline_calculation(self):
        """Test that baselines are calculated from history."""
        history = [
            self._create_checkin(10, sleep_hours=7.0),
            self._create_checkin(9, sleep_hours=7.2),
            self._create_checkin(8, sleep_hours=6.8),
            self._create_checkin(7, sleep_hours=7.1),
            self._create_checkin(1, sleep_hours=4.0),  # Deviation from baseline
        ]

        self.analyst.analyze("test_user", history)

        assert "test_user" in self.analyst.baselines_cache
        baselines = self.analyst.baselines_cache["test_user"]
        assert baselines["sleep_hours"] > 6.0
        assert baselines["is_default"] is False

    def test_window_analysis(self):
        """Test that different time windows are analyzed."""
        history = [
            self._create_checkin(40, sleep_hours=7.0),
            self._create_checkin(20, sleep_hours=7.0),
            self._create_checkin(10, sleep_hours=7.0),
            self._create_checkin(2, sleep_hours=4.0),
            self._create_checkin(1, sleep_hours=4.5),
        ]

        result = self.analyst.analyze("test_user", history)

        assert "3day" in result.windows
        assert "14day" in result.windows
        assert "30day" in result.windows
        assert result.windows["3day"]["available"] is True

    def test_combination_patterns(self):
        """Test that combination patterns are detected."""
        history = [
            self._create_checkin(5, sleep_hours=7.0, isolation=30),
            self._create_checkin(3, sleep_hours=4.5, isolation=75),
            self._create_checkin(1, sleep_hours=4.0, isolation=80),
        ]

        result = self.analyst.analyze("test_user", history)

        assert "SLEEP_ISOLATION_PATTERN" in result.reason_codes
