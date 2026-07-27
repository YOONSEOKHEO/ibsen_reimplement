# CLAUDE.md — 프로젝트 작업 맥락

IBSEN(감독-배우 에이전트 협업 드라마 대본 생성, ACL 2024) 프레임워크를 **한국어 수업용**으로
재구현하는 프로젝트. 목표: 한국 대학생이 AI 배우들과 대화하며 극을 만들어가는(플레이 중심)
경험을 웹으로 제공하고, 그 반응을 평가로 수집.

## 환경 (중요)

`ibsen` conda 환경(python 3.11)은 **일부러 옛 버전으로 고정**되어 있음. 절대 `pip install -U` 금지 —
스택이 연쇄적으로 깨짐(openai 0.28 / guidance 0.0.64 / langchain 0.0.354 / pydantic 1.10.12 기반).

```bash
# 최초 구축
conda create -y -n ibsen python=3.11
conda install -y -n ibsen -c conda-forge faiss-cpu=1.7.4   # faiss 는 pip 아닌 conda 로
bash restore_env.sh                                        # 나머지 pip 핀 설치 + 검증

# 환경이 깨졌을 때 복구
bash restore_env.sh
```

`api_key.py` 는 각 기기에서 로컬로만 설정(추적 안 함, GitHub 에 올리지 않음):
```bash
echo 'OPENAI_API_KEY = "sk-..."' > api_key.py
```

## 실행

```bash
conda run -n ibsen --no-capture-output python play.py   # 한국어 터미널 플레이
IBSEN_DEBUG=1 ... python play.py                        # 내부 동작(감독/기억 로그)까지 보기
```

## 주요 파일 / 구조

- `server/` — 프레임워크 본체: `stage.py`(오케스트레이션), `director.py`(플롯 통제),
  `actor.py`(캐릭터+기억), `prompter.py`/`prompt.py`(LLM 프롬프트), `utils.py`, `corpus.py`
- `server/display.py` — **(추가)** 터미널 표시 헬퍼: 화자별 색/포맷, stdout 억제, `IBSEN_DEBUG` 플래그
- `play.py` — **(추가)** 노이즈 제거한 한국어 터미널 프론트엔드 (원본 `terminal_frontend.py` 는 보존)
- `data/script/hedda_gabler_kr.json` — **(추가)** 나레이션을 한국어로 번역한 시나리오
- `restore_env.sh` — **(추가)** 의존성 원상복구 스크립트

## 한국어화 방식 (관례)

- 시나리오/프로필은 영어로 두고, **프롬프트로 배우·감독이 한국어 대사를 생성**하게 함
  (`server/prompt.py` 의 PROMPT_ACTOR_DIALOGUE_SYSTEM, PROMPT_DIRECTOR_SCRIPT 에 한국어 지시).
- 화자 배역 이름은 **코드 매칭 때문에 영어 유지**("Hedda Gai" 등) — UI 에서 한글 표시명으로 매핑.
- 학생에게 보이는 나레이션(배경/입퇴장)만 KR 스크립트에서 한국어로 번역.

## 현재 상태 / 다음 단계

- [x] 환경 구축, 터미널 정리, 한국어화(검증됨)
- [ ] 웹 백엔드 `web_server.py` — Flask REST, **학생별 세션 격리**(현재 백엔드는 전역 stage 하나라 충돌)
- [ ] 한국어 웹 채팅 UI (fetch 기반 단일 페이지; 장면 이동/진행/말걸기/인터뷰; 배역 한글 표시)
- [ ] 연구실 Mac Studio 배포 (최초 시범 최대 3명)

## 원격

- `origin` = 이 레포 (작업용)
- `upstream` = https://github.com/OpenDFM/ibsen (원본, 참고용)
