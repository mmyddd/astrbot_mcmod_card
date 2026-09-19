# -*- coding: utf-8 -*-
"""MC百科卡片插件：链接 → 合并转发（概览 / 正文分段 / 逐图）发送。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .data.html_scraper import fetch_many_bytes, gather_data
from .data.models import Meta, Section
from .img.render_cover import render_cover
from .img.render_radar import render_radar
from .render.forward import (
    _split_text,
    build_records,
    flatten_to_plain_records,
    heading_components,
)
from .render.tree import (
    BodyPart,
    ForwardNodeData,
    ForwardTreeBuilder,
    build_record_nodes,
    sanitize_nodes,
)

MCMOD_PATTERN = r"https://www\.mcmod\.cn/(class|modpack)/(\d+)\.html"

#: 支持合并转发（OneBot v11）的平台
FORWARD_PLATFORMS = ("aiocqhttp",)

#: 图片并发下载数
IMAGE_CONCURRENCY = 4

FAIL_MESSAGE = "检测到 MC 百科链接，但生成卡片失败，请查看日志"


@register("mcmod_card", "QiChen", "MC百科卡片解析（合并转发·分段正文）", "3.0.0")
class McmodCardPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.plugin_name = self.name
        self._init_data_dir()
        self._init_font_path()

    # ---------------------------------------------------------------- 初始化
    def _init_data_dir(self) -> None:
        base = Path(get_astrbot_data_path()) / "plugin_data" / self.plugin_name
        self.data_dir = base
        self.cache_dir = base / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _init_font_path(self) -> None:
        """字体优先取配置，其次取插件目录下的 resource/msyh.ttf。"""
        candidates: List[Path] = []
        configured = str(self.config.get("font_path") or "").strip()
        if configured:
            candidates.append(Path(configured))
        candidates.append(Path(__file__).resolve().parent / "resource" / "msyh.ttf")
        for candidate in candidates:
            if candidate.exists():
                self.font_path: Optional[str] = str(candidate)
                logger.info(f"使用字体: {self.font_path}")
                return
        self.font_path = None
        logger.warning("未找到可用中文字体，雷达图文字可能显示为方块")

    # ------------------------------------------------------------------ 配置
    def _bool(self, key: str, default: bool) -> bool:
        value = self.config.get(key, default)
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on", "是")
        return bool(value)

    def _int(self, key: str, default: int, minimum: int = 0, maximum: int = 10 ** 6) -> int:
        try:
            value = int(self.config.get(key, default))
        except (TypeError, ValueError):
            return default
        return max(minimum, min(maximum, value))

    def _tree_config(self) -> Dict[str, Any]:
        return {
            "node_name": str(self.config.get("node_name") or "MC百科"),
            "node_uin": str(self.config.get("node_uin") or "10000"),
            "overview_split": self._bool("overview_split", True),
            "include_cover": self._bool("include_cover", True),
            "include_radar": self._bool("include_radar", True),
            "include_images": self._bool("include_images", True),
            "max_images": self._int("max_images", 40, 0, 100),
            "max_nodes_per_message": self._int("max_nodes_per_message", 40, 1, 40),
        }

    # ------------------------------------------------------------------ 构建
    async def _attach_images(
        self,
        builder: ForwardTreeBuilder,
        meta: Meta,
        sections: Sequence[Section],
    ) -> None:
        """下载封面与画廊图片；封面额外裁切成缩略图。"""
        urls = builder.wanted_image_urls(meta, sections)
        if not urls:
            return
        try:
            raw = await fetch_many_bytes(urls, concurrency=IMAGE_CONCURRENCY)
        except Exception as exc:
            logger.warning(f"批量下载图片失败: {exc}")
            return

        for url in urls:
            payload = raw.get(url)
            if not payload:
                logger.warning(f"图片不可用，已跳过: {url}")
                continue
            if meta.cover_url and url == meta.cover_url:
                thumbnail = render_cover(payload)
                if thumbnail:
                    builder.image_data[url] = thumbnail
                continue
            builder.image_data[url] = payload

    def _render_radar(self, meta: Meta) -> Optional[bytes]:
        try:
            return render_radar(meta.rating or {}, font_path=self.font_path)
        except Exception as exc:
            logger.warning(f"生成雷达图失败: {exc}")
            return None

    async def _build_payload(self, data: Dict[str, Any]) -> Tuple[ForwardTreeBuilder, Optional[ForwardNodeData], List[BodyPart]]:
        meta: Meta = data["meta"]
        sections: Sequence[Section] = data.get("sections") or []
        builder = ForwardTreeBuilder(self._tree_config())
        await self._attach_images(builder, meta, sections)

        cover = builder.image_data.get(meta.cover_url) if meta.cover_url else None
        radar = self._render_radar(meta) if builder.include_radar else None
        overview = builder.build_overview(meta, cover=cover, radar=radar)
        parts = builder.build_body_parts(sections)
        return builder, overview, parts

    # ------------------------------------------------------------------ 发送
    def _supports_forward(self, event: AstrMessageEvent) -> bool:
        try:
            return event.get_platform_name() in FORWARD_PLATFORMS
        except Exception as exc:
            logger.debug(f"读取平台名称失败，按不支持合并转发处理: {exc}")
            return False

    async def _send(
        self,
        event: AstrMessageEvent,
        overview: Optional[ForwardNodeData],
        parts: Sequence[BodyPart],
    ):
        """把概览与正文**打包进同一条合并转发记录**发送，避免刷屏。

        记录内结构（深度恒为「记录 → 标题 → 内容」）::

            [1.1 概览：封面 + 名称]
            [1.2 数据 + 雷达图]
            [1.3 标签与作者]
            [1. 写在开头]
              └─ 段落 / 列表项 / 图片
            [1.1. 版本注意事项]
              └─ …

        平台不支持合并转发（或关闭了合并转发）时，退回逐条普通消息。
        """
        supports_forward = self._supports_forward(event)
        config = self._tree_config()
        nodes = build_record_nodes(overview, parts)
        if not nodes:
            yield event.plain_result("检测到 MC 百科链接，但没有解析到可发送的内容")
            return

        if supports_forward:
            records = build_records(nodes, config=config)
            if records:
                for record in records:
                    yield event.chain_result([record])
                return

        # 降级：标题单独成条，内容按编号逐条发送
        number_prefix = self._bool("number_prefix", True)
        if overview is not None:
            overview_nodes = sanitize_nodes([overview])
            for components in flatten_to_plain_records(
                overview_nodes, number_prefix=number_prefix
            ):
                yield event.chain_result(components)

        for index, part in enumerate(parts, start=1):
            for components in _wrap_plain(heading_components(part)):
                yield event.chain_result(components)
            content = sanitize_nodes(part.nodes)
            if not content:
                continue
            for components in flatten_to_plain_records(
                content, number_prefix=number_prefix, prefix=(index,)
            ):
                yield event.chain_result(components)


    # ------------------------------------------------------------------ 入口
    @filter.regex(MCMOD_PATTERN)
    async def send_mod_card(self, event: AstrMessageEvent):
        match = re.search(MCMOD_PATTERN, event.message_str)
        if not match:
            return
        full_url = match.group(0)
        content_type = match.group(1)

        try:
            data = await gather_data(
                url=full_url,
                content_type=content_type,
                cache_ttl=self._int("cache_ttl", 86400, 0),
                cache_dir=self.cache_dir,
            )
        except Exception as exc:
            logger.error(f"解析 {full_url} 失败: {exc}", exc_info=True)
            data = None

        if not data:
            yield event.plain_result(FAIL_MESSAGE)
            return

        try:
            builder, overview, parts = await self._build_payload(data)
        except Exception as exc:
            logger.error(f"构建转发内容失败: {exc}", exc_info=True)
            yield event.plain_result(FAIL_MESSAGE)
            return

        supports_forward = self._supports_forward(event)
        if not supports_forward and not self._bool("fallback_to_text", True):
            yield event.plain_result(self._plain_summary(overview, parts))
            event.stop_event()
            return

        async for result in self._send(event, overview, parts):
            yield result
        event.stop_event()

    def _plain_summary(self, overview: Optional[ForwardNodeData], parts: Sequence[BodyPart]) -> str:
        """既不支持合并转发、又关闭降级时的兜底：只发一段概要。"""
        lines: List[str] = []
        if overview is not None and overview.text():
            lines.append(overview.text())
        for part in parts:
            lines.append(part.heading)
            text = part.text()
            if text:
                lines.append(text)
        content = "\n".join(line for line in lines if line)
        if not content:
            return "当前平台不支持合并转发，请在 QQ（OneBot v11）中使用本插件"
        return content

    async def terminate(self) -> None:
        logger.info(f"插件 {self.plugin_name} 已卸载")


def _wrap_plain(components: Sequence[Any]) -> List[List[Comp.Plain]]:
    """把一串组件按长度上限切成多条普通消息（无内容时返回空列表）。"""
    messages: List[List[Comp.Plain]] = []
    for component in components:
        text = getattr(component, "text", "")
        if not text:
            continue
        for chunk in _split_text(text):
            messages.append([Comp.Plain(chunk)])
    return messages
