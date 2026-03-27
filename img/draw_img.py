# -*- coding: utf-8 -*-
import io
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import base64
from typing import List, Dict, Any

from astrbot.api import logger

DEFAULT_CONFIG = {
    "card_width": 450,
    "color_scheme": "default",
}

def create_gradient_background(width, height):
    array = np.zeros((height, width, 3), dtype=np.uint8)
    colors = [
        np.array([255, 107, 107]),
        np.array([255, 234, 167]),
        np.array([129, 236, 236]),
        np.array([162, 155, 254]),
    ]
    x, y = np.meshgrid(np.arange(width), np.arange(height))
    distances = [
        np.sqrt(((x - c[0] * width) ** 2 + (y - c[1] * height) ** 2))
        for c in [(0.1, 0.1), (0.9, 0.1), (0.1, 0.9), (0.9, 0.9)]
    ]
    total_dist = sum(1 / (d + 1e-6) for d in distances)
    weights = [(1 / (d + 1e-6)) / total_dist for d in distances]
    for i in range(len(colors)):
        array += np.uint8(np.expand_dims(weights[i], axis=-1) * colors[i])
    return Image.fromarray(array)

def fetch_image(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        if '@' in url:
            url = url.split('@')[0]
        response = requests.get(url, headers=headers, stream=True, timeout=5)
        response.raise_for_status()
        return Image.open(io.BytesIO(response.content)).convert("RGBA")
    except Exception as e:
        logger.warning(f"图片下载失败 {url}: {e}")
        placeholder = Image.new('RGBA', (80, 80), (200, 200, 200, 255))
        return placeholder

def create_radar_chart(data, labels, scores, color, size, font_path=None):
    data_closed = np.concatenate((data, [data[0]]))
    num_vars = len(labels)
    angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(size[0] / 100, size[1] / 100), subplot_kw=dict(polar=True))
    ax.set_facecolor((0, 0, 0, 0))
    fig.patch.set_alpha(0.0)

    ax.plot(angles, data_closed, color=color, linewidth=2, zorder=3)
    ax.fill(angles, data_closed, color=color, alpha=0.3, zorder=2)

    font_prop = None
    if font_path and Path(font_path).exists():
        try:
            font_prop = FontProperties(fname=font_path, size=10)
        except Exception as e:
            logger.warning(f"加载雷达图字体失败: {e}")

    ax.set_yticklabels([])
    ax.set_xticks(angles[:-1])
    label_with_score = [f"{label}\n{score}" for label, score in zip(labels, scores)]
    ax.set_xticklabels(label_with_score, color='white', fontproperties=font_prop, y=-0.1)
    ax.spines['polar'].set_visible(False)
    ax.grid(color=(1, 1, 1, 0.4), linestyle='--', linewidth=0.5, zorder=1)
    ax.set_rlim(0, 1)
    ax.set_yticks(np.arange(0.2, 1.2, 0.2))

    buf = io.BytesIO()
    plt.savefig(buf, format='png', transparent=True, bbox_inches='tight', pad_inches=0.1)
    buf.seek(0)
    plt.close(fig)
    return Image.open(buf).convert("RGBA")

def wrap_text(text, font, max_width, draw):
    if not text:
        return []
    lines = []
    current_line = ''
    for ch in text:
        test_line = current_line + ch
        bbox = draw.textbbox((0, 0), test_line, font=font)
        width = bbox[2] - bbox[0]
        if width <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = ch
    if current_line:
        lines.append(current_line)
    return lines

def summarize_versions(versions):
    if not versions:
        return "N/A"
    if len(versions) == 1:
        return versions[0]
    return f"{versions[0]}...{versions[-1]}"

