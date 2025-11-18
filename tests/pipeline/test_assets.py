from tq_oracle.pipeline.assets import _sanitize_adapter_kwargs


def test_sanitize_adapter_kwargs_drops_empty_collections():
    values = {
        "empty_dict": {},
        "empty_list": [],
        "none_value": None,
        "false_flag": False,
        "zero_value": 0,
        "address": "0x123",
    }

    sanitized = _sanitize_adapter_kwargs(values)

    assert sanitized == {
        "false_flag": False,
        "zero_value": 0,
        "address": "0x123",
    }
