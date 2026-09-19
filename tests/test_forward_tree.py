# -*- coding: utf-8 -*-
"""转发树测试：通用「标题 → 子转发」逻辑、编号、深度限制与记录分片。"""

from __future__ import annotations

from bs4 import BeautifulSoup

import astrbot.api.message_components as Comp
from mcmod_plugin.data.body_parser import BodyParser
from mcmod_plugin.data.meta_parser import MetaParser
from mcmod_plugin.render.forward import (
    build_forward_records,
    flatten_to_plain_records,
    to_component,
)
from mcmod_plugin.render.tree import (
    HARD_DEPTH_LIMIT,
    ForwardNodeData,
    ForwardTreeBuilder,
    plan_records,
)

URL_2524 = "https://www.mcmod.cn/class/2524.html"


def load(html: str):
    soup = BeautifulSoup(html, "lxml")
    meta = MetaParser(soup, url=URL_2524, content_type="class").parse()
    sections = BodyParser(soup).parse()
    return meta, sections


def fake_images(builder: ForwardTreeBuilder, meta, sections) -> None:
    for url in builder.wanted_image_urls(meta, sections):
        builder.image_data[url] = b"fake-image-bytes"


def test_overview_structure(class_2524_html: str) -> None:
    meta, sections = load(class_2524_html)
    builder = ForwardTreeBuilder({"include_radar": False})
    fake_images(builder, meta, sections)
    cover = builder.image_data.get(meta.cover_url)
    root = builder.build_overview(meta, cover=cover, radar=None)
    assert root is not None
    assert [len(child.blocks) for child in root.children] == [2, 1, 1]
    assert "Gregicality Legacy" in root.children[0].text()
    assert "热度: 5.0（名扬天下）" in root.children[1].text()
    assert "浏览量: 753.59万" in root.children[1].text()
    assert "标签（6）" in root.children[2].text()
    assert "作者（11）" in root.children[2].text()
    assert root.children[0].images()


def test_body_section_numbering(class_2524_html: str) -> None:
    meta, sections = load(class_2524_html)
    builder = ForwardTreeBuilder({})
    fake_images(builder, meta, sections)
    roots = builder.build_body(sections)
    assert [root.text().splitlines()[0] for root in roots] == [
        "1. 写在开头",
        "2. 模组简介",
        "3. 模组集成联动",
        "4. 画廊",
    ]
    # 2 级标题嵌套在 1 级标题下
    assert [child.text().splitlines()[0] for child in roots[0].children] == [
        "1.1. 版本注意事项",
        "1.2. 本模组资料常见问题",
    ]


def test_title_to_child_is_generic(class_2524_html: str) -> None:
    """每个内容块（段落 / 列表项 / 图片）都是标题节点的一个子转发节点。"""
    meta, sections = load(class_2524_html)
    builder = ForwardTreeBuilder({"include_images": False})
    roots = builder.build_body(sections)

    def walk(node):
        yield node
        for child in node.children:
            yield from walk(child)

    by_title = {}
    for node in walk(ForwardNodeData(children=roots)):
        lines = node.text().splitlines()
        if lines and ". " in lines[0]:
            by_title[lines[0].split(". ", 1)[1]] = node

    def is_heading(text: str) -> bool:
        head = text.splitlines()[0] if text else ""
        return bool(head) and head.split(". ", 1)[0].replace(".", "").isdigit()

    for section in sections:
        node = by_title[section.title]
        expected = [block.text for block in section.blocks if block.text]
        # 内容块与「子标题节点」按原始顺序混排在 children 中
        content_children = [child for child in node.children if not is_heading(child.text())]
        assert [child.text() for child in content_children] == expected


def test_list_items_become_child_nodes(class_2524_html: str) -> None:
    meta, sections = load(class_2524_html)
    builder = ForwardTreeBuilder({"include_images": False})
    roots = builder.build_body(sections)
    links = roots[2]
    assert len(links.children) == 10
    assert links.children[0].text() == "CEU 模组的全部功能（加入能源转换器，实现 FE 与 EU 的相互转换）；"
    assert links.children[9].text() == "CraftTweaker 联动（本模组支持 CrT 脚本）。"
    assert all(child.children == [] for child in links.children)


def test_images_become_child_nodes_too(class_2524_html: str) -> None:
    meta, sections = load(class_2524_html)
    builder = ForwardTreeBuilder({})
    fake_images(builder, meta, sections)
    roots = builder.build_body(sections)
    gallery = roots[-1]  # 4. 画廊
    assert len(gallery.children) == 7
    assert all(len(child.images()) == 1 for child in gallery.children)
    assert gallery.children[0].text() == "新的多方块"
    assert gallery.children[6].text() == "不同的矿物品级"


