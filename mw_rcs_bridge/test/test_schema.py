"""Unit tests for the RCS bridge dataclasses.  No ROS, no HTTP."""

import pytest

from mw_rcs_bridge import (
    CancelRequest,
    CancelResponse,
    OrderRequest,
    OrderResponse,
    StateSnapshot,
)


def test_order_request_from_dict_happy_path():
    req = OrderRequest.from_dict({
        'subjob_id': 'VisitThreePoints',
        'behavior_parameter': {'foo': 1},
        'userdata_in': {'bar': 'baz'},
        'order_id': 'abc',
        'order_update_id': 2,
    })
    assert req.subjob_id == 'VisitThreePoints'
    assert req.behavior_parameter == {'foo': 1}
    assert req.userdata_in == {'bar': 'baz'}
    assert req.order_id == 'abc'
    assert req.order_update_id == 2


def test_order_request_requires_subjob_id():
    with pytest.raises(ValueError):
        OrderRequest.from_dict({'behavior_parameter': {}})


def test_order_request_rejects_non_dict_body():
    with pytest.raises(TypeError):
        OrderRequest.from_dict(['nope'])  # type: ignore[arg-type]


def test_order_request_defaults_are_safe():
    req = OrderRequest.from_dict({'subjob_id': 'X'})
    assert req.behavior_parameter == {}
    assert req.userdata_in == {}
    assert req.order_id == ''
    assert req.order_update_id == 0


def test_order_response_to_dict_round_trip():
    resp = OrderResponse(ok=True, order_id='o', message='dispatched')
    assert resp.to_dict() == {
        'ok': True, 'order_id': 'o', 'message': 'dispatched',
    }


def test_cancel_request_requires_order_id():
    with pytest.raises(ValueError):
        CancelRequest.from_dict({})
    req = CancelRequest.from_dict({'order_id': 'o'})
    assert req.order_id == 'o'


def test_cancel_response_round_trip():
    assert CancelResponse(ok=True).to_dict() == {
        'ok': True, 'message': 'cancel requested',
    }


def test_state_snapshot_round_trip():
    snap = StateSnapshot(
        order_id='o', subjob_id='S',
        status='running', active_state='S.A.B',
        userdata_snapshot={'k': 1}, elapsed_sec=1.25,
    )
    d = snap.to_dict()
    assert d == {
        'order_id': 'o', 'subjob_id': 'S',
        'status': 'running', 'active_state': 'S.A.B',
        'userdata_snapshot': {'k': 1}, 'elapsed_sec': 1.25,
    }
