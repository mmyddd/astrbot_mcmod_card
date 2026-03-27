import re
import json
from pathlib import Path

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api import AstrBotConfig
import astrbot.core.message.components as Comp
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .data.html_scraper import gather_data
from .img.draw_img import generate_mod_cards

MCMOD_PATTERN = r"https://www\.mcmod\.cn/(class|modpack)/(\d+)\.html"


@register("mcmod_card", "QiChen", "MC百科卡片解析 (支持模组+整合包)", "2.0.0")
class McmodCardPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.plugin_name = self.name
        self._init_data_dir()
        self._init_font_paths()

    def _init_data_dir(self):
        base = Path(get_astrbot_data_path()) / "plugin_data" / self.plugin_name
        self.data_dir = base
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _init_font_paths(self):
        """处理字体路径，若配置为空或无效则自动查找"""
        font_path = self.config.get("font_path")
        # 如果配置了路径，先检查是否存在
        if font_path:
            p = Path(font_path)
            if p.exists():
                logger.info(f"使用配置的字体: {font_path}")
                if not self.config.get("font_bold_path"):
                    self.config["font_bold_path"] = font_path
                return
            else:
                logger.warning(f"配置的字体文件不存在: {font_path}，将尝试自动查找")

        # 自动查找字体
        base_dir = Path(__file__).resolve().parent.parent.parent  # AstrBot 根目录
        candidates = [
            base_dir / "resource" / "msyh.ttf",
            base_dir / "resource" / "simhei.ttf",
            base_dir / "resource" / "simsun.ttc",
        ]
        # 若用户之前配置了路径但无效，也尝试在其目录下查找同名文件
        if font_path:
            parent = Path(font_path).parent
            candidates.insert(0, parent / "msyh.ttf")
            candidates.insert(0, parent / "simhei.ttf")

        for f in candidates:
            if f.exists():
                self.config["font_path"] = str(f)
                if not self.config.get("font_bold_path"):
                    self.config["font_bold_path"] = str(f)
                logger.info(f"自动选用字体: {f}")
                return

        # 仍未找到
        self.config["font_path"] = ""
        self.config["font_bold_path"] = ""
        logger.warning("未找到任何中文字体，卡片文字将使用默认字体（可能无法显示中文）")

    async def parse_mcmod(self, event: AstrMessageEvent, url: str, content_type: str):
        """根据 content_type 爬取数据并生成卡片图片"""
        try:
            data = await gather_data(
                url=url,
                content_type=content_type,
                cache_ttl=self.config.get("cache_ttl", 86400),
                cache_dir=self.data_dir / "cache"
            )
            if not data:
                logger.warning(f"解析 {url} 失败，返回空数据")
                return None
            data_list = [data]
            img_base64 = generate_mod_cards(data_list, config=self.config)
            return img_base64
        except Exception as e:
            logger.error(f"处理 {url} 时发生错误: {e}", exc_info=True)
            return None

    @filter.regex(MCMOD_PATTERN)
    async def send_mod_img(self, event: AstrMessageEvent):
        msg = event.message_str
        match = re.search(MCMOD_PATTERN, msg)
        if not match:
            return
        full_url = match.group(0)
        content_type = match.group(1)  # "class" 或 "modpack"
        img_base64 = await self.parse_mcmod(event, full_url, content_type)
        if img_base64:
            yield event.chain_result([Comp.Image.fromBase64(img_base64)])
            # 已成功处理，阻止其他插件继续处理此消息
            event.stop_event()
        else:
            yield event.plain_result("检测到 MC 百科链接，但生成卡片失败，请查看日志")

    async def terminate(self):
        """插件卸载时执行清理（此处无特殊清理任务）"""
        logger.info(f"插件 {self.plugin_name} 已卸载")