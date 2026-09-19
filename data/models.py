# -*- coding: utf-8 -*-
"""MC百科数据结构定义（解析层、缓存层与渲染层共用）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

#: 缓存结构版本，解析结果结构变化时递增（旧缓存自动失效）
SCHEMA_VERSION = 2

#: 雷达图维度（与 mcmod 评分弹窗一一对应）
RATING_KEYS = (
    "fun",
    "difficulty",
    "stability",
    "practicality",
    "aesthetics",
    "balance",
    "compatibility",
    "durability",
)

RATING_LABELS = {
    "fun": "趣味",
    "difficulty": "难度",
    "stability": "稳定",
    "practicality": "实用",
    "aesthetics": "美观",
    "balance": "平衡",
    "compatibility": "兼容",
    "durability": "耐玩",
}


def _pick_fields(cls: Any, raw: Any) -> Dict[str, Any]:
    """只保留 dataclass 已声明的字段，避免缓存脏数据导致构造失败。"""
    if not isinstance(raw, dict):
        return {}
    names = getattr(cls, "__dataclass_fields__", {})
    return {key: value for key, value in raw.items() if key in names}


@dataclass
class Figure:
    """正文中的一张图片。"""

    url: str = ""
    caption: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"url": self.url, "caption": self.caption}

    @classmethod
    def from_dict(cls, raw: Any) -> "Figure":
        data = _pick_fields(cls, raw)
        return cls(url=str(data.get("url") or ""), caption=str(data.get("caption") or ""))


@dataclass
class Block:
    """正文中的最小内容块。

    kind: para（普通段落） / item（列表项） / figure（图片） / table（无图表格的兜底文本）
    """

    kind: str = "para"
    text: str = ""
    level: int = 0
    figure: Optional[Figure] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "kind": self.kind,
            "text": self.text,
            "level": self.level,
        }
        if self.figure is not None:
            data["figure"] = self.figure.to_dict()
        return data

    @classmethod
    def from_dict(cls, raw: Any) -> "Block":
        data = _pick_fields(cls, raw)
        figure = data.get("figure")
        return cls(
            kind=str(data.get("kind") or "para"),
            text=str(data.get("text") or ""),
            level=int(data.get("level") or 0),
            figure=Figure.from_dict(figure) if isinstance(figure, dict) else None,
        )


@dataclass
class Section:
    """正文中的一个标题分区（对应 mcmod 的 common-text-title）。"""

    title: str = ""
    level: int = 1
    blocks: List[Block] = field(default_factory=list)

    @property
    def figures(self) -> List[Figure]:
        return [
            block.figure
            for block in self.blocks
            if block.kind == "figure" and block.figure is not None
        ]

    @property
    def text_blocks(self) -> List[Block]:
        return [block for block in self.blocks if block.kind != "figure"]

    @property
    def paragraph_count(self) -> int:
        return sum(1 for block in self.blocks if block.kind in ("para", "table"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "level": self.level,
            "blocks": [block.to_dict() for block in self.blocks],
        }

    @classmethod
    def from_dict(cls, raw: Any) -> "Section":
        data = _pick_fields(cls, raw)
        blocks = data.get("blocks")
        return cls(
            title=str(data.get("title") or ""),
            level=int(data.get("level") or 1),
            blocks=[Block.from_dict(item) for item in blocks] if isinstance(blocks, list) else [],
        )


@dataclass
class Meta:
    """页面头部信息（class 与 modpack 页面同构，共用一套字段）。"""

    content_type: str = "class"
    url: str = ""
    short_name: str = ""
    chinese_name: str = ""
    english_name: str = ""
    status: List[str] = field(default_factory=list)
    source: str = ""
    tags: List[str] = field(default_factory=list)
    authors: List[str] = field(default_factory=list)
    mc_versions: Dict[str, List[str]] = field(default_factory=dict)
    view_count: str = ""
    fill_rate: str = ""
    heat_index: str = ""
    heat_average: str = ""
    rating_score: str = ""
    rating_level: str = ""
    red_count: str = ""
    red_percentage: str = ""
    black_count: str = ""
    black_percentage: str = ""
    modpack_count: str = ""
    cover_url: str = ""
    rating: Dict[str, int] = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        parts = [part for part in (self.short_name, self.chinese_name) if part]
        if parts:
            return " ".join(parts)
        return self.english_name or "未知条目"

    @property
    def subtitle(self) -> str:
        if self.english_name and self.english_name != self.chinese_name:
            return self.english_name
        return ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content_type": self.content_type,
            "url": self.url,
            "short_name": self.short_name,
            "chinese_name": self.chinese_name,
            "english_name": self.english_name,
            "status": list(self.status),
            "source": self.source,
            "tags": list(self.tags),
            "authors": list(self.authors),
            "mc_versions": {key: list(value) for key, value in self.mc_versions.items()},
            "view_count": self.view_count,
            "fill_rate": self.fill_rate,
            "heat_index": self.heat_index,
            "heat_average": self.heat_average,
            "rating_score": self.rating_score,
            "rating_level": self.rating_level,
            "red_count": self.red_count,
            "red_percentage": self.red_percentage,
            "black_count": self.black_count,
            "black_percentage": self.black_percentage,
            "modpack_count": self.modpack_count,
            "cover_url": self.cover_url,
            "rating": dict(self.rating),
        }

    @classmethod
    def from_dict(cls, raw: Any) -> "Meta":
        data = _pick_fields(cls, raw)
        rating = data.get("rating")
        versions = data.get("mc_versions")
        return cls(
            content_type=str(data.get("content_type") or "class"),
            url=str(data.get("url") or ""),
            short_name=str(data.get("short_name") or ""),
            chinese_name=str(data.get("chinese_name") or ""),
            english_name=str(data.get("english_name") or ""),
            status=[str(item) for item in data.get("status") or []],
            source=str(data.get("source") or ""),
            tags=[str(item) for item in data.get("tags") or []],
            authors=[str(item) for item in data.get("authors") or []],
            mc_versions={
                str(key): [str(item) for item in value or []]
                for key, value in (versions or {}).items()
            },
            view_count=str(data.get("view_count") or ""),
            fill_rate=str(data.get("fill_rate") or ""),
            heat_index=str(data.get("heat_index") or ""),
            heat_average=str(data.get("heat_average") or ""),
            rating_score=str(data.get("rating_score") or ""),
            rating_level=str(data.get("rating_level") or ""),
            red_count=str(data.get("red_count") or ""),
            red_percentage=str(data.get("red_percentage") or ""),
            black_count=str(data.get("black_count") or ""),
            black_percentage=str(data.get("black_percentage") or ""),
            modpack_count=str(data.get("modpack_count") or ""),
            cover_url=str(data.get("cover_url") or ""),
            rating={str(key): int(value or 0) for key, value in (rating or {}).items()},
        )
