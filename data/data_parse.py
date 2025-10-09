from bs4 import BeautifulSoup
import re


class ModInfoParser:
    """模组信息解析器"""
    
    def __init__(self, html_content: str):
        """
        初始化解析器
        :param html_content: HTML内容字符串
        """
        self.soup = BeautifulSoup(html_content, 'html.parser')

    async def gather_info(self):
        res = {}
        res.update(self.get_title())
        res.update(self.get_tag())
        # 弃用
        # res.update(self.get_categories())
        res.update(self.get_votes())
        res.update(self.get_view_count())
        res.update(self.get_mc_versions())
        res.update(self.get_modpack_count())
        res.update(self.get_authors())
        res.update(self.get_rating())
        res.update(self.get_img_url())
        return res

    def get_title(self) -> dict[str, str]:
        """
        解析模组标题信息，包括状态和名称
        :return: 包含状态和名称信息的字典
        """
        res = {
            'status': '',
            'name': {
            }
        }
        
        # 查找标题容器
        title_div = self.soup.select_one('div.class-title')
        if not title_div:
            return res
        
        # 解析状态信息
        status_elements = title_div.select('div.class-official-group div')
        statue=''
        for element in status_elements:
            status_text = element.get_text(strip=True)
            if status_text:
                statue = statue +status_text+' '
        statue = statue.strip(' ')
        res['status']=statue
        
        # 解析名称信息
        # 短名称
        short_name = title_div.select_one('span.short-name')
        if short_name:
            res['name']['short-name']=short_name.get_text(strip=True)
        
        # 中文名称
        chinese_name = title_div.select_one('h3')
        if chinese_name:
            res['name']['chinese-name']=chinese_name.get_text(strip=True)
        
        # 英文名称
        english_name = title_div.select_one('h4')
        if english_name:
            res['name']['english-name']=english_name.get_text(strip=True)
        return res

    def get_tag(self) -> dict[str, list[str]]:
        """
        解析模组标签信息
        :return: 包含标签信息的字典
        """
        res = {
            'tags': []
        }
        
        # 查找标签容器
        tag_container = self.soup.select_one('li.col-lg-12.tag')
        if not tag_container:
            return res
        
        # 解析标签
        tag_links = tag_container.select('ul li a')
        tags = []
        for link in tag_links:
            tag_text = link.get_text(strip=True)
            if tag_text:
                tags.append(tag_text)
        
        # 返回标签列表
        res['tags'] = tags
        return res

    def get_categories(self) -> dict[str, list[str]]:
        """
        解析模组分类标签信息
        :return: 包含分类信息的字典
        """
        res = {
            'categories': []
        }
        
        # 查找分类容器
        category_container = self.soup.select_one('div.common-class-category')
        if not category_container:
            return res
        
        # 解析分类标签
        category_links = category_container.select('ul li a')
        categories = []
        for link in category_links:
            category_text = link.get_text(strip=True)
            if category_text:
                categories.append(category_text)
        
        # 返回分类列表
        res['categories'] = categories
        return res

    def get_votes(self) -> dict[str, dict[str, str]]:
        """
        解析红黑票投票信息，提取票数和百分比
        :return: 包含投票信息的字典
        """
        res = {
            'votes': {
                'red_count': '',
                'red_percentage': '',
                'black_count': '',
                'black_percentage': ''
            }
        }
        
        # 查找投票容器
        vote_container = self.soup.select_one('div.text-block')
        if not vote_container:
            return res
        
        # 解析所有span元素中的投票信息
        vote_spans = vote_container.select('span')
        for span in vote_spans:
            vote_text = span.get_text(strip=True)
            
            # 解析红票信息
            if '红票' in vote_text:
                # 使用正则表达式提取数字和百分比
                red_match = re.search(r'红票(\d+)\s*\((\d+%)\)', vote_text)
                if red_match:
                    res['votes']['red_count'] = red_match.group(1)
                    res['votes']['red_percentage'] = red_match.group(2)
            
            # 解析黑票信息
            elif '黑票' in vote_text:
                # 使用正则表达式提取数字和百分比
                black_match = re.search(r'黑票(\d+)\s*\((\d+%)\)', vote_text)
                if black_match:
                    res['votes']['black_count'] = black_match.group(1)
                    res['votes']['black_percentage'] = black_match.group(2)
        
        return res

    def get_view_count(self) -> dict[str, str]:
        """
        解析总浏览量信息
        :return: 包含浏览量信息的字典
        """
        res = {
            'view_count': ''
        }
        
        # 查找浏览量容器
        view_container = self.soup.select_one('div.span[title]')
        if not view_container:
            return res
        
        # 查找包含"总浏览"文本的元素
        view_elements = self.soup.select('div.span')
        for element in view_elements:
            # 检查是否包含"总浏览"文本
            if element.select_one('p.t') and '总浏览' in element.select_one('p.t').get_text(strip=True):
                # 获取浏览量数值
                count_element = element.select_one('p.n')
                if count_element:
                    res['view_count'] = count_element.get_text(strip=True)
                    break
        
        return res

    def get_mc_versions(self) -> dict[str, dict[str, list[str]]]:
        """
        解析支持的MC版本信息，按加载器分组
        :return: 包含MC版本信息的字典
        """
        res = {
            'mc_versions': {}
        }
        
        # 查找MC版本容器
        mcver_container = self.soup.select_one('li.col-lg-12.mcver')
        if not mcver_container:
            return res
        
        # 解析所有ul元素
        ul_elements = mcver_container.select('ul')
        
        for ul in ul_elements:
            # 查找加载器名称（如"NeoForge:"、"Forge:"）
            loader_name = None
            versions = []
            
            for li in ul.select('li'):
                li_text = li.get_text(strip=True)
                
                # 检查是否是加载器名称（以冒号结尾且不是版本号）
                if li_text.endswith(':'):
                    # 去掉冒号作为加载器名称
                    potential_loader = li_text[:-1]
                    # 如果这个文本不是版本号格式（如1.21.1），则认为是加载器名称
                    if not re.match(r'^\d+\.\d+(\.\d+)?$', potential_loader):
                        loader_name = potential_loader
                # 检查是否是版本号链接
                elif li.select_one('a') and 'mcver=' in li.select_one('a').get('href', ''):
                    version_link = li.select_one('a')
                    version_text = version_link.get_text(strip=True)
                    if version_text:
                        versions.append(version_text)
            
            # 如果找到了加载器和版本，添加到结果中
            if loader_name and versions:
                res['mc_versions'][loader_name] = versions
        
        return res

    def get_modpack_count(self) -> dict[str, str]:
        """
        解析整合包使用数量信息
        :return: 包含整合包数量信息的字典
        """
        res = {
            'modpack_count': ''
        }
        
        # 查找整合包信息容器
        modpack_container = self.soup.select_one('li.col-lg-12.infolist.modpack')
        if not modpack_container:
            return res
        
        # 获取容器内的文本内容
        container_text = modpack_container.get_text(strip=True)
        
        # 使用正则表达式提取数量
        # 匹配模式：有 X 个已收录的整合包使用了
        count_match = re.search(r'有\s*(\d+)\s*个已收录的整合包使用了', container_text)
        if count_match:
            res['modpack_count'] = count_match.group(1)
        
        return res

    def get_authors(self) -> dict[str, list[str]]:
        """
        解析所有作者的名字信息
        :return: 包含作者名字列表的字典
        """
        res = {
            'authors': []
        }
        
        # 查找作者信息容器
        author_container = self.soup.select_one('li.col-lg-12.author')
        if not author_container:
            return res
        
        # 查找所有作者成员
        member_elements = author_container.select('li span.member span.name a')
        
        for member in member_elements:
            author_name = member.get_text(strip=True)
            if author_name:
                res['authors'].append(author_name)
        
        return res

    def get_rating(self) -> dict[str, int]:
        res = {
            'fun': 0,
            'difficulty': 0,
            'stability': 0,
            'practicality': 0,
            'aesthetics': 0,
            'balance': 0,
            'compatibility': 0,
            'durability': 0
        }

        # 中文到英文键的映射关系（以中文含义为准进行精准翻译）
        cn_to_en = {
            '趣味': 'fun',
            '难度': 'difficulty',
            '稳定': 'stability',
            '实用': 'practicality',
            '美观': 'aesthetics',
            '平衡': 'balance',
            '兼容': 'compatibility',
            '持久': 'durability'
        }

        # 先找到外层评分块
        rating_block = self.soup.select_one('div.class-rating-block')
        if not rating_block:
            return res

        # 在评分块中找到包含评分数据的具体元素
        rating_div = rating_block.find('div', id='class-rating')
        if not rating_div:
            return res

        # 提取并解码评分字符串
        title_str = rating_div.get('data-original-title', '')
        if not title_str:
            return res

        # 处理HTML实体编码
        import html
        decoded_str = html.unescape(title_str)

        # 按<br/>分割评分项
        rating_items = decoded_str.split('<br/>')

        # 解析每个评分项
        import re
        for item in rating_items:
            item = item.strip()
            if not item:
                continue

            # 分割键名和值
            if ':' in item:
                key_cn, value_str = item.split(':', 1)
                key_cn = key_cn.strip()
                value_str = value_str.strip()

                # 提取数字部分
                num_match = re.search(r'\d+', value_str)
                if num_match and key_cn in cn_to_en:
                    res[cn_to_en[key_cn]] = int(num_match.group())

        return res

    def get_img_url(self):
        res={
            'img-url':''
        }
        # 定位包含图片的div容器
        cover_div = self.soup.select_one('div.class-cover-image')
        if not cover_div:
            return ""

        # 从div中找到img标签
        img_tag = cover_div.find('img')
        if not img_tag:
            return ""

        # 提取图片链接（src属性）
        img_url = img_tag.get('src', '')

        # 处理可能的相对路径，补充协议头（如果需要）
        if img_url.startswith('//'):
            img_url = f'https:{img_url}'  # 或 'http:' 取决于网站支持
        res['img-url'] = img_url
        return res
