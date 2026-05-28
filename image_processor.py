"""
Python图像处理模块
纯Python处理PNG立绘：缩放、定位、裁剪、锐化
不再依赖Photoshop进行最终处理
"""
import os
import threading
from typing import List, Optional, Callable, Dict

from PIL import Image, ImageFilter

from config import AppConfig
from file_manager import SpriteEntry


def apply_sharpen(img: Image.Image, amount: float = 0.9) -> Image.Image:
    """
    PIL智能锐化（模拟PS智能锐化效果）
    amount: 锐化强度 (0.0 ~ 5.0), PS参数0.9 → percent=90
    """
    if amount <= 0:
        return img
    percent = int(amount * 100)
    radius = 1.0
    threshold = 0
    return img.filter(ImageFilter.UnsharpMask(
        radius=radius, percent=percent, threshold=threshold
    ))


def process_single(
    input_path: str,
    output_path: str,
    entry: SpriteEntry,
    config: AppConfig,
) -> bool:
    """
    处理单个立绘PNG文件
    流程: 加载 → 缩放 → 定位到输出画布 → 锐化 → 保存
    """
    try:
        source = Image.open(input_path)
        if source.mode != 'RGBA':
            source = source.convert('RGBA')
    except Exception:
        return False

    src_w, src_h = entry.src_width, entry.src_height
    scale = entry.scale if entry.scale > 0 else 1.0
    new_w = max(1, int(src_w * scale))
    new_h = max(1, int(src_h * scale))

    scaled = source.resize((new_w, new_h), Image.LANCZOS)
    source.close()

    canvas = Image.new("RGBA",
                       (config.output_width, config.output_height),
                       (0, 0, 0, 0))

    paste_x = int((config.output_width - new_w) / 2 + entry.translate_x)
    paste_y = int((config.output_height - new_h) / 2 + entry.translate_y)

    canvas.paste(scaled, (paste_x, paste_y), scaled)

    canvas = apply_sharpen(canvas, config.sharpen_amount)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    canvas.save(output_path, "PNG", optimize=True)
    canvas.close()

    return True


def process_batch(
    input_dir: str,
    output_dir: str,
    entries: List[SpriteEntry],
    config: AppConfig,
) -> Dict[str, bool]:
    """批量处理立绘文件"""
    results = {}
    total = len(entries)

    for i, entry in enumerate(entries):
        basename = os.path.splitext(entry.basename)[0]
        input_path = os.path.join(input_dir, entry.basename)
        output_path = os.path.join(output_dir, f"{basename}.png")

        if not os.path.exists(input_path):
            ply_path = os.path.join(input_dir, f"{basename}.png")
            if os.path.exists(ply_path):
                input_path = ply_path
            else:
                results[entry.file_path] = False
                continue

        success = process_single(input_path, output_path, entry, config)
        results[entry.file_path] = success

    return results


class ImageProcessor:
    """图像处理器（含进度回调）"""

    def __init__(self, config: AppConfig):
        self.config = config
        self._progress_callback: Optional[Callable] = None
        self._log_callback: Optional[Callable] = None

    def set_progress_callback(self, callback: Callable):
        self._progress_callback = callback

    def set_log_callback(self, callback: Callable):
        self._log_callback = callback

    def _progress(self, current: int, total: int, message: str = ""):
        if self._progress_callback:
            self._progress_callback(current, total, message)

    def _log(self, msg: str):
        if self._log_callback:
            self._log_callback(msg)

    def process_entries(
        self,
        input_dir: str,
        output_dir: str,
        entries: List[SpriteEntry],
    ) -> Dict[str, bool]:
        results = {}
        total = len(entries)

        for i, entry in enumerate(entries):
            self._progress(i + 1, total, f"处理中: {i+1}/{total}")
            self._log(f"处理: {entry.basename}")

            input_path = os.path.join(input_dir, entry.basename)
            if not os.path.exists(input_path):
                alt_path = os.path.join(input_dir,
                    os.path.splitext(entry.basename)[0] + ".png")
                if os.path.exists(alt_path):
                    input_path = alt_path
                else:
                    self._log(f"跳过 (文件不存在): {entry.basename}")
                    results[entry.file_path] = False
                    continue

            basename = os.path.splitext(entry.basename)[0]
            output_path = os.path.join(output_dir, f"{basename}.png")

            success = process_single(input_path, output_path, entry, self.config)
            results[entry.file_path] = success
            if not success:
                self._log(f"失败: {entry.basename}")

        self._progress(total, total, "处理完成!")
        return results

    def process_threaded(self, input_dir: str, output_dir: str,
                          entries: List[SpriteEntry]) -> threading.Thread:
        thread = threading.Thread(
            target=self.process_entries,
            args=(input_dir, output_dir, entries),
            daemon=True
        )
        thread.start()
        return thread
