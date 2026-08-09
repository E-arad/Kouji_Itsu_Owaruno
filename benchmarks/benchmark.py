"""縮小率と探索性能の関係の計測。

検証する問いは2つ。

1. ``--scale`` の適正値。増加により探索は高速化。ただしグリッド膨張の分だけ
   経路の道外れが増加。速度と経路品質の両方を計測し折衷点を特定。
2. 本ソフトウェアの必要性。目測による2点間距離と、実際の道のりとの乖離を計測。

使い方::

    uv run python benchmarks/benchmark.py
    uv run python benchmarks/benchmark.py --plot results.pdf

作図には matplotlib が必要（``uv add --group dev matplotlib``）。
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image
from scipy import ndimage

from Kouji_Itsu_Owaruno.mask import build_walkable_mask, make_grid
from Kouji_Itsu_Owaruno.search import bfs, path_length_px, path_to_pixels, snap_to_walkable

BoolArray = NDArray[np.bool_]
Cell = tuple[int, int]

DEFAULT_MAP = (
    Path(__file__).resolve().parents[1] / "src" / "Kouji_Itsu_Owaruno" / "data" / "map.png"
)
SCALES = (1, 2, 3, 4, 6, 8)
REPEATS = 3
SEED = 0


@dataclass(frozen=True)
class ScaleResult:
    """ある縮小率での測定結果。"""

    scale: int
    cells: int
    grid_seconds: float
    search_median: float
    search_worst: float
    mean_deviation_px: float
    on_road_ratio: float
    search_times: list[float]


def sample_pairs(
    grid: BoolArray, count: int, min_distance_cells: float, seed: int = SEED
) -> list[tuple[Cell, Cell]]:
    """十分離れた地点ペアの無作為抽出。シード固定による再現性の確保。"""
    ys, xs = np.nonzero(grid)
    rng = np.random.default_rng(seed)
    pairs: list[tuple[Cell, Cell]] = []
    while len(pairs) < count:
        i, j = rng.integers(0, len(ys), 2)
        start = (int(ys[i]), int(xs[i]))
        goal = (int(ys[j]), int(xs[j]))
        if np.hypot(start[0] - goal[0], start[1] - goal[1]) >= min_distance_cells:
            pairs.append((start, goal))
    return pairs


def road_half_width_px(walkable: BoolArray) -> float:
    """道の代表的な半幅の算出。経路の道上判定の基準値。"""
    inside = ndimage.distance_transform_edt(walkable)
    peaks = ndimage.maximum_filter(inside, size=9)
    ridge = inside[(inside >= peaks - 1e-9) & (inside > 2)]
    return float(np.median(ridge))


def measure_scales(rgb: NDArray[np.uint8], scales: tuple[int, ...]) -> list[ScaleResult]:
    """縮小率ごとの探索時間と経路品質の計測。"""
    walkable = build_walkable_mask(rgb)
    distance_to_road = ndimage.distance_transform_edt(~walkable)
    tolerance = road_half_width_px(walkable)
    height, width = walkable.shape

    reference = make_grid(rgb, 1)
    pairs_px = [((sy, sx), (gy, gx)) for (sy, sx), (gy, gx) in sample_pairs(reference, 8, 1200.0)]

    results: list[ScaleResult] = []
    for scale in scales:
        started = time.perf_counter()
        grid = make_grid(rgb, scale)
        grid_seconds = time.perf_counter() - started

        timings: list[float] = []
        deviations: list[float] = []
        on_road: list[float] = []

        for (sy, sx), (gy, gx) in pairs_px:
            start = snap_to_walkable(grid, sy // scale, sx // scale)
            goal = snap_to_walkable(grid, gy // scale, gx // scale)
            if start is None or goal is None:
                continue

            runs = []
            path = None
            for _ in range(REPEATS):
                tick = time.perf_counter()
                path = bfs(grid, start, goal)
                runs.append(time.perf_counter() - tick)
            if path is None:
                continue

            timings.append(min(runs))
            pixels = path_to_pixels(path, scale)
            rows = np.clip([y for _x, y in pixels], 0, height - 1)
            cols = np.clip([x for x, _y in pixels], 0, width - 1)
            distances = distance_to_road[rows, cols]
            deviations.append(float(distances.mean()))
            on_road.append(float((distances <= tolerance).mean()))

        results.append(
            ScaleResult(
                scale=scale,
                cells=int(grid.sum()),
                grid_seconds=grid_seconds,
                search_median=float(np.median(timings)),
                search_worst=float(max(timings)),
                mean_deviation_px=float(np.mean(deviations)),
                on_road_ratio=float(np.mean(on_road)),
                search_times=timings,
            )
        )
    return results


def measure_detour(rgb: NDArray[np.uint8], scale: int, count: int = 200) -> list[float]:
    """実際の道のりと直線距離との倍率の収集。"""
    grid = make_grid(rgb, scale)
    ratios: list[float] = []
    for start, goal in sample_pairs(grid, count, 400.0 / scale):
        path = bfs(grid, start, goal)
        if path is None:
            continue
        straight = float(np.hypot(start[0] - goal[0], start[1] - goal[1]) * scale)
        ratios.append(path_length_px(path_to_pixels(path, scale)) / straight)
    return ratios


def render_figure(results: list[ScaleResult], ratios: list[float], output: Path) -> None:
    """測定結果の3枚のグラフ化。matplotlib 不在なら何もせず終了。"""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib が無いため図は作成しません")
        return

    scales = [r.scale for r in results]
    figure, axes = plt.subplots(1, 3, figsize=(7.6, 2.45))

    axes[0].plot(scales, [r.search_median for r in results], "o-")
    axes[0].axhline(1.0, color="red", ls="--", lw=1, label="1.0 s")
    axes[0].set_yscale("log")
    axes[0].set_xlabel("scale")
    axes[0].set_ylabel("search time [s]")
    axes[0].legend(fontsize=7)

    axes[1].plot(scales, [100 * r.on_road_ratio for r in results], "s-", color="green")
    axes[1].set_xlabel("scale")
    axes[1].set_ylabel("path on road [%]")

    axes[2].hist(ratios, bins=np.arange(1.0, 4.0, 0.2), color="#7aa8cc", edgecolor="white")
    axes[2].axvline(float(np.median(ratios)), color="red", ls="--", lw=1.3)
    axes[2].set_xlabel("actual / straight-line")
    axes[2].set_ylabel("pairs")

    for axis in axes:
        axis.grid(alpha=0.3)
    figure.tight_layout()
    figure.savefig(output)
    print(f"図を保存しました: {output}")


def main(argv: list[str] | None = None) -> int:
    """ベンチマークの実行と結果表示。"""
    parser = argparse.ArgumentParser(description="縮小率と探索性能の関係を測ります。")
    parser.add_argument("map_image", nargs="?", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--json", type=Path, help="結果を JSON で保存する")
    parser.add_argument("--plot", type=Path, help="グラフを保存する (.pdf / .png)")
    args = parser.parse_args(argv)

    Image.MAX_IMAGE_PIXELS = None
    rgb = np.asarray(Image.open(args.map_image).convert("RGB"))
    print(f"地図: {args.map_image}  {rgb.shape[1]}x{rgb.shape[0]} 画素")

    results = measure_scales(rgb, SCALES)
    print(
        f"\n{'scale':>5} {'cells':>10} {'median[s]':>10} {'worst[s]':>9} "
        f"{'dev[px]':>8} {'on road':>8}"
    )
    for row in results:
        print(
            f"{row.scale:>5} {row.cells:>10,} {row.search_median:>10.3f} "
            f"{row.search_worst:>9.3f} {row.mean_deviation_px:>8.2f} "
            f"{100 * row.on_road_ratio:>7.1f}%"
        )

    ratios = measure_detour(rgb, scale=2)
    median = float(np.median(ratios))
    print(f"\n実際の道のり / 直線距離  (n={len(ratios)})")
    print(
        f"  中央値 {median:.2f} 倍   四分位 {np.percentile(ratios, 25):.2f}"
        f"-{np.percentile(ratios, 75):.2f}   最大 {max(ratios):.2f}"
    )
    print(f"  1.5倍を超えたペア: {100 * float(np.mean(np.array(ratios) > 1.5)):.0f}%")

    if args.json:
        payload: dict[str, Any] = {
            "scales": [asdict(r) for r in results],
            "detour_ratios": ratios,
        }
        args.json.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        print(f"\nJSON を保存しました: {args.json}")

    if args.plot:
        render_figure(results, ratios, args.plot)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
