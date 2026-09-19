# -*- coding: utf-8 -*-
"""发送结构测试：标题写在聊天记录外，内容进合并转发记录。"""

from __future__ import annotations

from bs4 import BeautifulSoup

import astrbot.api.message_components as Comp
from mcmod_plugin.data.body_parser import BodyParser
from mcmod_plugin.data.meta_parser import MetaParser
from mcmod_plugin.render.forward import (
    build_forward_records,
    build_records,
    flatten_to_plain_records,
    heading_components,
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
    assert root.children[0].images()


def test_heading_numbering(class_2524_html: str) -> None:
    meta, sections = load(class_2524_html)
    builder = ForwardTreeBuilder({"include_images": False})
    parts = builder.build_body_parts(sections)
    assert [part.heading for part in parts] == [
        "1. 写在开头",
        "1.1. 版本注意事项",
        "1.2. 本模组资料常见问题",
        "2. 模组简介",
        "3. 模组集成联动",
        "4. 画廊",
    ]
    assert [part.level for part in parts] == [1, 2, 2, 1, 1, 1]


def test_heading_is_sent_as_plain_message(class_2524_html: str) -> None:
    """标题必须是聊天记录外的普通消息。"""
    meta, sections = load(class_2524_html)
    builder = ForwardTreeBuilder({"include_images": False})
    parts = builder.build_body_parts(sections)
    components = heading_components(parts[0])
    assert len(components) == 1
    assert isinstance(components[0], Comp.Plain)
    assert components[0].text == "1. 写在开头"


def test_heading_not_inside_forward_record(class_2524_html: str) -> None:
    """转发记录的节点里不应再出现标题文本。"""
    meta, sections = load(class_2524_html)
    builder = ForwardTreeBuilder({"include_images": False})
    parts = builder.build_body_parts(sections)
    links = next(part for part in parts if part.title == "模组集成联动")
    records = build_records(links.nodes, config={})
    assert records
    node = records[0].nodes[0]
    plain = [c.text for c in node.content if isinstance(c, Comp.Plain)]
    assert plain == ["CEU 模组的全部功能（加入能源转换器，实现 FE 与 EU 的相互转换）；"]
    assert not any("模组集成联动" in text for text in plain)


def test_every_block_becomes_a_node(class_2524_html: str) -> None:
    meta, sections = load(class_2524_html)
    builder = ForwardTreeBuilder({"include_images": False})
    parts = builder.build_body_parts(sections)
    by_title = {part.title: part for part in parts}
    for section in sections:
        expected = [block.text for block in section.blocks if block.text]
        actual = [node.text() for node in by_title[section.title].nodes]
        assert actual == expected


def test_list_items_are_separate_nodes(class_2524_html: str) -> None:
    meta, sections = load(class_2524_html)
    builder = ForwardTreeBuilder({"include_images": False})
    parts = builder.build_body_parts(sections)
    links = next(part for part in parts if part.title == "模组集成联动")
    assert len(links.nodes) == 10
    assert links.nodes[0].text() == "CEU 模组的全部功能（加入能源转换器，实现 FE 与 EU 的相互转换）；"
    assert links.nodes[9].text() == "CraftTweaker 联动（本模组支持 CrT 脚本）。"


def test_images_are_separate_nodes(class_2524_html: str) -> None:
    meta, sections = load(class_2524_html)
    builder = ForwardTreeBuilder({})
    fake_images(builder, meta, sections)
    parts = builder.build_body_parts(sections)
    gallery = next(part for part in parts if part.title == "画廊")
    assert len(gallery.nodes) == 7
    assert all(len(node.images()) == 1 for node in gallery.nodes)
    assert gallery.nodes[0].text() == "新的多方块"
    assert gallery.nodes[6].text() == "不同的矿物品级"


def test_images_can_be_disabled(class_2524_html: str) -> None:
    meta, sections = load(class_2524_html)
    builder = ForwardTreeBuilder({"include_images": False})
    fake_images(builder, meta, sections)
    parts = builder.build_body_parts(sections)
    gallery = next(part for part in parts if part.title == "画廊")
    assert gallery.heading == "4. 画廊"  # 标题仍然发送
    assert gallery.nodes == []


def test_image_budget(class_2524_html: str) -> None:
    meta, sections = load(class_2524_html)
    builder = ForwardTreeBuilder({"max_images": 2})
    fake_images(builder, meta, sections)
    assert len(builder.wanted_image_urls(meta, sections)) == 3  # 封面 + 2 张正文图
    parts = builder.build_body_parts(sections)
    gallery = next(part for part in parts if part.title == "画廊")
    assert len(gallery.nodes) == 2


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
    folded = _node_text(component)
    assert "孙节点" in folded
    assert "曾孙节点" in folded


def test_plan_records_keeps_everything_in_one_record() -> None:
    """默认所有顶层节点进同一条记录，不刷屏。"""
    roots = []
    for index in range(3):
        node = ForwardNodeData(blocks=[("text", f"分区{index}")])
        for sub in range(3):
            node.children.append(ForwardNodeData(blocks=[("text", f"子{sub}")]))
        roots.append(node)
    records = plan_records(roots, max_nodes_per_message=40)
    assert len(records) == 1
    assert records[0] == roots


def test_plan_records_splits_only_when_over_limit() -> None:
    """超过上限才分片，且不切开任何一个节点的子树。"""
    roots = [
        ForwardNodeData(
            blocks=[("text", f"分区{index}")],
            children=[ForwardNodeData(blocks=[("text", "子")])],
        )
        for index in range(5)
    ]
    records = plan_records(roots, max_nodes_per_message=2)
    assert [len(record) for record in records] == [2, 2, 1]
    for record in records:
        for node in record:
            assert node.children, "节点子树不应被拆开"


def test_build_forward_records_compat(class_2524_html: str) -> None:
    meta, sections = load(class_2524_html)
    builder = ForwardTreeBuilder({})
    fake_images(builder, meta, sections)
    overview = builder.build_overview(
        meta, cover=builder.image_data.get(meta.cover_url), radar=None
    )
    roots = [node for part in builder.build_body_parts(sections) for node in part.nodes]
    records, leftovers = build_forward_records(overview, roots, config={})
    assert len(records) >= 1
    assert leftovers == []
    assert isinstance(records[0], Comp.Nodes)


def test_plain_fallback_sends_heading_then_content(class_2524_html: str) -> None:
    meta, sections = load(class_2524_html)
    builder = ForwardTreeBuilder({})
    fake_images(builder, meta, sections)
    parts = builder.build_body_parts(sections)
    links = next(part for part in parts if part.title == "模组集成联动")
    messages = flatten_to_plain_records(links.nodes, prefix=(3,))
    texts = [
        item.text for message in messages for item in message if isinstance(item, Comp.Plain)
    ]
    assert texts[0].startswith("3.1 CEU 模组的全部功能")
    assert texts[9].startswith("3.10 CraftTweaker 联动")


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
