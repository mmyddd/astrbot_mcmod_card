from bs4 import BeautifulSoup
import re
import html

class BaseParser:
    """解析器基类，定义通用方法"""
    def __init__(self, html_content: str):
        self.soup = BeautifulSoup(html_content, 'lxml')

    async def gather_info(self):
        raise NotImplementedError


class ModInfoParser(BaseParser):
    """模组信息解析器（适用于 /class/ 页面）"""
    async def gather_info(self):
        res = {}
        res.update(self.get_title())
        res.update(self.get_tag())
        res.update(self.get_votes())
        res.update(self.get_view_count())
        res.update(self.get_mc_versions())
        res.update(self.get_modpack_count())
        res.update(self.get_authors())
        res.update(self.get_rating())
        res.update(self.get_img_url())
        res.update(self.get_description())
        res.update(self.get_heat_index())
        res.update(self.get_rating_score())
        logger.debug(f"解析结果: {res}")
        return res

    def get_title(self):
        res = {'status': '', 'name': {}}
        title_div = self.soup.select_one('div.class-title')
        if not title_div:
            return res

        status_elements = title_div.select('div.class-official-group div')
        status = ' '.join(el.get_text(strip=True) for el in status_elements if el.get_text(strip=True))
        res['status'] = status

        short_name = title_div.select_one('span.short-name')
        if short_name:
            res['name']['short-name'] = short_name.get_text(strip=True)

        chinese_name = title_div.select_one('h3')
        if chinese_name:
            res['name']['chinese-name'] = chinese_name.get_text(strip=True)

        english_name = title_div.select_one('h4')
        if english_name:
            res['name']['english-name'] = english_name.get_text(strip=True)

        return res

    def get_tag(self):
        res = {'tags': []}
        tag_container = self.soup.select_one('li.col-lg-12.tag')
        if tag_container:
            tags = [a.get_text(strip=True) for a in tag_container.select('ul li a') if a.get_text(strip=True)]
            res['tags'] = tags
        return res

    def get_votes(self):
        res = {
            'votes': {
                'red_count': '',
                'red_percentage': '',
                'black_count': '',
                'black_percentage': ''
            }
        }
        vote_container = self.soup.select_one('div.text-block')
        if vote_container:
            for span in vote_container.select('span'):
                text = span.get_text(strip=True)
                if '红票' in text:
                    m = re.search(r'红票(\d+)\s*\((\d+%)\)', text)
                    if m:
                        res['votes']['red_count'] = m.group(1)
                        res['votes']['red_percentage'] = m.group(2)
                elif '黑票' in text:
                    m = re.search(r'黑票(\d+)\s*\((\d+%)\)', text)
                    if m:
                        res['votes']['black_count'] = m.group(1)
                        res['votes']['black_percentage'] = m.group(2)
        return res

    def get_view_count(self):
        res = {'view_count': ''}
        for el in self.soup.select('div.span'):
            if el.select_one('p.t') and '总浏览' in el.select_one('p.t').get_text(strip=True):
                count_el = el.select_one('p.n')
                if count_el:
                    res['view_count'] = count_el.get_text(strip=True)
                break
        return res

    def get_mc_versions(self):
        res = {'mc_versions': {}}
        mcver_container = self.soup.select_one('li.col-lg-12.mcver')
        if not mcver_container:
            return res

        for ul in mcver_container.find_all('ul', recursive=False):
            loader = None
            versions = []
            for li in ul.find_all('li', recursive=False):
                text = li.get_text(strip=True)
                if text.endswith(':') and not re.match(r'^\d+\.\d+(\.\d+)?$', text[:-1]):
                    loader = text[:-1].strip()
                else:
                    a_tag = li.find('a')
                    if a_tag and 'mcver=' in a_tag.get('href', ''):
                        v = a_tag.get_text(strip=True)
                        if v:
                            versions.append(v)
            if loader and versions:
                res['mc_versions'][loader] = versions
        return res

    def get_modpack_count(self):
        res = {'modpack_count': ''}
        container = self.soup.select_one('li.col-lg-12.infolist.modpack')
        if container:
            m = re.search(r'有\s*(\d+)\s*个已收录的整合包使用了', container.get_text(strip=True))
            if m:
                res['modpack_count'] = m.group(1)
        return res

    def get_authors(self):
        res = {'authors': []}
        author_container = self.soup.select_one('li.col-lg-12.author')
        if author_container:
            names = [a.get_text(strip=True) for a in author_container.select('li span.member span.name a')]
            res['authors'] = names
        return res

    def get_rating(self):
        res = {
            'fun': 0, 'difficulty': 0, 'stability': 0, 'practicality': 0,
            'aesthetics': 0, 'balance': 0, 'compatibility': 0, 'durability': 0
        }
        cn_to_en = {
            '趣味': 'fun', '难度': 'difficulty', '稳定': 'stability', '实用': 'practicality',
            '美观': 'aesthetics', '平衡': 'balance', '兼容': 'compatibility', '持久': 'durability'
        }
        rating_block = self.soup.select_one('div.class-rating-block')
        if rating_block:
            rating_div = rating_block.find('div', id='class-rating')
            if rating_div and rating_div.get('data-original-title'):
                decoded = html.unescape(rating_div['data-original-title'])
                for item in decoded.split('<br/>'):
                    item = item.strip()
                    if ':' in item:
                        key_cn, val_str = item.split(':', 1)
                        key_cn = key_cn.strip()
                        if key_cn in cn_to_en:
                            m = re.search(r'\d+', val_str)
                            if m:
                                res[cn_to_en[key_cn]] = int(m.group())
        return res

    def get_img_url(self):
        res = {'img-url': ''}
        cover = self.soup.select_one('div.class-cover-image img')
        if cover and cover.get('src'):
            url = cover['src']
            if url.startswith('//'):
                url = 'https:' + url
            res['img-url'] = url
        return res

    def get_description(self):
        desc_div = self.soup.select_one('div.text-area.common-text')
        if desc_div:
            text = desc_div.get_text(separator=' ', strip=True)
            return {'description': text}
        return {'description': ''}

    def get_heat_index(self):
        heat_div = self.soup.select_one('div.block-right .text')
        if heat_div:
            text = heat_div.get_text(strip=True)
            match = re.search(r'昨日指数:\s*(\d+)', text)
            if match:
                return {'heat_index': match.group(1)}
        return {'heat_index': ''}

    def get_rating_score(self):
        score_div = self.soup.select_one('div.class-excount .star .block-left')
        if score_div:
            score = score_div.select_one('p.up')
            level = score_div.select_one('p.down')
            return {
                'rating_score': score.get_text(strip=True) if score else '',
                'rating_level': level.get_text(strip=True) if level else ''
            }
        return {'rating_score': '', 'rating_level': ''}


