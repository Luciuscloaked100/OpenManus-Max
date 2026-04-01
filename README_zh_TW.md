[English](README.md) | [简体中文](README_zh.md) | [繁體中文](README_zh_TW.md) | [한국어](README_ko.md) | [日本語](README_ja.md)

<div align="center">
  <h1>🚀 OpenManus-Max</h1>
  <p><strong>一個具備多級權限與信任衰減機制的高級自主 AI Agent 框架</strong></p>

  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
  [![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
</div>

## 👋 簡介

OpenManus 非常棒，但 **OpenManus-Max** 將其提升到了一個全新的高度！

受 Manus 的沙盒安全性和 IronClaw 的本地執行靈活性的啟發，OpenManus-Max 是一個經過全面重構的企業級 AI Agent 框架。它引入了 **DAG 任務調度器**、**分層記憶系統**、**20+ 內建工具**，以及革命性的**多級權限引擎**與 **Skill 信任衰減機制**。

無論你是需要一個在 Docker 沙盒中安全運行的 Agent，還是一個完全釋放本地權限、能控制你桌面的全能助手，OpenManus-Max 都能滿足你的需求。

## ✨ 核心特性

- 🛡️ **多級權限引擎**：支援 `YOLO`（完全放權）、`STANDARD`（攔截高危操作）、`STRICT`（嚴格審批）或 `SANDBOX`（Docker 隔離）四種模式。
- 🧩 **Skill 系統與信任衰減**：支援載入自定義 `SKILL.md` 檔案。當載入第三方不受信的 Skill 時，系統會自動觸發「信任衰減」，剝奪 Agent 的寫入/執行權限，防止 Prompt 注入攻擊。
- 🧠 **分層記憶系統**：工作記憶（精確上下文） $\rightarrow$ LLM 驅動的情節記憶（智能摘要） $\rightarrow$ 全局黑板（共享狀態）。
- ⚡ **DAG 任務調度器**：自動將複雜目標分解為有向無環圖（DAG），並支援非同步並行執行。
- 🛠️ **20+ 內建工具**：Python/Shell 執行、多引擎 Web 搜尋、深度網頁爬取、多模態視覺分析、數據視覺化、桌面自動化（RPA）等。
- 🔌 **MCP & A2A 協議**：內建 Model Context Protocol (MCP) 客戶端和 Agent-to-Agent (A2A) HTTP 伺服器。
- ⏰ **Routine 守護進程**：支援在後台運行定時任務（Cron/Interval），狀態持久化到 SQLite。

## 🚀 安裝指南

我們推薦使用 `uv` 以獲得更快的安裝體驗。

```shell
# 1. 複製倉庫
git clone https://github.com/your-repo/OpenManus-Max.git
cd OpenManus-Max

# 2. 建立虛擬環境
uv venv --python 3.11
source .venv/bin/activate

# 3. 安裝依賴
uv pip install -e ".[all]"
```

## ⚙️ 配置說明

在專案根目錄建立 `config.toml` 檔案（可以從範例檔案複製）：

```shell
cp config.example.toml config.toml
```

編輯 `config.toml` 設定你的 API 金鑰和首選權限模式：

```toml
[llm]
model = "gpt-4o"
base_url = "https://api.openai.com/v1"
api_key = "sk-..."

[permission]
# 可選模式: yolo, standard, strict, sandbox
mode = "standard"
```

## 🎯 快速啟動

以互動模式運行 OpenManus-Max：

```shell
openmanus-max
```

### 其他執行模式

```shell
# 單任務模式
openmanus-max -t "幫我清理一下 Downloads 目錄"

# YOLO 模式（完全本地權限，無確認提示）
openmanus-max --mode yolo -t "分析系統日誌並修復錯誤"

# Sandbox 模式（在 Docker 中安全執行）
openmanus-max --mode sandbox -t "運行這個不受信的腳本"

# DAG 規劃模式（適用於複雜任務）
openmanus-max --dag "調研 AI 發展趨勢並生成一份 PPT"

# 啟動 Routine 守護進程
openmanus-max --routine
```

## 📚 Skill 系統

你可以透過在 `~/.openmanus-max/skills/` 目錄下新增 Skill 來擴展 Agent 的能力。一個 Skill 就是一個包含 `SKILL.md` 檔案的目錄，檔案頂部使用 YAML frontmatter：

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

*注意：放置在 `~/.openmanus-max/installed/` 目錄下的 Skill 會被視為不受信，系統會自動衰減 Agent 的危險工具權限。*

## 🤝 貢獻指南

歡迎任何形式的貢獻！請隨時提交 Pull Request。

## 📄 授權條款

本專案採用 MIT 授權條款 - 詳情請參閱 [LICENSE](LICENSE) 檔案。

## 🙏 致謝

特別感謝原版 [OpenManus](https://github.com/FoundationAgents/OpenManus) 團隊以及 [IronClaw](https://github.com/nearai/ironclaw) 專案，他們的架構設計為本專案提供了重要靈感。
