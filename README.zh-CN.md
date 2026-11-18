# AIShotExplain · 按 F9 截图，直接让 AI 解释

**为「读外文书籍时快速理解屏幕上的内容」而做的小工具。**

按 F9 → 拖一个框 → 一秒出解释。不用再走"托盘菜单 → 截图模式 → 拖框 → 再点一次 → AI 解释"那一套。

```
按 F9  →  拖选一块区域  →  0.4 秒开始出字，约 3-5 秒出完整解释
```

![status](https://img.shields.io/badge/platform-Windows%2010%2F11-blue)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

---

## 为什么做这个

现有的截图工具让你走菜单：

```
托盘右键 → 菜单 → 选截图模式 → 拖框 → 再点一次菜单 → "AI 解释"
```

读书时你一天要重复几十次，四五步太多。这个工具只要**一个键**。

---

## 功能

| | |
|---|---|
| **一键触发** | 全局热键（默认 **F9**），任何程序上都能用 |
| **区域截图** | 全屏遮罩，拖框选区，`Esc` 取消；支持多显示器 |
| **流式输出** | **0.4 秒**出第一个字，不用干等 |
| **Markdown 渲染** | 标题/加粗/列表/代码都是**排好版**的，不是原始 `**#` |
| **继续追问** | 针对同一张图接着问，不用重新截图 |
| **护眼配色** | 淡黄底 + 深灰字（对比度约 11:1），长时间读不累 |
| **快捷键可选** | 界面上点 ⚙ 就能换键，**即时生效不用重启** |
| **模型可选** | 同一个对话框里切换速度/深度 |
| **零第三方依赖** | 只用 `tkinter` + `Pillow` + `ctypes` |

---

## 环境要求

- Windows 10 / 11（x64）
- Python 3.10+（在 3.14 上验证）
- `pip install pillow`
- 一个**支持视觉**的模型 API Key（见下方）

---

## 安装

```bat
git clone https://github.com/FelixHong2026/aishot-explain.git
cd aishot-explain
pip install -r requirements.txt
```

把 API Key 放进环境变量（推荐，避免写进仓库）：

```bat
setx ZHIPU_API_KEY "你的key"
```

然后双击 **`启动.bat`**。

> 用 `pythonw` 启动，**没有黑框**。进程常驻后台占着热键，**没有托盘图标**。

---

## 使用

```
1. 启动.bat          启动一次即可，之后常驻
2. 按 F9             屏幕变暗，提示"拖拽选择要解释的区域"
3. 拖一个框，松手     约 0.4 秒开始出字，3-5 秒出完整解释
```

结果窗口里：

| 按钮 | 作用 |
|---|---|
| 底部输入框 + 回车 | 针对同一张图继续追问 |
| **⚙** | 设置：换快捷键 / 换模型 |
| 复制 | 复制全部答案 |
| 重截 | 关掉重新截 |
| 关闭 / Esc | 关闭窗口 |

### 换快捷键的两种方式

1. 结果窗口点 **⚙** → 选键 → **保存** —— **立即生效**（旧热键注销 + 新热键在线程中重新注册）
2. 双击 **`设置快捷键.bat`** —— 只开设置窗口（主程序没在跑时用这个）

支持：`F1`~`F12`、`PrintScreen`、`Insert`、`Home`、`End`、`Pause`、`ScrollLock`

---

## 配置

`config.json`（首次修改设置时创建；删掉会回落到默认值）：

```jsonc
{
  "hotkey": "F9",
  "provider": "zhipu",                                  // zhipu | openai
  "base_url": "https://open.bigmodel.cn/api/paas/v4",
  "model": "glm-4v-flash",
  "stream": true,
  "api_key": "",                                        // 留空则读 ZHIPU_API_KEY
  "prompt": "请解释这张图片里的内容，用 Markdown 格式回答…",
  "max_tokens": 1024,
  "temperature": 0.3,
  "thumb_max_width": 300,
  "thumb_max_height": 140
}
```

### 模型怎么选（同一张测试图实测）

| 模型 | 耗时 | 说明 |
|---|---|---|
| **`glm-4v-flash`** | **5.3 秒** | **默认，免费** |
| `glm-4v-plus` | 4.5 秒 | 最快，收费，细节更足 |
| `glm-4v` | 4.6 秒 | |
| `glm-4.5v` | 18.4 秒 | 推理模型，最聪明但慢 |

配合 `"stream": true`，**感知等待 = 首字时间 = 0.37~0.44 秒**。

> ⚠️ **`max_tokens` 有坑**：`glm-4v-flash` 上限是 **1024**，超了直接报 `HTTP 400 code 1210`。
> 程序会自动对 `*flash*` 模型截断，并在仍报错时自动降级重试一次。

### 用其他 OpenAI 兼容的视觉模型

```jsonc
{
  "provider": "openai",
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-4o-mini",
  "api_key": "sk-..."
}
```

### ⚠️ DeepSeek 不行

`deepseek-v4-pro` / `deepseek-flash` 会**静默忽略图片** —— 返回 `HTTP 200`，
但模型回答"无法读取这张图片"。它不是视觉模型，也不报错。别踩这个坑。

---

## 提示词模板

默认提示词是为读书调好的，其他场景可以直接换：

**只翻译**
```
把图片里的文字翻译成中文，保持原段落结构，不要加解释。
```

**学术/技术资料**
```
识别图片中的文字并解释：术语含义、公式推导思路、这段内容在讲什么。
```

**古文/文言**
```
识别图中的古文，给出白话文翻译，并解释生僻字词和典故出处。
```

---

## 实现原理

```
RegisterHotKey (ctypes)  →  每个热键一个专用线程持有注册
        ↓
tkinter 全屏遮罩  →  拖框  →  PIL.ImageGrab 裁剪
        ↓
base64 PNG POST 给视觉模型 API，stream=true
        ↓
SSE 数据块  →  queue.Queue  →  主线程泵（root.after 40ms）
        ↓
原始文字实时追加；收到 [DONE] 后整段重新按 Markdown 渲染
```

三个关键设计：

1. **`RegisterHotKey` 绑定线程** —— 注销必须在注册它的那个线程做，所以换热键时向该线程投递 `WM_QUIT`，停掉再起新线程。
2. **tkinter 不是线程安全的** —— 所有界面更新都走 `queue.Queue` + 主线程泵。在工作线程里调 `widget.after()` 表面能跑，直到它不跑为止（这个 bug 真实发生过：一次 HTTP 400 之后整个程序就"卡死"了）。
3. **流式先原样、结束再渲染** —— 每个块都重排版会很卡；只在完成时渲染一次，既保证 0.4 秒首字，又保证格式干净。

---

## 文件说明

```
aishot_explain.pyw    主程序（约 570 行）
config.json           用户配置（已 gitignore）
启动.bat              启动器（pythonw，无黑框）
设置快捷键.bat         只开设置窗口
aishop.log            运行日志 —— 出问题先看这里
```

---

## 已知限制

- **仅 Windows** —— `RegisterHotKey` / `ImageGrab` 都是 Windows 路径
- **需要联网** —— 解释来自 API，离线用不了
- **单一热键** —— 不支持组合键（`Ctrl+Alt+X`），只支持单键
- **没有托盘图标** —— 退出靠任务管理器结束 `pythonw.exe`
- **默认不开机自启** —— 需要的话把快捷方式丢进 `shell:startup`，或用计划任务做延迟启动
- **未做代码签名** —— 首次运行可能被 SmartScreen 提示

---

## 许可

MIT —— 见 [LICENSE](LICENSE)。

第三方： [Pillow](https://python-pillow.org/)（HPND）、Tcl/Tk（BSD-style）。