class ModpackInfoParser(BaseParser):
    """整合包信息解析器（适用于 /modpack/ 页面）"""
    async def gather_info(self):
        res = {}
        res.update(self.get_title())
        res.update(self.get_tag())
        res.update(self.get_votes())
        res.update(self.get_view_count())
        res.update(self.get_mc_versions())
        res.update(self.get_authors())
        res.update(self.get_img_url())
        res.update(self.get_description())
        # 整合包没有雷达图评分，设置默认值
        res.update({'modpack_count': '', 'votes': {'red_count': '0', 'red_percentage': '0%', 'black_count': '0', 'black_percentage': '0%'}})
        # 热度字段可能不存在
        res.update({'heat_index': '', 'rating_score': '', 'rating_level': ''})
        logger.debug(f"解析结果: {res}")
        return res

    def get_title(self):
        res = {'status': '', 'name': {}}
        title_div = self.soup.select_one('div.modpack-title') or self.soup.select_one('div.class-title')
        if title_div:
            name_elem = title_div.select_one('h1') or title_div.select_one('h3')
            if name_elem:
                res['name']['chinese-name'] = name_elem.get_text(strip=True)
            short = title_div.select_one('span.short-name')
            if short:
                res['name']['short-name'] = short.get_text(strip=True)
            status = title_div.select_one('div.modpack-status')
            if status:
                res['status'] = status.get_text(strip=True)
        return res

    def get_tag(self):
        res = {'tags': []}
        tag_area = self.soup.select_one('div.tag-list') or self.soup.select_one('li.col-lg-12.tag')
        if tag_area:
            tags = [a.get_text(strip=True) for a in tag_area.select('a') if a.get_text(strip=True)]
            res['tags'] = tags
        return res

    def get_votes(self):
        return ModInfoParser.get_votes(self)

    def get_view_count(self):
        res = {'view_count': ''}
        for el in self.soup.select('div.span'):
            if el.select_one('p.t') and '总浏览' in el.select_one('p.t').get_text(strip=True):
                count_el = el.select_one('p.n')
                if count_el:
                    res['view_count'] = count_el.get_text(strip=True)
                break
        return res

    def get_mc_versions(self):
        res = {'mc_versions': {}}
        version_area = self.soup.select_one('li.col-lg-12.mcver') or self.soup.select_one('div.modpack-versions')
        if version_area:
            versions = []
            for a in version_area.select('a'):
                text = a.get_text(strip=True)
                if re.match(r'^\d+\.\d+(\.\d+)?$', text):
                    versions.append(text)
            if versions:
                res['mc_versions']['Minecraft'] = versions
        return res

    def get_authors(self):
        res = {'authors': []}
        author_area = self.soup.select_one('li.col-lg-12.author') or self.soup.select_one('div.modpack-author')
        if author_area:
            names = [a.get_text(strip=True) for a in author_area.select('a')]
            if names:
                res['authors'] = names
        return res

    def get_img_url(self):
        res = {'img-url': ''}
        cover = self.soup.select_one('div.modpack-cover img') or self.soup.select_one('div.class-cover-image img')
        if cover and cover.get('src'):
            url = cover['src']
            if url.startswith('//'):
                url = 'https:' + url
            res['img-url'] = url
        return res

    def get_description(self):
        desc_div = self.soup.select_one('div.modpack-description') or self.soup.select_one('div.summary')
        if desc_div:
            return {'description': desc_div.get_text(strip=True)}
        return {'description': ''}