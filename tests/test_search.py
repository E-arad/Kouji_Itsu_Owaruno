"""経路探索の試験
巨大地図の読み込みは回避 意図の判別可能な小グリッドを手組みして検証
"""

from __future__ import annotations

from itertools import pairwise

import numpy as np
import pytest
from numpy.typing import NDArray

from Kouji_Itsu_Owaruno.search import (
    NEIGHBORS,
    bfs,
    path_length_px,
    path_to_pixels,
    snap_to_walkable,
)

BoolArray = NDArray[np.bool_]


def grid_from_text(text: str) -> BoolArray:
    """``.`` は通行可能、``#`` は壁。試験意図の視覚的な明示が目的。"""
    rows = [line for line in text.strip().splitlines() if line.strip()]
    return np.array([[ch == "." for ch in row.strip()] for row in rows], dtype=bool)


def assert_valid_path(grid: BoolArray, path: list[tuple[int, int]]) -> None:
    """経路の妥当性検証。通行可能セルのみ通過。かつ隣接セル同士の連結。"""
    assert path, "経路が空です"
    for y, x in path:
        assert grid[y, x], f"経路が通行不可のセル {(y, x)} を通っています"
    for (y0, x0), (y1, x1) in pairwise(path):
        assert (y1 - y0, x1 - x0) in NEIGHBORS, f"{(y0, x0)} と {(y1, x1)} は隣接していません"


class TestBfs:
    def test_straight_corridor(self) -> None:
        grid = grid_from_text(
            """
            #####
            .....
            #####
            """
        )
        path = bfs(grid, (1, 0), (1, 4))
        assert path is not None
        assert_valid_path(grid, path)
        assert path == [(1, 0), (1, 1), (1, 2), (1, 3), (1, 4)]

    def test_start_equals_goal(self) -> None:
        grid = grid_from_text("...")
        assert bfs(grid, (0, 1), (0, 1)) == [(0, 1)]

    def test_returns_none_when_unreachable(self) -> None:
        grid = grid_from_text(
            """
            ..#..
            ..#..
            ..#..
            """
        )
        assert bfs(grid, (0, 0), (0, 4)) is None

    def test_goes_around_obstacle(self) -> None:
        grid = grid_from_text(
            """
            .....
            .###.
            .....
            """
        )
        path = bfs(grid, (0, 0), (2, 0))
        assert path is not None
        assert_valid_path(grid, path)
        assert (1, 1) not in path

    def test_uses_diagonal_moves(self) -> None:
        """斜め移動の効果。対角到達の手数は縦横移動より少数。"""
        grid = grid_from_text(
            """
            ...
            ...
            ...
            """
        )
        path = bfs(grid, (0, 0), (2, 2))
        assert path is not None
        assert len(path) == 3  # 斜めに2歩

    def test_finds_minimum_number_of_steps(self) -> None:
        """BFS の最小手数保証。遠回りの選択肢が存在しても最短を返却。"""
        grid = grid_from_text(
            """
            .....
            .###.
            .....
            .###.
            .....
            """
        )
        path = bfs(grid, (0, 0), (0, 4))
        assert path is not None
        assert len(path) == 5  # 上の行をまっすぐ進む

    @pytest.mark.parametrize("cell", [(-1, 0), (0, -1), (99, 0), (0, 99)])
    def test_rejects_out_of_bounds(self, cell: tuple[int, int]) -> None:
        grid = grid_from_text("...")
        with pytest.raises(ValueError, match="外です"):
            bfs(grid, cell, (0, 0))

    def test_rejects_blocked_endpoint(self) -> None:
        grid = grid_from_text(".#.")
        with pytest.raises(ValueError, match="通行可能ではありません"):
            bfs(grid, (0, 0), (0, 1))


class TestSnapToWalkable:
    def test_returns_same_cell_when_already_walkable(self) -> None:
        grid = grid_from_text("...")
        assert snap_to_walkable(grid, 0, 1) == (0, 1)

    def test_pulls_to_nearest_walkable_cell(self) -> None:
        grid = grid_from_text(
            """
            ###
            #.#
            ###
            """
        )
        assert snap_to_walkable(grid, 0, 0) == (1, 1)

    def test_returns_none_when_nothing_in_radius(self) -> None:
        grid = grid_from_text(
            """
            #.#
            ###
            ###
            """
        )
        assert snap_to_walkable(grid, 2, 2, radius=1) is None

    def test_handles_click_outside_grid(self) -> None:
        grid = grid_from_text(
            """
            ..#
            ..#
            """
        )
        assert snap_to_walkable(grid, -5, -5) == (0, 0)


class TestPathConversion:
    def test_maps_cells_to_pixel_centres_in_xy_order(self) -> None:
        # (y, x) = (1, 2) は scale=4 で画素 (2*4+2, 1*4+2) = (10, 6)
        assert path_to_pixels([(1, 2)], 4) == [(10, 6)]

    def test_scale_one_keeps_coordinates(self) -> None:
        assert path_to_pixels([(3, 7)], 1) == [(7, 3)]

    def test_length_counts_diagonal_as_sqrt_two(self) -> None:
        assert path_length_px([(0, 0), (1, 1)]) == pytest.approx(np.sqrt(2))

    def test_length_of_short_path_is_zero(self) -> None:
        assert path_length_px([]) == 0.0
        assert path_length_px([(5, 5)]) == 0.0

    def test_length_sums_segments(self) -> None:
        assert path_length_px([(0, 0), (3, 0), (3, 4)]) == pytest.approx(7.0)
