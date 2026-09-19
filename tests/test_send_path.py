# -*- coding: utf-8 -*-
"""发送路径测试：真实走一遍 _send_overview / _send_body 的生成器。

这里的重点是「插件真的能跑」——单元测试覆盖了解析与树构造，
但曾经漏掉过 main.py 里的名字错误（NameError），因此这里直接驱动发送协程。
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


def build_parts(html: str, content_type: str, url: str, config=None):
    soup = BeautifulSoup(html, "lxml")
    meta = MetaParser(soup, url=url, content_type=content_type).parse()
    sections = BodyParser(soup).parse()
    builder = ForwardTreeBuilder(config or {"include_images": False})
    return meta, builder, builder.build_body_parts(sections)


def drive(plugin, event, coro) -> None:
    async def run():
        async for _ in coro:
            pass

    asyncio.run(run())


def test_send_body_produces_headings_and_records(class_2524_html: str) -> None:
    """标题作为普通消息、内容作为合并转发记录，且二者交替出现。"""
    plugin = make_plugin()
    meta, builder, parts = build_parts(
        class_2524_html, "class", "https://www.mcmod.cn/class/2524.html"
    )
    event = FakeEvent()
    drive(plugin, event, plugin._send_body(event, parts, True, True))

    assert event.sent, "发送路径必须产出内容"
    plains = [item[1] for item in event.sent if item[0] == "plain"]
    chains = [item[1] for item in event.sent if item[0] == "chain"]
    assert any(isinstance(entry[0], Comp.Plain) for entry in chains)
    # 标题以普通消息发送
    heading_texts = [
        entry[0].text
        for entry in chains
        if isinstance(entry[0], Comp.Plain)
    ]
    assert any(text.startswith("1. ") for text in heading_texts)
    assert not plains, "支持合并转发时不应退回普通消息"


def test_send_body_fallback_without_forward(class_2524_html: str) -> None:
    """平台不支持合并转发时，全部走普通消息且不报错。"""
    plugin = make_plugin()
    meta, builder, parts = build_parts(
        class_2524_html, "class", "https://www.mcmod.cn/class/2524.html"
    )
    event = FakeEvent(platform="telegram")
    drive(plugin, event, plugin._send_body(event, parts, False, False))

    chains = [item[1] for item in event.sent if item[0] == "chain"]
    assert chains
    assert all(isinstance(entry[0], Comp.Plain) for entry in chains)
    texts = [entry[0].text for entry in chains]
    assert "1. 写在开头" in texts
    assert any(text.startswith("3.1 ") for text in texts)


def test_send_overview_runs(class_2524_html: str) -> None:
    plugin = make_plugin()
    soup = BeautifulSoup(class_2524_html, "lxml")
    meta = MetaParser(
        soup, url="https://www.mcmod.cn/class/2524.html", content_type="class"
    ).parse()
    builder = ForwardTreeBuilder({"include_radar": False})
    overview = builder.build_overview(meta, cover=None, radar=None)
    event = FakeEvent()
    drive(plugin, event, plugin._send_overview(event, overview, True, True))
    assert event.sent
    chain = event.sent[0][1]
    assert isinstance(chain[0], Comp.Nodes)


def test_send_body_without_content_still_sends_headings(modpack_897_html: str) -> None:
    """有的标题下没有正文，标题仍应发出且不报错。"""
    plugin = make_plugin()
    meta, builder, parts = build_parts(
        modpack_897_html,
        "modpack",
        "https://www.mcmod.cn/modpack/897.html",
        config={"include_images": False},
    )
    empty_parts = [part for part in parts if not part.nodes]
    assert empty_parts, "该页面应存在无正文的标题"
    event = FakeEvent()
    drive(plugin, event, plugin._send_body(event, empty_parts, True, True))
    texts = [
        entry[0].text for item in event.sent for entry in [item[1]] if isinstance(entry[0], Comp.Plain)
    ]
    for part in empty_parts:
        assert part.heading in texts


def test_wrap_plain_helper() -> None:
    """_wrap_plain 必须真的能构造 Plain 组件（曾经漏了 Comp 导入）。"""
    from mcmod_plugin.main import _wrap_plain

    messages = _wrap_plain([Comp.Plain("标题")])
    assert messages == [[Comp.Plain("标题")]] or [m[0].text for m in messages] == ["标题"]
    assert _wrap_plain([]) == []
