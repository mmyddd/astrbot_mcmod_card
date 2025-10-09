from bs4 import BeautifulSoup
import re
from typing import Dict, List, Optional


class ModInfoParser:
    """模组信息解析器"""
    
    def __init__(self, html_content: str):
        """
        初始化解析器
        :param html_content: HTML内容字符串
        """
        self.soup = BeautifulSoup(html_content, 'html.parser')
    
