# -*- coding: utf-8 -*-
"""mcmod 正文解析：按 mcmod 自己的排版逻辑切分标题 / 段落 / 列表 / 图片。

mcmod 正文结构（class 与 modpack 页面同构）::

    li.text-area.common-text
      ├─ p  <span class="common-text-title common-text-title-1">模组简介</span>
      ├─ p  普通段落（行内 <a>/<strong> 只保留可见文字）
      ├─ ul > li > p 列表项
      └─ table > tbody > tr > td > p > span.figure > img + span.figcaption
"""

from __future__ import annotations

import re
from typing import List, Optional, Sequence

from bs4 import BeautifulSoup, NavigableString, Tag

from astrbot.api import logger

from .models import Block, Figure, Section

#: 正文容器（class / modpack 页面同一套 class）
BODY_SELECTORS = (
    "li.text-area.common-text",
    "div.text-area.common-text",
    "li.text-area.text-area-post",
)

#: 标题行内 span 与图片容器
TITLE_CLASS = "common-text-title"
FIGURE_CLASS = "figure"
FIGCAPTION_CLASS = "figcaption"


#: 站内相对链接补全用
DEFAULT_BASE_URL = "https://www.mcmod.cn"

#: 懒加载占位图特征（必须取 data-src 才有真图）
LAZY_PLACEHOLDER_HINTS = ("loading", "loadfail", "none.jpg")

#: mcmod 注入的不可见字符
_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"), None)

#: 行内元素：内容并入当前段落，不打断文字流
INLINE_TAGS = frozenset({
    "a", "strong", "b", "i", "em", "u", "s", "small", "mark", "code", "kbd",
    "sup", "sub", "span", "font", "abbr", "cite", "q", "time", "var", "big",
    "tt", "ins", "del", "ruby", "rt", "rp", "wbr",
})

#: 块级元素：结束当前段落
BLOCK_TAGS = frozenset({
    "p", "div", "li", "ul", "ol", "table", "tbody", "thead", "tr", "td", "th",
    "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "section", "article",
    "figure", "figcaption", "dl", "dt", "dd", "hr",
})

_WHITESPACE_RE = re.compile(r"\s+")
_TITLE_LEVEL_RE = re.compile(r"common-text-title-(\d+)$")


def normalize_text(raw: Optional[str]) -> str:
    """折叠空白、去掉零宽字符，得到与浏览器渲染一致的可见文本。"""
    if not raw:
        return ""
    text = str(raw).translate(_INVISIBLE)
    return _WHITESPACE_RE.sub(" ", text).strip()


def absolutize_url(url: Optional[str], base_url: str = DEFAULT_BASE_URL) -> str:
    """把 ``//i.mcmod.cn/x.jpg``、``/pages/a.png`` 补成完整 URL。"""
    if not url:
        return ""
    value = str(url).strip().translate(_INVISIBLE)
    if not value or value.startswith("data:"):
        return ""
    lowered = value.lower()
    if any(hint in lowered for hint in LAZY_PLACEHOLDER_HINTS):
        return ""
    if value.startswith("//"):
        return "https:" + value
    if value.startswith("http://"):
        return "https://" + value[len("http://"):]
    if value.startswith("https://"):
        return value
    if value.startswith("/"):
        return base_url.rstrip("/") + value
    return base_url.rstrip("/") + "/" + value


def _title_level(span: Tag) -> int:
    """``common-text-title-2`` 之类的后缀就是层级，缺省为 1。"""
    for class_name in span.get("class") or []:
        match = _TITLE_LEVEL_RE.match(str(class_name))
        if match:
            try:
                return max(1, int(match.group(1)))
            except ValueError:
                return 1
    return 1


def _is_title_span(node: Tag) -> bool:
    if TITLE_CLASS not in (node.get("class") or []):
        return False
    return bool(normalize_text(node.get_text("")))


