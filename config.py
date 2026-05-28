"""
配置管理模块
管理输出尺寸、脸部区域、锐化参数、图层检测规则等用户设置
"""
import json
import os
from dataclasses import dataclass, field, asdict
from typing import List, Tuple


@dataclass
class AppConfig:
    # 输出设置
    output_width: int = 1280
    output_height: int = 1280

    # 脸部目标区域（在输出画布中的位置和大小）
    face_zone_x: int = 460
    face_zone_y: int = 250
    face_zone_w: int = 360
    face_zone_h: int = 420

    # 智能锐化参数
    sharpen_amount: float = 0.9

    # 检测模式: opencv / manual_point / manual_box
    detection_mode: str = "opencv"

    # 路径记忆
    last_input_folder: str = ""
    last_output_folder: str = ""

    # 图层检测关键词（逗号分隔）
    bg_layer_patterns: str = "背景,bg,background,底色,底图,灰色,灰底,back"
    wm_layer_patterns: str = "水印,watermark,logo,版权,标"

    # 模板匹配阈值
    template_match_threshold: float = 0.7

    # 外观主题: dark / light / system
    appearance_mode: str = "dark"
    color_theme: str = "blue"

    @property
    def face_zone(self) -> Tuple[int, int, int, int]:
        return (self.face_zone_x, self.face_zone_y,
                self.face_zone_w, self.face_zone_h)

    @property
    def face_center(self) -> Tuple[float, float]:
        return (self.face_zone_x + self.face_zone_w / 2,
                self.face_zone_y + self.face_zone_h / 2)

    @property
    def bg_patterns_list(self) -> List[str]:
        return [p.strip().lower() for p in self.bg_layer_patterns.split(",") if p.strip()]

    @property
    def wm_patterns_list(self) -> List[str]:
        return [p.strip().lower() for p in self.wm_layer_patterns.split(",") if p.strip()]

    def save(self, path: str = "config.json"):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str = "config.json") -> "AppConfig":
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls(**data)
        config = cls()
        config.save(path)
        return config


# 默认配置路径
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

# 素材目录
RESOURCES_DIR = os.path.join(os.path.dirname(__file__), "resources")
CASCADE_PATH = os.path.join(RESOURCES_DIR, "lbpcascade_animeface.xml")
CASCADE_URL = (
    "https://raw.githubusercontent.com/nagadomi/"
    "lbpcascade_animeface/master/lbpcascade_animeface.xml"
)
