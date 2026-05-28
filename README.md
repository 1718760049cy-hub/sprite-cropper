# 立绘裁剪工具 (Sprite Cropper)

批量处理游戏立绘的桌面工具。**Python 做界面 + 脸部检测 + 裁剪，Photoshop 仅做智能锐化（可选）。**

![Python](https://img.shields.io/badge/Python-3.9+-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)

## ✨ 功能

- 📁 支持 PSD / PNG 批量导入
- 🔍 动漫脸部自动检测（OpenCV cascade）
- ✏️ 预览每张图的脸部检测结果，可手动微调
- ✂️ 纯 Python 裁剪：脸部定位 → 等比缩放 → 输出固定尺寸
- 🎨 PS 智能锐化（最后一步，可跳过）
- 📐 预设管理：从已有的成品 PNG 一键导入脸部位置
- 🔲 PSD 自动隐藏背景图层和水印图层后导出 PNG

## 📸 界面预览

启动后你会看到：

- **顶部**：预设选择栏（可新建/删除/从 PNG 导入）
- **文件夹栏**：选择 PSD/PNG 所在目录
- **操作按钮**：导出 PSD → 脸部检测 → Python 裁剪 → PS 锐化
- **左侧**：文件列表（带检测状态标记）
- **右侧**：预览窗口（脸部框可手动调整）

## 🚀 快速开始

### 环境要求

| 组件 | 版本要求 | 必要性 |
|------|---------|--------|
| Python | 3.9+ | 必须 |
| Windows | 10/11 | 必须（PS COM 接口限制） |
| Photoshop | 2023+ | 可选（仅智能锐化和 PSD 导出时需） |

### 1. 安装 Python

如果你还没有 Python，去 [python.org](https://www.python.org/downloads/) 下载安装。安装时**勾选「Add Python to PATH」**。

验证安装是否成功：

```bash
python --version
```

### 2. 下载项目

```bash
git clone https://github.com/你的用户名/sprite-cropper.git
cd sprite-cropper
```

或者直接下载 ZIP 解压。

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

如果安装 `opencv-python` 失败，可以试试：

```bash
pip install opencv-python-headless
```

### 4. 配置文件（首次运行自动生成）

首次运行时会自动生成 `config.json` 和 `presets.json`，不必手动创建。

也可以参考 `config.example.json` 和 `presets.example.json` 了解格式。

### 5. 启动

```bash
python main.py
```

## 📖 使用流程

1. **选文件夹**：点击「浏览」选择包含立绘 PSD/PNG 的目录
2. **导 PSD**（如有 PSD 文件）：点「导出 PSD→PNG」，程序会通过 PS 自动隐藏背景/水印图层并导出为 PNG
3. **脸部检测**：点「批量脸部检测」，程序自动识别每张图的脸部位置
4. **逐张检查**：左侧点文件名预览，不对的话右侧手动调 x/y/w/h 数值
5. **Python 裁剪**：点按钮，选输出目录，程序按预设尺寸缩放定位裁出
6. **PS 锐化（可选）**：对裁剪后的 PNG 做智能锐化，需要 Photoshop 运行中

## 🔧 预设说明

预设决定了输出画布尺寸和脸部在画布中的目标位置。

- **手动创建**：点 `+` 输入画布尺寸和脸部目标位置
- **从 PNG 导入**：选一张已经裁好的成品立绘，程序自动读取画布尺寸 + 检测脸部位置并保存为预设

预设保存在 `presets.json`，可以手动编辑。

## 📁 项目结构

```
sprite_cropper/
├── main.py                 # GUI 主程序
├── config.py               # 配置数据模型
├── face_detector.py        # 脸部检测引擎（OpenCV 级联 + 模板匹配）
├── image_processor.py      # Python 裁剪处理
├── file_manager.py         # 文件扫描、图层分析、分组
├── preset_manager.py       # 预设增删改查
├── ps_automation.py        # Photoshop COM 自动化（JSX 驱动）
├── requirements.txt        # Python 依赖
├── config.example.json     # 配置文件示例
├── presets.example.json    # 预设文件示例
└── resources/
    └── lbpcascade_animeface.xml  # 动漫脸部检测模型
```

> `face_detector.py` 和 `file_manager.py` 包含了更完整的模块化设计（含模板匹配、手动标点、文件分组等功能），目前主程序尚未完全接入，这些是后续版本重构的基础设施。

## 🐛 常见问题

### 脸部检测不到？

- 确认图片里确实有完整的角色脸部
- 试试手动调检测参数：在 `_detect_all()` 方法里修改 `scaleFactor` 和 `minNeighbors`
- 手动在预览区输入脸部坐标 (x, y, w, h)

### Photoshop 连接失败？

1. 确保 Photoshop 已启动
2. 用管理员权限运行一次 PS
3. 点「检查 PS」按钮诊断
4. 如果 `pywin32` 安装有问题：`pip install pywin32` 后重启

### pip install 报错？

如果 `pywin32` 安装失败，去 [这里](https://github.com/mhammond/pywin32/releases) 下载对应 Python 版本的 `.whl` 文件手动安装。

### PSD 图层识别不准确？

在 `config.json` 中修改 `bg_layer_patterns` 和 `wm_layer_patterns`，添加你自己 PSD 中背景图层和水印图层的命名关键词。

## 🗺️ 路线图

- [ ] 将 `face_detector.py` 和 `file_manager.py` 完全接入主程序
- [ ] 支持更多输出格式（WebP、JPG）
- [ ] 批量处理进度可暂停/恢复
- [ ] 多语言支持（English UI）
- [ ] 打包为 exe 独立运行

## 📄 许可证

MIT License · 详见 [LICENSE](LICENSE)

## 🙏 致谢

- 动漫脸部检测模型来自 [nagadomi/lbpcascade_animeface](https://github.com/nagadomi/lbpcascade_animeface)
- GUI 框架：[customtkinter](https://github.com/TomSchimansky/CustomTkinter)
