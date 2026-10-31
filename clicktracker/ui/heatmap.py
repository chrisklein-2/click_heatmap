"""Heatmap maths and the matplotlib canvas that draws it."""
from __future__ import annotations

from dataclasses import dataclass

from PyQt6 import QtWidgets  # noqa: F401  (import first so matplotlib uses PyQt6)

import matplotlib
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.patches import PathPatch, Rectangle
from matplotlib.path import Path

from .theme import BG, BORDER, BORDER_BRIGHT, SURFACE, TEXT, TEXT_DIM

MAX_GRID = 720  # longest side of the density grid
DEFAULT_MONITOR = {"name": "Screen", "x": 0, "y": 0, "width": 1920, "height": 1080}
BUTTON_COLORS = {"left": "#ffffff", "right": "#4dd0e1", "middle": "#ffd54f"}
OTHER_BUTTON_COLOR = "#ff8a65"


@dataclass
class RenderOptions:
    show_heat: bool = True
    show_points: bool = False
    sigma: float = 40
    colormap: str = "turbo"
    opacity: float = 0.7
    boost: bool = False
    point_size: float = 8


# ------------------------------------------------------------------ maths
def monitor_bounds(monitors: list[dict]) -> tuple[int, int, int, int]:
    return (min(m["x"] for m in monitors), min(m["y"] for m in monitors),
            max(m["x"] + m["width"] for m in monitors), max(m["y"] + m["height"] for m in monitors))


def clamp_to_monitors(xs: np.ndarray, ys: np.ndarray, monitors: list[dict]):
    """Move any point that lies outside every monitor to the nearest monitor edge."""
    best_x, best_y = xs.copy(), ys.copy()
    best_d = np.full(xs.shape, np.inf)
    for m in monitors:
        cx = np.clip(xs, m["x"], m["x"] + m["width"] - 1)
        cy = np.clip(ys, m["y"], m["y"] + m["height"] - 1)
        d = (cx - xs) ** 2 + (cy - ys) ** 2
        closer = d < best_d
        best_x[closer], best_y[closer], best_d[closer] = cx[closer], cy[closer], d[closer]
    return best_x, best_y


def _gaussian_matrix(n: int, sigma: float) -> np.ndarray:
    idx = np.arange(n, dtype=np.float64)
    d = idx[:, None] - idx[None, :]
    return np.exp(-(d * d) / (2.0 * sigma * sigma))


def compute_density(xs, ys, monitors, bounds, sigma_px):
    """Blurred click density (0..1) plus a mask of grid cells that lie on a screen."""
    x0, y0, x1, y1 = bounds
    width, height = max(1, x1 - x0), max(1, y1 - y0)
    scale = min(1.0, MAX_GRID / max(width, height))
    gw, gh = max(2, round(width * scale)), max(2, round(height * scale))

    # Which cells are on a monitor (cell centres tested against each rectangle).
    cx = x0 + (np.arange(gw) + 0.5) * (width / gw)
    cy = y0 + (np.arange(gh) + 0.5) * (height / gh)
    mask = np.zeros((gh, gw), dtype=bool)
    for m in monitors:
        in_x = (cx >= m["x"]) & (cx < m["x"] + m["width"])
        in_y = (cy >= m["y"]) & (cy < m["y"] + m["height"])
        mask |= in_y[:, None] & in_x[None, :]

    hist, _, _ = np.histogram2d(ys, xs, bins=(gh, gw), range=((y0, y1), (x0, x1)))
    sigma = max(0.6, sigma_px * scale)
    density = _gaussian_matrix(gh, sigma) @ hist @ _gaussian_matrix(gw, sigma)
    density[~mask] = 0.0  # no heat outside the screens
    peak = density.max()
    if peak > 0:
        density /= peak
    return density, mask


