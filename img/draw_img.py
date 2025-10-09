# -*- coding: utf-8 -*-

# 导入必要的库
import io
import math
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pathlib import Path
# 导入 Matplotlib 相关库，用于生成雷达图
# 需要安装 matplotlib: pip install matplotlib
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import base64

# ----------------- 数据和配置 (Data and Configuration) -----------------

# 用户提供的原始数据 (已更新为新的 name 结构)
MOD_DATA = [
    {
        'status': '活跃 开源',
        'name': {'short-name': '[TLM]', 'chinese-name': '车万女仆', 'english-name': 'Touhou Little Maid'},
        'tags': ['女仆', '生物', '东方', '东方Project', '自定义模型', '附属包', '休闲'],
        'votes': {'red_count': '422', 'red_percentage': '98%', 'black_count': '10', 'black_percentage': '2%'},
        'view_count': '353.43万',
        'mc_versions': {'Forge': ['1.20.1', '1.20', '1.19.2', '1.18.2', '1.16.5', '1.12.2'],
                        'NeoForge': ['1.21.1', '1.21']},
        'modpack_count': '85',
        'authors': ['酒石酸菌', '琥珀酸', '帕金伊', 'Azumic', '小鱼飘飘', 'Snownee', '天顶乌', '天幂'],
        'fun': 1042, 'difficulty': 363, 'stability': 951, 'practicality': 1007,
        'aesthetics': 1055, 'balance': 951, 'compatibility': 950, 'durability': 959,
        'img-url': 'https://i.mcmod.cn/class/cover/20200521/1590019159_2_mrrK.jpg@480x300.jpg'
    }
]

# --- 字体配置 ---
# !!! 重要: 请将这里的路径改成你电脑上真实存在的中文字体文件路径 !!!
FONT_PATH = Path(__file__).resolve().parent.parent / 'resource' / 'msyh.ttf'
FONT_BOLD_PATH = Path(__file__).resolve().parent.parent / 'resource' / 'msyh.ttf'


# ----------------- 辅助函数 (Helper Functions) -----------------

def create_gradient_background(width, height):
    """
    创建一个漂亮的彩色渐变背景图
    :param width: 图片宽度
    :param height: 图片高度
    :return: PIL Image 对象
    """
    # 初始化一个黑色底板
    array = np.zeros((height, width, 3), dtype=np.uint8)
    # 定义四个角的颜色（高饱和度，易于与文字区分）
    colors = [
        np.array([255, 107, 107]), # 红
        np.array([255, 234, 167]), # 黄
        np.array([129, 236, 236]), # 青
        np.array([162, 155, 254]), # 紫
    ]
    # 使用距离加权平均创建渐变
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
    """
    从 URL 下载图片并返回 PIL Image 对象
    :param url: 图片的网址
    :return: PIL Image 对象, 如果下载失败则返回一个灰色占位图
    """
    try:
        # 添加 User-Agent 以防部分网站拒绝爬取
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, stream=True)
        response.raise_for_status() # 检查请求是否成功
        image_data = response.content
        return Image.open(io.BytesIO(image_data)).convert("RGBA")
    except requests.exceptions.RequestException as e:
        print(f"警告: 无法从 {url} 下载图片. 错误: {e}")
        # 返回一个圆角的灰色占位图
        placeholder = Image.new('RGBA', (80, 80), (200, 200, 200, 255))
        return placeholder


