#!/usr/bin/env python3
"""
立绘裁剪工具 v3
PNG为主：批量脸部检测 → Python裁剪 → PS智能锐化
"""
import os, sys, json, threading, time, tempfile
from typing import List, Optional, Tuple
import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image, ImageDraw

from ps_automation import PhotoshopController
from preset_manager import load_presets, save_presets, add_preset, delete_preset
from face_detector import ensure_cascade, pil_to_cv2

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ========== 工具函数 ==========

def load_image(path: str, max_size=400) -> Optional[Image.Image]:
    try:
        img = Image.open(path)
        if img.mode != 'RGBA': img = img.convert('RGBA')
        w, h = img.size
        s = min(max_size / max(w, h), 1.0)
        if s < 1.0: img = img.resize((int(w*s), int(h*s)), Image.LANCZOS)
        return img
    except: return None

def compute_crop(img_size: Tuple[int,int], face: Tuple[int,int,int,int], preset: dict):
    """计算缩放和平移参数"""
    fw, fh, fw2, fh2 = img_size[0], img_size[1], face[2], face[3]
    fx, fy = face[0], face[1]
    cx, cy = fx + fw2/2, fy + fh2/2
    
    sw = preset["face_w"] / fw2 if fw2 > 0 else 1.0
    sh = preset["face_h"] / fh2 if fh2 > 0 else 1.0
    scale = min(sw, sh)
    scale = min(scale, 2.5)
    scale = max(scale, 0.2)
    
    new_w = max(1, int(fw * scale))
    new_h = max(1, int(fh * scale))
    
    paste_x = (preset["w"] - new_w) // 2
    paste_y = (preset["h"] - new_h) // 2
    
    face_now_x = paste_x + int(scale * cx)
    face_now_y = paste_y + int(scale * cy)
    target_x = preset["face_x"] + preset["face_w"] // 2
    target_y = preset["face_y"] + preset["face_h"] // 2
    
    dx = target_x - face_now_x
    dy = target_y - face_now_y
    
    return {"scale": scale, "new_w": new_w, "new_h": new_h,
            "paste_x": paste_x, "paste_y": paste_y,
            "dx": dx, "dy": dy}

def python_crop(input_path: str, output_path: str, face: Tuple[int,int,int,int],
                preset: dict) -> bool:
    """Python裁剪：缩放→定位→输出"""
    try:
        img = Image.open(input_path)
        if img.mode != 'RGBA': img = img.convert('RGBA')
        
        params = compute_crop(img.size, face, preset)
        
        scaled = img.resize((params["new_w"], params["new_h"]), Image.LANCZOS)
        canvas = Image.new("RGBA", (preset["w"], preset["h"]), (0,0,0,0))
        px = params["paste_x"] + params["dx"]
        py = params["paste_y"] + params["dy"]
        canvas.paste(scaled, (px, py), scaled)
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        canvas.save(output_path, "PNG", optimize=True)
        return True
    except Exception as e:
        print(f"Crop error: {e}")
        return False


# ========== GUI ==========

