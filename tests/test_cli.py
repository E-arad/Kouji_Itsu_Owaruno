"""コマンドライン引数の試験 画面表示は無し 引数解釈のみ確認"""

from __future__ import annotations

import pytest

from Kouji_Itsu_Owaruno.__main__ import build_parser, main, resolve_map


class TestParser:
    def test_scale_defaults_to_two(self) -> None:
        assert build_parser().parse_args([]).scale == 2

    def test_scale_can_be_overridden(self) -> None:
        assert build_parser().parse_args(["--scale", "4"]).scale == 4

    def test_coordinates_can_be_overridden(self) -> None:
        args = build_parser().parse_args(["--lat", "35.0", "--lon", "139.0"])
        assert args.lat == 35.0
        assert args.lon == 139.0

    def test_map_cannot_be_replaced(self) -> None:
        """同梱地図の専用ツール。地図指定引数は受け付け不可。"""
        with pytest.raises(SystemExit):
            build_parser().parse_args(["other_map.png"])


class TestResolveMap:
    def test_bundled_map_is_shipped_with_the_package(self) -> None:
        assert resolve_map().exists()


class TestMain:
    def test_rejects_scale_below_one(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["--scale", "0"]) == 2
        assert "scale" in capsys.readouterr().err
