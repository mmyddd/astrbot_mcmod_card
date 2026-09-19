# -*- coding: utf-8 -*-
"""端到端测试：驱动真实的 send_mod_card 入口，杜绝「模块能跑但行为不对」。"""

from __future__ import annotations

import asyncio

from bs4 import BeautifulSoup

import astrbot.api.message_components as Comp
import mcmod_plugin.main as plugin_main
from mcmod_plugin.data.body_parser import BodyParser
from mcmod_plugin.data.meta_parser import MetaParser
from mcmod_plugin.render.tree import ForwardTreeBuilder

URL_CLASS = "https://www.mcmod.cn/class/2524.html"
URL_PACK = "https://www.mcmod.cn/modpack/897.html"


class FakeEvent:
    def __init__(self, url: str, platform: str = "aiocqhttp"):
        self.message_str = f"看看这个 {url}"
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


def run_entry(monkeypatch, html: str, url: str, content_type: str, config=None):
    """把 gather_data / 图片下载替换为离线实现，然后跑真实入口。"""
    soup = BeautifulSoup(html, "lxml")

    async def fake_gather(**kwargs):
        return {
            "meta": MetaParser(
                soup, url=url, content_type=content_type
            ).parse(),
            "sections": BodyParser(soup).parse(),
        }

    async def fake_images(urls, concurrency=4, timeout=10):
        return {target: b"fake-image" for target in urls}

    monkeypatch.setattr(plugin_main, "gather_data", fake_gather)
    monkeypatch.setattr(plugin_main, "fetch_many_bytes", fake_images)

    plugin = make_plugin(config)
    event = FakeEvent(url)

    async def run():
        async for _ in plugin.send_mod_card(event):
            pass

    asyncio.run(run())
    return event


def plain_texts(event) -> list:
    texts = []
    for chain in event.sent:
        for component in chain:
            if isinstance(component, Comp.Plain):
                texts.append(component.text)
    return texts


def test_entry_sends_exactly_one_message(monkeypatch, class_2524_html: str) -> None:
    """整页内容只发一条消息。"""
    event = run_entry(monkeypatch, class_2524_html, URL_CLASS, "class")
    assert len(event.sent) == 1, f"应只发 1 条，实际 {len(event.sent)} 条"
    assert isinstance(event.sent[0][0], Comp.Nodes)


def test_entry_keeps_every_heading(monkeypatch, modpack_897_html: str) -> None:
    """所有标题（含 3.1.1 这类子标题）都必须在消息里出现。"""
    event = run_entry(monkeypatch, modpack_897_html, URL_PACK, "modpack")
    assert len(event.sent) == 1
    record = event.sent[0][0]
    texts = _all_texts(record)
    for heading in (
        "1. 简介",
        "2. 总体介绍",
        "3. 内容展示",
        "3.1. 科技模块",
        "3.1.1. 机械动力（Create）",
        "3.1.2. 格雷科技（Gregtech）",
        "3.1.3. 血肉重铸2（Biomancy 2）",
        "3.1.4. 应用能源2（Applied Energistics 2）",
        "3.2. 魔法模块",
        "3.2.1. 植物魔法（Botania）",
        "3.2.2. 血魔法3（Blood Magic3）",
        "3.2.3. 新生魔艺（Ars Nouvaeu）",
        "3.3. 冒险模块",
    ):
        assert heading in texts, f"缺少子标题: {heading}"


def test_entry_depth_within_qq_limit(monkeypatch, modpack_897_html: str) -> None:
    event = run_entry(monkeypatch, modpack_897_html, URL_PACK, "modpack")
    assert _depth(event.sent[0][0]) <= 3


def test_entry_fallback_on_unsupported_platform(monkeypatch, class_2524_html: str) -> None:
    event = run_entry(
        monkeypatch, class_2524_html, URL_CLASS, "class"
    )
    assert event.stopped


def _all_texts(component) -> str:
    parts = []
    content = getattr(component, "content", None)
    if content is None:
        content = getattr(component, "nodes", [])
    for child in content:
        if isinstance(child, Comp.Plain):
            parts.append(child.text)
        elif isinstance(child, Comp.Node):
            parts.append(_all_texts(child))
    return "\n".join(parts)


def _depth(component) -> int:
    depth = 1
    content = getattr(component, "content", None) or getattr(component, "nodes", [])
    for child in content:
        if isinstance(child, Comp.Node):
            depth = max(depth, 1 + _depth(child))
    return depth
