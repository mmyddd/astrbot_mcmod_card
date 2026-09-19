# -*- coding: utf-8 -*-
"""标题层级测试：mcmod 的 common-text-title-1/2/3 → 1 / 1.1 / 1.1.1。"""

from __future__ import annotations

from bs4 import BeautifulSoup

from mcmod_plugin.data.body_parser import BodyParser
from mcmod_plugin.data.meta_parser import MetaParser
from mcmod_plugin.render.tree import ForwardTreeBuilder

URL_897 = "https://www.mcmod.cn/modpack/897.html"


def build(html: str, url: str, content_type: str):
    soup = BeautifulSoup(html, "lxml")
    meta = MetaParser(soup, url=url, content_type=content_type).parse()
    sections = BodyParser(soup).parse()
    builder = ForwardTreeBuilder({"include_images": False})
    return sections, builder.build_body_parts(sections)


def test_heading_levels_are_parsed(modpack_897_html: str) -> None:
    sections, _ = build(modpack_897_html, URL_897, "modpack")
    levels = {section.title: section.level for section in sections}
    assert levels["总体介绍"] == 1
    assert levels["内容展示"] == 1
    assert levels["科技模块"] == 2
    assert levels["魔法模块"] == 2
    assert levels["冒险模块"] == 2
    assert levels["机械动力（Create）"] == 3


def test_nested_numbering(modpack_897_html: str) -> None:
    _, parts = build(modpack_897_html, URL_897, "modpack")
    headings = [part.heading for part in parts]
    assert headings[0] == "1. 简介"
    assert headings[1] == "2. 总体介绍"
    assert headings[2] == "3. 内容展示"
    assert headings[3] == "3.1. 科技模块"
    assert headings[4] == "3.1.1. 机械动力（Create）"
    assert headings[5] == "3.1.2. 格雷科技（Gregtech）"
    assert headings[6] == "3.1.3. 血肉重铸2（Biomancy 2）"
    assert headings[7] == "3.1.4. 应用能源2（Applied Energistics 2）"
    assert headings[8] == "3.2. 魔法模块"
    assert headings[-1].startswith("7. 部分已添加")


def test_deeper_levels_reset_after_higher_level(modpack_897_html: str) -> None:
    _, parts = build(modpack_897_html, URL_897, "modpack")
    headings = [part.heading for part in parts]
    # 进入新的 2 级标题后，3 级编号重新从 1 开始
    assert "3.2.1. 植物魔法（Botania）" in headings
    assert "3.2.2. 血魔法3（Blood Magic3）" in headings
    assert "3.3.1. 艾利克斯的洞穴" not in headings  # 冒险模块无 3 级标题


def test_level3_body_belongs_to_its_own_heading(modpack_897_html: str) -> None:
    _, parts = build(modpack_897_html, URL_897, "modpack")
    create = next(part for part in parts if part.title == "机械动力（Create）")
    assert create.heading == "3.1.1. 机械动力（Create）"
    assert any("齿轮风格科技玩法" in node.text() for node in create.nodes)
    # 相邻标题的正文不会串到上一个标题里
    greg = next(part for part in parts if part.title == "格雷科技（Gregtech）")
    assert all("齿轮风格科技玩法" not in node.text() for node in greg.nodes)


def test_content_is_not_absorbed_by_headings(modpack_897_html: str) -> None:
    """标题在同一 <p> 内与图片/正文混排时，内容不能被标题吞掉。

    AE2 那段正文在 DOM 上位于「魔法模块」标题之前，因此归属「应用能源2」。
    """
    _, parts = build(modpack_897_html, URL_897, "modpack")
    ae2 = next(part for part in parts if part.title == "应用能源2（Applied Energistics 2）")
    assert any("对 AE2 进行了深度魔改" in node.text() for node in ae2.nodes)

    magic = next(part for part in parts if part.title == "魔法模块")
    assert all("对 AE2 进行了深度魔改" not in node.text() for node in magic.nodes)


def test_flat_pages_still_number_linearly(class_2524_html: str) -> None:
    sections, parts = build(
        class_2524_html, "https://www.mcmod.cn/class/2524.html", "class"
    )
    headings = [part.heading for part in parts]
    assert headings == [
        "1. 写在开头",
        "1.1. 版本注意事项",
        "1.2. 本模组资料常见问题",
        "2. 模组简介",
        "3. 模组集成联动",
        "4. 画廊",
    ]


def test_no_section_is_lost(modpack_897_html: str) -> None:
    sections, parts = build(modpack_897_html, URL_897, "modpack")
    titles = [part.title for part in parts]
    for section in sections:
        assert section.title in titles, section.title
