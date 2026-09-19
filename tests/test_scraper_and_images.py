# -*- coding: utf-8 -*-
"""缓存与图片渲染测试。"""

from __future__ import annotations

import json

from mcmod_plugin.data.html_scraper import (
    cache_path,
    parse_page,
    read_cache,
    write_cache,
)
from mcmod_plugin.data.models import SCHEMA_VERSION
from mcmod_plugin.img.render_cover import render_cover
from mcmod_plugin.img.render_radar import render_radar

URL = "https://www.mcmod.cn/class/2524.html"


def test_cache_write_and_read(tmp_path) -> None:
    payload = {"schema": SCHEMA_VERSION, "meta": {}, "sections": []}
    write_cache(tmp_path, URL, payload)
    assert cache_path(tmp_path, URL).exists()
    assert read_cache(tmp_path, URL, ttl=3600) == payload


def test_cache_ignores_legacy_schema(tmp_path) -> None:
    path = cache_path(tmp_path, URL)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"timestamp": 9999999999, "content": {"description": "old"}}),
        encoding="utf-8",
    )
    assert read_cache(tmp_path, URL, ttl=3600) is None


def test_cache_respects_ttl(tmp_path) -> None:
    payload = {"schema": SCHEMA_VERSION, "meta": {}, "sections": []}
    write_cache(tmp_path, URL, payload)
    assert read_cache(tmp_path, URL, ttl=3600) is not None
    assert read_cache(tmp_path, URL, ttl=0) is None


def test_cache_disabled_without_dir() -> None:
    assert read_cache(None, URL, ttl=3600) is None
    write_cache(None, URL, {})  # 不应抛异常


def test_parse_page_returns_serializable_payload(class_2524_html: str) -> None:
    payload = parse_page(class_2524_html, URL, "class")
    assert payload is not None
    assert payload["schema"] == SCHEMA_VERSION
    assert payload["meta"]["chinese_name"] == "Gregicality Legacy"
    assert len(payload["sections"]) == 6
    json.dumps(payload, ensure_ascii=False)  # 必须可 JSON 序列化


def test_parse_page_on_garbage_returns_none() -> None:
    assert parse_page("<html></html>", URL, "class") is None


def test_render_cover_produces_square_png() -> None:
    from PIL import Image
    import io

    source = Image.new("RGB", (640, 480), (120, 60, 200))
    buffer = io.BytesIO()
    source.save(buffer, format="PNG")
    result = render_cover(buffer.getvalue(), size=128)
    assert result is not None
    with Image.open(io.BytesIO(result)) as image:
        assert image.size == (128, 128)
        assert image.format == "PNG"


def test_render_cover_handles_bad_input() -> None:
    assert render_cover(None) is None
    assert render_cover(b"not an image") is None


def test_render_radar_bytes() -> None:
    rating = {
        "fun": 72, "difficulty": 68, "stability": 31, "practicality": 61,
        "aesthetics": 50, "balance": 52, "compatibility": 36, "durability": 70,
    }
    result = render_radar(rating)
    assert result is not None and result[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_radar_returns_none_without_data() -> None:
    assert render_radar({}) is None
    assert render_radar({"fun": 0, "difficulty": 0}) is None
