# OpenManus-Max: 多级权限与 Skill 系统架构方案

本文档详细介绍了 OpenManus-Max 中新增的**多级权限引擎**、**Skill 信任衰减系统**以及**双引擎执行器**的设计与实现。该方案参考了 IronClaw 的混合沙盒理念，并结合了用户可选权限模式的需求，旨在提供一个既能完全放权本地操作，又能严格管控沙盒执行的灵活架构。

## 1. 核心架构设计

为了实现“用户可选权限模式”，我们将原有的单一沙盒执行模式重构为以下三个核心组件：

1. **PermissionEngine (权限引擎)**：负责拦截所有工具调用，根据当前模式和工具风险等级决定是否放行、是否需要用户审批。
2. **SkillRegistry & Attenuation (Skill 信任衰减系统)**：负责加载本地 `SKILL.md`，并根据 Skill 的信任级别动态裁剪 Agent 的高危工具。
3. **ExecutionEngine (双引擎执行器)**：根据权限模式自动选择在本地宿主机（Local）还是 Docker 容器（Sandbox）中执行代码和命令。

---

## 2. 多级权限模式 (Permission Modes)

系统提供四种权限模式，用户可以通过 CLI 参数 `--mode` 或配置文件 `config.toml` 进行切换。

| 模式名称 | 风险等级 | 执行环境 | 审批策略 | 适用场景 |
| :--- | :--- | :--- | :--- | :--- |
| **YOLO** | 极高 | 本地宿主机 | **永不审批**。Agent 拥有完全的系统控制权。 | 信任的本地自动化任务、系统运维 |
| **STANDARD** | 中等 | 本地宿主机 | 默认模式。拦截 `SYSTEM` 级高危操作（如 `computer_use`），允许普通文件读写和安全命令。 | 日常开发、文件处理、数据分析 |
| **STRICT** | 低 | 本地宿主机 | 拦截所有 `WORKSPACE` 及以上操作。任何写入、执行动作都必须经过用户确认。 | 处理敏感数据、不确定的外部任务 |
| **SANDBOX** | 极低 | Docker 容器 | 强制在隔离容器中执行代码。限制文件访问只能在指定的 `workspace_dir` 内。 | 运行未知代码、处理不受信的网页内容 |

### 2.1 工具风险分级 (Tool Risk Levels)

每个工具都被赋予了一个固定的风险等级：

- `READ_ONLY (0)`: 纯读取操作（如 `web_search`, `vision_analyze`）。无需审批。
- `WORKSPACE (1)`: 仅影响工作区（如 `file_editor`, `planning`）。在 STRICT 模式下需审批。
- `EXECUTE (2)`: 代码执行（如 `python_execute`, `shell_exec`）。在 STANDARD 模式下需审批。
- `SYSTEM (3)`: 系统级控制（如 `computer_use`）。在 STANDARD 模式下需审批。
- `DESTRUCTIVE (4)`: 破坏性操作。默认拦截。

---

## 3. Skill 系统与信任衰减 (Trust Attenuation)

参考 IronClaw 的设计，我们引入了基于 `SKILL.md` 的技能系统，并实现了**信任衰减机制**，以防止恶意 Skill 滥用高危工具。

### 3.1 Skill 结构

一个 Skill 是一个包含 `SKILL.md` 的目录。`SKILL.md` 采用 Markdown Frontmatter 格式：

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

### 3.2 信任级别与衰减逻辑

Skill 分为两个信任级别：
- **TRUSTED (1)**: 存放在 `~/.openmanus-max/skills/` 下的用户自定义 Skill。
- **INSTALLED (0)**: 存放在 `~/.openmanus-max/installed/` 下的第三方下载 Skill。

**衰减机制 (Attenuation)**：
当 Agent 激活了一个 `INSTALLED` 级别的第三方 Skill 时，系统会**自动从 Agent 的可用工具列表中移除所有风险等级 $\ge$ `WORKSPACE` 的工具**（如 `shell_exec`, `python_execute`, `file_editor`）。
这意味着，第三方 Skill 只能使用 `web_search`, `browser` 等只读工具，彻底杜绝了恶意 Prompt 注入导致本地系统被破坏的风险。

---

## 4. 双引擎执行器 (Execution Engine)

为了支撑多级权限，我们重构了 `shell_exec` 和 `python_execute` 工具，使其底层调用统一的 `ExecutionEngine`。

执行器支持两种 Backend：
1. **Local Backend**: 直接在宿主机执行。适用于 YOLO, STANDARD, STRICT 模式。
2. **Docker Backend**: 在隔离的容器中执行。适用于 SANDBOX 模式。

执行器在执行前会调用 `PermissionEngine` 进行双重校验：
- **路径策略 (Path Policy)**: 检查命令或代码是否试图访问 `workspace_dir` 之外的敏感路径（如 `/etc/passwd`）。
- **命令策略 (Command Policy)**: 拦截危险命令（如 `rm -rf /`, `mkfs`）。

---

## 5. Routine 守护进程引擎

为了实现类似 Cron 的后台自动化能力，我们新增了 `RoutineEngine`。

- **触发器**: 支持 `INTERVAL` (固定间隔) 和 `CRON` (Cron 表达式) 两种触发方式。
- **持久化**: 任务状态和执行历史保存在 SQLite 数据库中 (`~/.openmanus-max/routines.db`)。
- **执行**: 守护进程在后台轮询，到达触发时间时，自动拉起一个配置了相应权限模式的 `ManusAgent` 执行预设的 Prompt。

---

## 6. 使用示例

### 6.1 切换权限模式

```bash
# 默认 Standard 模式（高危操作需确认）
openmanus-max -t "帮我清理一下 Downloads 目录"

# YOLO 模式（完全放权，直接执行）
openmanus-max --mode yolo -t "帮我清理一下 Downloads 目录"

# Sandbox 模式（在 Docker 中安全执行）
openmanus-max --mode sandbox -t "运行这个从网上下载的脚本"
```

### 6.2 CLI 交互命令

在交互模式下，可以使用内置命令查看系统状态：

```text
[You] > /permission

  Mode:             STANDARD
  Workspace:        /home/ubuntu/.openmanus-max/workspace
  Session approved: (none)
  Always approved:  (none)
  Writable paths:   ['/home/ubuntu/.openmanus-max/workspace', '/tmp']

[You] > /skills

Loaded skills:
  [TRUSTED] my-local-skill v1.0: A local skill
  [INSTALLED] third-party-tool v2.1: Downloaded from internet
```

## 7. 总结

通过引入多级权限引擎、Skill 信任衰减和双引擎执行器，OpenManus-Max 成功融合了 Manus 的沙盒安全性和 IronClaw 的本地操作灵活性。用户可以根据任务的信任度，在“绝对安全”和“绝对自由”之间自由切换。
