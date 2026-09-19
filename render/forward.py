# -*- coding: utf-8 -*-
"""把转发树物化为 AstrBot 组件。

发送结构：

    标题（普通消息，写在聊天记录外）
    合并转发记录（标题与下一个标题之间的段落 / 列表项 / 图片）
    标题（普通消息）
    合并转发记录
    …
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from astrbot.api import logger
import astrbot.api.message_components as Comp

from .tree import (
    DEFAULT_NODE_NAME,
    DEFAULT_NODE_UIN,
    HARD_DEPTH_LIMIT,
    HARD_NODE_LIMIT,
    BodyPart,
    ForwardNodeData,
    plan_records,
    sanitize_nodes,
)

#: 单个 Plain 段的最大长度（QQ 对单段文本有长度限制）
MAX_PLAIN_CHARS = 1500

#: 文本降级时每条消息的最大长度
MAX_TEXT_MESSAGE_CHARS = 1800


def _split_text(text: str, limit: int = MAX_PLAIN_CHARS) -> List[str]:
    """把超长文本按行切成多段，保证不丢内容。"""
    if len(text) <= limit:
        return [text]
    chunks: List[str] = []
    buffer = ""
    for line in text.split("\n"):
        while len(line) > limit:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = f"{buffer}\n{line}" if buffer else line
        if len(candidate) > limit:
            chunks.append(buffer)
            buffer = line
        else:
            buffer = candidate
    if buffer:
        chunks.append(buffer)
    return [chunk for chunk in chunks if chunk]


def _components_from_blocks(blocks: Sequence[Tuple[str, Any]]) -> List[Any]:
    content: List[Any] = []
    for kind, value in blocks:
        if kind == "text" and value:
            for chunk in _split_text(str(value)):
                content.append(Comp.Plain(chunk))
        elif kind == "image" and value:
            try:
                content.append(Comp.Image.fromBytes(bytes(value)))
            except Exception as exc:
                logger.warning(f"构造图片组件失败: {exc}")
    return content


def to_component(
    data: ForwardNodeData,
    name: str = DEFAULT_NODE_NAME,
    uin: str = DEFAULT_NODE_UIN,
    depth: int = 1,
) -> Comp.Node:
    """递归把转发节点转为 ``Comp.Node``（内容只允许 Plain / Image）。

    正文深度恒为「记录 → 节点」两层；这里仍保留深度保护，
    超出 QQ 三层嵌套上限的子树折叠为文本。
    """
    content = _components_from_blocks(data.blocks)
    if depth >= HARD_DEPTH_LIMIT:
        content.extend(_components_from_blocks(_fold_children(data.children)))
    else:
        for child in data.children:
            content.append(to_component(child, name=name, uin=uin, depth=depth + 1))
    return Comp.Node(content=content, name=name, uin=uin)


def _fold_children(nodes: Sequence[ForwardNodeData]) -> List[Tuple[str, Any]]:
    """把子树折叠成缩进文本；带标题的节点保留「标题行 + 正文」结构。"""
    blocks: List[Tuple[str, Any]] = []
    for node in nodes:
        lines = node.text().split("\n") if node.text() else []
        heading = lines[0] if lines else ""
        body = lines[1:]
        if heading:
            blocks.append(("text", f"\n{heading}"))
        for line in body:
            blocks.append(("text", f"　　{line}"))
        for image in node.images():
            blocks.append(("image", image))
        blocks.extend(_fold_children(node.children))
    return blocks


def _record_component(
    record: Sequence[ForwardNodeData],
    name: str,
    uin: str,
) -> Comp.Nodes:
    return Comp.Nodes(nodes=[to_component(node, name=name, uin=uin) for node in record])


def _record_options(config: Dict[str, Any]) -> Tuple[str, str, int]:
    name = str(config.get("node_name") or DEFAULT_NODE_NAME)
    uin = str(config.get("node_uin") or DEFAULT_NODE_UIN)
    try:
        limit = int(config.get("max_nodes_per_message", HARD_NODE_LIMIT) or HARD_NODE_LIMIT)
    except (TypeError, ValueError):
        limit = HARD_NODE_LIMIT
    return name, uin, limit


def build_forward_records(
    overview: Optional[ForwardNodeData],
    body: Sequence[ForwardNodeData],
    config: Optional[Dict[str, Any]] = None,
    forward_overview: bool = True,
    forward_body: bool = True,
) -> Tuple[List[Comp.Nodes], List[ForwardNodeData]]:
    """兼容入口：概览 + 一段正文 → 转发组件与需普通发送的节点。"""
    config = config or {}
    name, uin, limit = _record_options(config)
    records: List[Comp.Nodes] = []
    leftovers: List[ForwardNodeData] = []

    overview_nodes = sanitize_nodes([overview]) if overview is not None else []
    if overview_nodes and forward_overview:
        for record in plan_records(overview_nodes, limit):
            records.append(_record_component(record, name, uin))
    else:
        leftovers.extend(overview_nodes)

    body_roots = sanitize_nodes(list(body))
    if body_roots and forward_body:
        for record in plan_records(body_roots, limit):
            records.append(_record_component(record, name, uin))
    else:
        leftovers.extend(body_roots)

    return records, leftovers


def build_records(
    nodes: Sequence[ForwardNodeData],
    config: Optional[Dict[str, Any]] = None,
) -> List[Comp.Nodes]:
    """把一组节点转成一条或多条合并转发记录。"""
    name, uin, limit = _record_options(config or {})
    roots = sanitize_nodes(list(nodes))
    if not roots:
        return []
    return [
        _record_component(record, name, uin)
        for record in plan_records(roots, limit)
    ]


def flatten_to_plain_records(
    roots: Sequence[ForwardNodeData],
    number_prefix: bool = True,
    start_number: int = 1,
    prefix: Tuple[int, ...] = (),
) -> List[List[Any]]:
    """非 OneBot 平台降级：前序遍历，段落与图片各自单独成条消息。

    ``prefix`` 用于把内容编号挂在标题编号下（标题 3 → 内容 3.1、3.2…）。
    """
    messages: List[List[Any]] = []
    for kind, payload, path in iter_messages(
        roots, path=prefix, start_number=start_number
    ):
        if kind == "image":
            try:
                messages.append([Comp.Image.fromBytes(bytes(payload))])
            except Exception as exc:
                logger.warning(f"文本降级构造图片失败: {exc}")
            continue
        text = str(payload)
        if not text:
            continue
        prefix = f"{path} " if number_prefix and path and not text.startswith(path) else ""
        for chunk in _split_text(text, MAX_TEXT_MESSAGE_CHARS):
            messages.append([Comp.Plain(prefix + chunk)])
            prefix = ""
    return messages


def iter_messages(
    roots: Sequence[ForwardNodeData],
    path: Tuple[int, ...] = (),
    start_number: int = 1,
) -> Iterator[Tuple[str, Any, str]]:
    """前序遍历转发树，产出 ``(kind, payload, 编号)``。"""
    for offset, node in enumerate(roots):
        index = start_number + offset
        current = path + (index,)
        label = ".".join(str(part) for part in current)
        for kind, value in node.blocks:
            if value:
                yield (kind, value, label)
        yield from iter_messages(node.children, current)


def heading_components(part: BodyPart) -> List[Any]:
    """标题单独作为一条普通消息（写在聊天记录外）。"""
    return [Comp.Plain(chunk) for chunk in _split_text(part.heading)]


def part_plain_messages(
    part: BodyPart,
    number_prefix: bool = True,
    start_number: int = 1,
) -> List[List[Any]]:
    """非 OneBot 平台：标题 + 该标题下的每个段落 / 图片各成一条消息。"""
    messages: List[List[Any]] = [heading_components(part)]
    messages.extend(
        flatten_to_plain_records(
            part.nodes, number_prefix=number_prefix, start_number=start_number
        )
    )
    return messages
