from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.fake import FakeKeitaro
from app.service import admin_campaign_url, campaign_url, create_campaign, push_stream_offers


def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_create_campaign_builds_google_flow_and_offer_flow():
    db = session()
    client = FakeKeitaro()
    created = create_campaign(db, client, "  summer  ", ["AU", "MX"], 3749)

    campaign_payload = next(call[1] for call in client.calls if call[0] == "create_campaign")
    assert campaign_payload["name"] == "summer"
    assert campaign_payload["type"] == "position"
    assert campaign_payload["cost_type"] == "CPC"
    assert campaign_payload["cost_value"] == 0
    assert campaign_payload["cost_currency"] == "USD"
    assert campaign_payload["cost_auto"] is True
    assert campaign_payload["domain_id"] == 1
    assert campaign_payload["group_id"] == 7
    assert campaign_payload["traffic_source_id"] == 4
    assert len(campaign_payload["alias"]) == 6

    streams = [call[1] for call in client.calls if call[0] == "create_stream"]
    assert streams[0]["name"] == "Flow 1"
    assert streams[0]["position"] == 1
    assert streams[0]["schema"] == "redirect"
    assert streams[0]["action_payload"] == "https://google.com"
    assert streams[0]["filters"] == [{"name": "country", "mode": "accept", "payload": ["AU", "MX"]}]
    assert streams[1]["name"] == "Flow 2"
    assert streams[1]["position"] == 2
    assert streams[1]["schema"] == "landings"
    assert streams[1]["offers"] == [{"offer_id": 3749, "share": 100, "state": "active"}]
    assert created["url"].startswith("https://tdgk.host/")
    assert created["offer"]["id"] == 3749


def test_push_drops_removed_offers_and_keeps_shares():
    db = session()
    client = FakeKeitaro()
    offers = [
        {"offer_id": 11111, "share": 34, "removed": False, "binding_id": 1},
        {"offer_id": 3749, "share": 33, "removed": False, "binding_id": 2},
        {"offer_id": 3771, "share": 0, "removed": True, "binding_id": 3},
    ]
    push_stream_offers(db, client, 39212, 564221, offers)
    _name, stream_id, payload = next(call for call in client.calls if call[0] == "update_stream")
    assert stream_id == 564221
    assert payload["offers"] == [
        {"offer_id": 11111, "share": 34, "state": "active", "id": 1},
        {"offer_id": 3749, "share": 33, "state": "active", "id": 2},
    ]


def test_admin_link_uses_saved_panel_without_doubling_admin():
    assert admin_campaign_url(212301, "https://tlgk.host/admin") == "https://tlgk.host/admin/#!/campaign/212301/main"
    assert admin_campaign_url(5, "https://tlgk.host/") == "https://tlgk.host/admin/#!/campaign/5/main"


def test_click_link_uses_the_tracker_host():
    assert campaign_url({"alias": "qa2-ghost-23998-67da62"}, "https://tlgk.host/admin") == "https://tlgk.host/qa2-ghost-23998-67da62"


def test_missing_group_is_reported():
    db = session()
    client = FakeKeitaro()
    client.groups = []
    try:
        create_campaign(db, client, "x", ["AU"], 3749)
    except ValueError as exc:
        assert "FORTESTS" in str(exc)
    else:
        raise AssertionError("expected an error")
