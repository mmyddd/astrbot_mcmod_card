import aiohttp
import asyncio
from .data_parse import ModInfoParser


async def fetch_html(session, url, timeout=10):
    """
    异步获取网页的HTML内容
    :param session: aiohttp.ClientSession对象
    :param url: 要爬取的网页URL
    :param timeout: 超时时间(秒)
    :return: 网页HTML内容或None
    """
    try:
        # 设置请求头，模拟浏览器
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5"
        }

        # 发送GET请求
        async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout)
        ) as response:
            # 检查响应状态码，200表示成功
            if response.status == 200:
                # 返回HTML文本
                return await response.text()
            else:
                print(f"请求 {url} 失败，状态码: {response.status}")
                return None

    except Exception as e:
        print(f"爬取 {url} 时发生错误: {str(e)}")
        return None


async def gather_data(url):
    # 创建会话对象
    async with aiohttp.ClientSession() as session:
        html = await fetch_html(session, url)
        mod_info_parser = ModInfoParser(html_content=html)
        info_ = await mod_info_parser.gather_info()
        print(info_)
        return info_



if __name__ == "__main__":
    # 运行异步主函数
    asyncio.run(gather_data('https://www.mcmod.cn/class/1796.html'))
