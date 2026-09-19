# -*- coding: utf-8 -*-
"""把解析结果组织成发送结构。

两条通用规则：

1. **标题写在聊天记录外**：每个标题（含 1/1.1/1.1.1 编号）作为一条普通消息发送；
   标题与该标题之间的内容（段落、列表项、图片）放进紧随其后的合并转发记录。
2. **标题层级决定编号**：mcmod 的 ``common-text-title-1/2/3`` 直接映射为 1 / 1.1 / 1.1.1。

因此正文的深度恒为「记录 → 内容节点」两层，不再受 QQ 三层嵌套转发限制。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from astrbot.api import logger

from ..data.models import Meta, Section

#: 一个节点内的内容块：("text", 文本) 或 ("image", 图片字节)
ContentBlock = Tuple[str, Any]

#: 单条合并转发记录的顶层节点数上限
#: 结构已完全扁平，QQ 对「messages 数组长度」的容忍度较高（实测 60+ 正常），
#: 留一点余量并允许配置覆盖。
HARD_NODE_LIMIT = 80

#: 树深度硬上限（[记录] → [节点] = 2 层，留一层余量）
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

    def clone(self, depth: int = 0) -> "ForwardNodeData":
        """按深度上限克隆子树，超出部分折叠为文本（保险措施）。"""
        node = ForwardNodeData(blocks=list(self.blocks))
        if depth + 1 >= HARD_DEPTH_LIMIT:
            node.blocks.extend(flatten_to_blocks(self.children))
            return node
        node.children = [child.clone(depth + 1) for child in self.children]
        return node


@dataclass
class BodyPart:
    """一个标题及其直属内容（标题与内容都放进同一条合并转发记录）。"""

    number: str = ""
    title: str = ""
    level: int = 1
    nodes: List[ForwardNodeData] = field(default_factory=list)

    @property
    def heading(self) -> str:
        if not self.title:
            return f"{self.number}. 正文" if self.number else "正文"
        return f"{self.number}. {self.title}" if self.number else self.title

    def text(self) -> str:
        return "\n".join(node.text() for node in self.nodes if node.text())


def flatten_leaves(nodes: Sequence[ForwardNodeData]) -> List[ForwardNodeData]:
    """把任意节点树压成**一层叶子列表**（前序：本节点内容在前，子节点在后）。

    硬性约束：每个节点只允许包含自己的内容块（纯文本或纯图片），
    **绝不允许同时包含文本与子节点**——OneBot/NapCat 无法发送这种混合节点。
    因此这里把任何「既有内容又有子节点」的节点拆成两个兄弟节点。
    """
    flat: List[ForwardNodeData] = []
    for node in nodes:
        blocks = [block for block in node.blocks if block[1]]
        if blocks:
            flat.append(ForwardNodeData(blocks=blocks))
        if node.children:
            flat.extend(flatten_leaves(node.children))
    return flat


def build_record_nodes(
    overview: Optional[ForwardNodeData],
    parts: Sequence[BodyPart],
) -> List[ForwardNodeData]:
    """把所有内容装进**同一条**合并转发记录的节点列表（结构完全扁平）。

    顺序即阅读顺序，**先标题、后内容**；标题与内容互为兄弟节点，不做任何嵌套::

        [合并转发记录]        ← 整条记录只有 1 层，深度恒为 1
          ├─ 概览：封面 + 名称
          ├─ 概览：热度 / 指数 / 浏览量
          ├─ 概览：标签与作者
          ├─ 1. 写在开头                    ← 标题（纯文本）
          ├─ 1.1. 版本注意事项              ← 标题（纯文本）
          ├─ 注1：由 i18n自动汉化更新…       ← 内容（标题的下一个兄弟节点）
          ├─ 注2：此模组以 0.24.0-final…
          ├─ …
          └─ 4. 画廊
               ├─ [图片] 新的多方块          ← 图片各自成节点
               └─ …

    每个节点只承载自己的内容，绝不混排；整条记录深度恒为 1，
    既不受 QQ 嵌套层数限制，也避开了「文本 + 子节点混合」无法发送的问题。
    """
    raw: List[ForwardNodeData] = []
    if overview is not None:
        raw.append(overview)
    for part in parts:
        if part.heading:
            raw.append(ForwardNodeData(blocks=[("text", part.heading)]))
        raw.extend(part.nodes)
    return flatten_leaves(raw)


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
    """把节点切成「合并转发记录」。

    默认上游只传一次，也就是**所有内容装进同一条聊天记录**，避免刷屏；
    只有顶层节点数超过上限时才分片，且不切开任何一个节点的子树。
    """
    limit = max(1, min(int(max_nodes_per_message or HARD_NODE_LIMIT), HARD_NODE_LIMIT))
    items = list(roots)
    if len(items) <= limit:
        return [items] if items else []

    logger.info(f"顶层节点数 {len(items)} 超过单条转发上限 {limit}，将拆分为多条记录")
    return [items[start:start + limit] for start in range(0, len(items), limit)]


class ForwardTreeBuilder:
    """构造「概览记录」与「正文标题 + 内容」结构。"""

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
    def build_body_parts(self, sections: Sequence[Section]) -> List[BodyPart]:
        """按标题把正文拆成 BodyPart，编号遵循标题层级（1 / 1.1 / 1.1.1）。"""
        parts: List[BodyPart] = []
        counters: List[int] = []
        image_budget = self.max_images if self.include_images else 0

        for section in sections:
            level = max(1, int(section.level or 1))
            del counters[level:]  # 保留 1..level 级计数，重置更深层
            while len(counters) < level:
                counters.append(0)
            counters[level - 1] += 1
            number = ".".join(str(value) for value in counters)

            nodes: List[ForwardNodeData] = []
            for block in section.blocks:
                node = self._block_node(block, image_budget)
                if node is None:
                    continue
                image_budget -= len(node.images())
                nodes.append(node)

            parts.append(
                BodyPart(number=number, title=section.title, level=level, nodes=nodes)
            )
        return parts

    def _block_node(self, block, image_budget: int) -> Optional[ForwardNodeData]:
        """一个内容块 → 一个转发节点（图片块带图片与图注）。"""
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
