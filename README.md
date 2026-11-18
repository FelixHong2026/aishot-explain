# AIShotExplain

Press **F9** → drag a box → get an AI explanation of whatever you selected.

Built for one specific job: **reading foreign-language books on screen**. Instead of
OCR'ing a page, copying the text out, and pasting it into a chatbot, you drag a box over
the paragraph and the explanation shows up in about a second — translated, with the
background knowledge and terminology explained.

No dependencies beyond Python's standard library and Pillow. No installer. No telemetry.

```
按 F9  →  拖选一块区域  →  一秒出解释
```

---

## Why this exists

Existing screenshot tools make you go through a menu:

```
right‑click tray → menu → screenshot mode → drag → menu again → "AI explain"
```

That's 4–5 steps for something you do dozens of times while reading. This tool is one key.

---

## Features

| | |
|---|---|
| **One-key trigger** | Global hotkey (**F9** by default), works over any app |
| **Region capture** | Full-screen overlay, drag to select, `Esc` to cancel. Multi-monitor aware |
| **Streaming output** | First token arrives in **~0.4 s** — text streams in, no blank wait |
| **Markdown rendered** | Headings, bold, bullets, code blocks are **styled**, not shown as raw `**#` |
| **Follow-up questions** | Ask about the same screenshot again without re-capturing |
| **Eye-comfort palette** | Cream/paper background, dark-grey text — designed for long reading sessions |
| **Hotkey picker** | Change the hotkey in the UI; re-registers at runtime, no restart |
| **Model picker** | Switch between speed and depth from the same dialog |
| **Zero dependencies** | `tkinter` + `Pillow` + `ctypes` only |

---

## Requirements

- Windows 10 / 11 (x64)
- Python 3.10+ (tested on 3.14)
- `pip install pillow`
- An API key for a **vision-capable** model — see below

---

## Install

```bat
git clone https://github.com/FelixHong2026/aishot-explain.git
cd aishot-explain
pip install -r requirements.txt
```

Set your API key as an environment variable (recommended — keeps it out of the repo):

```bat
setx ZHIPU_API_KEY "your-key-here"
```

Then double-click **`启动.bat`** (start) — or `pythonw aishot_explain.pyw`.

> `pythonw` runs it without a console window. The process sits in the background
> holding the hotkey; there is no tray icon.

---

## Usage

```
1. 启动.bat          start it (once; it stays resident)
2. F9                screen dims, "drag to select the region" appears
3. drag a box        release → explanation appears in ~1 s and streams in
```

In the result window:

| Button | Action |
|---|---|
| Bottom input + Enter | follow-up question about the same screenshot |
| **⚙** | settings — change hotkey / model |
| 复制 | copy the whole answer |
| 重截 | close and re-capture |
| 关闭 / Esc | close |

### Changing the hotkey

Two ways:

1. Click **⚙** in the result window → pick a key → **保存**. Takes effect **immediately**
   (the old hotkey is unregistered and the new one registered in a fresh thread).
2. Double-click **`设置快捷键.bat`** — opens just the settings dialog (useful when the
   main program isn't running).

Supported keys: `F1`–`F12`, `PrintScreen`, `Insert`, `Home`, `End`, `Pause`, `ScrollLock`.

---

## Configuration

`config.json` (created on first edit; delete it to fall back to defaults):

```jsonc
{
  "hotkey": "F9",
  "provider": "zhipu",                                  // zhipu | openai
  "base_url": "https://open.bigmodel.cn/api/paas/v4",
  "model": "glm-4v-flash",
  "stream": true,
  "api_key": "",                                        // empty → read ZHIPU_API_KEY
  "prompt": "请解释这张图片里的内容，用 Markdown 格式回答…",
  "max_tokens": 1024,
  "temperature": 0.3,
  "thumb_max_width": 300,
  "thumb_max_height": 140
}
```

### Choosing a model

Measured on the same test image:

| Model | Latency | Note |
|---|---|---|
| **`glm-4v-flash`** | **5.3 s** | **default — free tier** |
| `glm-4v-plus` | 4.5 s | fastest, paid, more detail |
| `glm-4v` | 4.6 s | |
| `glm-4.5v` | 18.4 s | reasoning model — smarter but slow |

With `"stream": true`, perceived latency is the first-token time: **0.37–0.44 s**.

> ⚠️ **`max_tokens` matters.** `glm-4v-flash` caps it at **1024** — anything higher returns
> `HTTP 400 code 1210`. The app clamps automatically for `*flash*` models and retries once
> at 1024 if the server still complains.

### Using any OpenAI-compatible vision model

```jsonc
{
  "provider": "openai",
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-4o-mini",
  "api_key": "sk-..."
}
```

### ⚠️ DeepSeek does not work

`deepseek-v4-pro` / `deepseek-flash` **silently ignore images** — the request returns
`HTTP 200` and the model replies "cannot read this image". It is not a vision model and
does not say so. Use Zhipu, OpenAI, Gemini or another multimodal model.

---

## Prompt templates

The default prompt is tuned for reading. Swap it for other uses:

**Translate only**
```
把图片里的文字翻译成中文，保持原段落结构，不要加解释。
```

**Technical / academic**
```
识别图片中的文字并解释：术语含义、公式推导思路、这段内容在讲什么。
```

**Classical Chinese**
```
识别图中的古文，给出白话文翻译，并解释生僻字词和典故出处。
```

---

## How it works

```
RegisterHotKey (ctypes)  →  a dedicated thread per hotkey owns the registration
        ↓
full-screen tkinter overlay  →  drag rectangle  →  crop with PIL.ImageGrab
        ↓
POST base64 PNG to the vision API with stream=true
        ↓
SSE chunks  →  queue.Queue  →  main-thread pump (root.after 40 ms)
        ↓
raw text streams in live; on [DONE] the same text is re-rendered with Markdown tags
```

Three design decisions worth knowing:

1. **`RegisterHotKey` is thread-affine.** Unregistering must happen on the thread that
   registered it, so changing the hotkey posts `WM_QUIT` to that thread and starts a new one.
2. **tkinter is not thread-safe.** Every widget update goes through a `queue.Queue` drained
   by a main-thread pump. Calling `widget.after()` from a worker thread *appears* to work
   until it doesn't — that exact bug caused a "freezes after the first error" report.
3. **Stream raw, render at the end.** Formatting on every chunk would be slow and jumpy;
   rendering once on completion keeps first-token latency at ~0.4 s *and* gives clean output.

---

## Files

```
aishot_explain.pyw    main program (~570 lines)
config.json           user config (gitignored)
启动.bat              launcher (pythonw, no console)
设置快捷键.bat         opens only the settings dialog
aishop.log            runtime log — check here when something breaks
```

---

## Known limitations

- **Windows only.** `RegisterHotKey` / `ImageGrab` paths are Windows-specific.
- **Needs network.** The explanation comes from an API; nothing works offline.
- **Single hotkey.** No modifier combos (`Ctrl+Alt+X`) — only bare keys.
- **No tray icon.** To quit: Task Manager → end `pythonw.exe`.
- **No autostart by default.** Add a shortcut to `shell:startup`, or a scheduled task if you
  want a logon delay.
- **Unsigned.** No code signing certificate, so SmartScreen may warn on first run.

---

## License

MIT — see [LICENSE](LICENSE).

Third-party: [Pillow](https://python-pillow.org/) (HPND), Tcl/Tk (BSD-style).
