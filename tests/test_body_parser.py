# -*- coding: utf-8 -*-
"""正文解析器测试：标题切分、列表项、画廊图片。"""

from __future__ import annotations

from bs4 import BeautifulSoup

from mcmod_plugin.data.body_parser import BodyParser, absolutize_url, normalize_text

EXPECTED_TITLES_2524 = [
    "写在开头",
    "版本注意事项",
    "本模组资料常见问题",
    "模组简介",
    "模组集成联动",
    "画廊",
]

EXPECTED_LINKS_2524 = [
    "CEU 模组的全部功能（加入能源转换器，实现 FE 与 EU 的相互转换）；",
    "无中生有联动（对 GTCE 新增矿物的支持）；",
    "林业联动（加入 GTCE 相关的蜜蜂，以及新的蜂箱组构件）；",
    "匠魂2联动（对 GTCE 新增金属的熔融支持）；",
    "神秘农业联动（对 GTCE 新增有关作物的支持）；",
    "开放式电脑联动（提供 GTCE 机器的 API 函数接口）；",
    "应用能源2联动（使得 GTCE 新增的工具能够被终端识别）；",
    "精致存储联动（使得 GTCE 新增的工具能够被终端识别）；",
    "XNet 联动（使得 GTCE 新增的机器能够在 XNet 控制器 中被正确渲染）；",
    "CraftTweaker 联动（本模组支持 CrT 脚本）。",
]

EXPECTED_GALLERY_CAPTIONS = [
    "新的多方块",
    "中央监控器",
    "与 Mod 联动",
    "自由扳手",
    "核燃料",
    "新的电路板",
    "不同的矿物品级",
]


def parse(html: str) -> list:
    return BodyParser(BeautifulSoup(html, "lxml")).parse()


def test_section_titles_and_order(class_2524_html: str) -> None:
    sections = parse(class_2524_html)
    assert [section.title for section in sections] == EXPECTED_TITLES_2524
    assert [section.level for section in sections] == [1, 2, 2, 1, 1, 1]


def test_link_section_items_keep_dom_order(class_2524_html: str) -> None:
    sections = parse(class_2524_html)
    target = next(item for item in sections if item.title == "模组集成联动")
    items = [block.text for block in target.blocks if block.kind == "item"]
    assert items == EXPECTED_LINKS_2524


def test_inline_links_do_not_split_paragraphs(class_2524_html: str) -> None:
    sections = parse(class_2524_html)
    target = next(item for item in sections if item.title == "模组简介")
    paragraphs = [block.text for block in target.blocks if block.kind == "para"]
    first = paragraphs[0]
    assert first.startswith("Gregic Additions 的最新分支")
    assert "匠魂与林业的联动" in first
    # 行内链接不应被拆成独立段落
    assert not any(text == "匠魂" for text in paragraphs)


def test_figure_section_and_images(class_2524_html: str) -> None:
    sections = parse(class_2524_html)
    gallery = sections[-1]
    assert gallery.title == "画廊"
    figures = gallery.figures
    assert [figure.caption for figure in figures] == EXPECTED_GALLERY_CAPTIONS
    assert all(figure.url.startswith("https://") for figure in figures)
    # 懒加载占位图不能被当成正文图片
    assert all("loading-colourful" not in figure.url for figure in figures)
    assert gallery.figures[0].url.endswith("1618728791_68738_SqTc.webp")


def test_section_without_body_keeps_title(class_2524_html: str) -> None:
    sections = parse(class_2524_html)
    opening = sections[0]
    assert opening.title == "写在开头"
    assert opening.blocks == []


def test_class_1188_has_no_images_and_no_empty_blocks(class_1188_html: str) -> None:
    sections = parse(class_1188_html)
    assert sections
    assert all(not section.figures for section in sections)
    assert all(section.title for section in sections)
    for section in sections:
        for block in section.blocks:
            assert block.text or block.figure is not None


def test_modpack_page_uses_same_parser(modpack_1_html: str) -> None:
    sections = parse(modpack_1_html)
    titles = [section.title for section in sections]
    assert "" not in titles
    assert titles[0] == "简介"
    assert "画廊" in titles
    gallery = next(item for item in sections if item.title == "画廊")
    assert gallery.figures


def test_malformed_html_does_not_raise() -> None:
    assert parse("<html><body><p>没有正文容器</p></body></html>") == []
    empty = parse(
        '<div class="class-text"><li class="text-area common-text">'
        '<p><span class="common-text-title common-text-title-1">标题</span></p>'
        '<ul></ul><script>var a=1;</script></li></div>'
    )
    assert [section.title for section in empty] == ["标题"]
    assert empty[0].blocks == []


def test_helpers() -> None:
    assert normalize_text("a\u200bb\u00a0 c") == "ab c"
    assert absolutize_url("//i.mcmod.cn/a.png") == "https://i.mcmod.cn/a.png"
    assert absolutize_url("/pages/a.png") == "https://www.mcmod.cn/pages/a.png"
    assert absolutize_url("http://www.mcmod.cn/a.png") == "https://www.mcmod.cn/a.png"
    assert absolutize_url("//www.mcmod.cn/static/public/images/loading-colourful.gif") == ""
