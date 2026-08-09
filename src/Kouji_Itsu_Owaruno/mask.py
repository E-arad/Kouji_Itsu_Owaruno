"""歩行可能領域の判定。探索グリッドの生成。

判定基準は画素色のみ。系統は2つ。

1. マゼンタ手動指定 — 作者の描き込み線。無条件で通行可能。
   構内通路・階段・建物間の抜け道など、地図描画から道と判別不能な経路の救済。
   本ソフトウェアの主系統。
2. 色条件自動抽出 — 白色路・緑白色路・ベージュ色路。手動指定の補助。
   対象地図は道が描き込み済みのため寄与は僅少。

最終マスクは両系統の論理和。

調整対象は同梱地図のみ。描き込み無しの地図では道の取りこぼしが多数。意味のある経路は不成立。
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy import ndimage

__all__ = [
    "USER_PATH_RGB",
    "build_color_mask",
    "build_walkable_mask",
    "make_grid",
    "remove_thin_noise",
]

BoolArray = NDArray[np.bool_]
RGBArray = NDArray[np.uint8]

#: 描き込み色。「ここは歩ける」の指定用。
USER_PATH_RGB: tuple[int, int, int] = (255, 0, 255)


def build_color_mask(rgb: RGBArray) -> BoolArray:
    """色条件のみによる道路画素の抽出。

    Args:
        rgb: ``(H, W, 3)`` の RGB 画像。

    Returns:
        道路判定画素が ``True`` の ``(H, W)`` 真偽値配列。
    """
    r = rgb[:, :, 0].astype(int)
    g = rgb[:, :, 1].astype(int)
    b = rgb[:, :, 2].astype(int)

    white_road = (r > 228) & (g > 224) & (b > 210) & (np.abs(r - g) < 22)
    # 緑白色路。背景の薄緑 (212,228,205) は b<215 のため除外
    greenish_road = (r > 215) & (g > 232) & (b > 214)
    tan_road = (
        (r > 195) & (r < 245) & (g > 180) & (g < 230) & (b > 110) & (b < 185) & ((r - b) > 40)
    )
    return np.asarray(white_road | greenish_road | tan_road, dtype=bool)


def remove_thin_noise(mask: BoolArray, *, keep_radius: int = 3) -> BoolArray:
    """幅1〜2画素の細線誤検出の除去。

    手順は収縮・膨張・積。収縮で「太い芯」のみ残存。芯の膨張範囲と元マスクの積を採用。
    十分な幅の道は芯が生存。建物輪郭のような細線のみ消滅。

    Args:
        mask: 元の通行可能マスク。
        keep_radius: 芯の膨張回数。大きいほど元形状を保持。

    Returns:
        細線成分の除去後マスク。
    """
    structure = np.ones((3, 3), dtype=bool)
    core = ndimage.binary_erosion(mask, structure=structure, iterations=1)
    grown = ndimage.binary_dilation(core, structure=structure, iterations=keep_radius)
    return np.asarray(mask & grown, dtype=bool)


def build_user_path_mask(rgb: RGBArray) -> BoolArray:
    """マゼンタ描き込み領域の抽出。

    再保存時の色ずれを考慮。厳密一致ではなく余裕を持った範囲判定。
    """
    r = rgb[:, :, 0].astype(int)
    g = rgb[:, :, 1].astype(int)
    b = rgb[:, :, 2].astype(int)
    return np.asarray((r > 200) & (g < 90) & (b > 200), dtype=bool)


def build_walkable_mask(rgb: RGBArray) -> BoolArray:
    """自動抽出と手動指定の統合。最終的な通行可能マスク。"""
    color = remove_thin_noise(build_color_mask(rgb))
    return np.asarray(color | build_user_path_mask(rgb), dtype=bool)


def downscale(mask: BoolArray, scale: int) -> BoolArray:
    """``scale`` 画素四方ブロックの1セルへの集約。

    ブロック内に通行可能画素が1個でも存在すれば通行可能セル扱い（``any`` 集約）。
    細道の消失防止が目的。
    """
    if scale < 1:
        raise ValueError(f"scale は1以上である必要があります: {scale}")
    if scale == 1:
        return mask
    h, w = mask.shape
    hh, ww = h // scale, w // scale
    if hh == 0 or ww == 0:
        raise ValueError(f"scale={scale} は画像 {mask.shape} に対して大きすぎます")
    trimmed = mask[: hh * scale, : ww * scale]
    return np.asarray(trimmed.reshape(hh, scale, ww, scale).any(axis=(1, 3)), dtype=bool)


def largest_component(mask: BoolArray) -> BoolArray:
    """最大連結成分の抽出。

    色条件由来の孤立領域、および未接続の道を除去。
    通行可能セルが皆無なら全 ``False`` をそのまま返す。
    """
    if not mask.any():
        return mask
    labels, _ = ndimage.label(mask, structure=np.ones((3, 3)))
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0  # 背景の除外
    return np.asarray(labels == sizes.argmax(), dtype=bool)


def make_grid(rgb: RGBArray, scale: int, *, dilation: int = 2) -> BoolArray:
    """RGB画像からの探索グリッド生成。

    工程は縮小・膨張・成分抽出。``scale`` 分の1へ縮小。縮小由来の途切れを膨張で接続。
    最終的に最大連結成分のみ残存。

    Args:
        rgb: ``(H, W, 3)`` の RGB 画像。
        scale: 縮小率。大きいほど高速。ただし経路の道外れが増加。
        dilation: 縮小後の膨張回数。
            経路の道外側へのはみ出しは最大 ``dilation * scale`` 画素。

    Returns:
        探索対象セルが ``True`` のグリッド。
    """
    mask = build_walkable_mask(rgb)
    small = downscale(mask, scale)
    if dilation > 0:
        small = np.asarray(
            ndimage.binary_dilation(small, structure=np.ones((3, 3)), iterations=dilation),
            dtype=bool,
        )
    return largest_component(small)
