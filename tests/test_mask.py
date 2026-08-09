"""通行可能マスクとグリッド生成の試験
狙いの色のみ配置した小さな合成画像で検証
"""

from __future__ import annotations

import numpy as np
import pytest
from numpy.typing import NDArray

from Kouji_Itsu_Owaruno.mask import (
    USER_PATH_RGB,
    build_color_mask,
    build_user_path_mask,
    build_walkable_mask,
    downscale,
    largest_component,
    make_grid,
    remove_thin_noise,
)

RGBArray = NDArray[np.uint8]

BACKGROUND = (212, 228, 205)  # 地図の背景（薄緑）
WHITE_ROAD = (240, 238, 230)
GREENISH_ROAD = (223, 241, 223)
TAN_ROAD = (220, 200, 150)


def blank_image(height: int, width: int, colour: tuple[int, int, int] = BACKGROUND) -> RGBArray:
    """単色塗りつぶし画像の生成。"""
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :] = colour
    return image


class TestBuildColorMask:
    @pytest.mark.parametrize("colour", [WHITE_ROAD, GREENISH_ROAD, TAN_ROAD])
    def test_detects_each_road_colour(self, colour: tuple[int, int, int]) -> None:
        image = blank_image(4, 4)
        image[1:3, :] = colour
        mask = build_color_mask(image)
        assert mask[1:3, :].all()

    def test_background_is_not_a_road(self) -> None:
        """背景の薄緑と緑白色路は近似色。取り違えの不在を確認。"""
        assert not build_color_mask(blank_image(4, 4, BACKGROUND)).any()


class TestUserPath:
    def test_magenta_is_walkable(self) -> None:
        image = blank_image(4, 4)
        image[2, :] = USER_PATH_RGB
        assert build_user_path_mask(image)[2, :].all()

    def test_tolerates_compression_artifacts(self) -> None:
        """再保存時のマゼンタの色ずれ。多少の誤差を許容。"""
        image = blank_image(2, 2)
        image[0, 0] = (255, 0, 252)
        image[0, 1] = (250, 8, 249)
        mask = build_user_path_mask(image)
        assert mask[0, 0] and mask[0, 1]

    def test_user_path_survives_thin_noise_removal(self) -> None:
        """描き込み線の保護。幅1画素でも消滅は不可。"""
        image = blank_image(7, 7)
        image[3, :] = USER_PATH_RGB
        assert build_walkable_mask(image)[3, :].all()


class TestRemoveThinNoise:
    def test_removes_one_pixel_line(self) -> None:
        mask = np.zeros((9, 9), dtype=bool)
        mask[4, :] = True  # 幅1画素の線＝建物の輪郭のような誤検出
        assert not remove_thin_noise(mask).any()

    def test_keeps_thick_area(self) -> None:
        mask = np.zeros((9, 9), dtype=bool)
        mask[2:7, 2:7] = True  # 幅5画素の塊＝本物の道
        assert remove_thin_noise(mask).any()


class TestDownscale:
    def test_shape_shrinks_by_scale(self) -> None:
        mask = np.zeros((10, 8), dtype=bool)
        assert downscale(mask, 2).shape == (5, 4)

    def test_single_walkable_pixel_survives(self) -> None:
        """any 集約の性質。ブロック内1画素で残存。細道の保護が目的。"""
        mask = np.zeros((6, 6), dtype=bool)
        mask[3, 3] = True
        assert downscale(mask, 3)[1, 1]

    def test_scale_one_is_identity(self) -> None:
        mask = np.array([[True, False]], dtype=bool)
        assert np.array_equal(downscale(mask, 1), mask)

    def test_remainder_rows_are_trimmed(self) -> None:
        mask = np.zeros((7, 7), dtype=bool)
        assert downscale(mask, 3).shape == (2, 2)

    @pytest.mark.parametrize("scale", [0, -1])
    def test_rejects_non_positive_scale(self, scale: int) -> None:
        with pytest.raises(ValueError, match="1以上"):
            downscale(np.zeros((4, 4), dtype=bool), scale)

    def test_rejects_scale_larger_than_image(self) -> None:
        with pytest.raises(ValueError, match="大きすぎます"):
            downscale(np.zeros((4, 4), dtype=bool), 5)


class TestLargestComponent:
    def test_keeps_only_the_biggest_blob(self) -> None:
        mask = np.zeros((9, 9), dtype=bool)
        mask[0:2, 0:2] = True  # 小さい島 (4セル)
        mask[4:8, 4:8] = True  # 大きい島 (16セル)
        result = largest_component(mask)
        assert result[4:8, 4:8].all()
        assert not result[0:2, 0:2].any()

    def test_diagonally_touching_blobs_count_as_one(self) -> None:
        mask = np.zeros((4, 4), dtype=bool)
        mask[0, 0] = mask[1, 1] = mask[2, 2] = True
        assert largest_component(mask).sum() == 3

    def test_empty_mask_stays_empty(self) -> None:
        assert not largest_component(np.zeros((4, 4), dtype=bool)).any()


class TestMakeGrid:
    def test_builds_connected_grid_from_drawn_path(self) -> None:
        image = blank_image(30, 30)
        image[10:13, 2:28] = USER_PATH_RGB  # 横一本の道
        grid = make_grid(image, scale=2)
        assert grid.any()
        assert grid.shape == (15, 15)

    def test_isolated_specks_are_dropped(self) -> None:
        image = blank_image(30, 30)
        image[10:13, 2:28] = USER_PATH_RGB  # 本線
        image[27, 27] = USER_PATH_RGB  # 遠く離れた点
        grid = make_grid(image, scale=2)
        assert not grid[13, 13]

    def test_image_without_roads_yields_empty_grid(self) -> None:
        assert not make_grid(blank_image(30, 30), scale=2).any()

    def test_dilation_zero_keeps_grid_thin(self) -> None:
        image = blank_image(30, 30)
        image[10:13, 2:28] = USER_PATH_RGB
        thin = make_grid(image, scale=2, dilation=0)
        thick = make_grid(image, scale=2, dilation=2)
        assert thin.sum() < thick.sum()
