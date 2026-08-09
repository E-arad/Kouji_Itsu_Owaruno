"""コマンドラインからの起動口。

実行形式は ``python -m Kouji_Itsu_Owaruno`` または ``kouji``。

本ソフトウェアは同梱地図の専用ツール。起動時は常に同梱地図を使用。差し替えは不可。
理由は :mod:`Kouji_Itsu_Owaruno.mask` を参照。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from Kouji_Itsu_Owaruno import __version__
from Kouji_Itsu_Owaruno.config import DEFAULT_LATITUDE, DEFAULT_LONGITUDE, DEFAULT_SCALE

#: 同梱地図。歩行可能路の描き込み済み。他地図での動作は保証対象外。
BUNDLED_MAP = Path(__file__).resolve().parent / "data" / "map.png"


def resolve_map() -> Path:
    """同梱地図の所在の解決。PyInstaller 単一ファイル化にも対応。"""
    base = getattr(sys, "_MEIPASS", None)
    if base is not None:
        return Path(base) / "Kouji_Itsu_Owaruno" / "data" / "map.png"
    return BUNDLED_MAP


def build_parser() -> argparse.ArgumentParser:
    """コマンドライン引数の定義。"""
    parser = argparse.ArgumentParser(
        prog="kouji",
        description="同梱の地図を2回クリックして、歩ける道をたどる経路を表示します。",
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=DEFAULT_SCALE,
        help=f"探索グリッドの縮小率。大きいほど速いが経路が粗くなる (既定: {DEFAULT_SCALE})",
    )
    parser.add_argument("--lat", type=float, default=DEFAULT_LATITUDE, help="天気を調べる緯度")
    parser.add_argument("--lon", type=float, default=DEFAULT_LONGITUDE, help="天気を調べる経度")
    parser.add_argument("--version", action="version", version=f"Kouji_Itsu_Owaruno {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    """エントリポイント。戻り値は終了コード。"""
    args = build_parser().parse_args(argv)

    if args.scale < 1:
        print("エラー: --scale は1以上を指定してください", file=sys.stderr)
        return 2

    image_path = resolve_map()
    if not image_path.exists():
        print(f"エラー: 同梱の地図が見つかりません: {image_path}", file=sys.stderr)
        return 1

    from Kouji_Itsu_Owaruno.gui import run  # tkinter の読み込みは画面表示の直前まで遅延

    run(image_path, scale=args.scale, latitude=args.lat, longitude=args.lon)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
