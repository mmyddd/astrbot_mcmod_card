# -*- coding: utf-8 -*-
"""封面缩略图渲染：居中裁切为正方形 PNG，保证转发节点内排版稳定。"""

from __future__ import annotations

import io
from typing import Optional, Tuple

from PIL import Image

from astrbot.api import logger

DEFAULT_COVER_SIZE = 256


def render_cover(
    data: Optional[bytes],
    size: int = DEFAULT_COVER_SIZE,
    max_aspect: float = 1.6,
) -> Optional[bytes]:
    """把封面图裁切并缩放为 ``size x size`` 的 PNG，失败返回 None。"""
    if not data:
        return None
    try:
        with Image.open(io.BytesIO(data)) as image:
            image = image.convert("RGBA")
            width, height = image.size
            if width <= 0 or height <= 0:
                return None

            side = min(width, height)
            if width >= height and width / max(height, 1) > max_aspect:
                # 过宽的长图（如 960x200 横幅）只取中间 1:1 区域
                side = min(height, width)
            left = max(0, (width - side) // 2)
            top = max(0, (height - side) // 2)
            cropped = image.crop((left, top, left + side, top + side))
            resized = cropped.resize((size, size), Image.Resampling.LANCZOS)

            buffer = io.BytesIO()
            resized.save(buffer, format="PNG")
            return buffer.getvalue()
    except Exception as exc:
        logger.warning(f"封面缩略图渲染失败: {exc}")
        return None


def cover_size() -> Tuple[int, int]:
    return (DEFAULT_COVER_SIZE, DEFAULT_COVER_SIZE)