def create_radar_chart(data, labels, color, size):
    """
    使用 matplotlib 创建一个透明背景的雷达图 (已优化，使用中文自定义字体)
    :param data: 归一化后的雷达图数值
    :param labels: 雷达图维度标签（中文）
    :param color: 雷达图线条和填充的颜色 (RGB元组，0-1.0)
    :param size: 图表尺寸 (宽, 高)
    :return: PIL Image 对象 (RGBA格式)
    """
    # 闭合数据点
    data_closed = np.concatenate((data, [data[0]]))
    num_vars = len(labels)
    # 计算每个维度对应的角度
    angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
    angles += angles[:1]

    # 创建一个极坐标子图，figsize单位是英寸
    fig, ax = plt.subplots(figsize=(size[0] / 100, size[1] / 100), subplot_kw=dict(polar=True))
    # 设置图表背景完全透明
    ax.set_facecolor((0, 0, 0, 0))
    fig.patch.set_alpha(0.0)

    # 绘制雷达图的线和填充
    ax.plot(angles, data_closed, color=color, linewidth=2, zorder=3)
    ax.fill(angles, data_closed, color=color, alpha=0.3, zorder=2)

    # 尝试加载中文字体，失败则使用默认字体
    try:
        font_prop = FontProperties(fname=FONT_PATH, size=12)
    except Exception:
        font_prop = None
        print(f"雷达图警告：找不到字体文件: {FONT_PATH}，将使用 Matplotlib 默认字体。")

    # 隐藏 Y 轴刻度标签
    ax.set_yticklabels([])
    # 设置 X 轴刻度 (标签)
    ax.set_xticks(angles[:-1])
    # 设置 X 轴刻度标签为中文，并将其颜色改为白色，使其在卡片背景上更清晰
    ax.set_xticklabels(labels, color='white', fontproperties=font_prop, y=-0.1)
    # 隐藏极坐标轴的边框
    ax.spines['polar'].set_visible(False)
    # 设置网格线的颜色为浅灰色且半透明
    ax.grid(color=(1, 1, 1, 0.4), linestyle='--', linewidth=0.5, zorder=1)
    # 设置极径的范围 (0到1)
    ax.set_rlim(0, 1)
    # 设置极径的刻度（0.2为一个单位）
    ax.set_yticks(np.arange(0.2, 1.2, 0.2))

    # 将 Matplotlib 图形保存到内存中的字节流
    buf = io.BytesIO()
    plt.savefig(buf, format='png', transparent=True, bbox_inches='tight', pad_inches=0.1)
    buf.seek(0)
    plt.close(fig) # 关闭图形，释放内存

    # 从字节流中加载 PIL Image 对象
    return Image.open(buf).convert("RGBA")


def summarize_list(items, max_len=35):
    """
    将一个列表（如作者、版本）缩短为一个简洁的字符串
    :param items: 列表
    :param max_len: 字符串的最大长度
    :return: 缩短后的字符串
    """
    if not items:
        return "N/A"
    if len(items) <= 2:
        return ', '.join(items)
    full_str = ', '.join(items)
    if len(full_str) > max_len:
        return f"{items[0]}, {items[1]}..."
    return full_str


def summarize_versions(versions):
    """
    将版本号列表概括成 "最新版本...最老版本" 的格式
    :param versions: 版本号列表
    :return: 概括后的字符串
    """
    if not versions:
        return "N/A"
    if len(versions) == 1:
        return versions[0]
    return f"{versions[0]}...{versions[-1]}"


