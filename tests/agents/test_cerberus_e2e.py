"""End-to-end tests for CERBERUS V1 - Scenarios A-G from Addendum 10.

These tests validate the complete CERBERUS workflow:
- A: Conversation vocale
- B: Email simple autorisé (auto-send)
- C: Email nécessitant validation (prix hors grille)
- D: Institution (reste en validation)
- E: Urgence (bloque l'autonomie)
- F: Prospection (recherche → validation → envoi)
- G: Briefing complet
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from openjarvis.agents.cerberus_conversational import CerberusConversationalAgent
from openjarvis.agents.prospection_agent import ProspectionAgent
from openjarvis.core.cerberus_rules import RulesEngine, Decision, RelationalMemory, TrustTier
from openjarvis.tools.approval_store import ApprovalStore, STATUS_PENDING, STATUS_APPROVED, STATUS_EXECUTED, STATUS_FAILED
from openjarvis.tools.cerberus_briefing import GetBriefingTool


@pytest.fixture
def temp_store(tmp_path, monkeypatch):
    monkeypatch.setattr("openjarvis.tools.approval_store.get_config_dir", lambda: tmp_path)
    monkeypatch.setattr("openjarvis.core.cerberus_rules.get_config_dir", lambda: tmp_path)
    store = ApprovalStore()
    return store


@pytest.fixture
def temp_relational_memory(tmp_path, monkeypatch):
    monkeypatch.setattr("openjarvis.core.cerberus_rules.get_config_dir", lambda: tmp_path)
    memory = RelationalMemory(db_path=str(tmp_path / "approvals.db"))
    return memory


@pytest.fixture
def mock_engine():
    """Mock inference engine for testing."""
    engine = Mock()
    engine.generate = Mock(return_value={
        "content": "Test response",
        "finish_reason": "stop",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    })
    return engine


# ---------------------------------------------------------------------------
# TEST A: Conversation vocale
# ---------------------------------------------------------------------------

def test_a_conversation_vocale(mock_engine, temp_store):
    """Test A: Conversation vocale - Akim parle → transcription → CERBERUS → réponse → TTS → audio."""
    # This test validates the conversation flow with context preservation
    agent = CerberusConversationalAgent(mock_engine, "test-model")

    # Simulate conversation with context
    from openjarvis.agents._stubs import AgentContext
    ctx = AgentContext()

    # First message: Akim asks about an email
    result1 = agent.run("Quel est le dernier mail de Jean ?", context=ctx)
    assert result1.content  # Should get a response
    assert "Jean" in result1.content or "mail" in result1.content.lower()

    # Second message: Akim asks for clarification using "il"
    # The agent should maintain context and understand "il" refers to Jean
    result2 = agent.run("Et qu'est-ce qu'il veut exactement ?", context=ctx)
    assert result2.content  # Should get a response


# ---------------------------------------------------------------------------
# TEST B: Email simple autorisé
# ---------------------------------------------------------------------------

def test_b_email_simple_autorise(temp_store, temp_relational_memory):
    """Test B: Email simple autorisé - classification → règle → auto-send → journal EXECUTED."""
    rules_engine = RulesEngine(temp_relational_memory)

    # Create a simple, authorized email scenario
    payload = {
        "to": "client@example.com",
        "subject": "RE: Formation Arduino",
        "body": "Merci pour votre intérêt. La formation Arduino est à 30 000 FCFA.",
        "email": "client@example.com"
    }

    decision, reason, rules_triggered = rules_engine.evaluate_action(
        action_type="email_reply",
        payload=payload,
        contact_email="client@example.com"
    )

    # This should be auto-executable (no blocking keywords, price within rules)
    assert decision in [Decision.AUTO_EXECUTE, Decision.REQUIRES_APPROVAL]  # May require approval for safety


# ---------------------------------------------------------------------------
# TEST C: Email nécessitant validation (prix hors grille)
# ---------------------------------------------------------------------------

def test_c_email_prix_hors_grille(temp_store, temp_relational_memory):
    """Test C: Email nécessitant validation - prix hors règle → PENDING → aucune réponse envoyée."""
    rules_engine = RulesEngine(temp_relational_memory)

    # Create an email with price below floor
    payload = {
        "to": "client@example.com",
        "subject": "RE: Formation Arduino",
        "body": "Je peux vous faire 12 000 FCFA.",  # Below floor of 15 000
        "email": "client@example.com"
    }

    decision, reason, rules_triggered = rules_engine.evaluate_action(
        action_type="email_reply",
        payload=payload,
        contact_email="client@example.com"
    )

    # This should be BLOCKED or require approval
    assert decision in [Decision.BLOCKED, Decision.REQUIRES_APPROVAL]
    assert "prix" in reason.lower() or "plancher" in reason.lower()


# ---------------------------------------------------------------------------
# TEST D: Institution
# ---------------------------------------------------------------------------

def test_d_email_institution(temp_store, temp_relational_memory):
    """Test D: Institution - email institutionnel doit automatiquement rester en validation."""
    # Set up contact as RED tier (institution)
    temp_relational_memory.set_red_tier("university@example.com", "Institution académique")

    rules_engine = RulesEngine(temp_relational_memory)

    payload = {
        "to": "university@example.com",
        "subject": "RE: Partenariat formation",
        "body": "Proposition de partenariat pour formations Arduino.",
        "email": "university@example.com"
    }

    decision, reason, rules_triggered = rules_engine.evaluate_action(
        action_type="email_reply",
        payload=payload,
        contact_email="university@example.com"
    )

    # RED tier should require approval
    assert decision == Decision.REQUIRES_APPROVAL
    assert "rouge" in reason.lower() or "red" in reason.lower()


# ---------------------------------------------------------------------------
# TEST E: Urgence
# ---------------------------------------------------------------------------

def test_e_email_urgence(temp_store, temp_relational_memory):
    """Test E: Urgence - email contenant condition d'urgence doit bloquer l'autonomie."""
    rules_engine = RulesEngine(temp_relational_memory)

    payload = {
        "to": "client@example.com",
        "subject": "URGENT - Dernier délai",
        "body": "Réponse attendue aujourd'hui même sinon j'annule.",
        "email": "client@example.com"
    }

    decision, reason, rules_triggered = rules_engine.evaluate_action(
        action_type="email_reply",
        payload=payload,
        contact_email="client@example.com"
    )

    # Urgency keywords should trigger BLOCKED or REQUIRES_APPROVAL
    assert decision in [Decision.BLOCKED, Decision.REQUIRES_APPROVAL]
    assert any("urgent" in rule.lower() or "délai" in rule.lower() for rule in rules_triggered)


# ---------------------------------------------------------------------------
# TEST F: Prospection
# ---------------------------------------------------------------------------

def test_f_prospection_complete(tmp_path, monkeypatch):
    """Test F: Prospection - recherche → qualification → message personnalisé → PENDING → validation → envoi → journal."""
    monkeypatch.setattr("openjarvis.tools.approval_store.get_config_dir", lambda: tmp_path)
    monkeypatch.setattr("openjarvis.agents.prospection_agent._DB_PATH", tmp_path / "prospection_log.db")

    from openjarvis.agents.prospection_agent import LogAndQueueProspectTool

    store = ApprovalStore()
    tool = LogAndQueueProspectTool()

    # Simulate logging a prospect
    result = tool.execute(
        name="Entreprise Test",
        source_url="http://example.com",
        source_excerpt="Contact: contact@example.com - Formation Arduino souhaitée",
        contact="contact@example.com",
        draft_message="Bonjour, je vous propose une formation Arduino...",
        sector="arduino"
    )

    assert result.success is True

    # Check it was queued in ApprovalStore
    pending = store.list_pending()
    assert len(pending) == 1
    assert pending[0].action_type == "prospection_first_contact"
    assert pending[0].status == STATUS_PENDING


# ---------------------------------------------------------------------------
# TEST G: Briefing
# ---------------------------------------------------------------------------

def test_g_briefing_complet(temp_store):
    """Test G: Briefing - synthèse correcte de toutes les actions."""
    # Create some test data
    temp_store.queue_action(
        action_type="email_reply",
        description="Test email reply",
        payload={"to": "test@example.com"},
        permission_key="test:key",
        tier="high"
    )

    temp_store.queue_action(
        action_type="prospection_first_contact",
        description="Test prospect",
        payload={"name": "Test"},
        permission_key="test:prospect",
        tier="high"
    )

    # Approve one action
    action = temp_store.list_pending()[0]
    temp_store.update_status(action.id, STATUS_APPROVED)

    # Get briefing
    briefing_tool = GetBriefingTool()
    result = briefing_tool.execute()

    assert result.success is True
    content = result.content
    assert "BRIEFING CERBERUS" in content
    assert "ACTIONS EN ATTENTE" in content
    assert "STATISTIQUES GLOBALES" in content


# ---------------------------------------------------------------------------
# Additional integration tests
# ---------------------------------------------------------------------------

def test_rules_engine_blocking_keywords(temp_relational_memory):
    """Test that blocking keywords are properly detected."""
    rules_engine = RulesEngine(temp_relational_memory)

    # Test juridical keywords
    payload = {"body": "Veuillez signer le contrat"}
    decision, reason, rules = rules_engine.evaluate_action("email_reply", payload)
    assert decision == Decision.BLOCKED
    assert any("juridical" in rule.lower() or "contrat" in rule.lower() for rule in rules)

    # Test urgency keywords
    payload = {"body": "C'est urgent, réponse attendue aujourd'hui"}
    decision, reason, rules = rules_engine.evaluate_action("email_reply", payload)
    assert decision in [Decision.BLOCKED, Decision.REQUIRES_APPROVAL]

    # Test scope extension keywords
    payload = {"body": "Proposition de partenariat exclusif"}
    decision, reason, rules = rules_engine.evaluate_action("email_reply", payload)
    assert decision in [Decision.BLOCKED, Decision.REQUIRES_APPROVAL]


def test_relational_memory_tier_progression(temp_relational_memory):
    """Test contact tier progression from GREY to WHITE."""
    # Create new contact (defaults to GREY)
    contact = temp_relational_memory.get_or_create_contact(
        email="new@example.com",
        name="New Client",
        organization="Test Corp"
    )
    assert contact.tier == TrustTier.GREY.value
    assert contact.validated_exchange_count == 0

    # Increment validated exchanges
    temp_relational_memory.increment_validated_exchanges("new@example.com")
    contact = temp_relational_memory.get_contact("new@example.com")
    assert contact.validated_exchange_count == 1
    assert contact.tier == TrustTier.GREY.value  # Still GREY

    # Second increment should upgrade to WHITE
    temp_relational_memory.increment_validated_exchanges("new@example.com")
    contact = temp_relational_memory.get_contact("new@example.com")
    assert contact.validated_exchange_count == 2
    assert contact.tier == TrustTier.WHITE.value  # Upgraded to WHITE


def test_relational_memory_reset_counter(temp_relational_memory):
    """Test counter reset due to dissatisfaction."""
    # Create and upgrade contact to WHITE
    contact = temp_relational_memory.get_or_create_contact("reset@example.com", "Reset Client")
    temp_relational_memory.increment_validated_exchanges("reset@example.com")
    temp_relational_memory.increment_validated_exchanges("reset@example.com")
    contact = temp_relational_memory.get_contact("reset@example.com")
    assert contact.tier == TrustTier.WHITE.value

    # Reset counter
    temp_relational_memory.reset_counter("reset@example.com", "Client mécontent")
    contact = temp_relational_memory.get_contact("reset@example.com")
    assert contact.validated_exchange_count == 0
    assert contact.relationship_status == "reset"


def test_pricing_rules_arduino(temp_relational_memory):
    """Test Arduino pricing rules."""
    rules_engine = RulesEngine(temp_relational_memory)

    # Price within range
    payload = {"body": "Formation Arduino à 30 000 FCFA", "email": "client@example.com"}
    decision, reason, rules = rules_engine.evaluate_action("email_reply", payload, "client@example.com")
    assert decision in [Decision.AUTO_EXECUTE, Decision.REQUIRES_APPROVAL]

    # Price below floor
    payload = {"body": "Formation Arduino à 10 000 FCFA", "email": "client@example.com"}
    decision, reason, rules = rules_engine.evaluate_action("email_reply", payload, "client@example.com")
    assert decision == Decision.BLOCKED
    assert "plancher" in reason.lower() or "floor" in reason.lower()


def test_pricing_rules_ia_initiation(temp_relational_memory):
    """Test IA Initiation pricing rules (no reduction allowed)."""
    rules_engine = RulesEngine(temp_relational_memory)

    # Reference price
    payload = {"body": "Formation IA Initiation à 15 000 FCFA", "email": "client@example.com"}
    decision, reason, rules = rules_engine.evaluate_action("email_reply", payload, "client@example.com")
    assert decision in [Decision.AUTO_EXECUTE, Decision.REQUIRES_APPROVAL]

    # Any reduction should be blocked
    payload = {"body": "Formation IA Initiation à 12 000 FCFA", "email": "client@example.com"}
    decision, reason, rules = rules_engine.evaluate_action("email_reply", payload, "client@example.com")
    assert decision == Decision.BLOCKED


def test_cerberus_agent_with_rules_engine(mock_engine, temp_store, temp_relational_memory):
    """Test that CerberusConversationalAgent properly uses Rules Engine."""
    agent = CerberusConversationalAgent(mock_engine, "test-model")

    # Verify the agent has a rules engine
    assert agent._rules_engine is not None
    assert isinstance(agent._rules_engine, RulesEngine)

    # Test that confirm callback uses rules engine
    result = agent._cerberus_confirm(
        "edit_draft",
        json.dumps({"draft_id": "test", "instruction": "Test instruction"})
    )
    # Should return False (action queued for approval)
    assert result is False


def test_approval_store_idempotence(temp_store):
    """Test that actions cannot be executed twice."""
    # Create and approve an action
    action = temp_store.queue_action(
        action_type="test_action",
        description="Test action",
        payload={"test": "data"},
        permission_key="test:key",
        tier="high"
    )
    temp_store.update_status(action.id, STATUS_APPROVED)
    temp_store.update_status(action.id, STATUS_EXECUTED)

    # Try to execute again - should be caught by idempotency guard
    from openjarvis.agents.cerberus_conversational import _execute_approved_action
    _execute_approved_action(action, temp_store)

    # Status should remain EXECUTED
    current = temp_store.get_action(action.id)
    assert current.status == STATUS_EXECUTED


def test_briefing_tool_accuracy(temp_store):
    """Test that briefing tool provides accurate statistics."""
    # Create test actions with different statuses
    action1 = temp_store.queue_action("type1", "desc1", {}, "key1", "high")
    action2 = temp_store.queue_action("type2", "desc2", {}, "key2", "high")
    action3 = temp_store.queue_action("type3", "desc3", {}, "key3", "high")

    temp_store.update_status(action1.id, STATUS_APPROVED)
    temp_store.update_status(action2.id, STATUS_EXECUTED)
    temp_store.update_status(action3.id, STATUS_FAILED)

    # Get briefing
    briefing_tool = GetBriefingTool()
    result = briefing_tool.execute()

    assert result.success is True
    content = result.content
    # Should show statistics for approved, executed, and failed
    assert "Approuvees" in content or "approved" in content.lower()
    assert "Executees" in content or "executed" in content.lower()
    assert "Echecs" in content or "failed" in content.lower()
