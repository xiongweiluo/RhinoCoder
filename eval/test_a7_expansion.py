from agent.collection_campaign import load_campaign
from tools.audit_a7_expansion import DEFAULT_MANIFEST


def test_a7_public_campaign_contains_500_tasks_and_46_tags():
    campaign = load_campaign(DEFAULT_MANIFEST)
    tags = {tag for task in campaign.tasks for tag in task.get("tags") or []}

    assert campaign.target == 500
    assert len(campaign.tasks) == 500
    assert len(tags) == 46
