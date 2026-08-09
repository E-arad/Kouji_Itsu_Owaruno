"""グリッド上経路探索。

等間隔グリッド。隣接セル間コストは全て同一。ゆえに重み付きグラフ用手法は不要。
幅優先探索(BFS)のみで最小手数経路が確定。

親ポインタは ``y * W + x`` の1次元整数。``int64`` 配列1枚に格納。``-1`` が未訪問印。
訪問済み判定と経路復元を1枚で兼用。別途フラグ配列は不要。
"""

from __future__ import annotations

from collections import deque

import numpy as np
from numpy.typing import NDArray

__all__ = ["NEIGHBORS", "bfs", "path_to_pixels", "snap_to_walkable"]

BoolArray = NDArray[np.bool_]
Cell = tuple[int, int]

#: 8近傍。斜め移動許可。経路形状の自然化。
NEIGHBORS: tuple[Cell, ...] = (
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
)


def snap_to_walkable(grid: BoolArray, y: int, x: int, *, radius: int = 150) -> Cell | None:
    """最近傍の通行可能セルへ吸着。

    道の真上への正確なクリックは期待不能。近傍走査による自動吸着で対応。

    Args:
        grid: 探索グリッド。
        y: 行位置（セル単位）。
        x: 列位置（セル単位）。
        radius: 近傍探索半径（セル単位）。

    Returns:
        最近傍の通行可能セル ``(y, x)``。範囲内不在なら ``None``。
    """
    h, w = grid.shape
    if 0 <= y < h and 0 <= x < w and grid[y, x]:
        return y, x

    y0, y1 = max(0, y - radius), min(h, y + radius)
    x0, x1 = max(0, x - radius), min(w, x + radius)
    window = grid[y0:y1, x0:x1]
    if not window.any():
        return None

    ys, xs = np.mgrid[y0:y1, x0:x1]
    dist2 = (ys - y) ** 2 + (xs - x) ** 2
    # 通行不可セルの除外。十分大きな値で潰す
    dist2 = np.where(window, dist2, np.iinfo(np.int64).max)
    flat = int(np.argmin(dist2))
    return int(ys.flat[flat]), int(xs.flat[flat])


def bfs(grid: BoolArray, start: Cell, goal: Cell) -> list[Cell] | None:
    """``start`` から ``goal`` への最小手数経路。

    Args:
        grid: 探索グリッド。``True`` が通行可能。
        start: 開始セル ``(y, x)``。通行可能必須。
        goal: 目標セル ``(y, x)``。通行可能必須。

    Returns:
        始点から終点へのセル列。到達不能なら ``None``。
        ``start == goal`` なら要素1個のリスト。

    Raises:
        ValueError: 始点・終点がグリッド外、または通行不可。
    """
    h, w = grid.shape
    for name, (cy, cx) in (("start", start), ("goal", goal)):
        if not (0 <= cy < h and 0 <= cx < w):
            raise ValueError(f"{name}={(cy, cx)} がグリッド {grid.shape} の外です")
        if not grid[cy, cx]:
            raise ValueError(f"{name}={(cy, cx)} は通行可能ではありません")

    sy, sx = start
    gy, gx = goal
    prev = np.full((h, w), -1, dtype=np.int64)
    prev[sy, sx] = sy * w + sx  # 始点は自己参照。経路復元の終端条件
    queue: deque[Cell] = deque([(sy, sx)])

    while queue:
        y, x = queue.popleft()
        if (y, x) == (gy, gx):
            break
        for dy, dx in NEIGHBORS:
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and grid[ny, nx] and prev[ny, nx] < 0:
                prev[ny, nx] = y * w + x
                queue.append((ny, nx))

    if prev[gy, gx] < 0:
        return None

    path: list[Cell] = []
    cursor = gy * w + gx
    while True:
        y, x = divmod(cursor, w)
        path.append((y, x))
        if (y, x) == (sy, sx):
            break
        cursor = int(prev[y, x])
    path.reverse()
    return path


def path_to_pixels(path: list[Cell], scale: int) -> list[Cell]:
    """グリッド座標から元画像の画素座標 ``(x, y)`` へ変換。

    セル中心を代表点とするため ``scale // 2`` を加算。
    描画用途のため戻り値は ``(x, y)`` 順。``(y, x)`` ではない点に注意。
    """
    half = scale // 2
    return [(x * scale + half, y * scale + half) for y, x in path]


def path_length_px(pixels: list[Cell]) -> float:
    """画素座標経路の幾何長。斜め移動は ``sqrt(2)`` として計上。"""
    if len(pixels) < 2:
        return 0.0
    points = np.asarray(pixels, dtype=float)
    deltas = np.diff(points, axis=0)
    return float(np.hypot(deltas[:, 0], deltas[:, 1]).sum())
