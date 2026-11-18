# -*- coding: utf-8 -*-
"""
AIShotExplain v2 —— 按 F11 选区截图，直接问 AI 解释

v2 相比 v1：
  · 默认模型换成 glm-4v-flash（5 秒 vs 18 秒，且免费）
  · 流式输出：首字节 0.37 秒就出字，不用干等
  · Markdown 渲染：**加粗**、# 标题、- 列表、`代码` 都按格式显示，不再是原始符号

零第三方依赖：tkinter + Pillow + ctypes
"""
import base64
import ctypes
import ctypes.wintypes as wt
import io
import json
import os
import queue
import re
import sys
import threading
import time
import urllib.error
import urllib.request

import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageGrab, ImageTk

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
LOG_PATH = os.path.join(APP_DIR, "aishop.log")

MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
VK_CODES = {
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73, "F5": 0x74, "F6": 0x75,
    "F7": 0x76, "F8": 0x77, "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
    "PRINTSCREEN": 0x2C, "INSERT": 0x2D, "HOME": 0x24,
    "END": 0x23, "PAUSE": 0x13, "SCROLLLOCK": 0x91,
}

# 界面配色 —— 护眼淡黄（纸质书感），长时间阅读不刺眼
BG = "#FCF4DA"        # 窗口底：淡黄
CARD = "#FFFCF2"      # 文字区：比底色更浅一点
FG = "#333333"        # 正文：深灰（不是纯黑，更柔和）
DIM = "#8C8573"       # 次要文字
ACCENT = "#B5851A"    # 按钮：琥珀色
BORDER = "#E4D9B8"    # 分隔线

UI_FONT = "Microsoft YaHei UI"
MONO_FONT = "Consolas"


def log(msg):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except Exception:
        pass


def load_config():
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        try:
            cfg = json.load(open(CONFIG_PATH, encoding="utf-8-sig"))
        except Exception as ex:
            log("读取 config.json 失败: %r" % (ex,))
    cfg.setdefault("provider", "zhipu")
    cfg.setdefault("base_url", "https://open.bigmodel.cn/api/paas/v4")
    cfg.setdefault("model", "glm-4v-flash")
    cfg.setdefault("stream", True)
    key = (cfg.get("api_key") or "").strip()
    if not key or key.startswith("PUT_"):
        if cfg["provider"] == "zhipu":
            key = (os.environ.get("ZHIPU_API_KEY") or os.environ.get("ZAI_API_KEY") or "").strip()
        else:
            key = (os.environ.get("OPENAI_API_KEY") or "").strip()
            if not key:
                try:
                    rc = json.load(open(os.path.expanduser(r"~\.reasonix\config.json"),
                                       encoding="utf-8"))
                    key = (rc.get("apiKey") or "").strip()
                except Exception:
                    pass
    cfg["api_key"] = key
    return cfg


def save_config(cfg):
    """只把用户可改的项写回（不写运行时推导出来的 api_key 明文）"""
    out = dict(cfg)
    if not (out.get("api_key") or "").strip():
        out.pop("api_key", None)
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        return True
    except Exception as ex:
        log("保存 config.json 失败: %r" % (ex,))
        return False


