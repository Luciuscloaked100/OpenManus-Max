[English](README.md) | [简体中文](README_zh.md) | [繁體中文](README_zh_TW.md) | [한국어](README_ko.md) | [日本語](README_ja.md)

<div align="center">
  <h1>🚀 OpenManus-Max</h1>
  <p><strong>다중 권한 및 신뢰 감쇠 메커니즘을 갖춘 고급 자율 AI 에이전트 프레임워크</strong></p>

  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
  [![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
</div>

## 👋 소개

OpenManus는 훌륭하지만, **OpenManus-Max**는 이를 완전히 새로운 수준으로 끌어올립니다!

Manus의 샌드박스 보안과 IronClaw의 로컬 실행 유연성에서 영감을 받은 OpenManus-Max는 완전히 리팩토링된 엔터프라이즈급 AI 에이전트 프레임워크입니다. **DAG 작업 스케줄러**, **계층적 메모리**, **20개 이상의 내장 도구**, 그리고 혁신적인 **다중 권한 엔진** 및 **Skill 신뢰 감쇠 메커니즘**을 특징으로 합니다.

Docker 샌드박스에서 안전하게 실행되는 에이전트가 필요하든, 데스크톱을 제어하는 완전히 해방된 로컬 비서가 필요하든, OpenManus-Max는 모든 요구를 충족합니다.

## ✨ 주요 기능

- 🛡️ **다중 권한 엔진**: `YOLO`(완전한 액세스), `STANDARD`(고위험 작업 차단), `STRICT`(승인 필요) 또는 `SANDBOX`(Docker 격리) 모드 중에서 선택할 수 있습니다.
- 🧩 **Skill 시스템 및 신뢰 감쇠**: 사용자 정의 `SKILL.md` 파일을 로드합니다. 타사 Skill이 로드되면 시스템은 자동으로 "신뢰 감쇠"를 트리거하여 프롬프트 주입 공격을 방지하기 위해 에이전트의 쓰기/실행 권한을 박탈합니다.
- 🧠 **계층적 메모리**: 작업 메모리 $\rightarrow$ LLM 기반 에피소드 요약 $\rightarrow$ 글로벌 블랙보드.
- ⚡ **DAG 작업 스케줄러**: 복잡한 목표를 방향성 비순환 그래프(DAG)로 자동 분해하고 비동기 병렬 실행을 지원합니다.
- 🛠️ **20개 이상의 내장 도구**: Python/Shell 실행, 웹 검색(다중 엔진), 심층 웹 크롤링, 비전 분석, 데이터 시각화, 데스크톱 자동화(RPA) 등.
- 🔌 **MCP & A2A 프로토콜**: 내장된 Model Context Protocol (MCP) 클라이언트 및 Agent-to-Agent (A2A) HTTP 서버.
- ⏰ **Routine 데몬**: 백그라운드에서 예약된 작업(Cron/Interval)을 실행하고 SQLite에 상태를 유지합니다.

## 🚀 설치 가이드

더 빠른 설치 경험을 위해 `uv`를 사용하는 것을 권장합니다.

```shell
# 1. 저장소 복제
git clone https://github.com/your-repo/OpenManus-Max.git
cd OpenManus-Max

# 2. 가상 환경 생성
uv venv --python 3.11
source .venv/bin/activate

# 3. 종속성 설치
uv pip install -e ".[all]"
```

## ⚙️ 구성

루트 디렉토리에 `config.toml` 파일을 생성합니다(예제에서 복사할 수 있음):

```shell
cp config.example.toml config.toml
```

`config.toml`을 편집하여 API 키와 선호하는 권한 모드를 설정합니다:

```toml
[llm]
model = "gpt-4o"
base_url = "https://api.openai.com/v1"
api_key = "sk-..."

[permission]
# 선택 가능한 모드: yolo, standard, strict, sandbox
mode = "standard"
```

## 🎯 빠른 시작

대화형 모드에서 OpenManus-Max 실행:

```shell
openmanus-max
```

### 기타 실행 모드

```shell
# 단일 작업 모드
openmanus-max -t "Downloads 폴더 정리해줘"

# YOLO 모드 (완전한 로컬 액세스, 확인 없음)
openmanus-max --mode yolo -t "시스템 로그를 분석하고 오류를 수정해줘"

# Sandbox 모드 (Docker에서 안전하게 실행)
openmanus-max --mode sandbox -t "이 신뢰할 수 없는 스크립트를 실행해줘"

# 복잡한 작업을 위한 DAG 계획 모드
openmanus-max --dag "AI 트렌드를 조사하고 PPT 프레젠테이션을 생성해줘"

# Routine 데몬 시작
openmanus-max --routine
```

## 📚 Skill 시스템

`~/.openmanus-max/skills/`에 Skill을 추가하여 에이전트의 기능을 확장할 수 있습니다. Skill은 YAML 프런트매터가 포함된 `SKILL.md` 파일이 있는 디렉토리입니다:

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

*참고: `~/.openmanus-max/installed/`에 배치된 Skill은 신뢰할 수 없는 것으로 간주되며 에이전트의 위험한 도구 권한이 자동으로 감쇠됩니다.*

## 🤝 기여 가이드

모든 형태의 기여를 환영합니다! 언제든지 Pull Request를 제출해 주세요.

## 📄 라이선스

이 프로젝트는 MIT 라이선스에 따라 라이선스가 부여됩니다 - 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

## 🙏 감사의 말

영감을 준 원래의 [OpenManus](https://github.com/FoundationAgents/OpenManus) 팀과 [IronClaw](https://github.com/nearai/ironclaw) 프로젝트에 특별한 감사를 드립니다.
