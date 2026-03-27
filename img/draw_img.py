# -*- coding: utf-8 -*-
import io
import math
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import base64
import re

from astrbot.api import logger

# 默认配置
DEFAULT_CONFIG = {
    "font_path": None,
    "font_bold_path": None,
    "card_width": 450,
    "card_height": 700,
    "color_scheme": "default",
}

def create_gradient_background(width, height):
    """创建渐变背景"""
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
    """下载图片，失败返回占位图"""
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

def create_radar_chart(data, labels, color, size, font_path=None):
    """创建雷达图，data 已归一化到 0~1"""
    data_closed = np.concatenate((data, [data[0]]))
    num_vars = len(labels)
    angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(size[0] / 100, size[1] / 100), subplot_kw=dict(polar=True))
    ax.set_facecolor((0, 0, 0, 0))
    fig.patch.set_alpha(0.0)

    ax.plot(angles, data_closed, color=color, linewidth=2, zorder=3)
    ax.fill(angles, data_closed, color=color, alpha=0.3, zorder=2)

    # 设置中文字体
    font_prop = None
    if font_path and Path(font_path).exists():
        try:
            font_prop = FontProperties(fname=font_path, size=12)
        except Exception as e:
            logger.warning(f"加载雷达图字体失败: {e}")

    ax.set_yticklabels([])
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, color='white', fontproperties=font_prop, y=-0.1)
    ax.spines['polar'].set_visible(False)
    ax.grid(color=(1, 1, 1, 0.4), linestyle='--', linewidth=0.5, zorder=1)
    ax.set_rlim(0, 1)
    ax.set_yticks(np.arange(0.2, 1.2, 0.2))

    buf = io.BytesIO()
    plt.savefig(buf, format='png', transparent=True, bbox_inches='tight', pad_inches=0.1)
    buf.seek(0)
    plt.close(fig)
    return Image.open(buf).convert("RGBA")

def summarize_list(items, max_len=35):
    if not items:
        return "N/A"
    if len(items) <= 2:
        return ', '.join(items)
    full = ', '.join(items)
    if len(full) > max_len:
        return f"{items[0]}, {items[1]}..."
    return full

def summarize_versions(versions):
    if not versions:
        return "N/A"
    if len(versions) == 1:
        return versions[0]
    return f"{versions[0]}...{versions[-1]}"

def draw_vote_chart(draw, x, y, votes, font_sm):
    """绘制投票条形图"""
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

def generate_mod_cards(data_list, config=None):
    """生成卡片图片，返回 base64 字符串"""
    cfg = DEFAULT_CONFIG.copy()
    if config:
        cfg.update(config)

    card_width = cfg["card_width"]
    card_height = cfg["card_height"]
    padding = 50
    gap = 40
    num_cards = len(data_list)
    img_width = padding * 2 + card_width * num_cards + gap * (num_cards - 1)
    img_height = padding * 2 + card_height

    background = create_gradient_background(img_width, img_height)
    canvas = Image.new('RGBA', (img_width, img_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    # 加载字体
    font_path = cfg.get("font_path")
    font_bold_path = cfg.get("font_bold_path", font_path)
    try:
        if font_path and Path(font_path).exists():
            font_sm = ImageFont.truetype(font_path, 16)
            font_md = ImageFont.truetype(font_path, 20)
            font_lg_bold = ImageFont.truetype(font_bold_path or font_path, 28) if (font_bold_path or font_path) else ImageFont.load_default()
            font_tag = ImageFont.truetype(font_path, 16)
        else:
            logger.warning("未找到中文字体，使用默认字体，可能导致中文显示异常")
            font_sm = font_md = font_lg_bold = font_tag = ImageFont.load_default()
    except Exception as e:
        logger.error(f"字体加载失败: {e}，使用默认字体")
        font_sm = font_md = font_lg_bold = font_tag = ImageFont.load_default()

    text_colors = {
        'name': (51, 0, 0),
        'status': (0, 255, 255),
        'label': (255, 255, 255),
        'view_count': (255, 255, 255),
        'versions': (255, 255, 0),
        'authors': (255, 51, 51),
        'english_name': (255, 255, 255)
    }
    tag_colors = [
        (100, 180, 255), (255, 165, 0), (162, 155, 254),
        (255, 107, 107), (129, 236, 236), (255, 234, 167),
    ]

    for i, mod in enumerate(data_list):
        card_x = padding + i * (card_width + gap)
        card_y = padding
        card_box = (card_x, card_y, card_x + card_width, card_y + card_height)

        # 毛玻璃效果
        region = background.crop(card_box)
        blurred = region.filter(ImageFilter.GaussianBlur(radius=15))
        glass = Image.new('RGBA', (card_width, card_height), (255, 255, 255, 40))
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

        # 开始使用左侧坐标布局（从图标左下方开始）
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
            draw.text((left_x, current_y), f"作者: {summarize_list(authors, 35)}",
                      fill=text_colors['authors'], font=font_sm)
            current_y += 40
        else:
            current_y += 25

        # 雷达图（仅当存在评分数据时）
        rating_keys = ['fun', 'difficulty', 'stability', 'practicality', 'aesthetics', 'balance', 'compatibility', 'durability']
        values = [mod.get(k, 0) for k in rating_keys]
        if any(v > 0 for v in values):
            max_val = max(values)
            if max_val == 0:
                max_val = 1
            normalized = np.array(values) / max_val
            labels_cn = ['趣味', '难度', '稳定', '实用', '美观', '平衡', '兼容', '耐玩']
            # 根据名称决定雷达图颜色
            if 'Touhou' in str(name_data):
                color = (0, 1.0, 1.0, 1)
            else:
                color = (1.0, 0.4, 0.4, 1)
            radar = create_radar_chart(normalized, labels_cn, color, (220, 220), font_path)
            radar_x = card_x + (card_width - radar.width) // 2
            radar_y = current_y - 20
            canvas.paste(radar, (radar_x, radar_y), radar)

    final = Image.alpha_composite(background.convert('RGBA'), canvas)
    buf = io.BytesIO()
    final.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode('utf-8')