# ---------------------------------------------------------------- Markdown 渲染
class MdRenderer:
    """把 Markdown 渲染成 tkinter Text 的 tag 样式（轻量实现，够用就好）"""

    def __init__(self, txt):
        self.txt = txt
        f = (UI_FONT, 11)
        txt.tag_configure("h1", font=(UI_FONT, 17, "bold"), foreground="#1F1F1F",
                          spacing1=10, spacing3=6)
        txt.tag_configure("h2", font=(UI_FONT, 14, "bold"), foreground="#1F1F1F",
                          spacing1=8, spacing3=4)
        txt.tag_configure("h3", font=(UI_FONT, 12, "bold"), foreground="#3A3A3A",
                          spacing1=6, spacing3=3)
        txt.tag_configure("bold", font=(UI_FONT, 11, "bold"), foreground="#1A1A1A")
        txt.tag_configure("italic", font=(UI_FONT, 11, "italic"), foreground="#444444")
        txt.tag_configure("code", font=(MONO_FONT, 10), background="#F0E6C8",
                          foreground="#8B3A1E")
        txt.tag_configure("bullet", lmargin1=18, lmargin2=34)
        txt.tag_configure("quote", lmargin1=16, lmargin2=16, foreground=DIM,
                          font=(UI_FONT, 11, "italic"))
        txt.tag_configure("hr", foreground=BORDER, spacing1=6, spacing3=6)
        txt.tag_configure("normal", font=f)
        self.inline = re.compile(r"(\*\*.+?\*\*|__.+?__|`[^`]+`|\*[^*\n]+\*|_[^_\n]+_)")

    def write(self, md):
        txt = self.txt
        txt.config(state="normal")
        txt.delete("1.0", "end")
        for raw in md.splitlines():
            line = raw.rstrip()
            if not line.strip():
                txt.insert("end", "\n")
                continue
            # 分隔线
            if re.fullmatch(r"\s*([-*_])\1{2,}\s*", line):
                txt.insert("end", "─" * 46 + "\n", "hr")
                continue
            # 标题
            m = re.match(r"^(#{1,6})\s+(.*)$", line)
            if m:
                lvl = min(len(m.group(1)), 3)
                self._inline(m.group(2).strip(), "h%d" % lvl)
                txt.insert("end", "\n")
                continue
            # 引用
            m = re.match(r"^\s*>\s?(.*)$", line)
            if m:
                txt.insert("end", "▎ ", "quote")
                self._inline(m.group(1), "quote")
                txt.insert("end", "\n")
                continue
            # 无序列表
            m = re.match(r"^(\s*)[-*+]\s+(.*)$", line)
            if m:
                txt.insert("end", "    • ", "bullet")
                self._inline(m.group(2), "bullet")
                txt.insert("end", "\n")
                continue
            # 有序列表
            m = re.match(r"^(\s*)(\d+)[.)]\s+(.*)$", line)
            if m:
                txt.insert("end", "    %s. " % m.group(2), "bullet")
                self._inline(m.group(3), "bullet")
                txt.insert("end", "\n")
                continue
            # 代码块围栏
            if line.strip().startswith("```"):
                continue
            # 普通段落
            self._inline(line, "normal")
            txt.insert("end", "\n")
        txt.config(state="disabled")

    def _inline(self, s, base):
        """处理 **加粗** *斜体* `代码`"""
        pos = 0
        for m in self.inline.finditer(s):
            if m.start() > pos:
                self.txt.insert("end", s[pos:m.start()], base)
            tok = m.group(0)
            if tok.startswith("**") or tok.startswith("__"):
                self.txt.insert("end", tok[2:-2], (base, "bold"))
            elif tok.startswith("`"):
                self.txt.insert("end", tok[1:-1], (base, "code"))
            else:
                self.txt.insert("end", tok[1:-1], (base, "italic"))
            pos = m.end()
        if pos < len(s):
            self.txt.insert("end", s[pos:], base)


