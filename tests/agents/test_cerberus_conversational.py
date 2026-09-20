import pytest
import json
from openjarvis.agents.cerberus_conversational import (
    ListAlertsTool,
    ListDraftsTool,
    ViewEmailTool,
    SuggestVariantsTool,
    CerberusConversationalAgent,
)
from openjarvis.tools.approval_store import ApprovalStore

@pytest.fixture
def temp_store(tmp_path, monkeypatch):
    monkeypatch.setattr("openjarvis.tools.approval_store.get_config_dir", lambda: tmp_path)
    store = ApprovalStore()
    return store

def test_cerberus_tools_dont_crash(temp_store):
    list_alerts = ListAlertsTool()
    res = list_alerts.execute()
    assert res.success is True

    list_drafts = ListDraftsTool()
    res = list_drafts.execute()
    assert res.success is True

    view_email = ViewEmailTool()
    res = view_email.execute(email_id="123")
    assert res.success is False  # Because it's not found

def test_cerberus_confirm_queues_action(temp_store):
    class DummyEngine:
        pass
    
    agent = CerberusConversationalAgent(DummyEngine(), "model")
    
    # Write action should be queued, not crashed
    result = agent._cerberus_confirm("edit_draft", json.dumps({"draft_id": "draft_1", "instruction": "fix"}))
    assert result is False
    
    # Check it was queued
    pending = temp_store.list_pending()
    assert len(pending) == 1
    assert pending[0].action_type == "conversational_edit_draft"
    assert pending[0].permission_key == "conversational_edit_draft:target:draft_1"


def test_view_email_found(tmp_path, monkeypatch):
    """ViewEmailTool doit utiliser item.description (pas item.summary) quand
    le payload ne contient pas de cle 'body' -- c'est le bug exact de l'Addendum 10.
    """
    monkeypatch.setattr("openjarvis.tools.approval_store.get_config_dir", lambda: tmp_path)
    store = ApprovalStore()
    action = store.queue_action(
        action_type="draft_pending",
        description="Brouillon pour Mme Traore",
        payload={},  # payload SANS cle "body" -- chemin fautif avant correctif
        permission_key="draft_pending:target:test123",
        tier="high",
    )
    view_email = ViewEmailTool()
    res = view_email.execute(email_id=action.id)
    assert res.success is True
    assert "Brouillon pour Mme Traore" in res.content
