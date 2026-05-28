"""
文件管理模块
负责扫描输入文件夹、加载PSD/PNG、分析图层结构、分组去重
"""
import os
import hashlib
import json
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from config import AppConfig


class FileType(Enum):
    PSD = "psd"
    PNG = "png"


@dataclass
class LayerInfo:
    name: str
    index: int
    visible: bool
    is_group: bool = False


@dataclass
class SpriteEntry:
    """立绘条目，存储文件信息和检测状态"""
    file_path: str
    file_type: FileType
    group_id: str = ""           # 分组ID（同立绘染色变体共享）
    is_group_reference: bool = True  # 是否是组的参考图

    # 源文件信息
    src_width: int = 0
    src_height: int = 0
    layers: List[LayerInfo] = field(default_factory=list)
    layer_structure_hash: str = ""  # 图层结构哈希，用于分组

    # 脸部检测结果 (源图像素坐标)
    face_detected: bool = False
    detection_mode: str = ""
    face_rect: Optional[Tuple[int,int,int,int]] = None  # (x, y, w, h)

    # 处理参数
    scale: float = 1.0
    translate_x: float = 0.0
    translate_y: float = 0.0
    calculated: bool = False

    # 状态
    confirmed: bool = False
    needs_review: bool = False
    error_message: str = ""

    @property
    def basename(self) -> str:
        return os.path.basename(self.file_path)

    @property
    def is_psd(self) -> bool:
        return self.file_type == FileType.PSD

    @property
    def is_png(self) -> bool:
        return self.file_type == FileType.PNG

    @property
    def face_center(self) -> Optional[Tuple[float, float]]:
        if self.face_rect:
            return (self.face_rect[0] + self.face_rect[2]/2,
                    self.face_rect[1] + self.face_rect[3]/2)
        return None


class FileManager:
    """文件管理器"""

    SUPPORTED_EXTENSIONS = {'.psd', '.png'}

    def __init__(self, config: AppConfig):
        self.config = config
        self.entries: List[SpriteEntry] = []
        self.groups: Dict[str, List[SpriteEntry]] = {}

    def scan_folder(self, folder_path: str) -> List[SpriteEntry]:
        """扫描文件夹, 返回所有立绘条目"""
        self.entries = []
        if not os.path.isdir(folder_path):
            return self.entries

        for filename in sorted(os.listdir(folder_path)):
            ext = os.path.splitext(filename)[1].lower()
            if ext not in self.SUPPORTED_EXTENSIONS:
                continue

            file_path = os.path.join(folder_path, filename)
            file_type = FileType.PSD if ext == '.psd' else FileType.PNG

            entry = SpriteEntry(file_path=file_path, file_type=file_type)

            try:
                self._analyze_file(entry)
            except Exception as e:
                entry.error_message = f"文件分析失败: {e}"
                entry.needs_review = True

            self.entries.append(entry)

        # 分组
        self._group_entries()

        return self.entries

    def _analyze_file(self, entry: SpriteEntry):
        """分析文件基本信息"""
        if entry.is_psd:
            self._analyze_psd(entry)
        else:
            self._analyze_png(entry)

    def _analyze_psd(self, entry: SpriteEntry):
        """分析PSD文件的图层结构"""
        try:
            from psd_tools import PSDImage
            psd = PSDImage.open(entry.file_path)
            entry.src_width = psd.width
            entry.src_height = psd.height

            layer_infos = []
            for i, layer in enumerate(psd.descendants()):
                if not layer.is_group():
                    layer_infos.append(LayerInfo(
                        name=layer.name,
                        index=i,
                        visible=layer.visible
                    ))

            entry.layers = layer_infos

            # 计算图层结构哈希
            structure = json.dumps([
                {"name": l.name, "visible": l.visible}
                for l in layer_infos
            ], ensure_ascii=False)
            entry.layer_structure_hash = hashlib.md5(
                structure.encode('utf-8')
            ).hexdigest()

        except ImportError:
            entry.error_message = "psd-tools 未安装，无法分析PSD"
            entry.needs_review = True
        except Exception as e:
            entry.error_message = f"PSD分析错误: {e}"
            entry.needs_review = True

    def _analyze_png(self, entry: SpriteEntry):
        """分析PNG文件基本信息"""
        try:
            from PIL import Image
            img = Image.open(entry.file_path)
            entry.src_width, entry.src_height = img.size
            img.close()
            entry.layer_structure_hash = hashlib.md5(
                f"png:{entry.src_width}x{entry.src_height}".encode()
            ).hexdigest()
        except Exception as e:
            entry.error_message = f"PNG分析错误: {e}"
            entry.needs_review = True

    def _group_entries(self):
        """将条目按图层结构相似度分组"""
        self.groups = {}
        hash_groups: Dict[str, List[SpriteEntry]] = {}

        for entry in self.entries:
            h = entry.layer_structure_hash
            if h not in hash_groups:
                hash_groups[h] = []
            hash_groups[h].append(entry)

        group_idx = 0
        for entries in hash_groups.values():
            group_id = f"group_{group_idx:03d}"
            group_idx += 1
            self.groups[group_id] = entries

            entries[0].is_group_reference = True
            for e in entries:
                e.group_id = group_id

    def get_group_reference(self, group_id: str) -> Optional[SpriteEntry]:
        """获取组的参考条目"""
        group = self.groups.get(group_id, [])
        for entry in group:
            if entry.is_group_reference:
                return entry
        return group[0] if group else None

    def apply_to_group(self, group_id: str, reference: SpriteEntry):
        """将参考图的检测结果应用到同组其他文件"""
        group = self.groups.get(group_id, [])
        for entry in group:
            if entry is not reference and not entry.face_detected:
                entry.face_rect = reference.face_rect
                entry.detection_mode = "inherited"
                entry.face_detected = True

    def get_statistics(self) -> Dict[str, int]:
        """获取统计信息"""
        stats = {
            "total": len(self.entries),
            "psd": sum(1 for e in self.entries if e.is_psd),
            "png": sum(1 for e in self.entries if e.is_png),
            "groups": len(self.groups),
            "detected": sum(1 for e in self.entries if e.face_detected),
            "confirmed": sum(1 for e in self.entries if e.confirmed),
            "errors": sum(1 for e in self.entries if e.error_message),
        }
        return stats
