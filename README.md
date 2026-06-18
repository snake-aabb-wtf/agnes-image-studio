# Agnes Image Studio ✦

输入 **API Key** 和 **Prompt**，调用 [Agnes Image 2.1 Flash](https://agnes-ai.com/doc/agnes-image-21-flash) 生成图片的专业桌面应用。

基于 **PySide6 (Qt6)** 构建，支持文生图、图生图、变体生成、批量生成、历史画廊等完整能力。

---

## ✨ 功能特性

| 能力 | 说明 |
|------|------|
| 🎨 **文生图 (txt2img)** | 输入提示词，生成图片 |
| 🖼️ **图生图 (img2img)** | 拖入参考图，按提示词变换（保留构图改风格） |
| 🎲 **变体生成** | 右键历史图「以此图生成变体」，以它为参考再创作 |
| 🔢 **批量生成** | 一次生成 1–4 张，结果可切换查看 |
| 📚 **历史画廊** | SQLite 持久化，重启不丢失；缩略图浏览、搜索、收藏 |
| 📋 **提示词模板** | 内置 10 种风格（电影感/动漫/写实/水彩/赛博朋克…）一键插入 |
| ⭐ **提示词收藏** | 收藏常用 prompt，随时复用 |
| 🔍 **智能预览** | 鼠标滚轮缩放、拖拽平移、双击自适应、1:1 实际尺寸 |
| 📎 **图片操作** | 复制到剪贴板、另存为、打开所在文件夹、复制提示词 |
| ⚙️ **设置面板** | 可调超时 (60–360s)、默认尺寸、是否保存 API Key |
| 🌙 **深色主题** | Catppuccin Mocha 配色，护眼美观 |

---

## 🚀 快速开始

### 方式一：一键启动（推荐）

双击 **`run.bat`**，首次运行会自动创建虚拟环境并安装依赖，之后直接启动 GUI。

### 方式二：手动

```bash
# 1. 创建虚拟环境
python -m venv .venv

# 2. 安装依赖
.venv\Scripts\pip install -r requirements.txt

# 3. 启动 GUI
.venv\Scripts\python agnes_gui.py
```

### 获取 API Key

前往 [Agnes AI](https://agnes-ai.com/) 注册，在控制台创建免费 API Key。

---

## 🖥️ 使用指南

### 三栏界面

```
┌─────────────┬─────────────────────────┬────────────┐
│  左：参数面板 │    中：大图预览          │ 右：历史画廊 │
│             │                         │            │
│ • API Key   │  滚轮缩放/拖拽平移        │ 缩略图列表   │
│ • 模式切换   │  双击自适应              │ 搜索/收藏   │
│ • Prompt    │                         │ 右键菜单：   │
│ • 模板/收藏  │  revised_prompt 信息     │  复用/变体   │
│ • 尺寸/张数  │                         │  收藏/删除   │
│ • 参考图拖拽  │  本次结果切换(批量时)     │            │
│ • 生成按钮   │                         │            │
└─────────────┴─────────────────────────┴────────────┘
```

### 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl + Enter` | 生成图片 |
| 双击预览区 | 自适应窗口大小 |

### 操作流程

**文生图：** 输入 API Key → 输入提示词（可套模板）→ 选尺寸 → 点「生成图片」

**图生图：** 点「图生图」模式 → 拖入参考图 → 输入变换提示词（如"水彩画风格"）→ 生成

**生成变体：** 右键历史图 → 「以此图生成变体」→ 自动载入参考图，修改提示词后生成

---

## 📁 文件结构

```
Agnes\
├── .venv\                  # 虚拟环境（所有依赖在此）
├── agnes_gui.py            # 主程序（PySide6 GUI）
├── agnes_client.py         # API 客户端封装（httpx）
├── agnes_store.py          # 历史画廊存储（SQLite）+ 配置
├── requirements.txt        # 依赖清单
├── run.bat                 # 一键启动
└── README.md
```

**用户数据**（图片、历史、配置）存放在：
`%LOCALAPPDATA%\AgnesImageStudio\`（Win），内含 `images/`、`thumbs/`、`history.db`、`config.json`。

---

## 🔌 API 接口细节

封装层 `agnes_client.py` 正确处理了官方文档的全部字段：

| 功能 | 实现要点 |
|------|---------|
| 模型 | `agnes-image-2.1-flash` |
| 文生图 | `model` + `prompt` + `size` + `n` |
| 图生图 | `extra_body.image = [url 或 data:image/png;base64,...]` |
| URL 输出 | `extra_body.response_format = "url"` |
| base64 输出 | 顶层 `return_base64 = true`（**不放** extra_body） |
| 自定义尺寸 | 任意 `WIDTHxHEIGHT` |
| 超时 | 60–360s 可调（默认 180s） |
| 响应解析 | `data[].url`、`data[].b64_json`、`revised_prompt`、`created` |

---

## 🛠️ 开发说明

### 依赖

| 包 | 用途 |
|----|------|
| PySide6 | Qt6 GUI 框架 |
| httpx | HTTP 客户端（连接池、超时、错误处理） |
| Pillow | 图片处理（缩略图、Data URI 编解码、尺寸读取） |
| qtawesome | FontAwesome 图标库 |
| platformdirs | 跨平台数据目录定位 |

### 运行 CLI 版本（无 GUI）

```bash
.venv\Scripts\python agnes_client.py -k YOUR_KEY -p "a cute corgi" -s 1024x1024
```

---

## ❓ 常见问题

**Q: 生成很慢 / 超时？**
A: 图片生成通常需 20–40s，图生图可能更久。在「设置」中把超时调到 360s。

**Q: 如何更换 API Key？**
A: 直接在左上角输入框修改，勾选设置里的「保存」会自动持久化。

**Q: 历史图片存在哪？**
A: `%LOCALAPPDATA%\AgnesImageStudio\`。卸载程序不会删除，可手动清理。

**Q: 图生图支持哪些输入？**
A: 本地图片（自动转 base64 Data URI）或公共图片 URL。
