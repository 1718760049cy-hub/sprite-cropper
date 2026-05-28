"""
人脸检测模块
支持三种检测模式:
1. OpenCV动漫人脸检测 (自动)
2. 手动标点模式 (用户点击脸部中心, 模板匹配用于同类文件)
3. 手动框选模式 (用户绘制脸部区域)
"""
import os
import cv2
import numpy as np
from typing import Optional, Tuple, List
from PIL import Image
from config import AppConfig, CASCADE_PATH, CASCADE_URL, RESOURCES_DIR


def ensure_cascade() -> bool:
    """确保级联文件存在, 不存在则自动下载"""
    if os.path.exists(CASCADE_PATH):
        return True
    try:
        import urllib.request
        os.makedirs(RESOURCES_DIR, exist_ok=True)
        urllib.request.urlretrieve(CASCADE_URL, CASCADE_PATH)
        return os.path.exists(CASCADE_PATH)
    except Exception:
        return False


class FaceDetector:
    """人脸检测器，支持三种检测模式"""

    def __init__(self, config: AppConfig):
        self.config = config
        self._cascade = None
        self._manual_point: Optional[Tuple[int, int]] = None
        self._manual_rect: Optional[Tuple[int, int, int, int]] = None
        self._template: Optional[np.ndarray] = None
        self._template_point: Optional[Tuple[int, int]] = None
        self._init_opencv()

    def _init_opencv(self):
        """初始化OpenCV级联分类器（处理中文路径兼容性）"""
        if not ensure_cascade():
            self._cascade = None
            return
        try:
            import tempfile
            import shutil
            temp_path = os.path.join(
                tempfile.gettempdir(), "_animeface_cascade.xml")
            if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                shutil.copy2(CASCADE_PATH, temp_path)
            self._cascade = cv2.CascadeClassifier(temp_path)
            if self._cascade.empty():
                self._cascade = None
        except Exception:
            self._cascade = None

    @property
    def is_opencv_ready(self) -> bool:
        return self._cascade is not None

    # ========== 模式 A: OpenCV 自动检测 ==========

    def detect_opencv(self, image: np.ndarray, restrict_region: Optional[Tuple[int,int,int,int]] = None) -> Optional[Tuple[int,int,int,int]]:
        """
        OpenCV动漫人脸检测
        image: BGR numpy数组
        restrict_region: 可选限定区域 (x,y,w,h), 只在此区域内检测
        返回: (x, y, w, h) 或 None
        """
        if self._cascade is None:
            return None

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # 多尺度检测
        faces = None
        for scale in [1.01, 1.05, 1.1, 1.15, 1.2]:
            faces = self._cascade.detectMultiScale(
                gray, scaleFactor=scale, minNeighbors=5,
                minSize=(50, 50), maxSize=(600, 600)
            )
            if len(faces) > 0:
                break

        if faces is None or len(faces) == 0:
            return None

        if restrict_region:
            rx, ry, rw, rh = restrict_region
            faces_in_region = []
            for (x, y, w, h) in faces:
                cx, cy = x + w/2, y + h/2
                if rx <= cx <= rx + rw and ry <= cy <= ry + rh:
                    faces_in_region.append((x, y, w, h))
            if faces_in_region:
                faces = np.array(faces_in_region)

        # 如果有多个检测结果, 取面积最大的
        if len(faces) > 1:
            best = max(faces, key=lambda f: f[2] * f[3])
        else:
            best = faces[0]
        return tuple(int(v) for v in best)

    # ========== 模式 B: 手动标点 + 模板匹配 ==========

    def set_manual_point(self, point: Tuple[int, int], image: np.ndarray,
                         template_half_size: int = 120):
        """
        设置手动标点, 并提取模板用于同类文件匹配
        point: (x, y) 脸部中心点
        image: 源图像
        template_half_size: 模板区域半径
        """
        h, w = image.shape[:2]
        px, py = int(point[0]), int(point[1])

        self._manual_point = (px, py)

        # 提取模板区域
        x1 = max(0, px - template_half_size)
        y1 = max(0, py - template_half_size)
        x2 = min(w, px + template_half_size)
        y2 = min(h, py + template_half_size)
        if x2 > x1 and y2 > y1:
            self._template = image[y1:y2, x1:x2].copy()
            self._template_point = (px - x1, py - y1)

    def match_template(self, image: np.ndarray) -> Optional[Tuple[int,int,int,int]]:
        """
        使用已保存的模板在目标图像中搜索匹配位置
        返回脸部矩形: (x, y, w, h)
        """
        if self._template is None or self._template_point is None:
            return None

        # 模板匹配
        result = cv2.matchTemplate(image, self._template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val < self.config.template_match_threshold:
            return None

        # 计算脸部中心
        mx = max_loc[0] + self._template_point[0]
        my = max_loc[1] + self._template_point[1]

        # 估算脸部矩形
        th, tw = self._template.shape[:2]
        fw = int(tw * 0.6)
        fh = int(th * 0.8)
        x = int(mx - fw / 2)
        y = int(my - fh / 2)

        return (x, y, fw, fh)

    # ========== 模式 C: 手动框选 ==========

    def set_manual_rect(self, rect: Tuple[int, int, int, int]):
        """设置手动框选区域 (x, y, w, h)"""
        self._manual_rect = tuple(int(v) for v in rect)

    def get_manual_rect_face(self) -> Optional[Tuple[int,int,int,int]]:
        """获取手动框选的脸部矩形"""
        return self._manual_rect

    # ========== 统一检测接口 ==========

    def detect(self, image: np.ndarray,
               restrict_region: Optional[Tuple[int,int,int,int]] = None,
               use_template: bool = False) -> Optional[Tuple[int,int,int,int]]:
        """
        根据当前配置的检测模式执行检测
        返回脸部矩形: (x, y, w, h)
        """
        mode = self.config.detection_mode

        if mode == "manual_point":
            if use_template and self._template is not None:
                return self.match_template(image)
            elif self._manual_point is not None:
                # 标点模式下, 返回以标点为中心的默认大小矩形
                px, py = self._manual_point
                return (px - 90, py - 110, 180, 220)
            else:
                return None

        elif mode == "manual_box":
            return self._manual_rect

        elif mode == "opencv":
            return self.detect_opencv(image, restrict_region)

        return None

    def reset_manual(self):
        """重置手动模式的状态"""
        self._manual_point = None
        self._manual_rect = None
        self._template = None
        self._template_point = None

    def has_template(self) -> bool:
        return self._template is not None


def pil_to_cv2(pil_image: Image.Image) -> np.ndarray:
    """PIL Image 转 OpenCV BGR numpy数组"""
    if pil_image.mode == "RGBA":
        pil_image = pil_image.convert("RGB")
    return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)


