# -*- coding: utf-8 -*-
"""mcmod 页面头部信息解析（class 与 modpack 页面同构，共用一套选择器）。"""

from __future__ import annotations

import html
import re
from typing import Dict, List

from bs4 import BeautifulSoup

from astrbot.api import logger

from .body_parser import absolutize_url, normalize_text
from .models import RATING_KEYS, Meta

#: 中文评分维度 → 字段名
RATING_CN_TO_KEY = {
    "趣味": "fun",
    "难度": "difficulty",
    "稳定": "stability",
    "实用": "practicality",
    "美观": "aesthetics",
    "平衡": "balance",
    "兼容": "compatibility",
    "持久": "durability",
    "耐玩": "durability",
}

_VERSION_RE = re.compile(r"^\d+(?:\.\d+)*$")
_HEAT_RE = re.compile(r"昨日指数[:：]?\s*([\d.]+)")
_HEAT_AVG_RE = re.compile(r"昨日平均指数[:：]?\s*([\d.]+)")
_RED_RE = re.compile(r"红票\s*(\d+)\s*[\(（]\s*(\d+%)\s*[\)）]")
_BLACK_RE = re.compile(r"黑票\s*(\d+)\s*[\(（]\s*(\d+%)\s*[\)）]")
_MODPACK_COUNT_RE = re.compile(r"有\s*(\d+)\s*个已收录的整合包")
_MCVER_TEXT_RE = re.compile(r"([A-Za-z][\w+.\- ]*?)\s*[:：]\s*([\d][\d.,\s]*)")


