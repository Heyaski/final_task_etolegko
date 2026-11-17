"""Доли офферов в потоке.

Число на экране — это поле share в Keitaro, показанное с знаком %.
После добавления, удаления и возврата активные доли заново делятся так,
чтобы в сумме было 100. Остаток от деления достаётся последним активным
офферам, затем строки сортируются по доле по убыванию. Так 3 оффера
становятся 34 / 33 / 33, а 4 — по 25.

Ручной шаг ±1 сохраняет текущую сумму: прибавка забирается у других
активных офферов, убавка отдаётся следующему.
"""

from __future__ import annotations


def _active(rows: list[dict]) -> list[dict]:
    return [row for row in rows if not row.get("removed")]


def distribute(count: int) -> list[int]:
    if count <= 0:
        return []
    base, remainder = divmod(100, count)
    shares = [base] * count
    for offset in range(remainder):
        shares[count - 1 - offset] += 1
    return shares


def equalize(rows: list[dict]) -> list[dict]:
    active = _active(rows)
    shares = distribute(len(active))
    for row, share in zip(active, shares, strict=True):
        row["share"] = share
    for row in rows:
        if row.get("removed"):
            row["share"] = 0
    active.sort(key=lambda row: (-int(row["share"]), int(row.get("_order", 0))))
    removed = [row for row in rows if row.get("removed")]
    return active + removed


def nudge(rows: list[dict], offer_id: int, delta: int) -> list[dict]:
    active = _active(rows)
    target = next((row for row in active if int(row["offer_id"]) == int(offer_id)), None)
    if target is None or delta == 0 or len(active) < 2:
        return rows
    delta = max(-int(target["share"]), min(100, delta))
    if delta == 0:
        return rows
    others = [row for row in active if row is not target]
    if delta > 0:
        need = delta
        for donor in sorted(others, key=lambda row: -int(row["share"])):
            take = min(need, int(donor["share"]))
            donor["share"] = int(donor["share"]) - take
            need -= take
            if need == 0:
                break
        target["share"] = int(target["share"]) + (delta - need)
    else:
        give = -delta
        target["share"] = int(target["share"]) - give
        others[0]["share"] = int(others[0]["share"]) + give
    return rows


def apply_share_op(rows: list[dict], op: str, offer_id: int | None = None, delta: int = 0, offer: dict | None = None) -> list[dict]:
    rows = [dict(row) for row in rows]
    for index, row in enumerate(rows):
        row.setdefault("_order", index)
        row["removed"] = bool(row.get("removed"))
        row["share"] = int(row.get("share") or 0)
        row["offer_id"] = int(row["offer_id"])

    if op == "equalize":
        return equalize(rows)

    if op == "nudge":
        if offer_id is None:
            raise ValueError("Не выбран оффер")
        return nudge(rows, offer_id, delta)

    if op == "remove":
        if offer_id is None:
            raise ValueError("Не выбран оффер")
        row = next((item for item in rows if item["offer_id"] == int(offer_id) and not item["removed"]), None)
        if row is None:
            raise ValueError("Оффер не найден в потоке")
        row["removed"] = True
        row["share"] = 0
        return equalize(rows)

    if op == "restore":
        if offer_id is None:
            raise ValueError("Не выбран оффер")
        row = next((item for item in rows if item["offer_id"] == int(offer_id) and item["removed"]), None)
        if row is None:
            raise ValueError("Оффер не снят")
        row["removed"] = False
        return equalize(rows)

    if op == "add":
        if not offer or offer.get("id") is None:
            raise ValueError("Выберите оффер")
        new_id = int(offer["id"])
        existing = next((item for item in rows if item["offer_id"] == new_id), None)
        if existing and not existing["removed"]:
            raise ValueError("Этот оффер уже есть в потоке")
        if existing and existing["removed"]:
            existing["removed"] = False
            existing["name"] = offer.get("name") or existing.get("name") or str(new_id)
        else:
            rows.append(
                {
                    "offer_id": new_id,
                    "name": offer.get("name") or str(new_id),
                    "share": 0,
                    "removed": False,
                    "url": offer.get("url") or "",
                    "binding_id": None,
                    "_order": len(rows),
                }
            )
        return equalize(rows)

    raise ValueError(f"Неизвестная операция: {op}")


def active_sum(rows: list[dict]) -> int:
    return sum(int(row.get("share") or 0) for row in rows if not row.get("removed"))