class App:
    def __init__(self):
        self.ps = PhotoshopController()
        self.presets = load_presets()
        self.current_preset_idx = 0
        self.files: List[str] = []
        self.entries: dict = {}  # file_path -> {img, face, confirmed}
        self.processing = False
        self.stop_requested = False

        self._build_ui()
        self._refresh_presets()

    def _build_ui(self):
        self.root = ctk.CTk()
        self.root.title("立绘裁剪工具 v3")
        self.root.geometry("900x750")
        self.root.minsize(700, 600)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(5, weight=1)

        pad = dict(padx=12, pady=(6,2), sticky="ew")
        row = 0

        # --- 行1: 预设 ---
        pf = ctk.CTkFrame(self.root); pf.grid(row=row, column=0, **pad)
        pf.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(pf, text="预设:").pack(side="left", padx=5)
        self.preset_combo = ctk.CTkComboBox(pf, values=[], command=self._on_preset, width=180)
        self.preset_combo.pack(side="left", padx=5)
        ctk.CTkButton(pf, text="+", width=35, command=self._new_preset).pack(side="left", padx=2)
        ctk.CTkButton(pf, text="-", width=35, command=self._del_preset).pack(side="left", padx=2)
        ctk.CTkButton(pf, text="从PNG导入", width=80, fg_color="#00695C",
                      command=self._import_preset).pack(side="left", padx=(10,2))
        row += 1

        # --- 行2: 文件夹 ---
        ff = ctk.CTkFrame(self.root); ff.grid(row=row, column=0, **pad)
        ff.grid_columnconfigure(0, weight=1)
        self.folder_var = ctk.StringVar()
        ctk.CTkEntry(ff, textvariable=self.folder_var, placeholder_text="选择PNG/PSD文件夹...").grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        ctk.CTkButton(ff, text="浏览", width=60, command=self._browse).grid(row=0, column=1, padx=3, pady=5)
        row += 1

        # --- 行3: 操作按钮 ---
        bf = ctk.CTkFrame(self.root); bf.grid(row=row, column=0, **pad)
        self.btn_export = ctk.CTkButton(bf, text="导出PSD→PNG", fg_color="#E65100", command=self._export_psds)
        self.btn_export.pack(side="left", padx=3)
        self.btn_detect = ctk.CTkButton(bf, text="批量脸部检测", fg_color="#1565C0", command=self._detect_all)
        self.btn_detect.pack(side="left", padx=3)
        self.btn_crop = ctk.CTkButton(bf, text="Python裁剪", fg_color="#2E7D32", command=self._crop_all)
        self.btn_crop.pack(side="left", padx=3)
        self.btn_sharpen = ctk.CTkButton(bf, text="PS智能锐化", fg_color="#6A1B9A", command=self._sharpen_all)
        self.btn_sharpen.pack(side="left", padx=3)
        self.btn_stop = ctk.CTkButton(bf, text="停止", fg_color="#555", width=50, state="disabled", command=self._stop)
        self.btn_stop.pack(side="right", padx=3)
        self.btn_check = ctk.CTkButton(bf, text="检查PS", fg_color="#00695C", width=70, command=self._check_ps)
        self.btn_check.pack(side="right", padx=3)
        row += 1

        # --- 行4: 进度 ---
        self.progress = ctk.CTkProgressBar(self.root); self.progress.grid(row=row, column=0, **pad)
        self.progress.set(0); row += 1
        self.status_var = ctk.StringVar(value="就绪")
        ctk.CTkLabel(self.root, textvariable=self.status_var, anchor="w").grid(row=row, column=0, **pad)
        row += 1

        # --- 行5: 主区域（文件列表+预览） ---
        main = ctk.CTkFrame(self.root, fg_color="transparent")
        main.grid(row=row, column=0, padx=12, pady=(5,10), sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_columnconfigure(1, weight=2)
        main.grid_rowconfigure(0, weight=1)

        # 文件列表
        list_frame = ctk.CTkFrame(main)
        list_frame.grid(row=0, column=0, sticky="nsew", padx=(0,5))
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(list_frame, text="文件列表", font=("", 13, "bold")).grid(row=0, column=0, padx=5, pady=3)
        self.file_list = ctk.CTkScrollableFrame(list_frame)
        self.file_list.grid(row=1, column=0, sticky="nsew", padx=3, pady=3)
        self.file_btns: List[ctk.CTkButton] = []

        # 预览区
        preview_frame = ctk.CTkFrame(main)
        preview_frame.grid(row=0, column=1, sticky="nsew")
        preview_frame.grid_rowconfigure(1, weight=1)
        preview_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(preview_frame, text="预览（点击左侧文件）", font=("", 13, "bold")).grid(row=0, column=0, padx=5, pady=3)
        self.preview_label = ctk.CTkLabel(preview_frame, text="", fg_color="#1a1a1a")
        self.preview_label.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        # 脸部微调
        adj = ctk.CTkFrame(preview_frame)
        adj.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        ctk.CTkLabel(adj, text="脸部(x,y,w,h):").pack(side="left", padx=3)
        self.face_vars = {}
        for lbl in ["x","y","w","h"]:
            v = ctk.StringVar(value="0")
            ctk.CTkEntry(adj, textvariable=v, width=55).pack(side="left", padx=2)
            self.face_vars[lbl] = v
        ctk.CTkButton(adj, text="应用", width=50, command=self._apply_face).pack(side="left", padx=5)
        ctk.CTkButton(adj, text="清空", width=50, command=self._clear_face).pack(side="left", padx=3)

        # --- 行6: 日志 ---
        self.log_text = ctk.CTkTextbox(self.root, height=120, font=("Consolas", 10))
        self.log_text.grid(row=row+1, column=0, padx=12, pady=(0,5), sticky="ew")
        self.root.grid_rowconfigure(row+1, weight=0)

    # ========== 预设 ==========

    def _refresh_presets(self):
        self.presets = load_presets()
        names = [p["name"] for p in self.presets]
        self.preset_combo.configure(values=names)
        if self.current_preset_idx >= len(self.presets): self.current_preset_idx = 0
        if names: self.preset_combo.set(names[self.current_preset_idx])

    def _on_preset(self, c):
        for i, p in enumerate(self.presets):
            if p["name"] == c: self.current_preset_idx = i; break

    def _new_preset(self):
        dialog = ctk.CTkToplevel(self.root); dialog.title("新建预设"); dialog.geometry("360x350")
        dialog.transient(self.root); dialog.grab_set()
        ctk.CTkLabel(dialog, text="预设名称:").pack(padx=15, pady=(15,2), anchor="w")
        nv = ctk.StringVar(value=f"预设{len(self.presets)+1}")
        ctk.CTkEntry(dialog, textvariable=nv).pack(padx=15, fill="x")
        fields = {"画布宽":"1280","画布高":"1280","脸部X":"460","脸部Y":"250","脸部W":"360","脸部H":"420","锐化强度":"0.9"}
        vs = {}
        for lbl, d in fields.items():
            ctk.CTkLabel(dialog, text=lbl).pack(padx=15, pady=(5,1), anchor="w")
            v = ctk.StringVar(value=d)
            ctk.CTkEntry(dialog, textvariable=v, width=100).pack(padx=15, fill="x")
            vs[lbl] = v
        def save():
            try:
                add_preset(nv.get().strip(), int(vs["画布宽"].get()), int(vs["画布高"].get()),
                          int(vs["脸部X"].get()), int(vs["脸部Y"].get()),
                          int(vs["脸部W"].get()), int(vs["脸部H"].get()),
                          float(vs["锐化强度"].get()))
                self._refresh_presets(); dialog.destroy()
            except: messagebox.showerror("错误", "数值无效")
        ctk.CTkButton(dialog, text="保存", fg_color="#2E7D32", command=save).pack(pady=15)

    def _del_preset(self):
        if len(self.presets) <= 1: return
        if messagebox.askyesno("确认", f"删除 {self.presets[self.current_preset_idx]['name']}?"):
            delete_preset(self.current_preset_idx)
            self.current_preset_idx = 0
            self._refresh_presets()

    def _import_preset(self):
        """从已裁好的PNG导入脸部位置作为预设"""
        fp = filedialog.askopenfilename(title="选择已裁好的立绘PNG",
                                         filetypes=[("PNG", "*.png")])
        if not fp: return
        img = Image.open(fp)
        w, h = img.size
        # 检测脸部
        face = None
        try:
            ensure_cascade()
            import cv2, numpy as np, tempfile, os
            cp = os.path.join(tempfile.gettempdir(), "_animeface_cascade.xml")
            cascade = cv2.CascadeClassifier(cp)
            if not cascade.empty():
                thumb = img.copy()
                s = min(300 / max(w, h), 1.0)
                thumb = thumb.resize((int(w*s), int(h*s)), Image.LANCZOS)
                if thumb.mode != 'RGB': thumb = thumb.convert('RGB')
                cv_img = cv2.cvtColor(np.array(thumb), cv2.COLOR_RGB2BGR)
                gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
                faces = cascade.detectMultiScale(gray, 1.05, 5, minSize=(25,25))
                if len(faces) > 0:
                    best = max(faces, key=lambda f: f[2]*f[3])
                    ratio = 1.0 / s
                    face = (int(best[0]*ratio), int(best[1]*ratio),
                            int(best[2]*ratio), int(best[3]*ratio))
        except: pass

        if face is None:
            face = (int(w*0.3), int(h*0.15), int(w*0.4), int(h*0.4))

        dialog = ctk.CTkToplevel(self.root); dialog.title("从图片导入预设")
        dialog.geometry("460x420"); dialog.transient(self.root); dialog.grab_set()
        ctk.CTkLabel(dialog, text="预设名称:").pack(padx=15, pady=(15,2), anchor="w")
        nv = ctk.StringVar(value=f"预设 {w}x{h}")
        ctk.CTkEntry(dialog, textvariable=nv).pack(padx=15, fill="x")
        ctk.CTkLabel(dialog, text=f"画布: {w}×{h}", font=("", 14, "bold")).pack(pady=5)
        ctk.CTkLabel(dialog, text="脸部位置（可在预览中拖拽调整后复制数值）", fg_color="transparent").pack()

        vs = {}
        for lbl, val in [("脸部X", face[0]), ("脸部Y", face[1]),
                          ("脸部W", face[2]), ("脸部H", face[3])]:
            f = ctk.CTkFrame(dialog, fg_color="transparent")
            f.pack(padx=15, fill="x")
            ctk.CTkLabel(f, text=lbl).pack(side="left")
            v = ctk.StringVar(value=str(val))
            ctk.CTkEntry(f, textvariable=v, width=80).pack(side="right")
            vs[lbl] = v
        # 锐化
        sf = ctk.CTkFrame(dialog, fg_color="transparent"); sf.pack(padx=15, fill="x")
        ctk.CTkLabel(sf, text="锐化强度").pack(side="left")
        sv = ctk.StringVar(value="0.9")
        ctk.CTkEntry(sf, textvariable=sv, width=80).pack(side="right")

        # 预览
        thumb = load_image(fp, 250)
        if thumb and face:
            overlay = thumb.copy(); draw = ImageDraw.Draw(overlay)
            ratio = thumb.size[0] / w
            fx, fy, fw, fh = [int(v*ratio) for v in face]
            draw.rectangle([fx, fy, fx+fw, fy+fh], outline="#00FF00", width=2)
            pi = ctk.CTkImage(overlay, size=overlay.size)
            ctk.CTkLabel(dialog, text="", image=pi).pack(pady=5)

        def save():
            try:
                add_preset(nv.get().strip(), w, h,
                          int(vs["脸部X"].get()), int(vs["脸部Y"].get()),
                          int(vs["脸部W"].get()), int(vs["脸部H"].get()),
                          float(sv.get()))
                self._refresh_presets(); dialog.destroy()
            except: messagebox.showerror("错误", "数值无效")
        ctk.CTkButton(dialog, text="保存预设", fg_color="#2E7D32", command=save).pack(pady=10)

    # ========== 文件 ==========

    def _browse(self):
        d = filedialog.askdirectory(title="选择文件夹")
        if not d:
            return
        self.folder_var.set(d)
        self.files = []
        exts = {'.psd','.png'}
        for f in sorted(os.listdir(d)):
            if os.path.splitext(f)[1].lower() in exts:
                self.files.append(os.path.join(d, f))
        self.entries = {}
        for fp in self.files:
            self.entries[fp] = {"img": None, "face": None, "confirmed": False}
        self._rebuild_file_list()
        self.log(f"加载 {len(self.files)} 个文件")
        if any(f.lower().endswith('.psd') for f in self.files):
            self.btn_export.configure(state="normal")

    def _rebuild_file_list(self, select=None):
        for b in self.file_btns: b.destroy()
        self.file_btns.clear()
        for fp in self.files:
            e = self.entries.get(fp, {})
            bn = os.path.basename(fp)
            status = ""
            if e.get("face"): status = " ●" if not e.get("confirmed") else " ✓"
            if e.get("confirmed"): status = " ✓"
            btn = ctk.CTkButton(self.file_list, text=f"{bn}{status}", anchor="w",
                                fg_color="transparent", hover_color="gray30",
                                command=lambda p=fp: self._select_file(p))
            btn.pack(fill="x", padx=2, pady=1)
            self.file_btns.append(btn)

    def _select_file(self, fp):
        e = self.entries.get(fp)
        if not e: return
        img = load_image(fp)
        e["img"] = img
        if e.get("face") and img:
            orig = Image.open(fp).size
            ratio = img.size[0] / orig[0]
            fx, fy, fw, fh = [int(v * ratio) for v in e["face"]]
            overlay = img.copy()
            draw = ImageDraw.Draw(overlay)
            draw.rectangle([fx, fy, fx+fw, fy+fh], outline="#00FF00", width=2)
            pimg = ctk.CTkImage(overlay, size=overlay.size)
        elif img:
            pimg = ctk.CTkImage(img, size=img.size)
        else:
            pimg = None

        if pimg:
            self.preview_label.configure(image=pimg)
        if e.get("face"):
            for i, k in enumerate(["x","y","w","h"]):
                self.face_vars[k].set(str(e["face"][i]))

        self._selected_file = fp

    def _apply_face(self):
        fp = getattr(self, '_selected_file', None)
        if not fp: return
        try:
            face = tuple(int(self.face_vars[k].get()) for k in ["x","y","w","h"])
            self.entries[fp]["face"] = face
            self.entries[fp]["confirmed"] = True
            self._rebuild_file_list()
            self._select_file(fp)
        except: pass

    def _clear_face(self):
        fp = getattr(self, '_selected_file', None)
        if not fp: return
        self.entries[fp]["face"] = None
        self.entries[fp]["confirmed"] = False
        self._rebuild_file_list()
        self._select_file(fp)

    # ========== 批量脸部检测 ==========

    def _detect_all(self):
        self.stop_requested = False
        import cv2, numpy as np, tempfile, shutil
        ensure_cascade()
        from config import CASCADE_PATH
        cp = os.path.join(tempfile.gettempdir(), "_animeface_cascade.xml")
        if not os.path.exists(cp) and os.path.exists(CASCADE_PATH):
            shutil.copy2(CASCADE_PATH, cp)
        cascade = cv2.CascadeClassifier(cp)
        if cascade.empty():
            messagebox.showerror("错误", "脸部检测模型加载失败")
            return
        ok = 0; total = len(self.files)
        for i, fp in enumerate(self.files):
            if self.stop_requested: break
            self._progress(i+1, total, f"检测: {i+1}/{total}")
            if self.entries[fp].get("confirmed"): ok += 1; continue
            try:
                orig = Image.open(fp); ow, oh = orig.size
                s = min(400 / max(ow, oh), 1.0)
                img = orig.resize((int(ow*s), int(oh*s)), Image.LANCZOS)
                if img.mode != 'RGB': img = img.convert('RGB')
                cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
                # 多尺度多参数尝试，取最好结果
                all_faces = []
                for sf in [1.01, 1.05, 1.1]:
                    for nn in [5, 4, 3]:
                        faces = cascade.detectMultiScale(gray, sf, nn, minSize=(20,20))
                        for f in faces: all_faces.append(f)
                if all_faces:
                    # 按面积排序，取中位数附近的（避免异常大的假阳性）
                    all_faces.sort(key=lambda f: f[2]*f[3])
                    best = all_faces[len(all_faces)//2]
                    ratio = 1.0 / s
                    face = (int(best[0]*ratio), int(best[1]*ratio),
                            int(best[2]*ratio), int(best[3]*ratio))
                    self.entries[fp]["face"] = face
                    self.entries[fp]["confirmed"] = True; ok += 1
            except Exception as e:
                self.log(f"  {os.path.basename(fp)}: {e}")
            self.root.update_idletasks()
        self._progress(1,1, f"检测完成: {ok}/{total}")
        self._rebuild_file_list()
        self.log(f"脸部检测: {ok}/{total} 成功")

    # ========== Python裁剪 ==========

    def _crop_all(self):
        output = filedialog.askdirectory(title="选择裁剪输出文件夹")
        if not output: return
        preset = self.presets[self.current_preset_idx]
        entries = [(fp, e) for fp, e in self.entries.items() if e.get("face") and e.get("confirmed")]
        if not entries:
            messagebox.showwarning("提示", "没有已确认脸部的文件")
            return

        ok = 0
        total = len(entries)
        for i, (fp, e) in enumerate(entries):
            if self.stop_requested: break
            self._progress(i+1, total, f"裁剪: {i+1}/{total}")
            bn = os.path.splitext(os.path.basename(fp))[0]
            out = os.path.join(output, f"{bn}.png")
            if python_crop(fp, out, e["face"], preset):
                ok += 1
                self.log(f"  [OK] {bn}.png")
            else:
                self.log(f"  [FAIL] {bn}")
            self.root.update_idletasks()
        self._progress(1,1, f"裁剪完成: {ok}/{total}")
        self.log(f"Python裁剪: {ok}/{total} 成功 → {output}")
        self._crop_output_dir = output

    # ========== PS智能锐化 ==========

    def _sharpen_all(self):
        d = getattr(self, '_crop_output_dir', None)
        if not d or not os.path.isdir(d):
            d = filedialog.askdirectory(title="选择要锐化的文件夹")
            if not d: return

        files = [os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith('.png')]
        if not files:
            messagebox.showwarning("提示", "没有PNG文件")
            return

        if not self.ps.connected and not self.ps.connect():
            messagebox.showerror("错误", "无法连接PS")
            return

        sharpen = self.presets[self.current_preset_idx].get("sharpen", 0.9)
        ok = 0
        total = len(files)
        for i, fp in enumerate(files):
            if self.stop_requested: break
            self._progress(i+1, total, f"锐化: {i+1}/{total}")
            bn = os.path.basename(fp)
            r = self.ps.js(
                f'(function(){{'
                f'var f=new File("{self.ps._esc(fp)}");'
                f'if(!f.exists)return"NF";'
                f'var d=app.open(f);'
                f'var desc=new ActionDescriptor();'
                f'var ref=new ActionReference();'
                f'ref.putEnumerated(charIDToTypeID("Lyr "),charIDToTypeID("Ordn"),charIDToTypeID("Trgt"));'
                f'desc.putReference(charIDToTypeID("null"),ref);'
                f'executeAction(stringIDToTypeID("newPlacedLayer"),desc,DialogModes.NO);'
                f'var d2=new ActionDescriptor();'
                f'd2.putDouble(charIDToTypeID("Amnt"),{sharpen}*100);'
                f'd2.putDouble(charIDToTypeID("Rds "),1.0);'
                f'd2.putEnumerated(charIDToTypeID("Nrse"),charIDToTypeID("Nrse"),stringIDToTypeID("gaussianNoise"));'
                f'executeAction(stringIDToTypeID("smartSharpen"),d2,DialogModes.NO);'
                f'var png=new PNGSaveOptions();png.compression=6;'
                f'd.saveAs(f,png,true,Extension.LOWERCASE);'
                f'd.close(SaveOptions.DONOTSAVECHANGES);'
                f'return"OK";'
                f'}})();'
            )
            if r == "OK": ok += 1; self.log(f"  [锐化] {bn}")
            else: self.log(f"  [失败] {bn}: {r}")
            self.root.update_idletasks()
        self._progress(1,1, "锐化完成")
        self.log(f"PS锐化: {ok}/{total} → {d}")

    # ========== PSD导出 ==========

    def _export_psds(self):
        psd_files = [f for f in self.files if f.lower().endswith('.psd')]
        if not psd_files: return
        d = os.path.join(os.path.dirname(psd_files[0]), "_png_export")
        os.makedirs(d, exist_ok=True)

        if not self.ps.connected and not self.ps.connect():
            messagebox.showerror("错误", "无法连接PS"); return

        ok = 0
        for i, fp in enumerate(psd_files):
            self._progress(i+1, len(psd_files), f"导出: {i+1}/{len(psd_files)}")
            bn = os.path.splitext(os.path.basename(fp))[0]
            out = os.path.join(d, f"{bn}.png")
            r = self.ps.js(
                f'(function(){{'
                f'var f=new File("{self.ps._esc(fp)}");'
                f'if(!f.exists)return"NF";'
                f'var doc=app.open(f);'
                f'for(var i=doc.artLayers.length-1;i>=Math.max(0,doc.artLayers.length-2);i--){{'
                f'var l=doc.artLayers[i];'
                f'if(l.kind==LayerKind.NORMAL){{'
                f'var b=l.bounds;'
                f'if(Math.abs(b[0].value)<1&&Math.abs(b[1].value)<1&&Math.abs(b[2].value-doc.width.value)<1&&Math.abs(b[3].value-doc.height.value)<1)'
                f'l.visible=false;'
                f'}}}}'
                f'var of=new File("{self.ps._esc(out)}");'
                f'var od=new File(of.parent);if(!od.exists)od.create();'
                f'var png=new PNGSaveOptions();png.compression=6;'
                f'doc.saveAs(of,png,true,Extension.LOWERCASE);'
                f'doc.close(SaveOptions.DONOTSAVECHANGES);'
                f'return of.exists?"OK":"FAIL";'
                f'}})();'
            )
            if r == "OK": ok += 1; self.log(f"  [导出] {bn}.png")
            else: self.log(f"  [失败] {bn}: {r}")
            self.root.update_idletasks()
        self._progress(1,1, "导出完成")
        self.log(f"PSD导出: {ok}/{len(psd_files)} → {d}")
        if ok > 0:
            self.folder_var.set(d)
            self.files = [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith('.png')]
            self.entries = {}
            for fp in self.files:
                self.entries[fp] = {"img": None, "face": None, "confirmed": False}
            self._rebuild_file_list()

    # ========== 工具 ==========

    def _check_ps(self):
        d = PhotoshopController.diagnose(); self.log(d)

    def _stop(self):
        self.stop_requested = True

    def _progress(self, cur, total, msg):
        self.root.after(0, lambda: (
            self.progress.set(cur/total if total>0 else 0),
            self.status_var.set(msg)
        ))

    def log(self, msg):
        self.root.after(0, lambda: (self.log_text.insert("end", msg+"\n"), self.log_text.see("end")))

    def run(self):
        self.root.mainloop()


def main():
    try:
        App().run()
    except Exception as e:
        import traceback
        traceback.print_exc()
        input("按回车退出...")

if __name__ == "__main__":
    main()
