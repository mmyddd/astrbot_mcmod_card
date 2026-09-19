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
    return sections, builder.build_body(sections)


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
    _, roots = build(modpack_897_html, URL_897, "modpack")
    titles = [root.text().splitlines()[0] for root in roots]
    assert titles[0] == "1. 简介"
    assert titles[1] == "2. 总体介绍"
    assert titles[2] == "3. 内容展示"
    assert titles[-1] == "7. 部分已添加 / 正在开发的特色内容"

    content = roots[2]
    assert content.children[0].text() == "3.1. 科技模块"
    assert content.children[1].text() == "3.2. 魔法模块"
    assert content.children[2].text() == "3.3. 冒险模块"


def test_level3_headings_nest_under_level2(modpack_897_html: str) -> None:
    _, roots = build(modpack_897_html, URL_897, "modpack")
    tech = roots[2].children[0]
    headings = [
        child.text().split("\n")[0]
        for child in tech.children
        if child.text().startswith("3.1.")
    ]
    assert headings == [
        "3.1.1. 机械动力（Create）",
        "3.1.2. 格雷科技（Gregtech）",
        "3.1.3. 血肉重铸2（Biomancy 2）",
        "3.1.4. 应用能源2（Applied Energistics 2）",
    ]


def test_level3_body_follows_its_own_heading(modpack_897_html: str) -> None:
    _, roots = build(modpack_897_html, URL_897, "modpack")
    tech = roots[2].children[0]
    children = tech.children
    create = next(child for child in children if child.text().startswith("3.1.1."))
    assert create.text().splitlines()[0] == "3.1.1. 机械动力（Create）"
    assert any("齿轮风格科技玩法" in child.text() for child in create.children)
    # 后继标题不会把前面标题的正文带走
    gregtech = next(child for child in children if child.text().startswith("3.1.2."))
    assert gregtech.text() == "3.1.2. 格雷科技（Gregtech）"


def test_deeper_levels_reset_after_higher_level(modpack_897_html: str) -> None:
    _, roots = build(modpack_897_html, URL_897, "modpack")
    content = roots[2]
    magic = content.children[1]
    # 同级 3 级标题在进入新的 2 级标题后重新从 1 开始编号
    assert magic.children[2].text().startswith("3.2.1. 植物魔法（Botania）")
    assert magic.children[3].text().startswith("3.2.2. 血魔法3（Blood Magic3）")


def test_flat_pages_still_number_linearly(class_2524_html: str) -> None:
    sections, roots = build(
        class_2524_html, "https://www.mcmod.cn/class/2524.html", "class"
    )
    # 模组页只有 1/2 级标题：写在开头(1) 下挂 版本注意事项(1.1)
    assert roots[0].text().splitlines()[0] == "1. 写在开头"
    assert roots[0].children[0].text().splitlines()[0] == "1.1. 版本注意事项"
    # 「模组简介」回到 1 级，编号继续递增而不是嵌套
    titles = [root.text().splitlines()[0] for root in roots]
    assert titles == [
        "1. 写在开头",
        "2. 模组简介",
        "3. 模组集成联动",
        "4. 画廊",
    ]


def test_no_section_is_lost(modpack_897_html: str) -> None:
    sections, roots = build(modpack_897_html, URL_897, "modpack")

    def collect(nodes):
        for node in nodes:
            yield node.text().splitlines()[0]
            yield from collect(node.children)

    headings = [text for text in collect(roots) if text]
    for section in sections:
        assert any(text.endswith(section.title) for text in headings), section.title
