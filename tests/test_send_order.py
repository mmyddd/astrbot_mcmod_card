# -*- coding: utf-8 -*-
"""发送顺序 / 竞态测试。

验证：

1. 同样输入，多次调用结果完全一致（确定性）；
2. 并发处理不会互相污染，也不会重复发送；
3. 不会出现「一半普通消息 + 一半合并转发」的混合态；
4. 结构扁平，无「文本 + 子节点」混合节点。
"""

from __future__ import annotations

import asyncio

from bs4 import BeautifulSoup

import astrbot.api.message_components as Comp
import mcmod_plugin.main as plugin_main
from mcmod_plugin.data.body_parser import BodyParser
from mcmod_plugin.data.meta_parser import MetaParser

URL_CLASS = "https://www.mcmod.cn/class/2524.html"
URL_PACK = "https://www.mcmod.cn/modpack/897.html"


class RecordingEvent:
    def __init__(self, url: str, platform: str = "aiocqhttp", tag: str = ""):
        self.message_str = f"看看 {url}"
        self.platform = platform
        self.tag = tag
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


def install_fakes(monkeypatch, html: str, url: str, content_type: str, delay: float = 0.0):
    soup = BeautifulSoup(html, "lxml")

    async def fake_gather(**kwargs):
        if delay:
            await asyncio.sleep(delay)
        return {
            "meta": MetaParser(soup, url=url, content_type=content_type).parse(),
            "sections": BodyParser(soup).parse(),
        }

    async def fake_images(urls, concurrency=4, timeout=10):
        if delay:
            await asyncio.sleep(delay)
        return {target: b"fake" for target in urls}

    monkeypatch.setattr(plugin_main, "gather_data", fake_gather)
    monkeypatch.setattr(plugin_main, "fetch_many_bytes", fake_images)


def run_one(plugin, event):
    async def run():
        async for _ in plugin.send_mod_card(event):
            pass

    asyncio.run(run())


def shape(event) -> list:
    """把一次发送压缩成可比对的「结构指纹」。"""
    fingerprint = []
    for chain in event.sent:
        for component in chain:
            if isinstance(component, Comp.Nodes):
                fingerprint.append(("Nodes", len(component.nodes)))
            elif isinstance(component, Comp.Plain):
                fingerprint.append(("Plain", component.text[:20]))
            else:
                fingerprint.append((type(component).__name__, 0))
    return fingerprint


def all_nodes(event) -> list:
    nodes = []
    for chain in event.sent:
        for component in chain:
            if isinstance(component, Comp.Nodes):
                nodes.extend(component.nodes)
    return nodes


def test_single_call_is_deterministic(monkeypatch, class_2524_html: str) -> None:
    """同样输入连跑三次，结构指纹必须完全一致。"""
    install_fakes(monkeypatch, class_2524_html, URL_CLASS, "class")
    results = []
    for _ in range(3):
        event = RecordingEvent(URL_CLASS)
        run_one(make_plugin(), event)
        results.append(shape(event))
    assert results[0] == results[1] == results[2]


def test_no_mixed_plain_and_forward(monkeypatch, modpack_897_html: str) -> None:
    """要么全走合并转发，要么全走降级。"""
    install_fakes(monkeypatch, modpack_897_html, URL_PACK, "modpack")
    for platform in ("aiocqhttp", "telegram"):
        event = RecordingEvent(URL_PACK, platform=platform)
        run_one(make_plugin(), event)
        names = {kind for kind, _ in shape(event)}
        if platform == "aiocqhttp":
            assert names == {"Nodes"}, f"{platform} 出现混合输出: {names}"
        else:
            assert "Nodes" not in names, f"{platform} 不应出现合并转发: {names}"


def test_structure_is_flat(monkeypatch, modpack_897_html: str) -> None:
    """记录内所有节点都是叶子：无嵌套、无混排。"""
    install_fakes(monkeypatch, modpack_897_html, URL_PACK, "modpack")
    event = RecordingEvent(URL_PACK)
    run_one(make_plugin(), event)
    for node in all_nodes(event):
        has_child = any(isinstance(c, Comp.Node) for c in node.content)
        has_text = any(isinstance(c, Comp.Plain) for c in node.content)
        assert not has_child, "记录内出现嵌套节点"
        assert not (has_text and has_child), "出现文本+子节点混合节点"
        assert node.content, "出现空节点"


def test_concurrent_calls_do_not_cross_contaminate(monkeypatch, class_2524_html: str) -> None:
    """5 路并发处理同一链接，各自独立、互不串台。"""
    install_fakes(monkeypatch, class_2524_html, URL_CLASS, "class", delay=0.01)

    async def run_all():
        events = [RecordingEvent(URL_CLASS, tag=str(i)) for i in range(5)]
        plugins = [make_plugin() for _ in range(5)]

        async def drive(plugin, event):
            async for _ in plugin.send_mod_card(event):
                pass

        await asyncio.gather(*(drive(p, e) for p, e in zip(plugins, events)))
        return events

    events = asyncio.run(run_all())
    shapes = {tuple(shape(event)) for event in events}
    assert len(shapes) == 1, "并发调用产生了不同的结果"
    for event in events:
        assert all(kind == "Nodes" for kind, _ in shape(event))


def test_repeat_call_same_plugin(monkeypatch, class_2524_html: str) -> None:
    """同一实例连续触发两次，结果一致且不累积。"""
    install_fakes(monkeypatch, class_2524_html, URL_CLASS, "class")
    plugin = make_plugin()
    first = RecordingEvent(URL_CLASS)
    second = RecordingEvent(URL_CLASS)
    run_one(plugin, first)
    run_one(plugin, second)
    assert shape(first) == shape(second)


def test_stop_event_called(monkeypatch, class_2524_html: str) -> None:
    install_fakes(monkeypatch, class_2524_html, URL_CLASS, "class")
    event = RecordingEvent(URL_CLASS)
    run_one(make_plugin(), event)
    assert event.stopped is True
