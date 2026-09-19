# -*- coding: utf-8 -*-
"""发送路径测试：真实走一遍 _send 生成器。

锁定的不变量：

1. 插件真的能跑（曾经漏过 main.py 的 NameError）；
2. 每个节点只承载自己的内容，**绝不出现「文本 + 子节点」混合节点**（NapCat 无法发送）；
3. 先发标题、后发内容，顺序与原文一致；
4. 消息条数很少（远小于逐条发送的几十条），不刷屏。
"""

from __future__ import annotations

import asyncio

from bs4 import BeautifulSoup

import astrbot.api.message_components as Comp
from mcmod_plugin.data.body_parser import BodyParser
from mcmod_plugin.data.meta_parser import MetaParser
from mcmod_plugin.render.tree import ForwardTreeBuilder


class FakeEvent:
    """最小事件替身：只提供发送路径真正用到的接口。"""

    def __init__(self, platform: str = "aiocqhttp"):
        self.platform = platform
        self.sent = []
        self.stopped = False

    def get_platform_name(self) -> str:
        return self.platform

    def chain_result(self, chain):
        self.sent.append(chain)
        return chain

    def plain_result(self, text):
        self.sent.append([Comp.Plain(text)])
        return text

    def stop_event(self) -> None:
        self.stopped = True


def make_plugin(config=None):
    from mcmod_plugin.main import McmodCardPlugin

    plugin = McmodCardPlugin.__new__(McmodCardPlugin)
    plugin.config = dict(config or {})
    plugin.plugin_name = "mcmod_card"
    plugin.data_dir = None
    plugin.cache_dir = None
    plugin.font_path = None
    return plugin


def build_payload(html: str, content_type: str, url: str, config=None):
    soup = BeautifulSoup(html, "lxml")
    meta = MetaParser(soup, url=url, content_type=content_type).parse()
    builder = ForwardTreeBuilder(config or {})
    sections = BodyParser(soup).parse()
    for target in builder.wanted_image_urls(meta, sections):
        builder.image_data[target] = b"fake-image"
    overview = builder.build_overview(
        meta, cover=builder.image_data.get(meta.cover_url), radar=None
    )
    return meta, builder, overview, builder.build_body_parts(sections)


def drive(plugin, event, coro) -> None:
    async def run():
        async for _ in coro:
            pass

    asyncio.run(run())


def record_nodes(event) -> list:
    """取出所有合并转发记录里的顶层节点。"""
    nodes = []
    for chain in event.sent:
        for component in chain:
            if isinstance(component, Comp.Nodes):
                nodes.extend(component.nodes)
    return nodes


def test_sends_few_messages_not_dozens(class_2524_html: str) -> None:
    """整页只发极少数消息，不再是几十条气泡。"""
    plugin = make_plugin()
    meta, builder, overview, parts = build_payload(
        class_2524_html, "class", "https://www.mcmod.cn/class/2524.html"
    )
    event = FakeEvent()
    drive(plugin, event, plugin._send(event, overview, parts))
    assert 1 <= len(event.sent) <= 3, f"消息条数 {len(event.sent)} 偏多"
    assert all(
        isinstance(chain[0], Comp.Nodes) for chain in event.sent
    ), "应当全部是合并转发记录"


def test_no_mixed_text_and_node(class_2524_html: str) -> None:
    """严禁出现同时含文本与子节点的节点。"""
    plugin = make_plugin()
    meta, builder, overview, parts = build_payload(
        class_2524_html, "class", "https://www.mcmod.cn/class/2524.html"
    )
    event = FakeEvent()
    drive(plugin, event, plugin._send(event, overview, parts))
    for node in record_nodes(event):
        has_text = any(isinstance(c, Comp.Plain) for c in node.content)
        has_child = any(isinstance(c, Comp.Node) for c in node.content)
        assert not (has_text and has_child), "出现文本+子节点混合节点"
        assert not has_child, "记录内不应再有嵌套节点（结构必须扁平）"


def test_every_node_has_content(class_2524_html: str) -> None:
    """不允许出现空节点。"""
    plugin = make_plugin()
    meta, builder, overview, parts = build_payload(
        class_2524_html, "class", "https://www.mcmod.cn/class/2524.html"
    )
    event = FakeEvent()
    drive(plugin, event, plugin._send(event, overview, parts))
    for node in record_nodes(event):
        assert node.content, "出现空节点"


def test_heading_comes_before_its_content(class_2524_html: str) -> None:
    """标题必须紧接在自己的内容之前。"""
    plugin = make_plugin()
    meta, builder, overview, parts = build_payload(
        class_2524_html, "class", "https://www.mcmod.cn/class/2524.html"
    )
    event = FakeEvent()
    drive(plugin, event, plugin._send(event, overview, parts))
    texts = [
        c.text for node in record_nodes(event) for c in node.content
        if isinstance(c, Comp.Plain)
    ]
    for part in parts:
        if part.heading:
            assert part.heading in texts, f"缺少标题 {part.heading}"
    # 列表项内容排在其标题之后
    links = "3. 模组集成联动"
    item = "CEU 模组的全部功能（加入能源转换器，实现 FE 与 EU 的相互转换）；"
    assert texts.index(links) < texts.index(item)


def test_all_headings_present(class_2524_html: str) -> None:
    plugin = make_plugin()
    meta, builder, overview, parts = build_payload(
        class_2524_html, "class", "https://www.mcmod.cn/class/2524.html"
    )
    event = FakeEvent()
    drive(plugin, event, plugin._send(event, overview, parts))
    texts = [
        c.text for node in record_nodes(event) for c in node.content
        if isinstance(c, Comp.Plain)
    ]
    for part in parts:
        assert part.heading in texts, f"缺少标题 {part.heading}"


def test_fallback_sends_plain_messages(class_2524_html: str) -> None:
    """平台不支持合并转发时退回逐条普通消息。"""
    plugin = make_plugin()
    meta, builder, overview, parts = build_payload(
        class_2524_html, "class", "https://www.mcmod.cn/class/2524.html"
    )
    event = FakeEvent(platform="telegram")
    drive(plugin, event, plugin._send(event, overview, parts))
    assert len(event.sent) > 1
    assert all(
        isinstance(chain[0], (Comp.Plain, Comp.Image)) for chain in event.sent
    ), "降级路径不应出现合并转发组件"
    texts = [
        chain[0].text for chain in event.sent if isinstance(chain[0], Comp.Plain)
    ]
    assert any(text.startswith("1. ") for text in texts)


def test_images_all_present(modpack_897_html: str) -> None:
    """图片一张都不能丢。"""
    plugin = make_plugin({"max_images": 40})
    meta, builder, overview, parts = build_payload(
        modpack_897_html,
        "modpack",
        "https://www.mcmod.cn/modpack/897.html",
        config={"max_images": 40},
    )
    event = FakeEvent()
    drive(plugin, event, plugin._send(event, overview, parts))
    images = sum(
        1 for node in record_nodes(event) for c in node.content
        if isinstance(c, Comp.Image)
    )
    assert images >= 19, f"图片数偏少: {images}"


def test_wrap_plain_helper() -> None:
    """_wrap_plain 必须真的能构造 Plain 组件（曾经漏了 Comp 导入）。"""
    from mcmod_plugin.main import _wrap_plain

    messages = _wrap_plain([Comp.Plain("标题")])
    assert [m[0].text for m in messages] == ["标题"]
    assert _wrap_plain([]) == []