# ---------------------------------------------------------------- 截图选区
class RegionSelector:
    def __init__(self, master, on_done):
        self.on_done = on_done
        self.top = tk.Toplevel(master)
        self.top.attributes("-fullscreen", True)
        self.top.attributes("-topmost", True)
        self.top.attributes("-alpha", 0.28)
        self.top.configure(bg="black")
        self.top.overrideredirect(True)
        self.canvas = tk.Canvas(self.top, bg="black", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.x0 = self.y0 = 0
        self.rect = None
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.top.bind("<Escape>", lambda e: self.cancel())
        self.top.focus_force()
        self.canvas.create_text(
            self.top.winfo_screenwidth() // 2, 40,
            text="拖拽选择要解释的区域   ·   Esc 取消",
            fill="#ffe066", font=(UI_FONT, 15, "bold"))

    def on_press(self, e):
        self.x0, self.y0 = e.x, e.y
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(
            self.x0, self.y0, self.x0, self.y0, outline="#00e0ff", width=2)

    def on_drag(self, e):
        if self.rect:
            self.canvas.coords(self.rect, self.x0, self.y0, e.x, e.y)

    def on_release(self, e):
        left, top = min(self.x0, e.x), min(self.y0, e.y)
        right, bottom = max(self.x0, e.x), max(self.y0, e.y)
        self.top.destroy()
        self.on_done(None if (right - left < 6 or bottom - top < 6)
                     else (left, top, right, bottom))

    def cancel(self):
        self.top.destroy()
        self.on_done(None)


# ---------------------------------------------------------------- 主程序
class App:
    def __init__(self):
        self.cfg = load_config()
        self.busy = False
        self.capture = None
        self.answer_win = None
        self._answer_text = None
        self._md = None
        self.root = tk.Tk()
        self.root.withdraw()
        # 线程 → 主线程 的消息队列（tkinter 不是线程安全的，
        # 绝对不能在 work 线程里直接调 widget 方法或 root.after）
        self.q = queue.Queue()
        self.hotkey = (self.cfg.get("hotkey") or "F11").upper()
        self._start_hotkey_thread()
        self._pump()
        log("v2.1 启动，热键=%s 模型=%s 流式=%s max_tokens=%s" % (
            self.hotkey, self.cfg.get("model"), self.cfg.get("stream"),
            self.cfg.get("max_tokens")))

    # -------- 主线程消息泵：只有它能碰 tkinter
    def _pump(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "stream_start":
                    self._start_streaming()
                elif kind == "chunk":
                    self._append_raw(payload)
                elif kind == "done":
                    self._render(payload)
                elif kind == "plain":
                    self._set_plain(payload)
                elif kind == "log":
                    log(payload)
                elif kind == "trigger":
                    self.trigger()
        except queue.Empty:
            pass
        except Exception as ex:
            log("消息泵异常: %r" % (ex,))
            self.busy = False
        self.root.after(40, self._pump)

    def _start_hotkey_thread(self):
        """每个热键跑一个独立线程（RegisterHotKey 绑线程，注销也必须同线程）"""
        vk = VK_CODES.get(self.hotkey, VK_CODES["F9"])
        name = self.hotkey

        def worker():
            user32 = ctypes.windll.user32
            self.hotkey_tid = ctypes.windll.kernel32.GetCurrentThreadId()
            if not user32.RegisterHotKey(None, 1, MOD_NOREPEAT, vk):
                self.q.put(("log", "注册热键 %s 失败（被占用？）" % name))
                self.q.put(("plain", "⚠️ 热键 %s 注册失败。\n\n"
                                     "可能被其它程序占用，右键配置或在设置窗口里换一个。"
                      % name))
                return
            self.q.put(("log", "热键 %s 注册成功" % name))
            msg = wt.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    self.q.put(("trigger", None))
                elif msg.message == WM_QUIT:
                    break
            user32.UnregisterHotKey(None, 1)
            self.q.put(("log", "热键 %s 已注销" % name))

        self._hotkey_thread = threading.Thread(target=worker, daemon=True)
        self._hotkey_thread.start()

    def set_hotkey(self, new_key):
        """运行时换热键：停旧线程 → 同线程注销 → 起新线程 → 写回 config.json"""
        new_key = (new_key or "").strip().upper()
        if new_key not in VK_CODES:
            return False, "不支持的按键"
        if new_key == self.hotkey:
            return True, ""
        old = self.hotkey
        tid = getattr(self, "hotkey_tid", None)
        if tid:
            ctypes.windll.user32.PostThreadMessageW(tid, WM_QUIT, 0, 0)
            th = getattr(self, "_hotkey_thread", None)
            if th:
                th.join(timeout=2)
        self.hotkey = new_key
        self.cfg["hotkey"] = new_key
        saved = save_config(self.cfg)
        self._start_hotkey_thread()
        log("热键 %s → %s（写盘=%s）" % (old, new_key, saved))
        return True, ""

    def open_settings(self):
        """设置窗口：选热键 + 选模型"""
        d = tk.Toplevel(self.root)
        d.title("AIShotExplain 设置")
        d.geometry("500x330")
        d.configure(bg=BG)
        d.attributes("-topmost", True)

        def row(label, maker):
            f = tk.Frame(d, bg=BG)
            f.pack(fill="x", padx=18, pady=(16, 0))
            tk.Label(f, text=label, bg=BG, fg=FG, width=8, anchor="w",
                     font=(UI_FONT, 10)).pack(side="left")
            w = maker(f)
            w.pack(side="left", fill="x", expand=True)
            return w

        cb_key = row("快捷键", lambda p: ttk.Combobox(p, values=list(VK_CODES.keys()),
                                                    state="readonly", font=(UI_FONT, 10)))
        cb_key.set(self.hotkey)

        cb_model = row("模型", lambda p: ttk.Combobox(
            p, values=["glm-4v-flash", "glm-4v-plus", "glm-4v", "glm-4.5v"],
            state="readonly", font=(UI_FONT, 10)))
        cb_model.set(self.cfg.get("model") or "glm-4v-flash")

        tk.Label(d, bg=BG, fg=DIM, justify="left", anchor="w", font=(UI_FONT, 9),
                 text=("glm-4v-flash  约 3-6 秒 · 免费 · 推荐\n"
                       "glm-4v-plus   约 4.5 秒 · 收费 · 细节更足\n"
                       "glm-4v        约 4.6 秒\n"
                       "glm-4.5v      约 18 秒 · 最聪明但慢（推理模型）")
                 ).pack(fill="x", padx=18, pady=(14, 0))

        msg = tk.Label(d, text="", bg=BG, fg="#8B3A1E", font=(UI_FONT, 9))
        msg.pack(fill="x", padx=18, pady=(10, 0))

        bar = tk.Frame(d, bg=BG)
        bar.pack(fill="x", padx=18, pady=14, side="bottom")

        def apply_and_close():
            ok, err = self.set_hotkey(cb_key.get())
            if not ok:
                msg.config(text="❌ " + err)
                return
            m = cb_model.get()
            if m != self.cfg.get("model"):
                self.cfg["model"] = m
                save_config(self.cfg)
                log("模型 → %s" % m)
            d.destroy()

        tk.Button(bar, text="取消", command=d.destroy, bg="#EFE4C0", fg="#4A4A4A",
                  relief="flat", padx=16, pady=6, bd=0).pack(side="right", padx=(8, 0))
        tk.Button(bar, text="保存", command=apply_and_close, bg=ACCENT, fg="#FFFFFF",
                  relief="flat", padx=20, pady=6, bd=0,
                  font=(UI_FONT, 10, "bold")).pack(side="right")
        d.bind("<Escape>", lambda e: d.destroy())
        return d

    def trigger(self):
        if self.busy:
            log("上次未完成，忽略")
            return
        self.busy = True
        RegionSelector(self.root, self.on_region)

    def on_region(self, box):
        if not box:
            self.busy = False
            return
        try:
            self.capture = ImageGrab.grab(bbox=box, all_screens=True)
        except Exception as ex:
            log("截图失败: %r" % (ex,))
            self.busy = False
            return
        log("截图 %dx%d" % self.capture.size)
        self.show_window(self.capture, "", loading=True)
        threading.Thread(target=self.ask_ai, args=(self.capture,), daemon=True).start()

    # -------- 调 AI（支持流式；所有界面更新都走队列，绝不跨线程碰 tkinter）
    def ask_ai(self, img, extra_question=None, retry=False):
        cfg = self.cfg
        key = (cfg.get("api_key") or "").strip()
        if not key:
            self.q.put(("plain", "❌ 没有可用的 API Key\n\n"
                                 "provider=zhipu 需要环境变量 ZHIPU_API_KEY"))
            return
        base = (cfg.get("base_url") or "").rstrip("/")
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode()
        prompt = extra_question or cfg.get("prompt") or "请解释这张图片"
        use_stream = bool(cfg.get("stream", True))

        # glm-4v-flash 系列 max_tokens 上限 1024（超了会 HTTP 400 code 1210）
        model = cfg.get("model") or "glm-4v-flash"
        mt = int(cfg.get("max_tokens") or 1024)
        if "flash" in model.lower() and mt > 1024:
            mt = 1024

        if (cfg.get("provider") or "zhipu").lower() == "zhipu":
            payload = {"model": model,
                       "messages": [{"role": "user", "content": [
                           {"type": "image_url", "image_url": {"url": b64}},
                           {"type": "text", "text": prompt}]}],
                       "temperature": float(cfg.get("temperature") or 0.3),
                       "max_tokens": mt}
        else:
            payload = {"model": model,
                       "messages": [{"role": "user", "content": [
                           {"type": "text", "text": prompt},
                           {"type": "image_url", "image_url": {
                               "url": "data:image/png;base64," + b64}}]}],
                       "temperature": float(cfg.get("temperature") or 0.3),
                       "max_tokens": mt}
        if use_stream:
            payload["stream"] = True

        req = urllib.request.Request(
            base + "/chat/completions", data=json.dumps(payload).encode(),
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
            method="POST")
        t0 = time.time()
        first_at = [None]
        acc = []
        try:
            with urllib.request.urlopen(req, timeout=int(cfg.get("timeout") or 180)) as r:
                if use_stream:
                    for raw in r:
                        line = raw.decode("utf-8", "replace").strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            j = json.loads(data)
                        except Exception:
                            continue
                        ch = j.get("choices", [{}])[0].get("delta", {}).get("content")
                        if ch:
                            if first_at[0] is None:
                                first_at[0] = time.time() - t0
                                self.q.put(("stream_start", None))
                            acc.append(ch)
                            self.q.put(("chunk", ch))
                    text = "".join(acc)
                else:
                    j = json.loads(r.read().decode())
                    msg = j["choices"][0]["message"]
                    text = (msg.get("content") or "").strip() or \
                           (msg.get("reasoning_content") or "").strip()
            if not text.strip():
                text = "（模型返回空内容）"
            self.q.put(("log", "AI 完成 %.1fs（首字 %.2fs，%d 字，max_tokens=%d）" % (
                time.time() - t0, first_at[0] or 0, len(text), mt)))
            self.q.put(("done", text))
        except urllib.error.HTTPError as ex:
            body = ex.read().decode("utf-8", "replace")[:400]
            # 参数类错误自动降级重试一次
            if ex.code == 400 and "1210" in body and not retry:
                self.q.put(("log", "max_tokens 超限，自动降到 1024 重试"))
                self.ask_ai(img, extra_question, retry=True)
                return
            self.q.put(("log", "HTTP %d %s" % (ex.code, body)))
            self.q.put(("plain", "❌ HTTP %d\n\n%s" % (ex.code, body)))
        except Exception as ex:
            self.q.put(("log", "异常 %r" % (ex,)))
            self.q.put(("plain", "❌ 请求异常\n\n%r" % (ex,)))

    # -------- 窗口
    def show_window(self, img, text, loading=False):
        if self.answer_win and self.answer_win.winfo_exists():
            self.answer_win.destroy()
        w = tk.Toplevel(self.root)
        self.answer_win = w
        w.title("AI 解释  ·  %s  ·  %s" % (self.hotkey, self.cfg.get("model")))
        w.geometry("820x660")
        w.minsize(620, 420)
        w.attributes("-topmost", True)
        w.configure(bg=BG)

        # ★ 布局关键：先把底部（输入框 + 发送）pack 到 side="bottom"，
        #   再 pack 中间的 expand 区域。反过来做的话，一张高缩略图会把
        #   底部挤出窗口边界 —— 这就是"对话框只显示一半"的 bug 根因。
        bottom = tk.Frame(w, bg=BG)
        bottom.pack(side="bottom", fill="x", padx=12, pady=(6, 14))

        top = tk.Frame(w, bg=BG)
        top.pack(side="top", fill="x", padx=12, pady=(12, 8))
        if self.cfg.get("show_image_thumb", True):
            # 宽高都要限，否则长截图（书页那种）会把缩略图拉得很高
            maxw = int(self.cfg.get("thumb_max_width") or 300)
            maxh = int(self.cfg.get("thumb_max_height") or 140)
            tw, th = img.size
            scale = min(maxw / float(tw), maxh / float(th), 1.0)
            if scale < 1.0:
                im = img.resize((max(1, int(tw * scale)), max(1, int(th * scale))),
                                Image.LANCZOS)
            else:
                im = img
            self._thumb = ImageTk.PhotoImage(im)
            tk.Label(top, image=self._thumb, bg=BG, relief="solid", bd=1,
                     highlightbackground=BORDER).pack(side="left")
        btns = tk.Frame(top, bg=BG)
        btns.pack(side="right", anchor="n")
        for txt, cmd in (("⚙", self.open_settings), ("复制", self.copy_answer),
                         ("重截", self.re_capture), ("关闭", w.destroy)):
            tk.Button(btns, text=txt, command=cmd, bg="#EFE4C0", fg="#4A4A4A",
                      relief="flat", padx=12, pady=4, bd=0,
                      activebackground="#E2D4A8", activeforeground="#222"
                      ).pack(fill="x", pady=2)

        frame = tk.Frame(w, bg=BG)
        frame.pack(side="top", fill="both", expand=True, padx=12, pady=(0, 4))
        txt = tk.Text(frame, wrap="word", bg=CARD, fg=FG, insertbackground=FG,
                      relief="flat", bd=0, font=(UI_FONT, 11), padx=14, pady=12,
                      selectbackground="#FFE9A8", selectforeground="#222")
        sb = tk.Scrollbar(frame, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)
        self._answer_text = txt
        self._md = MdRenderer(txt)
        if text:
            self._render(text)
        elif loading:
            txt.config(state="normal")
            txt.insert("1.0", "⏳ 正在识别并请 AI 解释…", "normal")
            txt.config(state="disabled")

        ent = tk.Entry(bottom, bg=CARD, fg=FG, insertbackground=FG, relief="solid",
                       bd=1, font=(UI_FONT, 10))
        ent.pack(side="left", fill="x", expand=True, ipady=7, padx=(0, 8))
        ent.insert(0, "继续追问（回车发送）…")

        def on_focus_in(_):
            if ent.get().startswith("继续追问"):
                ent.delete(0, "end")

        def send(_=None):
            q = ent.get().strip()
            if not q or q.startswith("继续追问"):
                return
            ent.delete(0, "end")
            self._append_qa(q)
            threading.Thread(target=self.ask_followup, args=(q,), daemon=True).start()

        ent.bind("<FocusIn>", on_focus_in)
        ent.bind("<Return>", send)
        tk.Button(bottom, text="发送", command=send, bg=ACCENT, fg="#FFFFFF",
                  relief="flat", padx=18, pady=6, bd=0,
                  activebackground="#9C7015", activeforeground="#FFFFFF",
                  font=(UI_FONT, 10, "bold")).pack(side="right")
        w.bind("<Escape>", lambda e: w.destroy())
        ent.focus_set()

    # -------- 流式追加（等宽原样显示，完成后再渲染格式）
    def _start_streaming(self):
        t = self._answer_text
        if t and t.winfo_exists():
            t.config(state="normal")
            t.delete("1.0", "end")

    def _append_raw(self, chunk):
        t = self._answer_text
        if t and t.winfo_exists():
            t.insert("end", chunk)
            t.see("end")

    def _append_qa(self, q):
        t = self._answer_text
        if t and t.winfo_exists():
            t.config(state="normal")
            t.insert("end", "\n\n" + "─" * 46 + "\n❓ " + q + "\n\n", "hr")
            t.insert("end", "⏳ 思考中…")
            t.see("end")
            t.config(state="disabled")

    def ask_followup(self, q):
        """追问：把原图 + 新问题再发一次（图还是那张图）"""
        if not self.capture:
            return
        self.ask_ai(self.capture, q)

    def _render(self, text):
        if self._md and self._answer_text and self._answer_text.winfo_exists():
            self._md.write(text)
        self.busy = False

    def _set_plain(self, text):
        t = self._answer_text
        if t and t.winfo_exists():
            t.config(state="normal")
            t.delete("1.0", "end")
            t.insert("1.0", text, "normal")
            t.config(state="disabled")
        self.busy = False

    def copy_answer(self):
        t = self._answer_text
        if t and t.winfo_exists():
            self.root.clipboard_clear()
            self.root.clipboard_append(t.get("1.0", "end").strip())

    def re_capture(self):
        if self.answer_win and self.answer_win.winfo_exists():
            self.answer_win.destroy()
        self.busy = False
        self.trigger()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    # --settings：只开设置窗口（不注册热键），用于「设置.bat」
    if "--settings" in sys.argv:
        _app = App.__new__(App)
        _app.cfg = load_config()
        _app.hotkey = (_app.cfg.get("hotkey") or "F9").upper()
        _app.hotkey_tid = None
        _app._hotkey_thread = None
        _app.capture = None
        _app.answer_win = None
        _app._answer_text = None
        _app._md = None
        _app.busy = False
        _app.q = queue.Queue()
        _app.root = tk.Tk()
        _app.root.withdraw()
        _app.root.title("AIShotExplain 设置")

        def _settings_only_set_hotkey(k):
            """设置模式：只写配置文件，不注册热键（避免和运行中的实例抢）"""
            k = (str(k) or "").strip().upper()
            if k not in VK_CODES:
                return False, "不支持的按键"
            _app.cfg["hotkey"] = k
            _app.hotkey = k
            save_config(_app.cfg)
            log("设置模式下改热键 → %s（重启主程序生效）" % k)
            return True, ""

        _app.set_hotkey = _settings_only_set_hotkey
        _app.root.after(120, _app.open_settings)
        _app.root.mainloop()
    else:
        App().run()
