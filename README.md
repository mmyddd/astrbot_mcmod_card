# MCMod Card

AstrBot 插件：检测 MC 百科（mcmod.cn）链接，按 MC 百科自己的排版逻辑解析，
并以**合并转发聊天记录**的形式分段发送。

支持模组（`/class/`）与整合包（`/modpack/`）页面。

## 效果

发送一条 `https://www.mcmod.cn/class/2524.html`，机器人会发出两条合并转发记录：

```text
【记录 1：概览】
├─ 1.1  [封面图] [GCY] Gregicality Legacy / 停更 · 开源 / 支持的MC版本: Forge: 1.12.2
├─ 1.2  热度: 5.0（名扬天下）/ 昨日指数: 951 / 昨日平均指数: 38.131 / 浏览量: 753.59万 / …
│       [评分雷达图]
└─ 1.3  标签（6）: 格雷 / 格雷科技 / …   作者（11）: decal06、hjaeee、…

【记录 2：正文（按标题分段，可能拆成多条记录）】
├─ 1. 写在开头
├─ 2. 版本注意事项
│    ├─ 2.1 注1：…
│    └─ 2.2 注2：…
├─ 3. 本模组资料常见问题
├─ 4. 模组简介
│    ├─ 4.1 …
│    └─ 4.2 该附属模组新增的内容大致包括：
├─ 5. 模组集成联动
│    ├─ 5.1 CEU 模组的全部功能（加入能源转换器，实现 FE 与 EU 的相互转换）；
│    ├─ 5.2 无中生有联动（对 GTCE 新增矿物的支持）；
│    └─ …  5.10 CraftTweaker 联动（本模组支持 CrT 脚本）。
└─ 6. 画廊
     ├─ 6.1 [图片] 新的多方块
     ├─ 6.2 [图片] 中央监控器
     └─ …
```

**通用规则只有两条：**

1. **标题 → 子转发节点**：MC 百科正文里 `common-text-title` 的每一个标题成为一个转发节点，
   标题与下一个同级标题之间的内容（段落、列表项、图片）按原始顺序**再各套一层子转发**，
   不针对「画廊」「列表」等做任何特殊处理——列表项逐条成节点，图片逐张成节点。
2. **标题层级决定编号**：MC 百科的标题自带 1/2/3 级（`common-text-title-1/2/3`），
   插件按同样的层级编号与嵌套，例如整合包页面：

   ```text
   3. 内容展示
      ├─ 3.1. 科技模块
      │    ├─ 3.1.1. 机械动力（Create）
      │    │    └─ 整合包基于 6.0+ 版本的机械动力，及诸多附属……
      │    ├─ 3.1.2. 格雷科技（Gregtech）
      │    └─ 3.1.4. 应用能源2（Applied Energistics 2）
      ├─ 3.2. 魔法模块
      └─ 3.3. 冒险模块
   ```

## 平台支持

| 平台 | 行为 |
| --- | --- |
| aiocqhttp（NapCat / Lagrange 等 OneBot v11） | 原生合并转发聊天记录 |
| Telegram / QQ 官方 / Discord / 其他 | 自动降级：按同样的顺序逐条发送普通文字与图片（可选带段落编号） |

合并转发是 OneBot v11 的能力，其他平台无法渲染，插件会自动降级而不是丢内容。

## 嵌套层级

QQ 最多支持三层嵌套转发：`[记录] → [标题节点] → [子节点]`。
插件按这个上限构造节点树：**三层以内保持真实嵌套**（例如 `3. 内容展示` → `3.1. 科技模块` → `3.1.1. 机械动力`），
超出三层的部分折叠为最近一层节点内的「标题行 + 缩进正文」，层级关系仍然可读；
单条转发记录超过节点上限时会按**标题边界**拆成多条记录依次发送
（不会把一个标题的子节点拆到两条记录里）。

## 配置

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `cache_ttl` | `86400` | 页面解析结果缓存秒数，`0` 关闭缓存 |
| `forward_overview` | `true` | 概览（ID/数据/标签）用合并转发发送 |
| `forward_body` | `true` | 正文用合并转发发送 |
| `node_name` / `node_uin` | `MC百科` / `10000` | 转发节点展示用的昵称与账号 |
| `max_nodes_per_message` | `40` | 单条转发记录最大节点数，超出按标题边界拆分 |
| `max_images` | `40` | 单次最多发送的正文图片数，`0` 表示不发图 |
| `overview_split` | `true` | 概览拆成 1/2/3 三个子节点 |
| `include_cover` | `true` | 概览中发送封面图 |
| `include_radar` | `true` | 概览中发送评分雷达图 |
| `include_images` | `true` | 发送正文图片 |
| `max_images` | `40` | 单次最多发送的正文图片数，`0` 表示不发图 |
| `number_prefix` | `true` | 降级为普通消息时是否加段落编号 |
| `fallback_to_text` | `true` | 平台不支持合并转发时降级为普通消息 |
| `font_path` | 空 | 雷达图字体，留空用内置 `resource/msyh.ttf` |

## 实现结构

```text
main.py                 插件入口：解析 → 构建转发树 → 发送/降级
data/body_parser.py     MC 百科正文解析（标题 / 段落 / 列表 / 图片，保留原始顺序）
data/meta_parser.py     页面头部字段解析（class 与 modpack 同构，共用一套选择器）
data/models.py          Meta / Section / Block / Figure 数据模型（含缓存序列化）
data/html_scraper.py    抓取与 schema 版本化缓存、图片批量下载
render/tree.py          通用「标题 → 子转发」树构造、深度折叠、记录分片
render/forward.py       转发树 → AstrBot 组件（Comp.Node / Comp.Nodes）与文本降级
img/render_cover.py     封面缩略图（252×252 PNG）
img/render_radar.py     八维评分雷达图（纯 PIL，无 matplotlib 依赖）
tests/                  pytest 用例与真实页面 fixtures
```

## 开发

```powershell
pip install -r requirements.txt
python -m pytest -q
```

测试使用 `tests/fixtures/` 中的真实页面快照，离线运行、不发起网络请求。