def draw_vote_chart(draw, x, y, votes, font_sm):
    """
    绘制一个科技简约风格的红黑投票条形图
    :param draw: ImageDraw 对象
    :param x: 绘制起始 X 坐标
    :param y: 绘制起始 Y 坐标
    :param votes: 投票数据字典
    :param font_sm: 小字体
    """
    red_count = int(votes['red_count'])
    black_count = int(votes['black_count'])
    red_pct = votes['red_percentage']
    black_pct = votes['black_percentage']
    total = red_count + black_count
    if total == 0: total = 1

    bar_width = 200
    bar_height = 16
    bar_y = y + 10

    # 投票图表颜色优化: 使用高亮颜色
    positive_color = (0, 255, 255, 255) # 青色
    positive_fill_color = (0, 255, 255, 100)
    negative_color = (150, 150, 150, 255)
    negative_fill_color = (150, 150, 150, 80)
    outline_color = (255, 255, 255, 150) # 亮白色边框

    # 绘制外边框
    draw.rectangle((x, bar_y, x + bar_width, bar_y + bar_height), outline=outline_color, width=1)

    # 绘制支持票 (红色/青色)
    red_width = (red_count / total) * bar_width
    if red_width > 0:
        draw.rectangle((x, bar_y, x + red_width, bar_y + bar_height), fill=positive_fill_color)
        # 绘制支持票的亮色边框，使其更清晰
        draw.rectangle((x, bar_y, x + red_width, bar_y + bar_height), outline=positive_color, width=1)

    # 绘制反对票 (黑色/灰色)
    black_start_x = x + red_width
    black_width = (black_count / total) * bar_width
    if black_width > 0:
        draw.rectangle((black_start_x, bar_y, black_start_x + black_width, bar_y + bar_height),
                       fill=negative_fill_color)
        draw.rectangle((black_start_x, bar_y, black_start_x + black_width, bar_y + bar_height), outline=negative_color,
                       width=1)

    # 文本颜色改为纯白色，提高对比度
    text_color = (255, 255, 255)
    if red_width > 30:
        draw.text((x + red_width / 2, bar_y + bar_height / 2), red_pct, fill=text_color, font=font_sm, anchor="mm")
    if black_width > 30:
        draw.text((black_start_x + black_width / 2, bar_y + bar_height / 2), black_pct, fill=text_color, font=font_sm,
                  anchor="mm")

    # 投票计数文本
    draw.text((x, bar_y + bar_height + 5), f"支持: {red_count} / 反对: {black_count} ", fill=(220, 220, 220),
              font=font_sm)


# ----------------- 主渲染函数 (Main Rendering Function) -----------------

