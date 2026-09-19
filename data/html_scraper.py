# -*- coding: utf-8 -*-
"""mcmod 页面抓取与缓存（缓存结构带 schema 版本，结构升级自动失效）。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
from bs4 import BeautifulSoup

from astrbot.api import logger

from .body_parser import BodyParser
from .meta_parser import MetaParser
from .models import SCHEMA_VERSION, Meta, Section

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

IMAGE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Referer": "https://www.mcmod.cn/",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}

FETCH_TIMEOUT = 20
IMAGE_TIMEOUT = 10
MAX_IMAGE_BYTES = 12 * 1024 * 1024


def _md5(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def cache_path(cache_dir: Path, url: str) -> Path:
    return cache_dir / f"{_md5(url)}.json"


def read_cache(cache_dir: Optional[Path], url: str, ttl: int) -> Optional[Dict[str, Any]]:
    """读取缓存；schema 不匹配或已过期都视为未命中。"""
    if cache_dir is None or ttl <= 0:
        return None
    path = cache_path(cache_dir, url)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        logger.warning(f"读取缓存失败 {url}: {exc}")
        return None

    if payload.get("schema") != SCHEMA_VERSION:
        logger.debug(f"缓存结构版本不匹配，忽略旧缓存: {url}")
        return None
    if time.time() - float(payload.get("timestamp", 0) or 0) >= ttl:
        return None
    content = payload.get("content")
    return content if isinstance(content, dict) else None


def write_cache(cache_dir: Optional[Path], url: str, content: Dict[str, Any]) -> None:
    if cache_dir is None:
        return
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": SCHEMA_VERSION,
            "timestamp": time.time(),
            "url": url,
            "content": content,
        }
        tmp_path = cache_path(cache_dir, url).with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        tmp_path.replace(cache_path(cache_dir, url))
    except Exception as exc:
        logger.warning(f"写入缓存失败 {url}: {exc}")


async def fetch_html(session: aiohttp.ClientSession, url: str, timeout: int = FETCH_TIMEOUT) -> Optional[str]:
    """抓取页面 HTML，失败返回 None。"""
    try:
        async with session.get(
            url,
            headers=DEFAULT_HEADERS,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            if resp.status != 200:
                logger.warning(f"请求 {url} 失败，状态码: {resp.status}")
                return None
            raw = await resp.read()
            encoding = resp.charset or "utf-8"
            if encoding.lower() in ("iso-8859-1", "ascii"):
                encoding = "utf-8"
            return raw.decode(encoding, errors="replace")
    except Exception as exc:
        logger.error(f"抓取 {url} 时发生错误: {exc}")
        return None


async def fetch_bytes(
    session: aiohttp.ClientSession,
    url: str,
    timeout: int = IMAGE_TIMEOUT,
) -> Optional[bytes]:
    """下载图片等二进制资源，失败返回 None。"""
    if not url:
        return None
    try:
        async with session.get(
            url,
            headers=IMAGE_HEADERS,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            if resp.status != 200:
                logger.warning(f"下载图片 {url} 失败，状态码: {resp.status}")
                return None
            data = await resp.read()
            if len(data) > MAX_IMAGE_BYTES:
                logger.warning(f"图片过大，已跳过: {url} ({len(data)} bytes)")
                return None
            return data or None
    except Exception as exc:
        logger.warning(f"下载图片 {url} 失败: {exc}")
        return None


def parse_page(
    html_text: str,
    url: str,
    content_type: str,
) -> Optional[Dict[str, Any]]:
    """把 HTML 解析为 ``{"meta": ..., "sections": ...}``。"""
    try:
        soup = BeautifulSoup(html_text, "lxml")
    except Exception as exc:
        logger.error(f"解析 HTML 失败 {url}: {exc}")
        return None

    meta = MetaParser(soup, url=url, content_type=content_type).parse()
    sections = BodyParser(soup).parse()
    if not meta.chinese_name and not meta.english_name and not sections:
        logger.warning(f"页面解析结果为空: {url}")
        return None
    return {
        "schema": SCHEMA_VERSION,
        "meta": meta.to_dict(),
        "sections": [section.to_dict() for section in sections],
    }


def load_page_data(payload: Dict[str, Any]) -> Dict[str, Any]:
    """把缓存/解析结果还原为 Meta + Section 对象。"""
    meta = Meta.from_dict(payload.get("meta"))
    sections = [
        Section.from_dict(item) for item in (payload.get("sections") or [])
    ]
    return {"meta": meta, "sections": sections}


async def gather_data(
    url: str,
    content_type: str = "class",
    cache_ttl: int = 86400,
    cache_dir: Optional[Path] = None,
    session: Optional[aiohttp.ClientSession] = None,
) -> Optional[Dict[str, Any]]:
    """抓取并解析页面，返回 ``{"meta": Meta, "sections": [Section]}``。"""
    cached = read_cache(cache_dir, url, cache_ttl)
    if cached:
        logger.debug(f"使用缓存数据: {url}")
        data = load_page_data(cached)
        if data["meta"].url == "":
            data["meta"].url = url
        return data

    owns_session = session is None
    if owns_session:
        session = aiohttp.ClientSession()
    try:
        html_text = await fetch_html(session, url)
    finally:
        if owns_session:
            await session.close()

    if not html_text:
        return None

    payload = parse_page(html_text, url, content_type)
    if payload is None:
        return None

    if cache_dir is not None and cache_ttl > 0:
        write_cache(cache_dir, url, payload)

    data = load_page_data(payload)
    if data["meta"].url == "":
        data["meta"].url = url
    return data


async def fetch_many_bytes(
    urls: List[str],
    concurrency: int = 4,
    timeout: int = IMAGE_TIMEOUT,
) -> Dict[str, Optional[bytes]]:
    """并发下载多张图片，返回 url -> bytes（失败为 None）。"""
    results: Dict[str, Optional[bytes]] = {}
    pending = [url for url in dict.fromkeys(urls) if url]
    if not pending:
        return results

    semaphore = asyncio.Semaphore(max(1, concurrency))
    async with aiohttp.ClientSession() as session:
        async def worker(target: str) -> None:
            async with semaphore:
                results[target] = await fetch_bytes(session, target, timeout=timeout)

        await asyncio.gather(*(worker(target) for target in pending), return_exceptions=True)
    return results
