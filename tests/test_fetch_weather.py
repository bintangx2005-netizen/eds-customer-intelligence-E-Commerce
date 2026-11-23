import json

import pytest

from etl import fetch_weather


def _fake(url, attempts=5):
    assert "precipitation_sum" in url and "archive-api.open-meteo.com" in url
    return {"daily": {"time": ["2018-01-01"], "precipitation_sum": [1.0], "temperature_2m_max": [30.0]}}


def test_ensure_downloads_only_missing_states(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_weather, "_request_json", _fake)
    (tmp_path / "SP.json").write_text("{}")
    done = fetch_weather.ensure(tmp_path, pause=0)
    assert len(done) == 26 and "SP" not in done
    assert json.loads((tmp_path / "RJ.json").read_text())["daily"]["precipitation_sum"] == [1.0]
    assert fetch_weather.ensure(tmp_path, pause=0) == []


def test_empty_response_raises_clear_error(monkeypatch):
    monkeypatch.setattr(fetch_weather, "_request_json", lambda url, attempts=5: {"error": True})
    with pytest.raises(RuntimeError, match="tidak berisi data harian"):
        fetch_weather.fetch_state("SP")


def test_all_27_states_have_coordinates():
    assert len(fetch_weather.CAPITALS) == 27