def _screen_clip(ax, monitors: list[dict]) -> PathPatch:
    """Compound path of all monitor rectangles, used to clip heat and dots exactly."""
    verts, codes = [], []
    for m in monitors:
        x0, y0 = m["x"], m["y"]
        x1, y1 = x0 + m["width"], y0 + m["height"]
        verts += [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
        codes += [Path.MOVETO, Path.LINETO, Path.LINETO, Path.LINETO, Path.CLOSEPOLY]
    return PathPatch(Path(verts, codes), transform=ax.transData)


# ----------------------------------------------------------------- canvas
class HeatmapCanvas(FigureCanvasQTAgg):
    def __init__(self, parent=None):
        super().__init__(Figure(facecolor=BG))
        self.setParent(parent)
        self.ax = self.figure.add_axes((0.01, 0.01, 0.98, 0.98))
        self.ax.set_facecolor(BG)
        self.ax.set_axis_off()
        self.setMinimumSize(400, 250)

    def render(self, clicks, monitors, background=None, background_bounds=None,
               options: RenderOptions | None = None) -> None:
        opts = options or RenderOptions()
        ax = self.ax
        ax.clear()
        ax.set_facecolor(BG)
        ax.set_axis_off()

        monitors = monitors or [DEFAULT_MONITOR]
        x0, y0, x1, y1 = bounds = monitor_bounds(monitors)
        clip = _screen_clip(ax, monitors)

        # Screen backdrop: a screenshot or plain monitor shapes.
        if background is not None and background_bounds is not None:
            bx0, by0, bx1, by1 = background_bounds
            img = ax.imshow(background, extent=(bx0, bx1, by1, by0), interpolation="bilinear", zorder=0)
            img.set_clip_path(clip)
        else:
            for m in monitors:
                ax.add_patch(Rectangle((m["x"], m["y"]), m["width"], m["height"],
                                       facecolor=SURFACE, edgecolor="none", zorder=0))

        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if clicks:
            xs = np.fromiter((c[0] for c in clicks), float, count=len(clicks))
            ys = np.fromiter((c[1] for c in clicks), float, count=len(clicks))
            xs, ys = clamp_to_monitors(xs, ys, monitors)

            if opts.show_heat:
                density, mask = compute_density(xs, ys, monitors, bounds, opts.sigma)
                if opts.boost:
                    density = np.sqrt(density)
                rgba = matplotlib.colormaps[opts.colormap](density)
                rgba[..., 3] = np.clip(density / 0.3, 0.0, 1.0) * opts.opacity * mask
                heat = ax.imshow(rgba, extent=(x0, x1, y1, y0), interpolation="bilinear", zorder=2)
                heat.set_clip_path(clip)

            if opts.show_points:
                self._draw_points(xs, ys, [c[2] for c in clicks], opts.point_size, clip)

            if not opts.show_heat and not opts.show_points:
                ax.text(cx, cy, "All layers are hidden", color=TEXT_DIM,
                        ha="center", va="center", fontsize=14, zorder=6)
        else:
            ax.text(cx, cy, "No clicks match the current filters", color=TEXT_DIM,
                    ha="center", va="center", fontsize=14, zorder=6)

        for i, m in enumerate(monitors, 1):
            ax.add_patch(Rectangle((m["x"], m["y"]), m["width"], m["height"], fill=False,
                                   edgecolor=BORDER_BRIGHT, linewidth=1.4, zorder=5))
            ax.text(m["x"] + 12, m["y"] + 12, f"Display {i} · {m['width']}×{m['height']}",
                    color=TEXT_DIM, fontsize=8, ha="left", va="top", zorder=6)

        # Small margin so screen edges are visible (and nothing is drawn in it).
        mx, my = (x1 - x0) * 0.01, (y1 - y0) * 0.01
        ax.set_xlim(x0 - mx, x1 + mx)
        ax.set_ylim(y1 + my, y0 - my)  # screen y grows downward
        ax.set_aspect("equal", adjustable="box")
        self.draw_idle()

    def _draw_points(self, xs, ys, buttons, size, clip) -> None:
        buttons = np.asarray(buttons, dtype=object)
        order = list(BUTTON_COLORS)
        names = sorted(set(buttons.tolist()), key=lambda b: order.index(b) if b in order else 99)
        for name in names:
            sel = buttons == name
            dots = self.ax.scatter(xs[sel], ys[sel], s=size,
                                   c=BUTTON_COLORS.get(name, OTHER_BUTTON_COLOR),
                                   edgecolors="black", linewidths=0.4, alpha=0.85, zorder=3,
                                   label=f"{name}  ({int(sel.sum()):,})")
            dots.set_clip_path(clip)
        self.ax.legend(loc="upper right", facecolor=SURFACE, edgecolor=BORDER,
                       labelcolor=TEXT, fontsize=8, framealpha=0.9)

    def export_png(self, path: str) -> None:
        self.figure.savefig(path, dpi=200, facecolor=BG, bbox_inches="tight", pad_inches=0.05)