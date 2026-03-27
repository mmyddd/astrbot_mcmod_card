import aiohttp
import asyncio
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any

from astrbot.api import logger

from .data_parse import ModInfoParser, ModpackInfoParser

async def fetch_html(session, url, timeout=10):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status == 200:
                return await resp.text()
            else:
                logger.warning(f"请求 {url} 失败，状态码: {resp.status}")
                return None
    except Exception as e:
        logger.error(f"爬取 {url} 时发生错误: {str(e)}")
        return None

def get_cache_path(cache_dir: Path, url: str) -> Path:
    """生成缓存文件路径"""
    import hashlib
    url_hash = hashlib.md5(url.encode()).hexdigest()
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{url_hash}.json"

def read_cache(cache_dir: Path, url: str, ttl: int) -> Optional[Dict[str, Any]]:
    """读取缓存，如果存在且未过期则返回数据"""
    if ttl <= 0:
        return None
    cache_file = get_cache_path(cache_dir, url)
    if not cache_file.exists():
        return None
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - data.get("timestamp", 0) < ttl:
            return data.get("content")
    except Exception as e:
        logger.warning(f"读取缓存失败: {e}")
    return None

def write_cache(cache_dir: Path, url: str, content: Dict[str, Any]):
    """写入缓存"""
    try:
        cache_file = get_cache_path(cache_dir, url)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({"timestamp": time.time(), "content": content}, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"写入缓存失败: {e}")

async def gather_data(url: str, content_type: str, cache_ttl: int = 86400, cache_dir: Path = None) -> Optional[Dict[str, Any]]:
    """
    根据 content_type 获取并解析数据，支持缓存
    :param url: 目标网址
    :param content_type: "class" 或 "modpack"
    :param cache_ttl: 缓存有效期（秒），0 表示禁用缓存
    :param cache_dir: 缓存目录，若为 None 则不使用缓存
    """
    if cache_dir is not None and cache_ttl > 0:
        cached = read_cache(cache_dir, url, cache_ttl)
        if cached:
            logger.debug(f"使用缓存数据: {url}")
            return cached

    async with aiohttp.ClientSession() as session:
        html = await fetch_html(session, url)
        if not html:
            return None

        # 根据类型选择解析器
        if content_type == "class":
            parser = ModInfoParser(html)
        elif content_type == "modpack":
            parser = ModpackInfoParser(html)
        else:
            logger.error(f"未知的内容类型: {content_type}")
            return None

        info = await parser.gather_info()
        if info and cache_dir is not None and cache_ttl > 0:
            write_cache(cache_dir, url, info)
        return info