def cv2_to_pil(cv2_image: np.ndarray) -> Image.Image:
    """OpenCV BGR numpy数组 转 PIL Image"""
    return Image.fromarray(cv2.cvtColor(cv2_image, cv2.COLOR_BGR2RGB))


def compute_scale_and_position(
    src_face_rect: Tuple[int, int, int, int],
    src_image_size: Tuple[int, int],
    config: AppConfig
) -> dict:
    """
    根据脸部检测结果, 计算缩放和放置参数
    src_face_rect: 源图中脸部矩形 (x, y, w, h)
    src_image_size: 源图尺寸 (w, h)
    返回: dict with scale, paste_x, paste_y, face_cx_in_output
    """
    fx, fy, fw, fh = src_face_rect
    src_w, src_h = src_image_size

    # 脸部中心
    face_cx = fx + fw / 2.0
    face_cy = fy + fh / 2.0

    # 目标脸部区域
    target_cx = config.face_zone_x + config.face_zone_w / 2.0
    target_cy = config.face_zone_y + config.face_zone_h / 2.0

    # 计算缩放比例 (使脸部大小匹配目标区域)
    scale_w = config.face_zone_w / fw if fw > 0 else 1.0
    scale_h = config.face_zone_h / fh if fh > 0 else 1.0
    scale = min(scale_w, scale_h)

    # 限制缩放范围, 防止过度放大导致模糊
    scale = min(scale, 2.5)
    scale = max(scale, 0.2)

    # 缩放后, 脸部中心在源图中的新坐标 (相对于缩放后图像)
    scaled_face_cx = scale * face_cx
    scaled_face_cy = scale * face_cy

    # 缩放后图像尺寸
    scaled_w = scale * src_w
    scaled_h = scale * src_h

    # Photoshop粘贴时默认居中 (假设)
    paste_x = (config.output_width - scaled_w) / 2.0
    paste_y = (config.output_height - scaled_h) / 2.0

    # 粘贴后脸部中心的位置
    face_cx_in_output = paste_x + scaled_face_cx
    face_cy_in_output = paste_y + scaled_face_cy

    # 计算需要的平移量
    dx = target_cx - face_cx_in_output
    dy = target_cy - face_cy_in_output

    return {
        "scale": scale,
        "paste_x": paste_x,
        "paste_y": paste_y,
        "translate_x": dx,
        "translate_y": dy,
        "src_face_cx": face_cx,
        "src_face_cy": face_cy,
        "target_cx": target_cx,
        "target_cy": target_cy,
    }
