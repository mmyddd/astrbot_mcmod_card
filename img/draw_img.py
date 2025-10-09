# -*- coding: utf-8 -*-

import io
from matplotlib.font_manager import FontProperties
import math
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops
from pathlib import Path

# ----------------- 数据和配置 (Data and Configuration) -----------------

# 用户提供的原始数据
MOD_DATA = [
    {
        'status': '活跃 开源', 'name': '[TLM] 车万女仆 Touhou Little Maid',
        'tags': ['女仆', '生物', '东方', '东方Project'],
        'votes': {'red_count': '422', 'red_percentage': '98%', 'black_count': '10', 'black_percentage': '2%'},
        'view_count': '353.40万',
        'mc_versions': {'Forge': ['1.20.1', '1.20', '1.19.2', '1.18.2', '1.16.5', '1.12.2'],
                        'NeoForge': ['1.21.1', '1.21']},
        'modpack_count': '85',
        'authors': ['酒石酸菌', '琥珀酸', '帕金伊', 'Azumic', '小鱼飘飘', 'Snownee', '天顶乌', '天幂'],
        'fun': 1039, 'difficulty': 363, 'stability': 948, 'practicality': 1004,
        'aesthetics': 1052, 'balance': 948, 'compatibility': 947, 'durability': 956,
        'img-url': 'https://i.mcmod.cn/class/cover/20200521/1590019159_2_mrrK.jpg'
    }
]

# --- 字体配置 ---
# !!! 重要: 请将这里的路径改成你电脑上真实存在的中文字体文件路径 !!!
# 例如在 Windows 上可能是: "C:/Windows/Fonts/msyh.ttc"
# 例如在 macOS 上可能是: "/System/Library/Fonts/PingFang.ttc"
# 否则会因为找不到字体而报错
FONT_PATH = Path(__file__).resolve().parent.parent/'resource'/'msyh.ttf'
FONT_BOLD_PATH = Path(__file__).resolve().parent.parent/'resource'/'msyh.ttf'


# ----------------- 辅助函数 (Helper Functions) -----------------

def create_gradient_background(width, height):
    """
    创建一个漂亮的彩色渐变背景图
    :param width: 图片宽度
    :param height: 图片高度
    :return: PIL Image 对象
    """
    # 使用 numpy 创建一个三维数组来表示图像
    array = np.zeros((height, width, 3), dtype=np.uint8)
    # 定义几个颜色点
    colors = [
        np.array([255, 107, 107]),  # 红色
        np.array([255, 234, 167]),  # 黄色
        np.array([129, 236, 236]),  # 青色
        np.array([162, 155, 254]),  # 紫色
    ]
    # 通过计算每个像素到颜色点的距离来生成平滑的渐变
    x, y = np.meshgrid(np.arange(width), np.arange(height))
    distances = [
        np.sqrt(((x - c[0] * width) ** 2 + (y - c[1] * height) ** 2))
        for c in [(0.1, 0.1), (0.9, 0.1), (0.1, 0.9), (0.9, 0.9)]
    ]
    total_dist = sum(1 / (d + 1e-6) for d in distances)
    weights = [(1 / (d + 1e-6)) / total_dist for d in distances]

    # 根据权重混合颜色
    for i in range(len(colors)):
        array += np.uint8(np.expand_dims(weights[i], axis=-1) * colors[i])

    return Image.fromarray(array)


def fetch_image(url):
    """
    从 URL 下载图片并返回 PIL Image 对象
    :param url: 图片的网址
    :return: PIL Image 对象, 如果下载失败则返回 None
    """
    try:
        # 添加User-Agent，模拟浏览器访问，防止被网站屏蔽
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, stream=True)
        response.raise_for_status()  # 如果请求失败 (例如 404), 会抛出异常
        image_data = response.content
        return Image.open(io.BytesIO(image_data))
    except requests.exceptions.RequestException as e:
        print(f"警告: 无法从 {url} 下载图片. 错误: {e}")
        # 创建一个灰色的占位图
        return Image.new('RGBA', (100, 100), (200, 200, 200, 255))


# 把它复制过去，替换掉你原来的整个 create_radar_chart 函数

