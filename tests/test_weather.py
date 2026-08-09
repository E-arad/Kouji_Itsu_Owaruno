"""天気解釈の試験。ネットワーク接続は無し。応答の形式のみ使用。"""

from __future__ import annotations

from typing import Any

import pytest

from Kouji_Itsu_Owaruno.weather import Weather, build_url, describe_code, parse_weather


def sample_payload(
    code: int = 0, precipitation: float = 0.0, probability: int | None = 10
) -> dict[str, Any]:
    """Open-Meteo 応答を模した辞書の生成。"""
    daily: dict[str, Any] = {}
    if probability is not None:
        daily["precipitation_probability_max"] = [probability]
    return {
        "current": {
            "weather_code": code,
            "temperature_2m": 21.5,
            "precipitation": precipitation,
            "wind_speed_10m": 8.0,
        },
        "daily": daily,
    }


class TestDescribeCode:
    def test_known_code(self) -> None:
        assert describe_code(0) == "快晴"

    def test_unknown_code_is_reported_with_its_number(self) -> None:
        assert "1234" in describe_code(1234)


class TestParseWeather:
    def test_reads_all_fields(self) -> None:
        weather = parse_weather(sample_payload(code=3, precipitation=0.0, probability=40))
        assert weather.code == 3
        assert weather.temperature_c == 21.5
        assert weather.precipitation_mm == 0.0
        assert weather.wind_speed_kmh == 8.0
        assert weather.precipitation_probability == 40

    def test_missing_daily_block_is_tolerated(self) -> None:
        payload = sample_payload(probability=None)
        assert parse_weather(payload).precipitation_probability is None

    def test_missing_current_block_raises(self) -> None:
        with pytest.raises(KeyError):
            parse_weather({})


class TestIsBad:
    @pytest.mark.parametrize("code", [0, 1, 2, 3, 45, 48])
    def test_dry_codes_are_fine(self, code: int) -> None:
        assert not parse_weather(sample_payload(code=code)).is_bad

    @pytest.mark.parametrize("code", [51, 61, 65, 71, 80, 95, 99])
    def test_rain_and_snow_codes_are_bad(self, code: int) -> None:
        assert parse_weather(sample_payload(code=code)).is_bad

    def test_any_precipitation_is_bad_even_with_a_clear_code(self) -> None:
        """晴れコードでも降水ありなら外出は非推奨。"""
        assert parse_weather(sample_payload(code=0, precipitation=0.2)).is_bad

    def test_boundary_code_50_is_fine_and_51_is_bad(self) -> None:
        assert not parse_weather(sample_payload(code=50)).is_bad
        assert parse_weather(sample_payload(code=51)).is_bad


class TestSummary:
    def test_contains_each_measurement(self) -> None:
        text = parse_weather(sample_payload(code=1, probability=30)).summary()
        assert "晴れ" in text
        assert "21.5" in text
        assert "30%" in text

    def test_unknown_probability_is_labelled(self) -> None:
        text = parse_weather(sample_payload(probability=None)).summary()
        assert "不明" in text


class TestBuildUrl:
    def test_includes_coordinates_and_needs_no_api_key(self) -> None:
        url = build_url(34.71, 135.24)
        assert "latitude=34.71" in url
        assert "longitude=135.24" in url
        assert "key" not in url.lower()


class TestWeatherIsImmutable:
    def test_cannot_be_modified_after_creation(self) -> None:
        weather = Weather(0, 20.0, 0.0, 5.0, 10)
        with pytest.raises(AttributeError):
            weather.code = 61  # type: ignore[misc]
