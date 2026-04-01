[English](README.md) | [简体中文](README_zh.md) | [繁體中文](README_zh_TW.md) | [한국어](README_ko.md) | [日本語](README_ja.md)

<div align="center">
  <h1>🚀 OpenManus-Max</h1>
  <p><strong>一个具备多级权限与信任衰减机制的高级自主 AI Agent 框架</strong></p>

  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
  [![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
</div>

## 👋 简介

OpenManus 非常棒，但 **OpenManus-Max** 将其提升到了一个全新的高度！

受 Manus 的沙盒安全性和 IronClaw 的本地执行灵活性的启发，OpenManus-Max 是一个经过全面重构的企业级 AI Agent 框架。它引入了 **DAG 任务调度器**、**分层记忆系统**、**20+ 内置工具**，以及革命性的**多级权限引擎**与 **Skill 信任衰减机制**。

无论你是需要一个在 Docker 沙盒中安全运行的 Agent，还是一个完全释放本地权限、能控制你桌面的全能助手，OpenManus-Max 都能满足你的需求。

## ✨ 核心特性

- 🛡️ **多级权限引擎**：支持 `YOLO`（完全放权）、`STANDARD`（拦截高危操作）、`STRICT`（严格审批）或 `SANDBOX`（Docker 隔离）四种模式。
- 🧩 **Skill 系统与信任衰减**：支持加载自定义 `SKILL.md` 文件。当加载第三方不受信的 Skill 时，系统会自动触发“信任衰减”，剥夺 Agent 的写入/执行权限，防止 Prompt 注入攻击。
- 🧠 **分层记忆系统**：工作记忆（精确上下文） $\rightarrow$ LLM 驱动的情节记忆（智能摘要） $\rightarrow$ 全局黑板（共享状态）。
- ⚡ **DAG 任务调度器**：自动将复杂目标分解为有向无环图（DAG），并支持异步并行执行。
- 🛠️ **20+ 内置工具**：Python/Shell 执行、多引擎 Web 搜索、深度网页爬取、多模态视觉分析、数据可视化、桌面自动化（RPA）等。
- 🔌 **MCP & A2A 协议**：内置 Model Context Protocol (MCP) 客户端和 Agent-to-Agent (A2A) HTTP 服务器。
- ⏰ **Routine 守护进程**：支持在后台运行定时任务（Cron/Interval），状态持久化到 SQLite。

## 🚀 安装指南

我们推荐使用 `uv` 以获得更快的安装体验。

```shell
# 1. 克隆仓库
git clone https://github.com/your-repo/OpenManus-Max.git
cd OpenManus-Max

# 2. 创建虚拟环境
uv venv --python 3.11
source .venv/bin/activate

# 3. 安装依赖
uv pip install -e ".[all]"
```

## ⚙️ 配置说明

在项目根目录创建 `config.toml` 文件（可以从示例文件复制）：

```shell
cp config.example.toml config.toml
```

编辑 `config.toml` 设置你的 API 密钥和首选权限模式：

```toml
[llm]
model = "gpt-4o"
base_url = "https://api.openai.com/v1"
api_key = "sk-..."

[permission]
# 可选模式: yolo, standard, strict, sandbox
mode = "standard"
```

## 🎯 快速启动

以交互模式运行 OpenManus-Max：

```shell
openmanus-max
```

### 其他执行模式

```shell
# 单任务模式
openmanus-max -t "帮我清理一下 Downloads 目录"

# YOLO 模式（完全本地权限，无确认提示）
openmanus-max --mode yolo -t "分析系统日志并修复错误"

# Sandbox 模式（在 Docker 中安全执行）
openmanus-max --mode sandbox -t "运行这个不受信的脚本"

# DAG 规划模式（适用于复杂任务）
openmanus-max --dag "调研 AI 发展趋势并生成一份 PPT"

# 启动 Routine 守护进程
openmanus-max --routine
```

## 📚 Skill 系统

你可以通过在 `~/.openmanus-max/skills/` 目录下添加 Skill 来扩展 Agent 的能力。一个 Skill 就是一个包含 `SKILL.md` 文件的目录，文件顶部使用 YAML frontmatter：

```markdown
---
name: github-pr-reviewer
version: "1.0.0"
description: Review GitHub Pull Requests
activation:
  keywords: ["github", "pr", "review"]
---
# GitHub PR Reviewer
When asked to review a PR, follow these steps...
```

*注意：放置在 `~/.openmanus-max/installed/` 目录下的 Skill 会被视为不受信，系统会自动衰减 Agent 的危险工具权限。*

## 🤝 贡献指南

欢迎任何形式的贡献！请随时提交 Pull Request。

## 📄 许可证

本项目采用 MIT 许可证 - 详情请参阅 [LICENSE](LICENSE) 文件。

## 🙏 致谢

特别感谢原版 [OpenManus](https://github.com/FoundationAgents/OpenManus) 团队以及 [IronClaw](https://github.com/nearai/ironclaw) 项目，他们的架构设计为本项目提供了重要灵感。