def create_radar_chart(data, labels, color, size):
    """
    使用 matplotlib 创建一个透明背景的雷达图
    :param data: 数值列表
    :param labels: 标签列表
    :param color: 图表的颜色 (r, g, b, a) 0-1之间
    :param size: 图片尺寸 (宽度, 高度)
    :return: PIL Image 对象
    """
    # 动态导入 matplotlib，避免在不需要时也加载
    import matplotlib.pyplot as plt
    # 新增: 从 matplotlib.font_manager 导入 FontProperties
    from matplotlib.font_manager import FontProperties

    # 为了让多边形闭合，需要在数据和标签的末尾添加第一个元素
    data_closed = np.concatenate((data, [data[0]]))

    num_vars = len(labels)
    # 计算每个标签的角度
    angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
    angles += angles[:1]  # 闭合

    fig, ax = plt.subplots(figsize=(size[0] / 100, size[1] / 100), subplot_kw=dict(polar=True))

    # 设置图表样式
    ax.set_facecolor((0, 0, 0, 0))  # 背景透明
    fig.patch.set_alpha(0.0)  # Figure背景也透明

    # 绘制数据多边形
    ax.plot(angles, data_closed, color=color, linewidth=2)
    ax.fill(angles, data_closed, color=color, alpha=0.25)

    # --- 这里是关键的修改 ---
    # 1. 检查字体文件是否存在，如果不存在则不使用自定义字体，避免崩溃
    try:
        # 2. 创建一个 FontProperties 对象
        font_prop = FontProperties(fname=FONT_PATH, size=12)
    except Exception:
        # 如果找不到字体文件，就将 font_prop 设为 None，matplotlib 会使用默认字体
        font_prop = None
        print("雷达图警告：找不到字体文件，将使用 Matplotlib 默认字体。")

    # 隐藏坐标轴标签和网格线
    ax.set_yticklabels([])
    ax.set_xticks(angles[:-1])
    # 3. 在这里使用创建好的 font_prop 对象
    ax.set_xticklabels(labels, color='white', fontproperties=font_prop)  # <-- 修改行
    ax.spines['polar'].set_visible(False)  # 隐藏最外层的圆形边框
    ax.grid(color=(1, 1, 1, 0.2))  # 设置网格线为半透明白色

    # 将绘制好的图表保存到内存中
    buf = io.BytesIO()
    plt.savefig(buf, format='png', transparent=True, bbox_inches='tight', pad_inches=0.1)
    buf.seek(0)
    plt.close(fig)  # 关闭图表以释放内存

    return Image.open(buf)


def summarize_list(items, max_len=30):
    """
    将一个列表（如作者、版本）缩短为一个简洁的字符串
    :param items: 字符串列表
    :param max_len: 允许的最大字符串长度
    :return: 缩短后的字符串
    """
    if not items:
        return "N/A"

    # 如果只有一两个元素，直接显示
    if len(items) <= 2:
        return ', '.join(items)

    # 尝试拼接，如果超长则用 "..."
    full_str = ', '.join(items)
    if len(full_str) > max_len:
        return f"{items[0]}, {items[1]}..."
    return full_str


def summarize_versions(versions):
    """
    将版本号列表概括成 "最新版本...最老版本" 的格式
    """
    if not versions:
        return "N/A"
    if len(versions) == 1:
        return versions[0]
    return f"{versions[0]}...{versions[-1]}"


def draw_vote_chart(draw, x, y, votes, font_sm):
    """
    绘制一个简单的红黑投票条形图
    :param draw: ImageDraw 对象
    :param x, y: 起始位置
    :param votes: 投票字典 {'red_count': str, 'red_percentage': str, 'black_count': str, 'black_percentage': str}
    :param font_sm: 小字体
    """
    red_count = int(votes['red_count'])
    black_count = int(votes['black_count'])
    total = red_count + black_count
    if total == 0:
        total = 1  # 避免除零

    # 条形图宽度和高度
    bar_width = 200
    bar_height = 20
    bar_y = y + 20

    # 绘制总条形背景
    draw.rounded_rectangle((x, bar_y, x + bar_width, bar_y + bar_height), radius=5, fill=(255, 255, 255, 50))

    # 绘制红条
    red_width = (red_count / total) * bar_width
    draw.rounded_rectangle((x, bar_y, x + red_width, bar_y + bar_height), radius=5, fill=(255, 0, 0, 200))

    # 绘制黑条
    black_width = (black_count / total) * bar_width
    draw.rounded_rectangle((x + red_width, bar_y, x + red_width + black_width, bar_y + bar_height), radius=5, fill=(0, 0, 0, 200))

    # 绘制标签
    draw.text((x, y), "Votes", fill=(255, 255, 255), font=font_sm)
    draw.text((x, bar_y + bar_height + 5), f"{red_count} (+98%) / {black_count} (-2%)", fill=(255, 255, 255), font=font_sm)


# ----------------- 主渲染函数 (Main Rendering Function) -----------------

