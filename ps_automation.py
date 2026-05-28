"""
Photoshop 操作模块
纯字符串返回，不用JSON（兼容所有PS版本）
"""
import os, threading
from typing import List, Optional, Callable, Dict, Tuple
from string import Template


# ======================================================================
# JSX 模板
# 全部使用纯字符串返回值，格式: "OK:data" / "ERR:msg" / "CANCEL"
# 不依赖 JSON.stringify（部分PS版本无此功能）
# ======================================================================

PROCESS_JSX = Template(r'''
(function(){
    var f=new File("${input_path}");
    if(!f.exists) return "SKIP:no_file";
    try{
        var doc=app.open(f);
        var isPsd=${is_psd};
        var bgKw=[${bg_patterns}]; var wmKw=[${wm_patterns}];
        if(isPsd){
            for(var i=doc.artLayers.length-1;i>=0;i--){
                var l=doc.artLayers[i],n=l.name.toLowerCase();
                for(var j=0;j<bgKw.length;j++){if(bgKw[j]&&n.indexOf(bgKw[j])>=0)l.visible=false;}
                for(var j=0;j<wmKw.length;j++){if(wmKw[j]&&n.indexOf(wmKw[j])>=0)l.visible=false;}
            }
            if(doc.artLayers.length>1){
                var bl=doc.artLayers[doc.artLayers.length-1];
                if(bl.visible&&bl.kind==LayerKind.NORMAL){
                    var b=bl.bounds;
                    if(Math.abs(b[0].value)<2&&Math.abs(b[1].value)<2&&Math.abs(b[2].value-doc.width.value)<2&&Math.abs(b[3].value-doc.height.value)<2){
                        var ck="头发,眼睛,脸,衣,手,脚,身,头,饰,肤,hair,eye,face,body,cloth,skin,hand,arm,leg,前,人物,立绘";
                        var isCh=false; var nn=bl.name.toLowerCase();
                        var ca=ck.split(","); for(var k=0;k<ca.length;k++){if(nn.indexOf(ca[k])>=0){isCh=true;break;}}
                        if(!isCh)bl.visible=false;
                    }
                }
            }
            try{doc.mergeVisibleLayers();}catch(e){}
        }
        var sw=Math.round(${src_w}*${scale}),sh=Math.round(${src_h}*${scale});
        if(sw<1)sw=1;if(sh<1)sh=1;
        doc.resizeImage(sw,sh,doc.resolution,ResampleMethod.BICUBIC);
        doc.selection.selectAll();doc.selection.copy();
        doc.close(SaveOptions.DONOTSAVECHANGES);
        var out=app.documents.add(${output_w},${output_h},72,"output",NewDocumentMode.RGB,DocumentFill.TRANSPARENT,1,BitsPerChannelType.EIGHT);
        out.paste();var sl=out.activeLayer;
        var px=(${output_w}-sw)/2,py=(${output_h}-sh)/2;
        sl.translate(${target_cx}-(px+${scale}*${src_face_cx}),${target_cy}-(py+${scale}*${src_face_cy}));
        var d1=new ActionDescriptor();var r1=new ActionReference();
        r1.putEnumerated(charIDToTypeID("Lyr "),charIDToTypeID("Ordn"),charIDToTypeID("Trgt"));
        d1.putReference(charIDToTypeID("null"),r1);
        executeAction(stringIDToTypeID("newPlacedLayer"),d1,DialogModes.NO);
        var d2=new ActionDescriptor();d2.putDouble(charIDToTypeID("Amnt"),${sharpen_amount}*100);
        d2.putDouble(charIDToTypeID("Rds "),1.0);
        d2.putEnumerated(charIDToTypeID("Nrse"),charIDToTypeID("Nrse"),stringIDToTypeID("gaussianNoise"));
        executeAction(stringIDToTypeID("smartSharpen"),d2,DialogModes.NO);
        var of=new File("${output_path}");var od=new File(of.parent);if(!od.exists)od.create();
        var png=new PNGSaveOptions();png.compression=6;
        out.saveAs(of,png,true,Extension.LOWERCASE);out.close(SaveOptions.DONOTSAVECHANGES);
        return of.exists?"OK":"FAIL:output_missing";
    }catch(e){return "ERR:"+e.toString();}
})();
''')


# 读取选区：返回 "OK:w,h,x1,y1,x2,y2" 或 "ERR:msg"
GET_SELECTION_JSX = r'''
(function(){
    try{
        var d=app.activeDocument;
        var s=d.selection.bounds;
        return "OK:"+d.width.value+","+d.height.value+","+
            s[0].value+","+s[1].value+","+s[2].value+","+s[3].value;
    }catch(e){return "ERR:"+e.toString();}
})();
'''


