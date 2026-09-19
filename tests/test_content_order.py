# -*- coding: utf-8 -*-
"""正文顺序守卫：标题与内容的先后关系必须与 mcmod 原页一致。

背景：解析层顺序是对的，但如果**缓存**里存着旧版本解析器产出的错乱结果，
TTL 内会直接把错乱内容发给用户。这里同时校验解析顺序与缓存版本策略。
"""

from __future__ import annotations

from bs4 import BeautifulSoup

import astrbot.api.message_components as Comp
from mcmod_plugin.data.body_parser import BodyParser
from mcmod_plugin.data.html_scraper import parse_page, read_cache, write_cache
from mcmod_plugin.data.meta_parser import MetaParser
from mcmod_plugin.data.models import SCHEMA_VERSION
from mcmod_plugin.render.forward import build_records
from mcmod_plugin.render.tree import ForwardTreeBuilder, build_record_nodes

URL_PACK = "https://www.mcmod.cn/modpack/897.html"


def build_texts(html: str, url: str, content_type: str) -> list:
    """按发送顺序取出所有纯文本节点内容。"""
    soup = BeautifulSoup(html, "lxml")
    meta = MetaParser(soup, url=url, content_type=content_type).parse()
    sections = BodyParser(soup).parse()
    builder = ForwardTreeBuilder({"include_images": False})
    parts = builder.build_body_parts(sections)
    overview = builder.build_overview(meta, cover=None, radar=None)
    records = build_records(build_record_nodes(overview, parts), config={})
    texts = []
    for record in records:
        for node in record.nodes:
            for component in node.content:
                if isinstance(component, Comp.Plain):
                    texts.append(component.text)
    return texts


def test_heading_precedes_its_own_content(modpack_897_html: str) -> None:
    """每个标题都必须排在它自己的内容之前。"""
    texts = build_texts(modpack_897_html, URL_PACK, "modpack")

    pairs = [
        ("3.1.4. 应用能源2（Applied Energistics 2）", "对 AE2 进行了深度魔改"),
        ("3.2. 魔法模块", "整合包中魔法线是一条与科技深度融合的支线"),
        ("3.2.1. 植物魔法（Botania）", "我们对植物魔法的资源获取"),
        ("3.1.3. 血肉重铸2（Biomancy 2）", "整合包通过自研模组 CTNH-Bio"),
        ("3.1.1. 机械动力（Create）", "整合包基于 6.0+ 版本的机械动力"),
    ]
    for heading, content in pairs:
        assert heading in texts, f"缺少标题 {heading}"
        body = next((t for t in texts if t.startswith(content)), None)
        assert body is not None, f"缺少内容 {content}"
        assert texts.index(heading) < texts.index(body), (
            f"顺序错乱：{heading} 出现在其内容之后"
        )


def test_section_order_matches_page(modpack_897_html: str) -> None:
    """标题出现的先后顺序必须与页面一致。"""
    texts = build_texts(modpack_897_html, URL_PACK, "modpack")
    headings = [
        t for t in texts
        if t[:1].isdigit() and len(t) < 45 and t.split(".")[0].isdigit()
    ]
    expected = [
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
        "4. 毕业基地展示",
        "5. 还有更多",
        "6. 配置需求",
    ]
    assert headings[: len(expected)] == expected


#: 解析/分段逻辑发生过重大修正，缓存结构版本不得低于此值。
#: 缺少这个下限，`range(1, SCHEMA_VERSION)` 之类的循环会跟着版本一起「自适应」，
#: 从而无法发现「改了解析器却忘记升版本」这类回归。
MIN_SCHEMA_VERSION = 3


def test_schema_version_is_not_downgraded() -> None:
    """缓存版本必须不低于已知正确值，防止旧缓存被复用。"""
    assert SCHEMA_VERSION >= MIN_SCHEMA_VERSION, (
        f"SCHEMA_VERSION={SCHEMA_VERSION} 低于最低要求 {MIN_SCHEMA_VERSION}；"
        "若确实要回退，请同时确认旧缓存不会再被复用"
    )


def test_stale_cache_is_never_served(tmp_path, modpack_897_html: str) -> None:
    """旧 schema 缓存必须被丢弃，重新解析得到正确顺序。"""
    fresh = parse_page(modpack_897_html, URL_PACK, "modpack")
    assert fresh is not None

    # 写一份「顺序错乱」的旧版缓存，并伪造为旧 schema
    import json
    import time
    from mcmod_plugin.data.html_scraper import cache_path

    scrambled = json.loads(json.dumps(fresh))
    scrambled["sections"] = list(reversed(scrambled["sections"]))

    for old_version in range(1, SCHEMA_VERSION):
        path = cache_path(tmp_path, URL_PACK)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({
                "schema": old_version,
                "timestamp": time.time(),
                "content": scrambled,
            }),
            encoding="utf-8",
        )
        assert read_cache(tmp_path, URL_PACK, ttl=86400) is None


def test_fresh_schema_cache_roundtrip(tmp_path, modpack_897_html: str) -> None:
    """当前 schema 的缓存可正常命中，且顺序保持。"""
    fresh = parse_page(modpack_897_html, URL_PACK, "modpack")
    write_cache(tmp_path, URL_PACK, fresh)
    hit = read_cache(tmp_path, URL_PACK, ttl=86400)
    assert hit is not None
    assert [s["title"] for s in hit["sections"]] == [
        s["title"] for s in fresh["sections"]
    ]