def generate_mod_cards(data_list):
    """
    根据Mod数据列表生成最终的展示图片 (已更新名称绘制逻辑和颜色)
    :param data_list: 包含多个Mod字典的列表
    """
    # ---- 1. 初始化画布和字体 (Initialize Canvas and Fonts) ----
    card_width, card_height = 450, 700
    padding, gap = 50, 40
    num_cards = len(data_list)
    img_width = padding * 2 + card_width * num_cards + gap * (num_cards - 1)
    img_height = padding * 2 + card_height

    # 创建渐变背景
    background = create_gradient_background(img_width, img_height)
    # 创建透明画布用于绘制内容
    canvas = Image.new('RGBA', (img_width, img_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    try:
        # 加载字体
        font_sm = ImageFont.truetype(FONT_PATH, 16)  # 小字体 (作者、版本内容)
        font_md = ImageFont.truetype(FONT_PATH, 20)  # 中字体 (标题)
        font_lg_bold = ImageFont.truetype(FONT_BOLD_PATH, 28)  # 大字体 (主要 Mod 名称)
        font_tag = ImageFont.truetype(FONT_BOLD_PATH, 16)  # 标签字体
    except IOError:
        print(f"警告: 字体文件未找到. 将使用默认字体.")
        font_sm = ImageFont.load_default()
        font_md = ImageFont.load_default()
        font_lg_bold = ImageFont.load_default()
        font_tag = ImageFont.load_default()

    # **【核心修改】优化后的颜色方案 (RGB 元组，0-255)**
    text_colors = {
        'name': (51, 0, 0),    # 纯白色 - Mod主要名称 (最高优先级)
        'status': (0, 255, 255),    # 亮青色/淡青色 - 状态 (高亮)
        'label': (255, 255, 255),   # 纯白色 - 标题标签 (例如“支持版本”)
        'view_count': (255, 255, 255), # 纯白色 - 浏览量
        'versions': (255, 255, 0),  # 亮黄色 - MC版本 (高亮)
        'authors': (255, 51, 51), # **第三次修改: 粉红色 - 作者**
        'english_name': (255, 255, 255) # **第三次修改: 纯白色 - 英文名称**
    }

    # 标签颜色列表 (用于标签气泡背景)
    tag_colors = [
        (100, 180, 255), (255, 165, 0), (162, 155, 254),
        (255, 107, 107), (129, 236, 236), (255, 234, 167),
    ]

    # ---- 2. 循环处理每个 Mod (Loop Through Each Mod) ----
    for i, mod_data in enumerate(data_list):

        # ---- 2.1. 计算卡片位置并创建毛玻璃背景 ----
        card_x = padding + i * (card_width + gap)
        card_y = padding
        card_box = (card_x, card_y, card_x + card_width, card_y + card_height)

        # 裁剪并模糊背景区域
        region = background.crop(card_box)
        blurred_region = region.filter(ImageFilter.GaussianBlur(radius=15))
        # 添加白色半透明层作为“毛玻璃”效果
        glass_layer = Image.new('RGBA', (card_width, card_height), (255, 255, 255, 40))
        frosted_glass = Image.alpha_composite(blurred_region.convert('RGBA'), glass_layer)
        canvas.paste(frosted_glass, card_box)
        # 绘制卡片边框
        draw.rounded_rectangle(card_box, radius=20, outline=(255, 255, 255, 200), width=3)

        # ---- 2.2. Mod 图标处理 ----
        mod_icon_url = mod_data['img-url'].split('@')[0]
        mod_icon = fetch_image(mod_icon_url)
        mod_icon = mod_icon.resize((80, 80), Image.Resampling.LANCZOS)
        # 创建圆形遮罩
        mask = Image.new('L', (80, 80), 0)
        draw_mask = ImageDraw.Draw(mask)
        draw_mask.ellipse((0, 0, 80, 80), fill=255)
        icon_pos = (card_x + 30, card_y + 30)
        canvas.paste(mod_icon, icon_pos, mask)

        # ---- 2.3. 绘制 Mod 名称和状态 ----
        text_x = icon_pos[0] + 80 + 20  # 图标右侧
        name_data = mod_data.get('name', {})
        current_y = card_y + 35

        # 尝试获取名称部分
        short_name = name_data.get('short-name', '')
        chinese_name = name_data.get('chinese-name', '')
        english_name = name_data.get('english-name', '')

        # 绘制名称主标题 (中文名/英文名)
        if chinese_name:
            # 缩写 + 中文名 (大字体, 纯白色)
            main_name = f"{short_name} {chinese_name}" if short_name else chinese_name
            draw.text((text_x, current_y), main_name, fill=text_colors['name'], font=font_lg_bold)
            current_y += font_lg_bold.size + 5

            # 第二行：英文名 (中等字体，**纯白色**)
            if english_name:
                draw.text((text_x, current_y), english_name, fill=text_colors['english_name'], font=font_md)
                current_y += font_md.size + 5
        elif english_name:
            # 缩写 + 英文名 (大字体, 纯白色)
            main_name = f"{short_name} {english_name}" if short_name else english_name
            draw.text((text_x, current_y), main_name, fill=text_colors['name'], font=font_lg_bold)
            current_y += font_lg_bold.size + 5
        else:
            # 默认占位
            draw.text((text_x, current_y), "Mod Name N/A", fill=text_colors['name'], font=font_lg_bold)
            current_y += font_lg_bold.size + 5

        # 状态信息 (亮青色高亮)
        draw.text((text_x, current_y), mod_data['status'], fill=text_colors['status'], font=font_sm)
        # 调整后续元素的起始 Y 坐标
        y_offset = max(icon_pos[1] + 80 + 10, current_y + font_sm.size + 10)  # 确保不低于图标底部

        # 绘制浏览量 (纯白色)
        draw.text((icon_pos[0], y_offset), f"浏览量: {mod_data['view_count']}", fill=text_colors['view_count'],
                  font=font_md)
        y_offset += 40

        # 绘制投票图表
        draw_vote_chart(draw, icon_pos[0], y_offset, mod_data['votes'], font_sm)
        y_offset += 75

        # 绘制MC版本信息
        draw.text((icon_pos[0], y_offset), "支持版本:", fill=text_colors['label'], font=font_md)
        y_offset += 28
        # 版本号信息 (亮黄色高亮)
        for loader, versions in mod_data['mc_versions'].items():
            line = f"{loader}: {summarize_versions(versions)}"
            draw.text((icon_pos[0], y_offset), line, fill=text_colors['versions'], font=font_sm)
            y_offset += 25

        # 绘制标签 (圆角气泡 + 换行)
        y_offset += 20
        tag_start_y = y_offset
        current_x = icon_pos[0]
        tag_height = 24
        tag_padding = 10
        card_right_bound = card_x + card_width - 20

        for idx, tag in enumerate(mod_data['tags']):
            color_idx = idx % len(tag_colors)
            tag_color = tag_colors[color_idx]

            bbox = draw.textbbox((0, 0), tag, font=font_tag)
            tag_text_width = bbox[2] - bbox[0]
            tag_width = tag_text_width + 16

            # 检查是否需要换行
            if current_x + tag_width > card_right_bound and current_x != icon_pos[0]:
                current_x = icon_pos[0]
                tag_start_y += tag_height + 10

            # 绘制标签背景
            tag_rect = (current_x, tag_start_y, current_x + tag_width, tag_start_y + tag_height)
            fill_color = (*tag_color, 120)
            outline_color = (*tag_color, 255)
            draw.rounded_rectangle(tag_rect, radius=8, fill=fill_color, outline=outline_color, width=1)
            # 绘制标签文本 (纯白色)
            text_pos = (current_x + 8, tag_start_y + (tag_height - font_tag.size) // 2 - 1)
            draw.text(text_pos, tag, fill=(255, 255, 255), font=font_tag)

            current_x += tag_width + tag_padding

        y_offset = tag_start_y + tag_height + 25 if len(mod_data['tags']) > 0 else y_offset + 25

        # 绘制作者信息 (**纯白色**)
        draw.text((icon_pos[0], y_offset), f"作者: {summarize_list(mod_data['authors'], 35)}", fill=text_colors[
            'authors'], font=font_sm)
        y_offset += 40

        # ---- 2.4. 绘制雷达图 ----
        radar_labels_cn = ['趣味', '难度', '稳定', '实用', '美观', '平衡', '兼容', '耐玩']
        radar_keys = ['fun', 'difficulty', 'stability', 'practicality', 'aesthetics', 'balance', 'compatibility',
                      'durability']
        radar_values = np.array([mod_data.get(key, 0) for key in radar_keys])
        # 将值归一化到 0 到 1 之间
        radar_values_normalized = radar_values / 1200.0

        # 根据 Mod 名称确定雷达图配色，使用高对比度的颜色
        if 'Touhou' in str(name_data):
            card_color = (0, 1.0, 1.0, 1) # 亮青色
        else:
            card_color = (1.0, 0.4, 0.4, 1) # 亮红色

        radar_chart = create_radar_chart(radar_values_normalized, radar_labels_cn, card_color, (220, 220))
        # 计算雷达图的居中位置
        y_offset -=20
        radar_pos = (card_x + (card_width - radar_chart.width) // 2, y_offset)
        canvas.paste(radar_chart, radar_pos, radar_chart)

    # ---- 3. 合成并保存 (Composite and Save) ----
    # 将绘制内容与渐变背景合成
    final_image = Image.alpha_composite(background.convert('RGBA'), canvas)
    buf = io.BytesIO()
    final_image.save(buf, format='PNG')
    img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    return img_base64


if __name__ == "__main__":
    # 当脚本直接被执行时，调用主函数
    base64_str = generate_mod_cards(MOD_DATA)
    print(base64_str)