def draw_vote_chart(draw, x, y, votes, font_sm):
    try:
        red_count = int(votes.get('red_count', '0'))
        black_count = int(votes.get('black_count', '0'))
    except:
        red_count = black_count = 0
    red_pct = votes.get('red_percentage', '0%')
    black_pct = votes.get('black_percentage', '0%')
    total = red_count + black_count
    if total == 0:
        total = 1

    bar_width = 200
    bar_height = 16
    bar_y = y + 10

    positive_color = (0, 255, 255, 255)
    positive_fill = (0, 255, 255, 100)
    negative_color = (150, 150, 150, 255)
    negative_fill = (150, 150, 150, 80)
    outline = (255, 255, 255, 150)

    draw.rectangle((x, bar_y, x + bar_width, bar_y + bar_height), outline=outline, width=1)

    red_width = (red_count / total) * bar_width
    if red_width > 0:
        draw.rectangle((x, bar_y, x + red_width, bar_y + bar_height), fill=positive_fill)
        draw.rectangle((x, bar_y, x + red_width, bar_y + bar_height), outline=positive_color, width=1)

    black_start = x + red_width
    black_width = (black_count / total) * bar_width
    if black_width > 0:
        draw.rectangle((black_start, bar_y, black_start + black_width, bar_y + bar_height),
                       fill=negative_fill)
        draw.rectangle((black_start, bar_y, black_start + black_width, bar_y + bar_height),
                       outline=negative_color, width=1)

    text_color = (255, 255, 255)
    if red_width > 30:
        draw.text((x + red_width / 2, bar_y + bar_height / 2), red_pct, fill=text_color, font=font_sm, anchor="mm")
    if black_width > 30:
        draw.text((black_start + black_width / 2, bar_y + bar_height / 2), black_pct, fill=text_color, font=font_sm, anchor="mm")

    draw.text((x, bar_y + bar_height + 5), f"支持: {red_count} / 反对: {black_count} ", fill=(220, 220, 220), font=font_sm)