class BodyParser:
    """把 ``li.text-area.common-text`` 解析成 Section 列表。"""

    def __init__(
        self,
        soup: BeautifulSoup,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self.soup = soup
        self.base_url = base_url or DEFAULT_BASE_URL

    # ------------------------------------------------------------------ 入口
    def parse(self) -> List[Section]:
        container = self._find_container()
        if container is None:
            logger.warning("mcmod 正文解析：未找到 li.text-area.common-text 容器")
            return []

        for tag in container.find_all(["script", "style"]):
            tag.decompose()

        sections: List[Section] = []
        current = Section(title="", level=1)
        saw_title = False

        for block in self._parse_children(container):
            if block.kind == "title":
                if current.blocks or current.title:
                    sections.append(current)
                current = Section(title=block.text, level=block.level or 1)
                saw_title = True
                continue
            current.blocks.append(block)

        if current.blocks or current.title:
            sections.append(current)

        sections = [section for section in sections if section.blocks or section.title]
        for section in sections:
            if not section.title:
                # 页首无标题的开场白统一称作「简介」
                section.title = "简介"

        logger.debug(
            "mcmod 正文解析完成：%s 个分区，%s 个内容块",
            len(sections),
            sum(len(section.blocks) for section in sections),
        )
        return sections

    # -------------------------------------------------------------- 内部工具
    def _find_container(self) -> Optional[Tag]:
        for selector in BODY_SELECTORS:
            container = self.soup.select_one(selector)
            if container is not None:
                return container
        return None

    def _parse_children(self, node: Tag) -> List[Block]:
        """按 DOM 顺序解析子节点，图片与文字保持原始次序。"""
        blocks: List[Block] = []
        buffer: List[str] = []

        def flush() -> None:
            if not buffer:
                return
            raw = "".join(buffer)
            del buffer[:]
            for line in raw.split("\n"):
                text = normalize_text(line)
                if text:
                    blocks.append(Block(kind="para", text=text))

        for child in node.children:
            if isinstance(child, NavigableString):
                buffer.append(str(child))
                continue
            if not isinstance(child, Tag):
                continue
            name = (child.name or "").lower()
            if name in ("script", "style"):
                continue
            if name == "br":
                buffer.append("\n")
                continue

            title_span = child.find("span", class_=TITLE_CLASS)
            if title_span is not None and _is_title_span(title_span):
                flush()
                title_text = normalize_text(title_span.get_text(""))
                if title_text:
                    blocks.append(
                        Block(kind="title", text=title_text, level=_title_level(title_span))
                    )
                remainder = normalize_text(
                    child.get_text("").replace(title_span.get_text(""), "")
                )
                if remainder:
                    blocks.append(Block(kind="para", text=remainder))
                continue

            if name in ("ul", "ol"):
                flush()
                blocks.extend(self._parse_list(child))
                continue

            if name == "table":
                flush()
                blocks.extend(self._parse_table(child))
                continue

            figure = self._figure_of(child)
            if figure is not None:
                flush()
                blocks.append(Block(kind="figure", figure=figure))
                continue

            if name in INLINE_TAGS and not child.find(["img", "br"]):
                # 行内元素（超链接 / 加粗等）并入当前段落，保持文字顺序
                buffer.append(child.get_text(""))
                continue

            if name == "p" or name in BLOCK_TAGS:
                flush()
                blocks.extend(self._parse_children(child))
                flush()
                continue

            blocks.extend(self._parse_children(child))

        flush()
        return blocks

    def _parse_list(self, node: Tag) -> List[Block]:
        blocks: List[Block] = []
        for item in node.find_all("li", recursive=False):
            for block in self._parse_children(item):
                if block.kind == "para":
                    block.kind = "item"
                blocks.append(block)
        return blocks

    def _parse_table(self, node: Tag) -> List[Block]:
        """表格以图片抽取为主；纯文字表格降级为一行文本。"""
        blocks: List[Block] = []
        for child in node.children:
            if isinstance(child, Tag):
                blocks.extend(self._parse_children(child))

        figures = [block for block in blocks if block.kind == "figure"]
        texts = [
            block.text for block in blocks if block.kind != "figure" and block.text
        ]
        if figures and not texts:
            return figures
        if figures:
            return figures + [Block(kind="table", text=" / ".join(texts))]
        if texts:
            return [Block(kind="table", text=" | ".join(texts))]
        return []

    def _figure_of(self, node: Tag) -> Optional[Figure]:
        """节点自身或其直接子级是否为「整块就是一张图」的 figure 容器。"""
        if not isinstance(node, Tag):
            return None

        span = node if FIGURE_CLASS in (node.get("class") or []) else None
        if span is None:
            span = node.find("span", class_=FIGURE_CLASS)
            if span is None:
                return None
            # 只有整块内容就是这张图时才在此截断，否则交给子节点递归
            outer = normalize_text(node.get_text(""))
            inner = normalize_text(span.get_text(""))
            if outer and outer != inner:
                return None

        img = span.find("img")
        if img is None:
            return None
        url = absolutize_url(
            img.get("data-src") or img.get("data-original") or img.get("src"),
            self.base_url,
        )
        if not url:
            return None
        caption_tag = span.find("span", class_=FIGCAPTION_CLASS)
        caption = normalize_text(caption_tag.get_text("")) if caption_tag else ""
        return Figure(url=url, caption=caption)
