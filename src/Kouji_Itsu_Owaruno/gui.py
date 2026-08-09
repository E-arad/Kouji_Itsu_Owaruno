"""Tkinter による地図表示と操作。
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image, ImageTk

from Kouji_Itsu_Owaruno import mask as mask_mod
from Kouji_Itsu_Owaruno import search as search_mod
from Kouji_Itsu_Owaruno.config import (
    DEFAULT_LATITUDE,
    DEFAULT_LONGITUDE,
    DEFAULT_SCALE,
    DISPLAY_MAX_WIDTH,
)
from Kouji_Itsu_Owaruno.weather import Weather, fetch_weather

if TYPE_CHECKING:
    from numpy.typing import NDArray

__all__ = ["App", "run"]

_START_COLOR = "#0078ff"
_GOAL_COLOR = "#00a000"
#: 経路の描画色。地図の道はマゼンタ。補色に近い黄系が最も判別しやすい。
#: 純黄 (#ffff00) は淡緑の地物との差が小さく、かつ長時間の閲覧で目が疲れる。
#: ゆえに彩度をわずかに落とした山吹色を採用。
_ROUTE_COLOR = "#ffd400"


class App:
    """地図表示と2点間経路描画のウィンドウ。"""

    def __init__(
        self,
        root: tk.Tk,
        image_path: Path,
        *,
        scale: int = DEFAULT_SCALE,
        latitude: float = DEFAULT_LATITUDE,
        longitude: float = DEFAULT_LONGITUDE,
    ) -> None:
        self.root = root
        self.image_path = image_path
        self.scale = scale
        self.latitude = latitude
        self.longitude = longitude

        self.image: Image.Image | None = None
        self.grid: NDArray[np.bool_] | None = None
        self.display_scale = 1.0
        self.fit_scale = 1.0
        self._photo: ImageTk.PhotoImage | None = None
        self.start: tuple[int, int] | None = None  # 元画像座標 (x, y)
        self.goal: tuple[int, int] | None = None
        self.route_px: list[tuple[int, int]] | None = None
        self.busy = False

        root.title("徒歩での最短経路")
        self._build_widgets()
        root.after(50, self._load_image)

    # ------------------------------------------------------------------ 画面構築

    def _build_widgets(self) -> None:
        bar = tk.Frame(self.root)
        bar.pack(fill=tk.X)
        reset = tk.Button(bar, text="リセット", command=self.reset_points)
        reset.pack(side=tk.LEFT, padx=4, pady=4)
        tk.Button(bar, text="天気", command=self.check_weather).pack(side=tk.LEFT, padx=4)
        zoom_in = tk.Button(bar, text="拡大 +", command=lambda: self.zoom(1.25))
        zoom_in.pack(side=tk.LEFT, padx=(12, 2))
        zoom_out = tk.Button(bar, text="縮小 −", command=lambda: self.zoom(0.8))
        zoom_out.pack(side=tk.LEFT, padx=2)
        self.status = tk.Label(bar, text="地図を読み込んでいます…", anchor="w")
        self.status.pack(side=tk.LEFT, padx=10)

        frame = tk.Frame(self.root)
        frame.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(frame, bg="#dddddd", cursor="crosshair")
        vbar = tk.Scrollbar(frame, orient=tk.VERTICAL, command=self.canvas.yview)
        hbar = tk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)
        hbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<MouseWheel>", self.on_wheel)  # Windows / macOS 用
        self.canvas.bind("<Button-4>", lambda _e: self.zoom(1.25))  # Linux 用
        self.canvas.bind("<Button-5>", lambda _e: self.zoom(0.8))

    def set_status(self, text: str) -> None:
        """ステータス行の文言の差し替え。"""
        self.status.config(text=text)

    # ------------------------------------------------------------------ 読み込み

    def _load_image(self) -> None:
        if not self.image_path.exists():
            messagebox.showerror(
                "画像が見つかりません", f"次の場所に画像がありません:\n{self.image_path}"
            )
            self.root.destroy()
            return

        self.image = Image.open(self.image_path).convert("RGB")
        width, _height = self.image.size
        self.fit_scale = min(1.0, DISPLAY_MAX_WIDTH / width)
        self.display_scale = self.fit_scale
        self.render()
        self.reset_points()
        self.set_status("通行可能な道を解析中…")
        self.busy = True
        threading.Thread(target=self._build_grid_worker, daemon=True).start()

    def _build_grid_worker(self) -> None:
        assert self.image is not None
        grid = mask_mod.make_grid(np.asarray(self.image), self.scale)
        self.root.after(0, self._on_grid_ready, grid)

    def _on_grid_ready(self, grid: NDArray[np.bool_]) -> None:
        self.grid = grid
        self.busy = False
        if not grid.any():
            self.set_status("通行可能な道が見つかりませんでした")
            messagebox.showwarning(
                "道が見つかりません",
                "同梱の地図から歩ける道を検出できませんでした。\n"
                "地図ファイルが壊れている可能性があります。",
            )
            return
        self.set_status("地図をクリックして始点を指定してください")

    # ------------------------------------------------------------------ 描画

    def render(self) -> None:
        """現在の表示倍率での全再描画。対象は地図・マーカー・経路。"""
        if self.image is None:
            return
        width, height = self.image.size
        resample = Image.Resampling.LANCZOS if self.display_scale < 1 else Image.Resampling.NEAREST
        shown = self.image.resize(
            (max(1, int(width * self.display_scale)), max(1, int(height * self.display_scale))),
            resample,
        )
        self._photo = ImageTk.PhotoImage(shown)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self._photo, tags="map")
        self.canvas.configure(scrollregion=(0, 0, shown.width, shown.height))

        if self.start is not None:
            self._draw_marker(self.start, _START_COLOR, "start")
        if self.goal is not None:
            self._draw_marker(self.goal, _GOAL_COLOR, "goal")
        if self.route_px:
            points: list[float] = []
            for px, py in self.route_px:
                points.extend([px * self.display_scale, py * self.display_scale])
            self.canvas.create_line(
                *points,
                fill=_ROUTE_COLOR,
                width=max(2, int(4 * self.display_scale / self.fit_scale)),
                tags="route",
            )

    def _draw_marker(self, point: tuple[int, int], color: str, tag: str) -> None:
        x = point[0] * self.display_scale
        y = point[1] * self.display_scale
        radius = 7
        self.canvas.create_oval(
            x - radius,
            y - radius,
            x + radius,
            y + radius,
            fill=color,
            outline="white",
            width=2,
            tags=tag,
        )

    def zoom(self, factor: float, focus: tuple[float, float] | None = None) -> None:
        """表示倍率の ``factor`` 倍。``focus`` の画面位置は固定。"""
        if self.image is None:
            return
        lo, hi = self.fit_scale * 0.5, self.fit_scale * 4
        new_scale = min(hi, max(lo, self.display_scale * factor))
        if abs(new_scale - self.display_scale) < 1e-9:
            return

        if focus is None:
            focus = (self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2)
        origin_x = self.canvas.canvasx(focus[0]) / self.display_scale
        origin_y = self.canvas.canvasy(focus[1]) / self.display_scale

        self.display_scale = new_scale
        self.render()

        width, height = self.image.size
        total_w, total_h = width * self.display_scale, height * self.display_scale
        self.canvas.xview_moveto(max(0.0, (origin_x * self.display_scale - focus[0]) / total_w))
        self.canvas.yview_moveto(max(0.0, (origin_y * self.display_scale - focus[1]) / total_h))

    def on_wheel(self, event: tk.Event[tk.Canvas]) -> None:
        """ホイール操作による拡大縮小。"""
        self.zoom(1.25 if event.delta > 0 else 0.8, focus=(event.x, event.y))

    # ------------------------------------------------------------------ 経路探索

    def on_click(self, event: tk.Event[tk.Canvas]) -> None:
        """1回目クリックで始点確定。2回目で終点確定と探索開始。"""
        if self.image is None or self.grid is None or self.busy:
            return
        x = int(self.canvas.canvasx(event.x) / self.display_scale)
        y = int(self.canvas.canvasy(event.y) / self.display_scale)

        if self.start is None:
            self.start = (x, y)
            self._draw_marker(self.start, _START_COLOR, "start")
            self.set_status("次に終点をクリックしてください")
        elif self.goal is None:
            self.goal = (x, y)
            self._draw_marker(self.goal, _GOAL_COLOR, "goal")
            self.set_status("経路を探索中…")
            self.busy = True
            threading.Thread(target=self._search_worker, daemon=True).start()

    def _search_worker(self) -> None:
        assert self.grid is not None and self.start is not None and self.goal is not None
        start = search_mod.snap_to_walkable(
            self.grid, self.start[1] // self.scale, self.start[0] // self.scale
        )
        goal = search_mod.snap_to_walkable(
            self.grid, self.goal[1] // self.scale, self.goal[0] // self.scale
        )
        path = None if start is None or goal is None else search_mod.bfs(self.grid, start, goal)
        self.root.after(0, self._on_search_done, path)

    def _on_search_done(self, path: list[tuple[int, int]] | None) -> None:
        self.busy = False
        if path is None:
            messagebox.showwarning(
                "経路なし", "経路が見つかりませんでした。\n点の位置を変えて試してください。"
            )
            self.reset_points()
            return
        self.route_px = search_mod.path_to_pixels(path, self.scale)
        self.render()
        length = search_mod.path_length_px(self.route_px)
        self.set_status(f"経路を表示しました（長さ 約{length:,.0f} px）。リセットで再指定できます")

    def reset_points(self) -> None:
        """始点・終点・経路の消去。初期状態への復帰。"""
        self.start = None
        self.goal = None
        self.route_px = None
        for tag in ("start", "goal", "route"):
            self.canvas.delete(tag)
        if self.image is not None and self.grid is not None:
            self.set_status("地図をクリックして始点を指定してください")

    # ------------------------------------------------------------------ 天気

    def check_weather(self) -> None:
        """現在天気の取得と表示。UI凍結の回避のため別スレッドで実行。"""
        self.set_status("天気を取得中…")
        threading.Thread(target=self._weather_worker, daemon=True).start()

    def _weather_worker(self) -> None:
        try:
            weather = fetch_weather(self.latitude, self.longitude)
        except Exception as exc:
            self.root.after(0, self._on_weather_error, exc)
            return
        self.root.after(0, self._on_weather_ready, weather)

    def _on_weather_error(self, exc: Exception) -> None:
        messagebox.showerror(
            "天気取得エラー", f"取得に失敗しました:\n{exc}\n\nネット接続を確認してください"
        )
        self.set_status("天気の取得に失敗しました")

    def _on_weather_ready(self, weather: Weather) -> None:
        if weather.is_bad:
            messagebox.showwarning(
                "悪天候です", weather.summary() + "\n\n危険ですので本日は利用しないでください！"
            )
        else:
            fine = weather.code in (0, 1, 2)
            hint = "歩ける天気です" if fine else "天気の急変に注意してください"
            messagebox.showinfo("灘区の今の天気", weather.summary() + "\n\n" + hint)
        self.set_status("天気を表示しました")


def run(
    image_path: Path,
    *,
    scale: int = DEFAULT_SCALE,
    latitude: float = DEFAULT_LATITUDE,
    longitude: float = DEFAULT_LONGITUDE,
) -> None:
    """ウィンドウの生成とイベントループの開始。"""
    root = tk.Tk()
    root.geometry("1050x780")
    App(root, image_path, scale=scale, latitude=latitude, longitude=longitude)
    root.mainloop()
