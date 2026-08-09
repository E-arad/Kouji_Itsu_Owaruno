"""既定値の集約。

画面非依存の処理（引数解析・試験）からの参照用。tkinter 非依存モジュールとして独立。
"""

from __future__ import annotations

__all__ = [
    "DEFAULT_LATITUDE",
    "DEFAULT_LONGITUDE",
    "DEFAULT_SCALE",
    "DISPLAY_MAX_WIDTH",
]

#: 探索グリッドの縮小率。
#:
#: グリッドには 3x3 膨張を2回適用。経路の道外側へのはみ出しは最大 ``2 * SCALE`` 画素。
#: 同梱地図の道は半幅およそ5画素。ゆえに 2 超過で経路の道外れが発生。
#: benchmarks/ の計測では 2 で 85%、3 で 29% が道上に収まる。
DEFAULT_SCALE = 2

#: 画面表示の初期幅上限（画素）。大きな地図はこの幅へ縮小表示。
DISPLAY_MAX_WIDTH = 1000

#: 天気問い合わせの既定地点（神戸市灘区付近）。
DEFAULT_LATITUDE = 34.71
DEFAULT_LONGITUDE = 135.24