class PhotoshopController:

    def __init__(self):
        self._ps = None

    def connect(self) -> bool:
        try:
            import pythoncom
            pythoncom.CoInitialize()
            import win32com.client
            self._ps = win32com.client.Dispatch("Photoshop.Application")
            self._ps.Visible = True
            return True
        except: return False

    @property
    def connected(self) -> bool: return self._ps is not None

    def get_version(self) -> str:
        try: return str(self._ps.Version)
        except: return "?"

    def js(self, code: str) -> str:
        """执行JSX字符串"""
        try: return str(self._ps.DoJavaScript(code)).strip()
        except Exception as e: return f"COM_ERR:{e}"

    def js_file(self, jsx_code: str) -> str:
        """通过临时文件执行JSX"""
        import tempfile
        tmp = os.path.join(tempfile.gettempdir(), "_ps_sprite.jsx")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(jsx_code)
        esc = tmp.replace("\\", "\\\\")
        # 用 evalFile 返回值更可靠
        r = self.js(f'$.evalFile(new File("{esc}"));')
        if r and r != "undefined":
            return r
        # 回退：手动eval
        return self.js(
            f'var _f=new File("{esc}");'
            f'_f.open("r");'
            f'var _code=_f.read();'
            f'_f.close();'
            f'eval(_code);'
        )

    # ==================== 预设 ====================

    def prompt_new_canvas(self) -> Optional[Tuple[int,int]]:
        r = self.js('(function(){try{var d=app.activeDocument;return d.width.value+","+d.height.value}catch(e){return""}})();')
        if r and "," in r:
            p=r.split(","); return (int(float(p[0])), int(float(p[1])))
        for jsx in [
            '''(function(){try{var d=new ActionDescriptor();d.putClass(stringIDToTypeID("new"),stringIDToTypeID("document"));executeAction(stringIDToTypeID("make"),d,DialogModes.ALL);var doc=app.activeDocument;if(doc)return"OK:"+doc.width.value+","+doc.height.value;return"CANCEL"}catch(e){return"ERR:"+e.toString()}})();''',
            '''(function(){try{var d=new ActionDescriptor();d.putClass(charIDToTypeID("Nw  "),charIDToTypeID("Dcmn"));executeAction(charIDToTypeID("Mk  "),d,DialogModes.ALL);var doc=app.activeDocument;if(doc)return"OK:"+doc.width.value+","+doc.height.value;return"CANCEL"}catch(e){return"ERR:"+e.toString()}})();''',
        ]:
            r=self.js(jsx)
            if r.startswith("OK:"):
                p=r[3:].split(","); return (int(float(p[0])), int(float(p[1])))
            if r=="CANCEL": return None
        return None

    def get_active_doc_size(self) -> Optional[Tuple[int,int]]:
        r=self.js('(function(){try{var d=app.activeDocument;return d.width.value+","+d.height.value}catch(e){return""}})();')
        try: p=r.split(","); return (int(float(p[0])), int(float(p[1])))
        except: return None

    def place_face_guide(self) -> str:
        return self.js(r'''
            (function(){try{var d=app.activeDocument,w=d.width.value,h=d.height.value;
            try{d.artLayers.getByName("[FACE_GUIDE]").remove()}catch(e){}
            var gl=d.artLayers.add();gl.name="[FACE_GUIDE]";gl.opacity=40;
            d.activeLayer=gl;return"OK:"+w+","+h}catch(e){return"ERR:"+e.toString()}})();
        ''')

    def read_selection_bounds(self) -> Optional[dict]:
        r = self.js(GET_SELECTION_JSX)
        if not r or not r.startswith("OK:"): return None
        try:
            parts = r[3:].split(",")
            return {"ok":True, "w":int(float(parts[0])),"h":int(float(parts[1])),
                    "x":int(float(parts[2])),"y":int(float(parts[3])),
                    "x2":int(float(parts[4])),"y2":int(float(parts[5]))}
        except: return None

    # ==================== 处理 ====================

    def process_sprite(self, input_path, output_path, preset, face_rect,
                       src_w, src_h, is_psd, bg_patterns, wm_patterns) -> str:
        fx,fy,fw,fh=face_rect
        cx=fx+fw/2.0; cy=fy+fh/2.0
        sw=preset["face_w"]/fw if fw>0 else 1.0
        sh_p=preset["face_h"]/fh if fh>0 else 1.0
        scale=min(sw,sh_p); scale=min(scale,2.5); scale=max(scale,0.2)
        tc=preset["face_x"]+preset["face_w"]/2.0
        ty=preset["face_y"]+preset["face_h"]/2.0
        bg=", ".join('"'+p+'"' for p in (bg_patterns or []) if p)
        wm=", ".join('"'+p+'"' for p in (wm_patterns or []) if p)
        return self.js(PROCESS_JSX.substitute(
            input_path=self._esc(input_path), output_path=self._esc(output_path),
            is_psd="true" if is_psd else "false", bg_patterns=bg, wm_patterns=wm,
            output_w=preset["w"], output_h=preset["h"], scale=scale,
            src_w=src_w, src_h=src_h, src_face_cx=cx, src_face_cy=cy,
            target_cx=tc, target_cy=ty, sharpen_amount=preset.get("sharpen",0.9)))

    # ==================== 诊断 ====================

    @staticmethod
    def diagnose() -> str:
        lines=[]
        try:
            import win32com.client
            lines.append("[OK] pywin32")
            try:
                ps=win32com.client.Dispatch("Photoshop.Application")
                lines.append(f"[OK] PS {ps.Version} | {ps.Path}")
            except Exception as e: lines.append(f"[FAIL] PS连接: {e}")
        except ImportError: lines.append("[FAIL] 需 pip install pywin32")
        return "\n".join(lines)

    @staticmethod
    def _esc(p):
        """转义路径：优先用Windows短路径（纯ASCII，避免COM编码问题）"""
        try:
            import win32api
            sp = win32api.GetShortPathName(p)
            if sp and os.path.exists(sp):
                return sp.replace("\\", "\\\\")
        except:
            pass
        return p.replace("\\", "\\\\").replace('"', '\\"')