def generate_mod_cards(data_list):
    """
    根据Mod数据列表生成最终的展示图片
    :param data_list: 包含多个Mod字典的列表
    """
    # ---- 1. 初始化画布和字体 (Initialize Canvas and Fonts) ----
    card_width, card_height = 450, 700
    padding, gap = 50, 40
    num_cards = len(data_list)
    img_width = padding * 2 + card_width * num_cards + gap * (num_cards - 1)
    img_height = padding * 2 + card_height

    # 创建背景
    background = create_gradient_background(img_width, img_height)
    # 创建一个用于绘制的图层
    canvas = Image.new('RGBA', (img_width, img_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    # 加载字体，如果失败则使用Pillow默认字体
    try:
        font_sm = ImageFont.truetype(FONT_PATH, 16)
        font_md = ImageFont.truetype(FONT_PATH, 20)
        font_lg_bold = ImageFont.truetype(FONT_BOLD_PATH, 28)
        # 为标签使用稍大的粗体字体以突出
        font_tag = ImageFont.truetype(FONT_BOLD_PATH, 18)
    except IOError:
        print(f"警告: 字体文件 '{FONT_PATH}' 或 '{FONT_BOLD_PATH}' 未找到. 将使用默认字体.")
        font_sm = ImageFont.load_default()
        font_md = ImageFont.load_default()
        font_lg_bold = ImageFont.load_default()
        font_tag = ImageFont.load_default()

    # 定义不同信息类型的颜色方案 (RGB 元组，0-255) - 避免绿色和粉色
    text_colors = {
        'name': (255, 255, 255),      # 白色 - Mod名称
        'status': (173, 216, 230),    # 浅蓝色 - 状态
        'view': (173, 216, 230),      # 浅蓝色 - 浏览量
        'votes': (255, 165, 0),       # 橙色 - 投票
        'versions': (255, 165, 0),    # 橙色 - MC版本
        'tags': (255, 255, 255),      # 白色 - 标签（每个独立颜色）
        'authors': (255, 255, 224),   # 浅黄色 - 作者
        'label': (255, 255, 255)      # 白色 - 标签标题如 "Tags:"
    }

    # 标签颜色列表（避免绿粉）
    tag_colors = [
        (173, 216, 230),  # 浅蓝
        (255, 165, 0),    # 橙
        (162, 155, 254),  # 紫
        (255, 107, 107),  # 红
        (129, 236, 236),  # 青
        (255, 234, 167),  # 黄
    ]

    # ---- 2. 循环处理每个 Mod (Loop Through Each Mod) ----
    for i, mod_data in enumerate(data_list):

        # ---- 2.1. 计算卡片位置并创建毛玻璃背景 (Calculate Position & Create Frosted Glass) ----
        card_x = padding + i * (card_width + gap)
        card_y = padding
        card_box = (card_x, card_y, card_x + card_width, card_y + card_height)

        # 截取卡片区域的背景
        region = background.crop(card_box)
        # 对截取的背景应用高斯模糊
        blurred_region = region.filter(ImageFilter.GaussianBlur(radius=20))

        # 创建一个半透明的白色矩形作为玻璃的基底
        glass_layer = Image.new('RGBA', (card_width, card_height), (255, 255, 255, 60))
        # 将模糊背景和半透明白色层混合
        frosted_glass = Image.alpha_composite(blurred_region.convert('RGBA'), glass_layer)

        # 在画布上绘制圆角矩形边框
        draw.rounded_rectangle(card_box, radius=20, outline=(255, 255, 255, 150), width=2)
        # 将制作好的毛玻璃背景粘贴到主画布上
        canvas.paste(frosted_glass, card_box)

        # ---- 2.2. 准备和处理数据 (Prepare and Process Data) ----
        # 获取Mod图标
        mod_icon_url = mod_data['img-url'].split('@')[0]  # 去掉URL中的尺寸限制
        mod_icon = fetch_image(mod_icon_url)
        mod_icon = mod_icon.resize((80, 80), Image.Resampling.LANCZOS)
        # 为图标创建一个圆形遮罩
        mask = Image.new('L', (80, 80), 0)
        draw_mask = ImageDraw.Draw(mask)
        draw_mask.ellipse((0, 0, 80, 80), fill=255)

        # 将图标粘贴到卡片上
        icon_pos = (card_x + 30, card_y + 30)
        canvas.paste(mod_icon, icon_pos, mask)

        # 准备雷达图数据
        radar_labels_cn = ['趣味', '难度', '稳定', '实用', '美观', '平衡', '兼容', '耐玩']
        radar_keys = ['fun', 'difficulty', 'stability', 'practicality', 'aesthetics', 'balance', 'compatibility',
                      'durability']
        radar_values = np.array([mod_data.get(key, 0) for key in radar_keys])
        # 将数据归一化到 0-1 范围 (这里假设最大值约为1200)
        radar_values_normalized = radar_values / 1200.0

        # 根据Mod名字选择一个主题色
        card_color = (0.8, 0.2, 0.2, 1) if 'Touhou' in mod_data['name'] else (0.2, 0.5, 0.8, 1)
        # 创建雷达图
        radar_chart = create_radar_chart(radar_values_normalized, radar_labels_cn, card_color, (300, 300))
        # 粘贴雷达图
        radar_pos = (card_x + (card_width - radar_chart.width) // 2, card_y + 250)
        canvas.paste(radar_chart, radar_pos, radar_chart)

        # ---- 2.3. 在卡片上绘制文本 (Draw Text on the Card) ----
        text_x = icon_pos[0] + 80 + 20  # 图标右侧

        # 绘制Mod名称（使用白色）
        draw.text((text_x, card_y + 40), mod_data['name'].split('] ')[-1], fill=text_colors['name'], font=font_lg_bold)
        # 绘制状态（使用浅蓝色）
        draw.text((text_x, card_y + 80), mod_data['status'], fill=text_colors['status'], font=font_sm)

        # 绘制浏览量
        y_offset = card_y + 140
        draw.text((icon_pos[0], y_offset), f"浏览量: {mod_data['view_count']}", fill=text_colors['view'], font=font_md)
        y_offset += 40  # 为投票图表留空间

        # 绘制投票图表
        draw_vote_chart(draw, icon_pos[0], y_offset, mod_data['votes'], font_sm)
        y_offset += 50  # 投票图表高度

        y_offset = card_y + 500  # 雷达图下方

        # 绘制MC版本信息（标题橙色，内容橙色）
        draw.text((icon_pos[0], y_offset), "支持版本:", fill=text_colors['name'], font=font_md)
        y_offset += 28
        for loader, versions in mod_data['mc_versions'].items():
            line = f"{loader}: {summarize_versions(versions)}"
            draw.text((icon_pos[0], y_offset), line, fill=text_colors['versions'], font=font_sm)
            y_offset += 22

        # 绘制标签：每个独立渲染，不同颜色，无逗号
        y_offset += 10
        # Tags标题

        y_offset += 25

        tag_start_y = y_offset
        current_x = icon_pos[0]
        tag_height = 24
        tag_padding = 10
        for idx, tag in enumerate(mod_data['tags']):
            color_idx = idx % len(tag_colors)
            tag_color = tag_colors[color_idx]

            # 计算标签文本边界
            bbox = draw.textbbox((0, 0), tag, font=font_tag)
            tag_width = bbox[2] - bbox[0] + 16  # 左右padding 8
            tag_rect = (current_x, tag_start_y, current_x + tag_width, tag_start_y + tag_height)

            # 如果下一标签会超出卡片宽度，换行
            if current_x + tag_width > card_x + card_width - 20:
                current_x = icon_pos[0]
                tag_start_y += tag_height + 5

            # 绘制半透明背景矩形
            draw.rounded_rectangle(tag_rect, radius=8, fill=(*tag_color, 100))
            # 绘制阴影
            shadow_offset = (1, 1)
            draw.text((current_x + 8 + shadow_offset[0], tag_start_y + 4 + shadow_offset[1]), tag, fill=(0, 0, 0, 128), font=font_tag)
            # 绘制主文本
            draw.text((current_x + 8, tag_start_y + 4), tag, fill=(255, 255, 255), font=font_tag)

            current_x += tag_width + tag_padding

        y_offset = tag_start_y + tag_height + 10 if len(mod_data['tags']) > 0 else y_offset + 10

        y_offset += 20
        # 绘制作者（浅黄色）
        draw.text((icon_pos[0], y_offset), f"作者: {summarize_list(mod_data['authors'], 35)}", fill=text_colors[
            'authors'],
                  font=font_sm)

    # ---- 3. 合成并保存 (Composite and Save) ----
    # 将绘制了所有元素的画布合成到渐变背景上
    final_image = Image.alpha_composite(background.convert('RGBA'), canvas)

    # 保存最终图片
    output_filename = "mod_showcase.png"
    final_image.save(output_filename)
    print(f"图片已成功生成并保存为 '{output_filename}'")


if __name__ == "__main__":
    # 当脚本直接被执行时，调用主函数
    generate_mod_cards(MOD_DATA)