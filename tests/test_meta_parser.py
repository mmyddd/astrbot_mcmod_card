# -*- coding: utf-8 -*-
"""头部信息解析测试（字段值来自实测页面）。"""

from __future__ import annotations

from bs4 import BeautifulSoup

from mcmod_plugin.data.meta_parser import MetaParser

URL_2524 = "https://www.mcmod.cn/class/2524.html"
URL_MODPACK = "https://www.mcmod.cn/modpack/1.html"


def parse(html: str, url: str, content_type: str = "class"):
    return MetaParser(BeautifulSoup(html, "lxml"), url=url, content_type=content_type).parse()


def test_class_2524_meta(class_2524_html: str) -> None:
    meta = parse(class_2524_html, URL_2524)
    assert meta.display_name == "[GCY] Gregicality Legacy"
    assert meta.status == ["停更", "开源"]
    assert meta.tags == ["格雷", "格雷科技", "GT", "GregTech", "GTCE", "GTAdditions"]
    assert len(meta.authors) == 11
    assert meta.authors[0] == "decal06"
    assert meta.mc_versions == {"Forge": ["1.12.2"]}
    assert meta.view_count == "753.59万"
    assert meta.fill_rate == "92.40%"
    assert meta.heat_index == "951"
    assert meta.heat_average == "38.131"
    assert meta.rating_score == "5.0"
    assert meta.rating_level == "名扬天下"
    assert (meta.red_count, meta.red_percentage) == ("27", "93%")
    assert (meta.black_count, meta.black_percentage) == ("2", "7%")
    assert meta.modpack_count == "2"
    assert meta.cover_url.endswith("1589344585_2_DuIR.jpg@480x300.jpg")


def test_class_2524_rating(class_2524_html: str) -> None:
    rating = parse(class_2524_html, URL_2524).rating
    assert rating == {
        "fun": 72,
        "difficulty": 68,
        "stability": 31,
        "practicality": 61,
        "aesthetics": 50,
        "balance": 52,
        "compatibility": 53,
        "durability": 70,
    }


def test_modpack_meta(modpack_1_html: str) -> None:
    meta = parse(modpack_1_html, URL_MODPACK, content_type="modpack")
    assert meta.content_type == "modpack"
    assert meta.display_name == "[GTNH] 格雷科技：新视野"
    assert meta.subtitle == "GT: New Horizons"
    assert meta.tags == ["GT", "格雷科技"]
    assert meta.mc_versions == {"Forge": ["1.7.10"]}
    assert meta.view_count == "106.48万"
    assert meta.heat_index == "767"
    assert (meta.red_count, meta.black_count) == ("196", "4")
    assert meta.cover_url.startswith("https://i.mcmod.cn/modpack/cover/")
    assert not any(meta.rating.values())


def test_class_1188_versions_parse(class_1188_html: str) -> None:
    meta = parse(class_1188_html, "https://www.mcmod.cn/class/1188.html")
    assert meta.english_name == "I18nUpdateMod"
    assert "Forge" in meta.mc_versions and "Fabric" in meta.mc_versions
    assert "1.21.10" in meta.mc_versions["Forge"]
    assert "1.12.2" in meta.mc_versions["Forge"]


def test_meta_roundtrip(class_2524_html: str) -> None:
    meta = parse(class_2524_html, URL_2524)
    restored = type(meta).from_dict(meta.to_dict())
    assert restored.to_dict() == meta.to_dict()


def test_empty_page_is_safe() -> None:
    meta = parse("<html><body></body></html>", "https://www.mcmod.cn/class/1.html")
    assert meta.tags == []
    assert meta.view_count == ""
    assert meta.heat_index == ""
