[English](README.md) | [简体中文](README_zh.md) | [繁體中文](README_zh_TW.md) | [한국어](README_ko.md) | [日本語](README_ja.md)

<div align="center">
  <h1>🚀 OpenManus-Max</h1>
  <p><strong>マルチレベル権限と信頼減衰メカニズムを備えた高度な自律型 AI エージェントフレームワーク</strong></p>

  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
  [![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
</div>

## 👋 はじめに

OpenManus は素晴らしいですが、**OpenManus-Max** はそれを次のレベルへと引き上げます！

Manus のサンドボックスセキュリティと IronClaw のローカル実行の柔軟性にインスパイアされた OpenManus-Max は、完全にリファクタリングされたエンタープライズグレードの AI エージェントフレームワークです。**DAG タスクスケジューラ**、**階層型メモリ**、**20以上の組み込みツール**、そして革新的な**マルチレベル権限エンジン**と **Skill 信頼減衰メカニズム**を備えています。

Docker サンドボックス内で安全に実行されるエージェントが必要な場合でも、デスクトップを制御する完全に解放されたローカルアシスタントが必要な場合でも、OpenManus-Max はあなたのニーズを満たします。

## ✨ 主な機能

- 🛡️ **マルチレベル権限エンジン**: `YOLO`（完全アクセス）、`STANDARD`（高リスク操作を傍受）、`STRICT`（承認が必要）、または `SANDBOX`（Docker 分離）から選択できます。
- 🧩 **Skill システムと信頼減衰**: カスタム `SKILL.md` ファイルをロードします。サードパーティの Skill がロードされると、システムは自動的に「信頼減衰」をトリガーし、プロンプトインジェクション攻撃を防ぐためにエージェントの書き込み/実行権限を剥奪します。
- 🧠 **階層型メモリ**: ワーキングメモリ $\rightarrow$ LLM 駆動のエピソード要約 $\rightarrow$ グローバルブラックボード。
- ⚡ **DAG タスクスケジューラ**: 複雑な目標を自動的に有向非巡回グラフ（DAG）に分解し、非同期並列実行をサポートします。
- 🛠️ **20以上の組み込みツール**: Python/Shell 実行、Web 検索（マルチエンジン）、ディープ Web クローリング、ビジョン分析、データ視覚化、デスクトップ自動化（RPA）など。
- 🔌 **MCP & A2A プロトコル**: Model Context Protocol (MCP) クライアントと Agent-to-Agent (A2A) HTTP サーバーを内蔵。
- ⏰ **Routine デーモン**: スケジュールされたタスク（Cron/Interval）をバックグラウンドで実行し、SQLite に永続化します。

## 🚀 インストール

より高速なインストール体験のために `uv` の使用をお勧めします。

```shell
# 1. リポジトリをクローン
git clone https://github.com/your-repo/OpenManus-Max.git
cd OpenManus-Max

# 2. 仮想環境を作成
uv venv --python 3.11
source .venv/bin/activate

# 3. 依存関係をインストール
uv pip install -e ".[all]"
```

## ⚙️ 設定

ルートディレクトリに `config.toml` ファイルを作成します（サンプルからコピーできます）：

```shell
cp config.example.toml config.toml
```

`config.toml` を編集して、API キーと希望する権限モードを設定します：

```toml
[llm]
model = "gpt-4o"
base_url = "https://api.openai.com/v1"
api_key = "sk-..."

[permission]
# 選択可能なモード: yolo, standard, strict, sandbox
mode = "standard"
```

## 🎯 クイックスタート

インタラクティブモードで OpenManus-Max を実行します：

```shell
openmanus-max
```

### その他の実行モード

```shell
# シングルタスクモード
openmanus-max -t "Downloads フォルダをクリーンアップして"

# YOLO モード（完全なローカルアクセス、確認なし）
openmanus-max --mode yolo -t "システムログを分析してエラーを修正して"

# Sandbox モード（Docker での安全な実行）
openmanus-max --mode sandbox -t "この信頼できないスクリプトを実行して"

# 複雑なタスクのための DAG プランニングモード
openmanus-max --dag "AI のトレンドを調査して PPT プレゼンテーションを生成して"

# Routine デーモンを開始
openmanus-max --routine
```

## 📚 Skill システム

`~/.openmanus-max/skills/` に Skill を追加することで、エージェントの機能を拡張できます。Skill は、YAML フロントマターを含む `SKILL.md` ファイルを含むディレクトリです：

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

*注: `~/.openmanus-max/installed/` に配置された Skill は信頼できないものとして扱われ、エージェントの危険なツール権限が自動的に減衰されます。*

## 🤝 貢献

あらゆる形での貢献を歓迎します！お気軽に Pull Request を送信してください。

## 📄 ライセンス

このプロジェクトは MIT ライセンスの下でライセンスされています - 詳細は [LICENSE](LICENSE) ファイルをご覧ください。

## 🙏 謝辞

インスピレーションを与えてくれたオリジナルの [OpenManus](https://github.com/FoundationAgents/OpenManus) チームと [IronClaw](https://github.com/nearai/ironclaw) プロジェクトに特別な感謝を捧げます。
