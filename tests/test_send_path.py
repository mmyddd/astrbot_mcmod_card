# -*- coding: utf-8 -*-
"""发送路径测试：真实走一遍 _send 生成器。

重点：

1. 插件真的能跑（曾经漏过 main.py 的 NameError）；
2. **所有内容打包进同一条合并转发记录**，不刷屏。
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
        self.sent.append(("chain", chain))
        return ("chain", chain)

    def plain_result(self, text):
        self.sent.append(("plain", text))
        return ("plain", text)

    def stop_event(self) -> None:
        self.stopped = True


def make_plugin(config=None):
    """绕过 AstrBot 的插件装载，直接实例化并注入配置。"""
    from mcmod_plugin.main import McmodCardPlugin

    plugin = McmodCardPlugin.__new__(McmodCardPlugin)
    plugin.config = dict(config or {})
    plugin.plugin_name = "mcmod_card"
    plugin.data_dir = None
    plugin.cache_dir = None
    plugin.font_path = None
    return plugin


def build_payload(html: str, content_type: str, url: str, config=None, images=True):
    soup = BeautifulSoup(html, "lxml")
    meta = MetaParser(soup, url=url, content_type=content_type).parse()
    builder = ForwardTreeBuilder(config or {"include_images": images})
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


def test_everything_is_one_forward_record(class_2524_html: str) -> None:
    """概览与正文必须打包进同一条合并转发记录。"""
    plugin = make_plugin()
    meta, builder, overview, parts = build_payload(
        class_2524_html, "class", "https://www.mcmod.cn/class/2524.html"
    )
    event = FakeEvent()
    drive(plugin, event, plugin._send(event, overview, parts))

    assert len(event.sent) == 1, f"应当只发一条消息，实际 {len(event.sent)} 条"
    kind, chain = event.sent[0]
    assert kind == "chain"
    assert isinstance(chain[0], Comp.Nodes)


def test_record_contains_overview_and_all_headings(class_2524_html: str) -> None:
    plugin = make_plugin()
    meta, builder, overview, parts = build_payload(
        class_2524_html, "class", "https://www.mcmod.cn/class/2524.html"
    )
    event = FakeEvent()
    drive(plugin, event, plugin._send(event, overview, parts))
    nodes = event.sent[0][1][0].nodes

    texts = []
    for node in nodes:
        for child in node.content:
            if isinstance(child, Comp.Plain):
                texts.append(child.text)
    joined = "\n".join(texts)
    assert "Gregicality Legacy" in joined          # 概览
    for part in parts:
        assert part.heading in texts, f"缺少标题 {part.heading}"


def test_record_depth_is_within_qq_limit(class_2524_html: str) -> None:
    """记录 → 标题 → 内容，深度不超过 QQ 的三层嵌套。"""
    plugin = make_plugin()
    meta, builder, overview, parts = build_payload(
        class_2524_html, "class", "https://www.mcmod.cn/class/2524.html"
    )
    event = FakeEvent()
    drive(plugin, event, plugin._send(event, overview, parts))
    record = event.sent[0][1][0]
    assert _depth_of(record) <= 3


def test_content_hangs_under_its_heading(class_2524_html: str) -> None:
    """列表项等内容作为标题节点的子节点。"""
    plugin = make_plugin()
    meta, builder, overview, parts = build_payload(
        class_2524_html,
        "class",
        "https://www.mcmod.cn/class/2524.html",
        config={"include_images": False},
    )
    event = FakeEvent()
    drive(plugin, event, plugin._send(event, overview, parts))
    nodes = event.sent[0][1][0].nodes

    links = next(
        node for node in nodes if node.content and getattr(node.content[0], "text", "") == "3. 模组集成联动"
    )
    assert len(links.content) == 11  # 标题 + 10 个列表项
    assert isinstance(links.content[-1], Comp.Node)


def test_fallback_sends_multiple_plain_messages(class_2524_html: str) -> None:
    """平台不支持合并转发时退回逐条普通消息。"""
    plugin = make_plugin()
    meta, builder, overview, parts = build_payload(
        class_2524_html,
        "class",
        "https://www.mcmod.cn/class/2524.html",
        config={"include_images": False},
    )
    event = FakeEvent(platform="telegram")
    drive(plugin, event, plugin._send(event, overview, parts))

    assert len(event.sent) > 1
    # 降级路径只允许纯文本与图片（不能出现合并转发组件）
    assert all(
        isinstance(entry[1][0], (Comp.Plain, Comp.Image)) for entry in event.sent
    )
    texts = [
        entry[1][0].text for entry in event.sent if isinstance(entry[1][0], Comp.Plain)
    ]
    assert any(text.startswith("1. ") for text in texts)


def test_one_record_even_with_images(modpack_897_html: str) -> None:
    """图片很多时依然只发一条记录。"""
    plugin = make_plugin({"max_images": 40})
    meta, builder, overview, parts = build_payload(
        modpack_897_html,
        "modpack",
        "https://www.mcmod.cn/modpack/897.html",
        config={"max_images": 40},
    )
    event = FakeEvent()
    drive(plugin, event, plugin._send(event, overview, parts))
    assert len(event.sent) == 1
    record = event.sent[0][1][0]
    images = _count_images(record)
    assert images >= 19, f"图片数偏少: {images}"


def test_wrap_plain_helper() -> None:
    """_wrap_plain 必须真的能构造 Plain 组件（曾经漏了 Comp 导入）。"""
    from mcmod_plugin.main import _wrap_plain

    messages = _wrap_plain([Comp.Plain("标题")])
    assert [m[0].text for m in messages] == ["标题"]
    assert _wrap_plain([]) == []


def _depth_of(component) -> int:
    depth = 1
    content = getattr(component, "content", None) or getattr(component, "nodes", [])
    for child in content:
        if isinstance(child, Comp.Node):
            depth = max(depth, 1 + _depth_of(child))
    return depth


def _count_images(component) -> int:
    total = 0
    content = getattr(component, "content", None) or getattr(component, "nodes", [])
    for child in content:
        if isinstance(child, Comp.Image):
            total += 1
        elif isinstance(child, Comp.Node):
            total += _count_images(child)
    return total