def generate_mod_cards(data_list: List[Dict[str, Any]], config: Dict = None, font_path: str = None) -> str:
    cfg = DEFAULT_CONFIG.copy()
    if config:
        cfg.update(config)

    card_width = cfg["card_width"]
    padding = 50
    gap = 40
    num_cards = len(data_list)

    try:
        if font_path and Path(font_path).exists():
            font_sm = ImageFont.truetype(font_path, 14)
            font_md = ImageFont.truetype(font_path, 18)
            font_lg_bold = ImageFont.truetype(font_path, 26)
            font_tag = ImageFont.truetype(font_path, 13)
            logger.debug(f"字体加载成功: {font_path}")
        else:
            logger.warning("字体加载失败，使用默认字体")
            font_sm = font_md = font_lg_bold = font_tag = ImageFont.load_default()
    except Exception as e:
        logger.error(f"字体加载异常: {e}，使用默认字体")
        font_sm = font_md = font_lg_bold = font_tag = ImageFont.load_default()

    # 动态行高（基于字体大小）
    line_height_sm = font_sm.size + 4
    line_height_md = font_md.size + 5
    line_height_lg = font_lg_bold.size + 5

    text_colors = {
        'name': (51, 0, 0),
        'status': (0, 255, 255),
        'label': (255, 255, 255),
        'view_count': (255, 255, 255),
        'versions': (255, 255, 0),
        'authors': (255, 51, 51),
        'english_name': (255, 255, 255),
        'description': (220, 220, 220)
    }
    tag_colors = [
        (100, 180, 255), (255, 165, 0), (162, 155, 254),
        (255, 107, 107), (129, 236, 236), (255, 234, 167),
    ]

    # 简介区域圆角矩形样式
    desc_bg_color = (0, 0, 0, 100)   # 半透明黑色背景
    desc_padding = 15
    desc_radius = 12

    # ========== 第一步：计算每张卡片所需高度 ==========
    card_heights = []
    for mod in data_list:
        y = 0
        # 图标 + 标题区域
        y += 110
        y += 30          # 状态行
        y += 40          # 浏览量行
        y += 75          # 投票图表
        y += 15          # 间距

        # MC 版本
        mc_versions = mod.get('mc_versions', {})
        if mc_versions:
            y += 28
            y += len(mc_versions) * 25
            y += 20
        else:
            y += 20

        # 标签
        tags = mod.get('tags', [])
        if tags:
            tag_y = 0
            tag_x = 0
            tag_h = 24
            pad = 10
            right_bound = card_width - 20
            dummy_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
            for tag in tags:
                bbox = dummy_draw.textbbox((0, 0), tag, font=font_tag)
                tw = bbox[2] - bbox[0] + 16
                if tag_x + tw > right_bound and tag_x != 0:
                    tag_x = 0
                    tag_y += tag_h + 10
                tag_x += tw + pad
            y += tag_y + tag_h + 25
        else:
            y += 25

        # 作者
        authors = mod.get('authors', [])
        if authors:
            author_str = ', '.join(authors)
            author_lines = wrap_text(author_str, font_sm, card_width - 60, dummy_draw)
            y += len(author_lines) * line_height_sm + 20
        else:
            y += 20

        # 雷达图（模组才有）
        rating_keys = ['fun', 'difficulty', 'stability', 'practicality', 'aesthetics', 'balance', 'compatibility', 'durability']
        values = [mod.get(k, 0) for k in rating_keys]
        if any(v > 0 for v in values):
            y += 250
        else:
            y += 10

        # 简介区域高度（单独计算）
        desc = mod.get('description', '')
        if desc:
            desc_lines = wrap_text(desc, font_sm, card_width - desc_padding * 2, dummy_draw)
            desc_height = len(desc_lines) * line_height_sm + desc_padding * 2
        else:
            desc_height = 0

        y += desc_height + 30   # 加上间距

        card_heights.append(y)

    total_card_height = max(card_heights) + 20
    img_width = padding * 2 + card_width * num_cards + gap * (num_cards - 1)
    img_height = padding * 2 + total_card_height

    background = create_gradient_background(img_width, img_height)
    canvas = Image.new('RGBA', (img_width, img_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    # ========== 第二步：实际绘制卡片 ==========
    for i, mod in enumerate(data_list):
        card_x = padding + i * (card_width + gap)
        card_y = padding
        card_box = (card_x, card_y, card_x + card_width, card_y + total_card_height)

        region = background.crop(card_box)
        blurred = region.filter(ImageFilter.GaussianBlur(radius=15))
        glass = Image.new('RGBA', (card_width, total_card_height), (255, 255, 255, 40))
        frosted = Image.alpha_composite(blurred.convert('RGBA'), glass)
        canvas.paste(frosted, card_box)
        draw.rounded_rectangle(card_box, radius=20, outline=(255, 255, 255, 200), width=3)

        # 图标
        icon_url = mod.get('img-url', '')
        if icon_url:
            icon = fetch_image(icon_url).resize((80, 80), Image.Resampling.LANCZOS)
            mask = Image.new('L', (80, 80), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse((0, 0, 80, 80), fill=255)
            canvas.paste(icon, (card_x + 30, card_y + 30), mask)

        # 名称与状态
        name_data = mod.get('name', {})
        text_x = card_x + 30 + 80 + 20
        y_pos = card_y + 35
        short = name_data.get('short-name', '')
        ch = name_data.get('chinese-name', '')
        en = name_data.get('english-name', '')

        if ch:
            main_name = f"{short} {ch}" if short else ch
            draw.text((text_x, y_pos), main_name, fill=text_colors['name'], font=font_lg_bold)
            y_pos += font_lg_bold.size + 5
            if en:
                draw.text((text_x, y_pos), en, fill=text_colors['english_name'], font=font_md)
                y_pos += font_md.size + 5
        elif en:
            main_name = f"{short} {en}" if short else en
            draw.text((text_x, y_pos), main_name, fill=text_colors['name'], font=font_lg_bold)
            y_pos += font_lg_bold.size + 5
        else:
            draw.text((text_x, y_pos), "Mod Name N/A", fill=text_colors['name'], font=font_lg_bold)
            y_pos += font_lg_bold.size + 5

        status = mod.get('status', '')
        if status:
            draw.text((text_x, y_pos), status, fill=text_colors['status'], font=font_sm)
            y_pos += font_sm.size + 10
        else:
            y_pos += 10

        # 热度（评分+等级）
        rating_score = mod.get('rating_score', '')
        rating_level = mod.get('rating_level', '')
        if rating_score and rating_level:
            draw.text((text_x, y_pos), f"热度: {rating_score} ({rating_level})", fill=text_colors['view_count'], font=font_sm)
            y_pos += font_sm.size + 5

        # 昨日指数（整合包专用）
        heat = mod.get('heat_index', '')
        if heat:
            draw.text((text_x, y_pos), f"昨日指数: {heat}", fill=text_colors['view_count'], font=font_sm)
            y_pos += font_sm.size + 5

        left_x = card_x + 30
        current_y = max(y_pos, card_y + 30 + 80 + 10)

        # 浏览量
        view = mod.get('view_count', '')
        if view:
            draw.text((left_x, current_y), f"浏览量: {view}", fill=text_colors['view_count'], font=font_md)
            current_y += 40

        # 投票
        votes = mod.get('votes')
        if votes and votes.get('red_count'):
            draw_vote_chart(draw, left_x, current_y, votes, font_sm)
            current_y += 75
        else:
            current_y += 15

        # MC版本
        mc_versions = mod.get('mc_versions', {})
        if mc_versions:
            draw.text((left_x, current_y), "支持版本:", fill=text_colors['label'], font=font_md)
            current_y += 28
            for loader, vers in mc_versions.items():
                line = f"{loader}: {summarize_versions(vers)}"
                draw.text((left_x, current_y), line, fill=text_colors['versions'], font=font_sm)
                current_y += 25
            current_y += 20
        else:
            current_y += 20

        # 标签
        tags = mod.get('tags', [])
        if tags:
            tag_x = left_x
            tag_y = current_y
            tag_h = 24
            pad = 10
            right_bound = card_x + card_width - 20
            for idx, tag in enumerate(tags):
                bbox = draw.textbbox((0, 0), tag, font=font_tag)
                tw = bbox[2] - bbox[0] + 16
                if tag_x + tw > right_bound and tag_x != left_x:
                    tag_x = left_x
                    tag_y += tag_h + 10
                color = tag_colors[idx % len(tag_colors)]
                draw.rounded_rectangle((tag_x, tag_y, tag_x + tw, tag_y + tag_h), radius=8,
                                       fill=(*color, 120), outline=(*color, 255), width=1)
                draw.text((tag_x + 8, tag_y + (tag_h - font_tag.size) // 2 - 1),
                          tag, fill=(255, 255, 255), font=font_tag)
                tag_x += tw + pad
            current_y = tag_y + tag_h + 25
        else:
            current_y += 25

        # 作者
        authors = mod.get('authors', [])
        if authors:
            draw.text((left_x, current_y), "作者:", fill=text_colors['label'], font=font_md)
            current_y += 20
            author_str = ', '.join(authors)
            author_lines = wrap_text(author_str, font_sm, card_width - 60, draw)
            for line in author_lines:
                draw.text((left_x, current_y), line, fill=text_colors['authors'], font=font_sm)
                current_y += line_height_sm
            current_y += 5

        # 雷达图（模组）
        rating_keys = ['fun', 'difficulty', 'stability', 'practicality', 'aesthetics', 'balance', 'compatibility', 'durability']
        labels_cn = ['趣味', '难度', '稳定', '实用', '美观', '平衡', '兼容', '耐玩']
        values = [mod.get(k, 0) for k in rating_keys]
        if any(v > 0 for v in values):
            max_val = max(values)
            if max_val == 0:
                max_val = 1
            normalized = np.array(values) / max_val
            if 'Touhou' in str(name_data):
                color = (0, 1.0, 1.0, 1)
            else:
                color = (1.0, 0.4, 0.4, 1)
            radar = create_radar_chart(normalized, labels_cn, values, color, (220, 220), font_path)
            radar_x = card_x + (card_width - radar.width) // 2
            radar_y = current_y
            canvas.paste(radar, (radar_x, radar_y), radar)
            current_y += radar.height + 20
        else:
            current_y += 10

                # 简介区域（圆角矩形，放在卡片底部）
        desc = mod.get('description', '')
        if desc:
            # 矩形背景宽度（左右各留30px）
            desc_rect_width = card_width - 60
            # 文本左右内边距（相对于矩形背景）
            desc_margin = 15
            # 文本实际可用宽度
            text_max_width = desc_rect_width - 2 * desc_margin

            # 按段落分割（保留原文本中的换行符）
            paragraphs = desc.split('\n')
            all_lines = []
            for para in paragraphs:
                if not para.strip():
                    continue
                # 对每个段落进行自动换行
                para_lines = wrap_text(para, font_sm, text_max_width, draw)
                if para_lines:
                    all_lines.extend(para_lines)
                    all_lines.append('')  # 段落之间加一个空行
            # 移除最后一个多余的空行
            if all_lines and all_lines[-1] == '':
                all_lines.pop()

            if all_lines:
                # 计算矩形高度：行数 * 行高 + 上下边距
                desc_height_total = len(all_lines) * line_height_sm + desc_margin * 2
                desc_rect = (left_x, current_y, left_x + desc_rect_width, current_y + desc_height_total)

                # 绘制半透明圆角矩形背景
                draw.rounded_rectangle(desc_rect, radius=12, fill=desc_bg_color)

                # 绘制文本（从矩形左上角 + desc_margin 开始）
                text_y = current_y + desc_margin
                for line in all_lines:
                    draw.text((left_x + desc_margin, text_y), line, fill=text_colors['description'], font=font_sm)
                    text_y += line_height_sm

                # 更新当前Y坐标，为后续元素留出间距
                current_y += desc_height_total + 20

    final = Image.alpha_composite(background.convert('RGBA'), canvas)
    buf = io.BytesIO()
    final.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode('utf-8')