"""
预设管理器
管理裁剪预设的创建、保存、加载
预设 = 输出画布尺寸 + 脸部目标位置
"""
import os
import json
from typing import List, Dict, Optional


PRESETS_FILE = "presets.json"


def load_presets() -> List[dict]:
    if not os.path.exists(PRESETS_FILE):
        _create_default_preset()
    try:
        with open(PRESETS_FILE, "r", encoding="utf-8") as f:
            presets = json.load(f)
        if not presets:
            _create_default_preset()
            return load_presets()
        return presets
    except Exception:
        return [_default_preset_data()]


def save_presets(presets: List[dict]):
    with open(PRESETS_FILE, "w", encoding="utf-8") as f:
        json.dump(presets, f, indent=2, ensure_ascii=False)


def _default_preset_data() -> dict:
    return {
        "name": "默认 1280x1280",
        "w": 1280, "h": 1280,
        "face_x": 460, "face_y": 250,
        "face_w": 360, "face_h": 420,
        "sharpen": 0.9,
    }


def _create_default_preset():
    save_presets([_default_preset_data()])


def add_preset(name: str, w: int, h: int,
               face_x: int, face_y: int,
               face_w: int, face_h: int,
               sharpen: float = 0.9) -> dict:
    preset = {
        "name": name, "w": w, "h": h,
        "face_x": face_x, "face_y": face_y,
        "face_w": face_w, "face_h": face_h,
        "sharpen": sharpen,
    }
    presets = load_presets()
    presets.append(preset)
    save_presets(presets)
    return preset


def update_preset(index: int, preset: dict):
    presets = load_presets()
    if 0 <= index < len(presets):
        presets[index] = preset
        save_presets(presets)


def delete_preset(index: int):
    presets = load_presets()
    if 0 <= index < len(presets) and len(presets) > 1:
        presets.pop(index)
        save_presets(presets)