def test_images_can_be_disabled(class_2524_html: str) -> None:
    meta, sections = load(class_2524_html)
    builder = ForwardTreeBuilder({"include_images": False})
    fake_images(builder, meta, sections)
    roots = builder.build_body(sections)
    gallery = roots[-1]
    assert gallery.text() == "4. 画廊"  # 标题保留，图片被跳过
    assert gallery.children == []
    assert not any(count_images(root) for root in roots)


def test_image_budget(class_2524_html: str) -> None:
    meta, sections = load(class_2524_html)
    builder = ForwardTreeBuilder({"max_images": 2})
    fake_images(builder, meta, sections)
    assert len(builder.wanted_image_urls(meta, sections)) == 3  # 封面 + 2 张正文图
    roots = builder.build_body(sections)
    gallery = roots[-1]
    assert len(gallery.children) == 2


def test_depth_limit_folds_extra_levels() -> None:
    deep = ForwardNodeData(blocks=[("text", "标题")])
    child = ForwardNodeData(blocks=[("text", "子节点")])
    grandchild = ForwardNodeData(blocks=[("text", "孙节点")])
    great = ForwardNodeData(blocks=[("text", "曾孙节点")])
    grandchild.children.append(great)
    child.children.append(grandchild)
    deep.children.append(child)

    component = to_component(deep)
    assert isinstance(component, Comp.Node)
    assert _depth_of(component) <= HARD_DEPTH_LIMIT
    # 超出三层的「孙 / 曾孙」被折叠成文本，仍保留在最近的可承载节点里
    folded = _node_text(component)
    assert "孙节点" in folded
    assert "曾孙节点" in folded


def test_plan_records_never_splits_a_section() -> None:
    roots = []
    for index in range(3):
        node = ForwardNodeData(blocks=[("text", f"分区{index}")])
        for sub in range(3):
            node.children.append(ForwardNodeData(blocks=[("text", f"子{sub}")]))
        roots.append(node)
    records = plan_records(roots, max_nodes_per_message=4)
    assert [sum(item.nodes_count() for item in record) for record in records] == [4, 4, 4]


def test_build_forward_records_and_fallback(class_2524_html: str) -> None:
    meta, sections = load(class_2524_html)
    builder = ForwardTreeBuilder({})
    fake_images(builder, meta, sections)
    overview = builder.build_overview(
        meta, cover=builder.image_data.get(meta.cover_url), radar=None
    )
    body = builder.build_body(sections)

    records, leftovers = build_forward_records(overview, body, config={})
    assert len(records) >= 2  # 概览 1 条 + 正文按 max_nodes_per_message 分片
    assert leftovers == []
    assert isinstance(records[0], Comp.Nodes)
    assert len(records[0].nodes) == 1
    assert isinstance(records[0].nodes[0], Comp.Node)
    assert len(records[0].nodes[0].content) == 3

    records, leftovers = build_forward_records(
        overview, body, config={}, forward_overview=False, forward_body=False
    )
    assert records == []
    assert len(leftovers) == 1 + len(body)


def test_plain_fallback_order(class_2524_html: str) -> None:
    meta, sections = load(class_2524_html)
    builder = ForwardTreeBuilder({})
    fake_images(builder, meta, sections)
    overview = builder.build_overview(
        meta, cover=builder.image_data.get(meta.cover_url), radar=None
    )
    body = builder.build_body(sections)
    messages = flatten_to_plain_records([overview] + body)
    texts = [
        item.text
        for message in messages
        for item in message
        if isinstance(item, Comp.Plain)
    ]
    assert texts[0].startswith("1.1 [GCY] Gregicality Legacy")
    assert any(text.startswith("1.2 热度: 5.0（名扬天下）") for text in texts)
    joined = "\n".join(texts)
    # 概览占 1，正文标题顺延为 2~5
    assert "4.1 CEU 模组的全部功能" in joined
    assert "4.10 CraftTweaker 联动" in joined
    images = [
        item for message in messages for item in message if isinstance(item, Comp.Image)
    ]
    assert len(images) == 1 + 7


def _node_text(node) -> str:
    parts = []
    for child in node.content:
        if isinstance(child, Comp.Plain):
            parts.append(child.text)
        elif isinstance(child, Comp.Node):
            parts.append(_node_text(child))
    return "\n".join(parts)


def _depth_of(node) -> int:
    depth = 1
    for child in node.content:
        if isinstance(child, Comp.Node):
            depth = max(depth, 1 + _depth_of(child))
    return depth


def count_images(node: ForwardNodeData) -> int:
    return len(node.images()) + sum(count_images(child) for child in node.children)
