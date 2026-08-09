"""Open-Meteo API による現在天気の取得"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Any

__all__ = ["WMO_DESCRIPTIONS", "Weather", "describe_code", "fetch_weather", "parse_weather"]

API_URL = "https://api.open-meteo.com/v1/forecast"

#: WMO 気象コードと日本語表記の対応表。
WMO_DESCRIPTIONS: dict[int, str] = {
    0: "快晴",
    1: "晴れ",
    2: "一部曇り",
    3: "曇り",
    45: "霧",
    48: "霧氷",
    51: "弱い霧雨",
    53: "霧雨",
    55: "強い霧雨",
    61: "小雨",
    63: "雨",
    65: "大雨",
    71: "小雪",
    73: "雪",
    75: "大雪",
    80: "にわか雨(弱)",
    81: "にわか雨",
    82: "にわか雨(強)",
    95: "雷雨",
    96: "雷雨(ひょう)",
    99: "激しい雷雨(ひょう)",
}

#: 以上のコードは雨・雪・雷を包含。外出不適と判定。
BAD_WEATHER_CODE_MIN = 51


def describe_code(code: int) -> str:
    """WMO 気象コードの日本語表記への変換。未知コードは数値を添えて返却。"""
    return WMO_DESCRIPTIONS.get(code, f"不明(コード{code})")


@dataclass(frozen=True)
class Weather:
    """ある地点の現在天気。"""

    code: int
    temperature_c: float
    precipitation_mm: float
    wind_speed_kmh: float
    precipitation_probability: int | None

    @property
    def description(self) -> str:
        """天気の日本語表記。"""
        return describe_code(self.code)

    @property
    def is_bad(self) -> bool:
        """外出不適の判定。降水あり、または雨雪雷コードなら ``True``。"""
        return self.code >= BAD_WEATHER_CODE_MIN or self.precipitation_mm > 0

    def summary(self) -> str:
        """人間可読な複数行要約。"""
        percent = self.precipitation_probability
        probability = "不明" if percent is None else f"{percent}%"
        return (
            f"天気: {self.description}\n"
            f"気温: {self.temperature_c}°C\n"
            f"降水量: {self.precipitation_mm} mm\n"
            f"風速: {self.wind_speed_kmh} km/h\n"
            f"今日の降水確率(最大): {probability}"
        )


def parse_weather(payload: dict[str, Any]) -> Weather:
    """Open-Meteo 応答の :class:`Weather` への変換。

    Raises:
        KeyError: 応答に ``current`` が不在。
    """
    current = payload["current"]
    daily = payload.get("daily") or {}
    probabilities = daily.get("precipitation_probability_max") or []
    probability = probabilities[0] if probabilities else None
    return Weather(
        code=int(current.get("weather_code", -1)),
        temperature_c=float(current["temperature_2m"]),
        precipitation_mm=float(current["precipitation"]),
        wind_speed_kmh=float(current["wind_speed_10m"]),
        precipitation_probability=None if probability is None else int(probability),
    )


def build_url(latitude: float, longitude: float) -> str:
    """指定地点の現在天気を問い合わせる URL の組み立て。"""
    return (
        f"{API_URL}?latitude={latitude}&longitude={longitude}"
        "&current=temperature_2m,precipitation,weather_code,wind_speed_10m"
        "&daily=precipitation_probability_max"
        "&timezone=Asia%2FTokyo&forecast_days=1"
    )


def fetch_weather(latitude: float, longitude: float, *, timeout: float = 10.0) -> Weather:
    """Open-Meteo からの現在天気の取得。認証は不要。

    Raises:
        urllib.error.URLError: 通信の失敗。
    """
    with urllib.request.urlopen(build_url(latitude, longitude), timeout=timeout) as response:
        payload: dict[str, Any] = json.load(response)
    return parse_weather(payload)
