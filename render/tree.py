# -*- coding: utf-8 -*-
"""把解析结果组织成「合并转发」树。

通用规则只有一条：**标题节点 → 子转发节点**。

    Node 5. 模组集成联动
      ├─ Node 5.1 CEU 模组的全部功能（…）；
      ├─ Node 5.2 无中生有联动（…）；
      └─ …

    Node 6. 画廊
      ├─ Node 6.1 [图片] 新的多方块
      └─ …

段落、列表项、图片一律按「一个内容块 = 一个子转发节点」处理，不做任何标题级特殊逻辑。
QQ 最多三层嵌套转发（[记录] → [标题节点] → [子节点]），更深的内容自动折叠进父节点文本。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from astrbot.api import logger

from ..data.models import Meta, Section

#: 一个节点内的内容块：("text", 文本) 或 ("image", 图片字节)
ContentBlock = Tuple[str, Any]

#: 单条合并转发记录的节点数硬上限（QQ 端限制较严）
HARD_NODE_LIMIT = 40

#: 树深度硬上限（[记录] → [标题] → [子节点] = 3 层）
HARD_DEPTH_LIMIT = 3

DEFAULT_NODE_NAME = "MC百科"
DEFAULT_NODE_UIN = "10000"


@dataclass
class ForwardNodeData:
    """渲染前的转发节点。"""

    blocks: List[ContentBlock] = field(default_factory=list)
    children: List["ForwardNodeData"] = field(default_factory=list)

    def text(self) -> str:
        return "\n".join(
            str(value) for kind, value in self.blocks if kind == "text" and value
        )

    def images(self) -> List[bytes]:
        return [value for kind, value in self.blocks if kind == "image" and value]

    def nodes_count(self) -> int:
        return 1 + sum(child.nodes_count() for child in self.children)

    def depth(self) -> int:
        if not self.children:
            return 1
        return 1 + max(child.depth() for child in self.children)

    def clone(self, depth: int = 0) -> "ForwardNodeData":
        """按深度上限克隆子树，超出部分折叠为文本（QQ 最多三层）。"""
        node = ForwardNodeData(blocks=list(self.blocks))
        if depth + 1 >= HARD_DEPTH_LIMIT:
            node.blocks.extend(flatten_to_blocks(self.children))
            return node
        node.children = [child.clone(depth + 1) for child in self.children]
        return node


def flatten_to_blocks(nodes: Sequence[ForwardNodeData]) -> List[ContentBlock]:
    """把子树按前序展开成同一层的文本 / 图片块。"""
    blocks: List[ContentBlock] = []
    for node in nodes:
        text = node.text()
        if text:
            blocks.append(("text", text))
        for image in node.images():
            blocks.append(("image", image))
        blocks.extend(flatten_to_blocks(node.children))
    return blocks


def sanitize_nodes(nodes: Sequence[ForwardNodeData]) -> List[ForwardNodeData]:
    """丢弃空节点并按深度上限裁剪，避免 QQ 端渲染失败。"""
    cleaned: List[ForwardNodeData] = []
    for node in nodes:
        children = sanitize_nodes(node.children)
        blocks = [block for block in node.blocks if block[1]]
        if not blocks and not children:
            continue
        cleaned.append(ForwardNodeData(blocks=blocks, children=children).clone())
    return cleaned


def plan_records(
    roots: Sequence[ForwardNodeData],
    max_nodes_per_message: int = HARD_NODE_LIMIT,
) -> List[List[ForwardNodeData]]:
    """把根节点切成多条「合并转发记录」，不切开任何一个根节点的子树。"""
    limit = max(1, min(int(max_nodes_per_message or HARD_NODE_LIMIT), HARD_NODE_LIMIT))
    records: List[List[ForwardNodeData]] = []
    current: List[ForwardNodeData] = []
    current_count = 0

    for root in roots:
        count = root.nodes_count()
        if current and current_count + count > limit:
            records.append(current)
            current = []
            current_count = 0
        if count > limit:
            logger.warning(f"单个分区节点数 {count} 超过上限 {limit}，已单独作为一条转发记录")
        current.append(root)
        current_count += count
        if current_count >= limit:
            records.append(current)
            current = []
            current_count = 0

    if current:
        records.append(current)
    return records


class ForwardTreeBuilder:
    """通用转发树构造器：标题 → 子转发，每个内容块一个子节点。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        config = config or {}
        self.node_name = str(config.get("node_name") or DEFAULT_NODE_NAME)
        self.node_uin = str(config.get("node_uin") or DEFAULT_NODE_UIN)
        self.overview_split = bool(config.get("overview_split", True))
        self.include_cover = bool(config.get("include_cover", True))
        self.include_radar = bool(config.get("include_radar", True))
        self.include_images = bool(config.get("include_images", True))
        try:
            self.max_images = max(0, int(config.get("max_images", 40) or 0))
        except (TypeError, ValueError):
            self.max_images = 40
        try:
            self.max_nodes_per_message = int(
                config.get("max_nodes_per_message", HARD_NODE_LIMIT) or HARD_NODE_LIMIT
            )
        except (TypeError, ValueError):
            self.max_nodes_per_message = HARD_NODE_LIMIT
        #: url -> 图片字节，由调用方填充
        self.image_data: Dict[str, bytes] = {}

    # ------------------------------------------------------------------ 概览
    def build_overview(
        self,
        meta: Meta,
        cover: Optional[bytes] = None,
        radar: Optional[bytes] = None,
    ) -> Optional[ForwardNodeData]:
        """1. 条目 ID + 封面；2. 热度/指数/浏览量 + 雷达图；3. 标签与作者。"""
        root = ForwardNodeData()
        header = self._header_text(meta)
        metrics = self._metrics_text(meta)
        tags_text = self._tags_text(meta)
        cover = cover if self.include_cover else None
        radar = radar if self.include_radar else None

        if not self.overview_split:
            lines = [line for line in (header, metrics, tags_text) if line]
            if lines:
                root.blocks.append(("text", "\n\n".join(lines)))
            if cover:
                root.blocks.append(("image", cover))
            if radar:
                root.blocks.append(("image", radar))
            return root if root.blocks else None

        info_blocks: List[ContentBlock] = []
        if cover:
            info_blocks.append(("image", cover))
        if header:
            info_blocks.append(("text", header))
        if info_blocks:
            root.children.append(ForwardNodeData(blocks=info_blocks))

        metric_blocks: List[ContentBlock] = []
        if metrics:
            metric_blocks.append(("text", metrics))
        if radar:
            metric_blocks.append(("image", radar))
        if metric_blocks:
            root.children.append(ForwardNodeData(blocks=metric_blocks))

        if tags_text:
            root.children.append(ForwardNodeData(blocks=[("text", tags_text)]))

        return root if root.children else None

    def _header_text(self, meta: Meta) -> str:
        lines = [meta.display_name]
        if meta.subtitle:
            lines.append(meta.subtitle)
        if meta.content_type == "modpack":
            lines.append("类型：整合包")
        facts: List[str] = []
        if meta.status:
            facts.append(" / ".join(meta.status))
        if meta.modpack_count:
            facts.append(f"{meta.modpack_count} 个整合包在使用")
        if facts:
            lines.append(" · ".join(facts))
        versions = self._version_line(meta)
        if versions:
            lines.append(versions)
        if meta.url:
            lines.append(meta.url)
        return "\n".join(line for line in lines if line)

    def _metrics_text(self, meta: Meta) -> str:
        lines: List[str] = []
        if meta.rating_score or meta.rating_level:
            level = f"（{meta.rating_level}）" if meta.rating_level else ""
            lines.append(f"热度: {meta.rating_score or '-'}{level}")
        if meta.heat_index:
            lines.append(f"昨日指数: {meta.heat_index}")
        if meta.heat_average:
            lines.append(f"昨日平均指数: {meta.heat_average}")
        if meta.view_count:
            lines.append(f"浏览量: {meta.view_count}")
        if meta.fill_rate:
            lines.append(f"资料填充率: {meta.fill_rate}")
        if meta.red_count or meta.black_count:
            lines.append(
                f"红票: {meta.red_count or 0} ({meta.red_percentage or '-'}) | "
                f"黑票: {meta.black_count or 0} ({meta.black_percentage or '-'})"
            )
        return "\n".join(lines)

    def _tags_text(self, meta: Meta) -> str:
        lines: List[str] = []
        if meta.tags:
            lines.append(f"标签（{len(meta.tags)}）: " + " / ".join(meta.tags))
        if meta.authors:
            lines.append(f"作者（{len(meta.authors)}）: " + "、".join(meta.authors))
        return "\n\n".join(lines)

    def _version_line(self, meta: Meta) -> str:
        parts: List[str] = []
        for loader, versions in (meta.mc_versions or {}).items():
            if not versions:
                continue
            summary = versions[0] if len(versions) == 1 else f"{versions[0]} ~ {versions[-1]}"
            parts.append(f"{loader}: {summary}")
        return "支持的MC版本: " + "；".join(parts) if parts else ""

    # ------------------------------------------------------------------ 正文
    def build_body(self, sections: Sequence[Section]) -> List[ForwardNodeData]:
        """正文：每个标题一个节点，标题下的每个内容块再套一层子转发节点。"""
        roots: List[ForwardNodeData] = []
        number = 0
        image_budget = self.max_images if self.include_images else 0

        for section in sections:
            number += 1
            node = self._section_node(section, number, image_budget)
            if node is None:
                number -= 1
                continue
            image_budget -= count_images(node)
            roots.append(node)
        return roots

    def _section_node(
        self,
        section: Section,
        number: int,
        image_budget: int,
    ) -> Optional[ForwardNodeData]:
        title = f"{number}. {section.title}" if section.title else f"{number}. 正文"
        node = ForwardNodeData(blocks=[("text", title)])
        for block in section.blocks:
            child = self._block_node(block, image_budget)
            if child is None:
                continue
            node.children.append(child)
        return node

    def _block_node(self, block, image_budget: int) -> Optional[ForwardNodeData]:
        """一个内容块 → 一个子转发节点（图片块带标题行）。"""
        if block.kind == "figure":
            if image_budget <= 0 or block.figure is None:
                return None
            data = self.image_data.get(block.figure.url)
            if not data:
                logger.warning(f"图片不可用，已跳过: {block.figure.url}")
                return None
            blocks: List[ContentBlock] = [("image", data)]
            if block.figure.caption:
                blocks.append(("text", block.figure.caption))
            return ForwardNodeData(blocks=blocks)

        if not block.text:
            return None
        return ForwardNodeData(blocks=[("text", block.text)])

    # ------------------------------------------------------------ 图片清单
    def wanted_image_urls(self, meta: Meta, sections: Sequence[Section]) -> List[str]:
        """需要预下载的图片：封面 + 正文图片（受 max_images 限制）。"""
        urls: List[str] = []
        if self.include_cover and meta.cover_url:
            urls.append(meta.cover_url)
        if self.include_images and self.max_images > 0:
            remaining = self.max_images
            for section in sections:
                for figure in section.figures:
                    if remaining <= 0:
                        break
                    if figure.url and figure.url not in urls:
                        urls.append(figure.url)
                        remaining -= 1
        return urls


def count_images(node: ForwardNodeData) -> int:
    return len(node.images()) + sum(count_images(child) for child in node.children)
