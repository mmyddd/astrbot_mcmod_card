# -*- coding: utf-8 -*-
"""8 维评分雷达图（趣味/难度/稳定/实用/美观/平衡/兼容/耐玩）。

纯 PIL 绘制，避免引入 matplotlib / numpy 等重型依赖。
"""

from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

from astrbot.api import logger

from ..data.models import RATING_KEYS, RATING_LABELS

#: 默认尺寸（宽, 高）
DEFAULT_RADAR_SIZE = (360, 300)

#: 默认配色：珊瑚红数据区 + 白色网格（贴合深色聊天背景）
DEFAULT_LINE_COLOR = (255, 107, 107, 255)
DEFAULT_FILL_COLOR = (255, 107, 107, 90)
DEFAULT_GRID_COLOR = (255, 255, 255, 70)
DEFAULT_TEXT_COLOR = (255, 255, 255, 255)

#: 网格环数
GRID_RINGS = 4


def _load_font(font_path: Optional[str], size: int) -> ImageFont.ImageFont:
    if font_path:
        try:
            if Path(font_path).exists():
                return ImageFont.truetype(font_path, size)
        except Exception as exc:
            logger.warning(f"加载雷达图字体失败: {exc}")
    try:
        return ImageFont.load_default(size)
    except Exception:
        return ImageFont.load_default()


def _axis_points(
    center: Tuple[float, float],
    radius: float,
    count: int,
) -> List[Tuple[float, float]]:
    cx, cy = center
    points = []
    for index in range(count):
        angle = -math.pi / 2 + 2 * math.pi * index / count
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return points


def render_radar(
    rating: Dict[str, int],
    font_path: Optional[str] = None,
    size: Sequence[int] = DEFAULT_RADAR_SIZE,
    keys: Sequence[str] = RATING_KEYS,
    line_color: Sequence[int] = DEFAULT_LINE_COLOR,
    fill_color: Sequence[int] = DEFAULT_FILL_COLOR,
    grid_color: Sequence[int] = DEFAULT_GRID_COLOR,
    text_color: Sequence[int] = DEFAULT_TEXT_COLOR,
) -> Optional[bytes]:
    """把 8 维评分画成雷达图并返回 PNG bytes；数据全为 0 时返回 None。"""
    values = [int(rating.get(key) or 0) for key in keys]
    if not any(value > 0 for value in values):
        return None

    width, height = int(size[0]), int(size[1])
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    font = _load_font(font_path, 13)
    center = (width / 2, height / 2)
    label_room = 34
    radius = max(10.0, min(width, height) / 2 - label_room)
    outer = _axis_points(center, radius, len(keys))

    # 网格环
    for ring in range(1, GRID_RINGS + 1):
        ring_points = _axis_points(center, radius * ring / GRID_RINGS, len(keys))
        draw.polygon(ring_points, outline=grid_color)

    # 轴线
    for point in outer:
        draw.line([center, point], fill=grid_color)

    # 数据区（归一化到最大值，即相对值）
    peak = max(values)
    data_points = _axis_points(center, radius, len(keys))
    shaped = [
        (
            center[0] + (point[0] - center[0]) * value / peak,
            center[1] + (point[1] - center[1]) * value / peak,
        )
        for point, value in zip(data_points, values)
    ]
    draw.polygon(shaped, fill=fill_color, outline=line_color)
    for point in shaped:
        draw.ellipse(
            (point[0] - 2.5, point[1] - 2.5, point[0] + 2.5, point[1] + 2.5),
            fill=line_color,
        )

    # 轴标签：维度名 + 数值
    for point, key, value in zip(outer, keys, values):
        dx, dy = point[0] - center[0], point[1] - center[1]
        length = math.hypot(dx, dy) or 1.0
        label_pos = (point[0] + dx / length * 20, point[1] + dy / length * 16)
        draw.multiline_text(
            label_pos,
            f"{RATING_LABELS.get(key, key)}\n{value}",
            font=font,
            fill=text_color,
            anchor="mm",
            align="center",
            spacing=2,
        )

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
