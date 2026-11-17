"""Локальный трекер с той же формой ответов, что Admin API.

Используется, пока в настройках нет ключа, и в тестах.
"""

from __future__ import annotations

from copy import deepcopy


class FakeKeitaro:
    def __init__(self):
        self.calls: list[tuple] = []
        self.domains = [{"id": 1, "name": "kylovoa.com", "is_ssl": True}]
        self.groups = [{"id": 7, "name": "FORTESTS", "type": "campaigns"}]
        self.sources = [{"id": 4, "name": "FORTESTS"}]
        self.offers = [
            {"id": 3749, "name": "Miaflow [BEAUTY-RO-BE_0009] [pl - spin ro -] 2. Основной, Румыния JS", "country": "RO", "action_payload": "https://example.com/spin"},
            {"id": 3771, "name": "Miaflow [BEAUTY-RO-BE_0008] [pl - prize ro -] 1. Основной, Румыния JS", "country": "RO", "action_payload": "https://example.com/prize"},
            {"id": 11111, "name": "11111 FitoMishki [Weight Loss-CO-DT_0309] [pl es -]", "country": "CO", "action_payload": "https://example.com/fito"},
            {"id": 11112, "name": "11112 Oxys [BEAUTY-CL-BE_0155] [pl es -]", "country": "CL", "action_payload": "https://example.com/oxys"},
            {"id": 11108, "name": "11108 Oxys [BEAUTY-CL-BE_0109] [pl es -]", "country": "CL", "action_payload": "https://example.com/oxys2"},
        ]
        self.campaigns = [
            {
                "id": 39212,
                "name": "campaign 2",
                "alias": "wVqN1R",
                "state": "active",
                "type": "position",
                "domain_id": 1,
                "group_id": 7,
                "traffic_source_id": 4,
                "cost_type": "CPC",
                "cost_value": 0,
                "cost_currency": "USD",
                "cost_auto": True,
            }
        ]
        self.streams = {
            39212: [
                {
                    "id": 564220,
                    "campaign_id": 39212,
                    "name": "Flow 1",
                    "type": "regular",
                    "schema": "redirect",
                    "action_type": "http",
                    "action_payload": "https://google.com",
                    "position": 1,
                    "state": "active",
                    "filters": [{"name": "country", "mode": "accept", "payload": ["AU"]}],
                    "offers": [],
                },
                {
                    "id": 564221,
                    "campaign_id": 39212,
                    "name": "Flow 2",
                    "type": "regular",
                    "schema": "landings",
                    "action_type": "http",
                    "action_payload": "",
                    "position": 2,
                    "state": "active",
                    "filters": [],
                    "offers": [
                        {"id": 1, "offer_id": 11111, "share": 34, "state": "active"},
                        {"id": 2, "offer_id": 3749, "share": 33, "state": "active"},
                        {"id": 3, "offer_id": 3771, "share": 33, "state": "active"},
                    ],
                },
            ]
        }
        self._campaign_seq = 40000
        self._stream_seq = 60000
        self._binding_seq = 100

    def list_campaigns(self) -> list:
        self.calls.append(("list_campaigns",))
        return deepcopy(self.campaigns)

    def get_campaign(self, campaign_id: int) -> dict:
        self.calls.append(("get_campaign", campaign_id))
        for campaign in self.campaigns:
            if campaign["id"] == int(campaign_id):
                return deepcopy(campaign)
        from app.keitaro import KeitaroError

        raise KeitaroError(404, "Кампания не найдена")

    def create_campaign(self, data: dict) -> dict:
        self.calls.append(("create_campaign", deepcopy(data)))
        self._campaign_seq += 1
        campaign = {"id": self._campaign_seq, "state": "active", **deepcopy(data)}
        self.campaigns.append(campaign)
        self.streams[campaign["id"]] = []
        return deepcopy(campaign)

    def delete_campaign(self, campaign_id: int) -> dict:
        self.calls.append(("delete_campaign", campaign_id))
        self.campaigns = [item for item in self.campaigns if item["id"] != int(campaign_id)]
        self.streams.pop(int(campaign_id), None)
        return {"success": True}

    def list_streams(self, campaign_id: int) -> list:
        self.calls.append(("list_streams", campaign_id))
        return deepcopy(self.streams.get(int(campaign_id), []))

    def create_stream(self, data: dict) -> dict:
        self.calls.append(("create_stream", deepcopy(data)))
        self._stream_seq += 1
        stream = {"id": self._stream_seq, "state": "active", "filters": [], "offers": [], **deepcopy(data)}
        self.streams.setdefault(int(data["campaign_id"]), []).append(stream)
        return deepcopy(stream)

    def update_stream(self, stream_id: int, data: dict) -> dict:
        self.calls.append(("update_stream", stream_id, deepcopy(data)))
        for streams in self.streams.values():
            for stream in streams:
                if stream["id"] == int(stream_id):
                    if "offers" in data:
                        offers = []
                        for item in data["offers"]:
                            self._binding_seq += 1
                            offers.append({"id": item.get("id") or self._binding_seq, "state": "active", **item})
                        stream["offers"] = offers
                    for key, value in data.items():
                        if key != "offers":
                            stream[key] = value
                    return deepcopy(stream)
        from app.keitaro import KeitaroError

        raise KeitaroError(404, "Поток не найден")

    def list_offers(self) -> list:
        self.calls.append(("list_offers",))
        return deepcopy(self.offers)

    def get_offer(self, offer_id: int) -> dict:
        self.calls.append(("get_offer", offer_id))
        for offer in self.offers:
            if offer["id"] == int(offer_id):
                return deepcopy(offer)
        from app.keitaro import KeitaroError

        raise KeitaroError(404, "Оффер не найден")

    def list_domains(self) -> list:
        return deepcopy(self.domains)

    def list_groups(self, group_type: str) -> list:
        return deepcopy([item for item in self.groups if item["type"] == group_type])

    def list_traffic_sources(self) -> list:
        return deepcopy(self.sources)

    def build_report(self, data: dict) -> dict:
        self.calls.append(("build_report", deepcopy(data)))
        grouping = data.get("grouping") or []
        if "day" in grouping:
            return {
                "rows": [
                    {"day": "2026-11-15", "offer_id": 11111, "stream_id": 564221, "clicks": 2},
                    {"day": "2026-11-16", "offer_id": 11111, "stream_id": 564221, "clicks": 4},
                    {"day": "2026-11-17", "offer_id": 3749, "stream_id": 564221, "clicks": 1},
                    {"day": "2026-11-17", "offer_id": 0, "stream_id": 564220, "clicks": 3},
                ]
            }
        return {
            "rows": [
                {"stream_id": 564221, "offer_id": 11111, "clicks": 4, "campaign_unique_clicks": 3, "conversions": 1, "revenue": 12.5},
                {"stream_id": 564221, "offer_id": 3749, "clicks": 1, "campaign_unique_clicks": 1, "conversions": 0, "revenue": 0},
                {"stream_id": 564220, "offer_id": 0, "clicks": 3, "campaign_unique_clicks": 3, "conversions": 0, "revenue": 0},
            ]
        }
