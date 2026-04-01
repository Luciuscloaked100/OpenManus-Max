[English](README.md) | [简体中文](README_zh.md) | [繁體中文](README_zh_TW.md) | [한국어](README_ko.md) | [日本語](README_ja.md)

<div align="center">
  <h1>🚀 OpenManus-Max</h1>
  <p><strong>An Advanced Autonomous AI Agent Framework with Multi-Level Permissions & Trust Attenuation</strong></p>

  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
  [![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
</div>

## 👋 Introduction

OpenManus is great, but **OpenManus-Max** takes it to the next level! 

Inspired by the sandboxed security of Manus and the local execution flexibility of IronClaw, OpenManus-Max is a fully refactored, enterprise-grade AI Agent framework. It features a **DAG Task Scheduler**, **Hierarchical Memory**, **20+ Built-in Tools**, and a revolutionary **Multi-Level Permission Engine** with **Skill Trust Attenuation**.

Whether you want an agent that safely runs in a Docker sandbox, or a fully unleashed local assistant that controls your desktop, OpenManus-Max has you covered.

## ✨ Key Features

- 🛡️ **Multi-Level Permission Engine**: Choose between `YOLO` (full access), `STANDARD` (intercepts high-risk), `STRICT` (requires approval), or `SANDBOX` (Docker isolation).
- 🧩 **Skill System & Trust Attenuation**: Load custom `SKILL.md` files. Third-party skills automatically trigger "Trust Attenuation", stripping the agent of write/execute permissions to prevent prompt injection attacks.
- 🧠 **Hierarchical Memory**: Working Memory $\rightarrow$ LLM-driven Episodic Summary $\rightarrow$ Global Blackboard.
- ⚡ **DAG Task Scheduler**: Automatically breaks down complex goals into Directed Acyclic Graphs (DAG) for parallel execution.
- 🛠️ **20+ Built-in Tools**: Python/Shell execution, Web Search (Multi-engine), Deep Web Crawling, Vision Analysis, Data Visualization, Desktop Automation (RPA), and more.
- 🔌 **MCP & A2A Protocol**: Built-in Model Context Protocol (MCP) client and Agent-to-Agent (A2A) HTTP server.
- ⏰ **Routine Daemon**: Run scheduled tasks (Cron/Interval) in the background with SQLite persistence.

## 🚀 Installation

We recommend using `uv` for a faster installation experience.

```shell
# 1. Clone the repository
git clone https://github.com/your-repo/OpenManus-Max.git
cd OpenManus-Max

# 2. Create virtual environment
uv venv --python 3.11
source .venv/bin/activate

# 3. Install dependencies
uv pip install -e ".[all]"
```

## ⚙️ Configuration

Create a `config.toml` file in the root directory (you can copy from `config.example.toml`):

```shell
cp config.example.toml config.toml
```

Edit `config.toml` to set your API keys and preferred permission mode:

```toml
[llm]
model = "gpt-4o"
base_url = "https://api.openai.com/v1"
api_key = "sk-..."

[permission]
# Choose from: yolo, standard, strict, sandbox
mode = "standard"
```

## 🎯 Quick Start

Run OpenManus-Max in interactive mode:

```shell
openmanus-max
```

### Other Execution Modes

```shell
# Single task mode
openmanus-max -t "Clean up my Downloads folder"

# YOLO mode (Full local access, no confirmations)
openmanus-max --mode yolo -t "Analyze system logs and fix errors"

# Sandbox mode (Safe execution in Docker)
openmanus-max --mode sandbox -t "Run this untrusted script"

# DAG Planning mode for complex tasks
openmanus-max --dag "Research AI trends and generate a PPT presentation"

# Start Routine Daemon
openmanus-max --routine
```

## 📚 Skill System

You can extend the agent's capabilities by adding skills to `~/.openmanus-max/skills/`. A skill is simply a directory containing a `SKILL.md` file with YAML frontmatter:

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

*Note: Skills placed in `~/.openmanus-max/installed/` are treated as untrusted and will automatically attenuate the agent's dangerous tools.*

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgements

Special thanks to the original [OpenManus](https://github.com/FoundationAgents/OpenManus) team and the [IronClaw](https://github.com/nearai/ironclaw) project for their inspiring architectures.
