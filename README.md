# XiaoZhi Windows MCP Agent Bridge

XiaoZhi Windows MCP Agent Bridge 是将桌面上带有麦克风与扬声器的 **ESP32 小智 AI 设备** 连接到本地 Windows 电脑的桥接服务。

通过标准的 **Model Context Protocol (MCP)**，小智可以作为**语音指挥官 (Voice Commander)**，调用 Windows 本地工具、执行电脑操作、全盘读写文件、控制 Edge 浏览器、截取屏幕进行视觉分析，并重点**调度本地 Codex CLI / Claude Code / OpenCode 等 AI Agent** 矩阵执行重型开发与工程任务。

---

## 整体架构：语音指挥官 + 本地 Agent 矩阵

```text
小智 ESP32 硬件 (麦克风/喇叭/屏幕)
       ↓ (语音交互)
 xiaozhi.me 官方云端 (ASR / LLM / TTS / MCP Client)
       ↓ (WebSocket JSON-RPC 2.0)
 XiaoZhi Windows Agent Bridge (本机 Python 进程)
       ↓
  Tool Registry (注册 49 个本地能力工具)
       ↓
┌─────────────────┬─────────────────┬─────────────────┬─────────────────┐
│ Windows 应用    │ 本地文件系统    │ 终端与 PowerShell│ 多 Agent 调遣器 │
│ • 智能启动/搜索 │ • 全盘/目录遍历 │ • Safe Terminal │ • Codex CLI 主力│
│ • 进程聚焦/退出 │ • 文件读写/删除 │ • 任意 Shell    │ • Claude / Open │
├─────────────────┼─────────────────┼─────────────────┼─────────────────┤
│ Desktop GUI     │ 屏幕视觉 (Vision│ Edge 浏览器     │ Skills/Workflow │
│ • 窗口枚举/点击 │ • 内存屏幕截图  │ • 网页搜索/打开 │ • 声明式 Skill  │
│ • 文本输入/按键 │ • MCP Image 回传│ • 页面提取/点击 │ • YAML 工作流   │
└─────────────────┴─────────────────┴─────────────────┴─────────────────┘
```

---

## 核心功能与语音指令

| 功能类别 | 语音指令示例 | 底层调用工具 |
| :--- | :--- | :--- |
| **Agent 调度** | *“小智，让 Codex 帮我把 ESP32 项目加上 Wi-Fi 重连逻辑”* | `dispatch_agent(agent_type="codex", task="...", mode="modify")` |
| **Agent 进度** | *“小智，刚才 Codex 的任务完成了吗？”* | `get_agent_status()` (返回精简语音摘要与改动统计) |
| **Agent 清单** | *“小智，我电脑里有哪些可以干活的 Agent？”* | `list_active_agents()` (检测 Codex, Claude, OpenCode 等) |
| **软件启动** | *“小智，打开 VS Code” / “打开飞书”* | `open_application`（智能扫描开始菜单与 PATH） |
| **屏幕视觉** | *“小智，看看我电脑屏幕上有什么”* | `screen_capture`（内存截屏回传多模态分析） |
| **文件查找** | *“小智，看看桌面上有哪些 PDF”* | `find_files(path="Desktop", pattern="*.pdf")` |
| **文件读写** | *“小智，帮我读取这个配置 / 写一个贪吃蛇”* | `read_text_file` / `write_text_file` |
| **项目 Git** | *“小智，看看我的项目最近改了什么”* | `git_status` / `git_diff` / `git_log` |
| **终端执行** | *“小智，运行这个项目的测试 / 查看 python 版本”* | `run_project_tests` / `run_shell_command` |
| **浏览器交互** | *“小智，搜索 ESP32-S3 数据手册”* | `browser_search` / `browser_open` |

---

## 快速配置与启动

### 1. 环境准备
- Windows 10 / 11
- Python 3.11+
- （可选）已安装的 Codex CLI (`npm i -g @openai/codex`)、Claude Code 等

安装依赖：
```powershell
pip install -r requirements.txt
```

### 2. 配置 MCP Endpoint
复制 `.env.example` 为 `.env` 并填入从小智控制台获取的 Endpoint：
```env
XIAOZHI_MCP_ENDPOINT=wss://api.xiaozhi.me/mcp/?token=YOUR_TOKEN_HERE
```

### 3. 配置 Workspace（可选）
在 `config.yaml` 中添加你的本地开发工程路径：
```yaml
workspaces:
  agent:
    path: .
  esp32:
    path: D:/Projects/esp32
  stm32:
    path: D:/Projects/stm32
```

### 4. 运行 Agent
```powershell
python main.py
```

终端将输出：
```text
===================================
 XiaoZhi Windows Agent
===================================
XiaoZhi MCP     CONNECTING
Tools           49
Security        ENABLED
Permission      UNRESTRICTED
MCP server handshake completed
Connected; registered 49 local tools
```

---

## 自动化测试

运行完整测试套件：
```powershell
python -m pytest
```