class MetaParser:
    """解析模块/整合包页面的头部字段，任何字段缺失都只置空、不抛异常。"""

    def __init__(self, soup: BeautifulSoup, url: str = "", content_type: str = "class") -> None:
        self.soup = soup
        self.url = url
        self.content_type = "modpack" if content_type == "modpack" else "class"

    # ------------------------------------------------------------------ 入口
    def parse(self) -> Meta:
        meta = Meta(content_type=self.content_type, url=self.url)
        for field, getter in (
            ("name", self._title),
            ("tags", self._tags),
            ("authors", self._authors),
            ("mc_versions", self._mc_versions),
            ("view", self._view_counts),
            ("heat", self._heat),
            ("votes", self._votes),
            ("rating_score", self._rating_score),
            ("rating", self._rating),
            ("cover_url", self._cover),
            ("modpack_count", self._modpack_count),
        ):
            try:
                value = getter()
            except Exception as exc:  # 单字段异常不影响整体
                logger.warning(f"mcmod 解析字段 {field} 失败: {exc}")
                continue
            if isinstance(value, dict):
                for key, item in value.items():
                    setattr(meta, key, item)
        return meta

    # -------------------------------------------------------------- 头部字段
    def _title(self) -> Dict[str, object]:
        title_div = self.soup.select_one("div.class-title") or self.soup.select_one(
            "div.modpack-title"
        )
        if title_div is None:
            return {"chinese_name": normalize_text(self.soup.title.get_text() if self.soup.title else "")}

        short = title_div.select_one("span.short-name")
        chinese = title_div.select_one("h3") or title_div.select_one("h1")
        english = title_div.select_one("h4")

        status: List[str] = []
        for node in title_div.select("div.class-official-group div"):
            text = normalize_text(node.get_text(""))
            if text and text not in status:
                status.append(text)
        if not status:
            for node in title_div.select("div.class-status, div.class-source"):
                text = normalize_text(node.get_text(""))
                if text and text not in status:
                    status.append(text)

        source = ""
        source_node = title_div.select_one("div.class-source")
        if source_node is not None:
            source = normalize_text(source_node.get_text(""))

        return {
            "short_name": normalize_text(short.get_text("")) if short else "",
            "chinese_name": normalize_text(chinese.get_text("")) if chinese else "",
            "english_name": normalize_text(english.get_text("")) if english else "",
            "status": status,
            "source": source,
        }

    def _tags(self) -> Dict[str, List[str]]:
        tags: List[str] = []
        container = self.soup.select_one("li.col-lg-12.tag") or self.soup.select_one(
            "div.tag-list"
        )
        if container is not None:
            for anchor in container.select("a"):
                text = normalize_text(anchor.get_text(""))
                if text and text not in tags:
                    tags.append(text)
        return {"tags": tags}

    def _authors(self) -> Dict[str, List[str]]:
        authors: List[str] = []
        container = self.soup.select_one("li.col-lg-12.author")
        if container is not None:
            for anchor in container.select("li span.member span.name a"):
                text = normalize_text(anchor.get_text(""))
                if text and text not in authors:
                    authors.append(text)
            if not authors:
                for anchor in container.select("a"):
                    text = normalize_text(anchor.get_text(""))
                    if text and text not in authors:
                        authors.append(text)
        return {"authors": authors}

    def _mc_versions(self) -> Dict[str, Dict[str, List[str]]]:
        versions: Dict[str, List[str]] = {}
        container = self.soup.select_one("li.col-lg-12.mcver")
        if container is None:
            return {"mc_versions": versions}

        for ul in container.find_all("ul"):
            loader = ""
            collected: List[str] = []
            for li in ul.find_all("li", recursive=False):
                text = normalize_text(li.get_text(""))
                anchor = li.find("a")
                href = str(anchor.get("href") or "") if anchor is not None else ""
                if "mcver=" in href:
                    if text and text not in collected:
                        collected.append(text)
                elif text.endswith((":", "：")) and not _VERSION_RE.match(text[:-1].strip()):
                    loader = text[:-1].strip()
            if loader and collected:
                versions[loader] = collected

        if not versions:
            raw = normalize_text(container.get_text(" "))
            raw = re.sub(r"^支持的\s*MC\s*版本[:：]?", "", raw).strip()
            for loader, values in _MCVER_TEXT_RE.findall(raw):
                loader = loader.strip()
                items = [item.strip() for item in re.split(r"[,\s]+", values) if item.strip()]
                items = [item for item in items if _VERSION_RE.match(item)]
                if loader and items:
                    versions.setdefault(loader, [])
                    for item in items:
                        if item not in versions[loader]:
                            versions[loader].append(item)
        return {"mc_versions": versions}

    def _view_counts(self) -> Dict[str, str]:
        view_count = ""
        fill_rate = ""
        for node in self.soup.select("div.span"):
            label_node = node.select_one("p.t")
            value_node = node.select_one("p.n")
            if label_node is None or value_node is None:
                continue
            label = normalize_text(label_node.get_text(""))
            value = normalize_text(value_node.get_text(""))
            if "总浏览" in label and not view_count:
                view_count = value
            elif "填充率" in label and not fill_rate:
                fill_rate = value
        return {"view_count": view_count, "fill_rate": fill_rate}

    def _heat(self) -> Dict[str, str]:
        texts = [
            normalize_text(node.get_text(" "))
            for node in self.soup.select("div.block-right .text")
        ]
        blob = " ".join(texts)
        heat_index = ""
        heat_average = ""
        match = _HEAT_RE.search(blob)
        if match:
            heat_index = match.group(1)
        match = _HEAT_AVG_RE.search(blob)
        if match:
            heat_average = match.group(1)
        return {"heat_index": heat_index, "heat_average": heat_average}

    def _votes(self) -> Dict[str, str]:
        container = self.soup.select_one("div.text-block")
        blob = normalize_text(container.get_text(" ")) if container is not None else ""
        red_count = red_percentage = black_count = black_percentage = ""
        match = _RED_RE.search(blob)
        if match:
            red_count, red_percentage = match.group(1), match.group(2)
        match = _BLACK_RE.search(blob)
        if match:
            black_count, black_percentage = match.group(1), match.group(2)
        return {
            "red_count": red_count,
            "red_percentage": red_percentage,
            "black_count": black_count,
            "black_percentage": black_percentage,
        }

    def _rating_score(self) -> Dict[str, str]:
        block = self.soup.select_one("div.class-excount .star .block-left")
        if block is None:
            return {"rating_score": "", "rating_level": ""}
        up = block.select_one("p.up")
        down = block.select_one("p.down")
        return {
            "rating_score": normalize_text(up.get_text("")) if up else "",
            "rating_level": normalize_text(down.get_text("")) if down else "",
        }

    def _rating(self) -> Dict[str, Dict[str, int]]:
        rating = {key: 0 for key in RATING_KEYS}
        node = self.soup.select_one("div.class-rating-block #class-rating")
        if node is None:
            node = self.soup.select_one("#class-rating")
        if node is None:
            return {"rating": rating}
        title = node.get("data-original-title") or node.get("title") or ""
        decoded = html.unescape(str(title)).replace("<br>", "<br/>")
        for item in decoded.split("<br/>"):
            text = normalize_text(item)
            if not text:
                continue
            parts = re.split(r"[:：]", text, maxsplit=1)
            if len(parts) != 2:
                continue
            key = RATING_CN_TO_KEY.get(parts[0].strip())
            if key is None:
                continue
            match = re.search(r"\d+", parts[1])
            if match:
                rating[key] = int(match.group())
        return {"rating": rating}

    def _cover(self) -> Dict[str, str]:
        node = self.soup.select_one("div.class-cover-image img") or self.soup.select_one(
            "div.modpack-cover img"
        )
        if node is None:
            return {"cover_url": ""}
        raw = node.get("src") or node.get("data-src")
        return {"cover_url": absolutize_url(raw)}

    def _modpack_count(self) -> Dict[str, str]:
        container = self.soup.select_one("li.col-lg-12.infolist.modpack")
        if container is None:
            return {"modpack_count": ""}
        match = _MODPACK_COUNT_RE.search(normalize_text(container.get_text(" ")))
        return {"modpack_count": match.group(1) if match else ""}
