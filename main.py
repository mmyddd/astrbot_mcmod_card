import re
import json

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.core.message.components as Comp


from .data.html_scraper import gather_data
from .img.draw_img import generate_mod_cards


MCMOD_MOD_PATTERN=r"https://www\.mcmod\.cn/class/(\d+)\.html"

@register("helloworld", "YourName", "一个简单的 Hello World 插件", "1.0.0")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        
    async def parse_mcmod(self,event: AstrMessageEvent,url):
        data = await gather_data(url)
        if data is None:
            raise Exception
        data_list=[]
        data_list.append(data)
        img_base64 = generate_mod_cards(data_list)
        return img_base64

    # 监测所有mcmod链接
    @filter.regex(MCMOD_MOD_PATTERN)
    async def send_mod_img(self, event: AstrMessageEvent):
        msg = event.message_str
        match = re.search(MCMOD_MOD_PATTERN, msg)
        mod_url = match.group(0)
        img_base64 = await self.parse_mcmod(event,mod_url)
        if img_base64 is not None:
            yield event.chain_result([Comp.Image.fromBase64(img_base64)])
        else:
            yield event.plain_result("检测到mcmod链接但解析失败,请查看日志")
