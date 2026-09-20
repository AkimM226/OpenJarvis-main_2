import pytest
from openjarvis.agents.prospection_agent import (
    LogAndQueueProspectTool,
    FlagOpportunityWithoutContactTool,
)
from openjarvis.tools.approval_store import ApprovalStore

@pytest.fixture
def temp_store(tmp_path, monkeypatch):
    monkeypatch.setattr("openjarvis.tools.approval_store.get_config_dir", lambda: tmp_path)
    monkeypatch.setattr("openjarvis.agents.prospection_agent._DB_PATH", tmp_path / "prospection_log.db")
    store = ApprovalStore()
    return store

def test_prospection_tools_dont_crash(temp_store):
    log_tool = LogAndQueueProspectTool()
    res = log_tool.execute(
        name="Test",
        source_url="http://test.com",
        source_excerpt="contact@test.com",
        contact="contact@test.com",
        draft_message="Hello",
        sector="arduino",
    )
    assert res.success is True
    
    pending = temp_store.list_pending()
    assert len(pending) == 1
    assert pending[0].action_type == "prospection_first_contact"
    assert pending[0].permission_key == "prospection_first_contact:url:http://test.com"
    
    flag_tool = FlagOpportunityWithoutContactTool()
    res = flag_tool.execute(
        name="Test Flag",
        source_url="http://test2.com",
        description="No contact",
        sector="arduino",
    )
    assert res.success is True
    
    pending = temp_store.list_pending()
    assert len(pending) == 2
    assert pending[1].action_type == "prospection_opportunity_flagged"
    assert pending[1].permission_key == "prospection_opportunity_flagged:url:http://test2.com"
