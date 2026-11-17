import pytest

from app.service import parse_geos
from app.share import active_sum, apply_share_op


def row(offer_id, share, order):
    return {"offer_id": offer_id, "name": str(offer_id), "share": share, "removed": False, "url": "", "binding_id": None, "_order": order}


def test_remove_gives_remainder_to_last_active_then_sorts():
    rows = [row(1, 25, 0), row(2, 25, 1), row(3, 25, 2), row(4, 25, 3)]
    result = apply_share_op(rows, "remove", offer_id=2)
    assert [(item["offer_id"], item["share"], item["removed"]) for item in result] == [
        (4, 34, False),
        (1, 33, False),
        (3, 33, False),
        (2, 0, True),
    ]
    assert active_sum(result) == 100


def test_add_splits_equally_and_keeps_order_when_tied():
    rows = [row(1, 34, 0), row(2, 33, 1), row(3, 33, 2)]
    result = apply_share_op(rows, "add", offer={"id": 9, "name": "new", "url": "https://x"})
    assert [item["share"] for item in result] == [25, 25, 25, 25]
    assert [item["offer_id"] for item in result] == [1, 2, 3, 9]
    assert active_sum(result) == 100


def test_restore_equalizes_everyone():
    rows = apply_share_op([row(1, 25, 0), row(2, 25, 1), row(3, 25, 2), row(4, 25, 3)], "remove", offer_id=2)
    restored = apply_share_op(rows, "restore", offer_id=2)
    assert active_sum(restored) == 100
    assert all(item["share"] == 25 and not item["removed"] for item in restored)


def test_nudge_keeps_the_current_sum():
    rows = [row(1, 50, 0), row(2, 50, 1)]
    result = apply_share_op(rows, "nudge", offer_id=1, delta=1)
    assert [(item["offer_id"], item["share"]) for item in result] == [(1, 51), (2, 49)]
    assert active_sum(result) == 100


def test_nudge_does_not_drop_below_zero():
    rows = [row(1, 0, 0), row(2, 100, 1)]
    result = apply_share_op(rows, "nudge", offer_id=1, delta=-1)
    assert result[0]["share"] == 0
    assert result[1]["share"] == 100


def test_duplicate_add_is_rejected():
    with pytest.raises(ValueError):
        apply_share_op([row(1, 100, 0)], "add", offer={"id": 1, "name": "same"})


def test_geos_accept_a_list_and_reject_garbage():
    assert parse_geos("mx, AU;ro") == ["MX", "AU", "RO"]
    with pytest.raises(ValueError):
        parse_geos("Mexico")
