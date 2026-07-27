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

# 웹(학생 여러 명, 세션 격리) — 터미널 2개.  포트 5000 은 macOS AirPlay 가 점유 → PORT=5055 권장
PORT=5055 conda run -n ibsen --no-capture-output python web_server.py   # [1] 서버
PORT=5055 bash serve_tunnel.sh                                          # [2] 공개 https(cloudflared)
```

## 주요 파일 / 구조

- `server/` — 프레임워크 본체: `stage.py`(오케스트레이션), `director.py`(플롯 통제),
  `actor.py`(캐릭터+기억), `prompter.py`/`prompt.py`(LLM 프롬프트), `utils.py`, `corpus.py`
- `server/display.py` — **(추가)** 터미널 표시 헬퍼: 화자별 색/포맷, stdout 억제, `IBSEN_DEBUG` 플래그
- `play.py` — **(추가)** 노이즈 제거한 한국어 터미널 프론트엔드 (원본 `terminal_frontend.py` 는 보존)
- `web_server.py` — **(추가)** Flask 웹 백엔드. `SessionManager`(학생별 `GenerativeStage` 격리),
  REST(`/api/start·state·action·interview·feedback`). 백그라운드 초기화, director 커서로 대사 추출.
- `templates/play.html` — **(추가)** fetch 기반 단일 페이지 한국어 채팅 UI (배역 한글 표시명 매핑)
- `serve_tunnel.sh` — **(추가)** Cloudflare Tunnel 로 공개 https 주소 발급
- `data/eval/feedback.jsonl` — **(런타임 생성, gitignore)** 학생 설문+대사 로그 수집물
- `data/script/*_kr.json` — 한국어 시나리오. 원본 `hedda_gabler_kr` +
  **(추가) `mystery_villa_kr`(추리), `job_interview_kr`(취업면접), `student_council_kr`(학생회갈등),
  `family_chuseok_kr`(가족드라마)** — 4종 신규. 단일 장소 3막 선형 구조.
- `restore_env.sh` — **(추가)** 의존성 원상복구 스크립트

## 한국어화 방식 (관례)

- 시나리오/프로필은 영어로 두고, **프롬프트로 배우·감독이 한국어 대사를 생성**하게 함
  (`server/prompt.py` 의 PROMPT_ACTOR_DIALOGUE_SYSTEM, PROMPT_DIRECTOR_SCRIPT 에 한국어 지시).
- 화자 배역 이름은 **코드 매칭 때문에 영어 유지**("Hedda Gai" 등) — UI 에서 한글 표시명으로 매핑.
- 학생에게 보이는 나레이션(배경/입퇴장)만 KR 스크립트에서 한국어로 번역.
- **신규 시나리오 스키마 확장**: 스크립트 최상위 `player`{name,display}, 각 actor 의 `display` 필드를
  두면 `web_server.py` 가 시나리오별 플레이어 배역·한글 표시명을 자동으로 읽음(하드코딩 불필요).
  `goals`·`description`·`relations` 는 영어, `intro`·`background`·`player_in/out`·`title`·`place` 는 한국어.
  신규 시나리오는 막당 단일 장소(빈 복도 허브 없음) → 학생이 시작하자마자 실제 장면에 참여.

## 현재 상태 / 다음 단계

- [x] 환경 구축, 터미널 정리, 한국어화(검증됨)
- [x] 웹 백엔드 `web_server.py` — Flask REST, **학생별 세션 격리**(`SessionManager`, 세션당 `GenerativeStage` 1개)
- [x] 한국어 웹 채팅 UI `templates/play.html` (장면 이동/진행/말걸기/인터뷰/평가; 배역 한글 표시)
- [x] 평가 수집(`/api/feedback` → `data/eval/feedback.jsonl`), Cloudflare Tunnel 공개(`serve_tunnel.sh`)
- [x] `ibsen` env 구축·검증(이 기계) — faiss/flask/server 모듈 import OK, `web_server.py` 컴파일 OK
- [x] **엔드투엔드 실플레이 검증(완료)** — 세션 초기화(~2분)/장면이동/진행(한국어 대사)/말걸기(본인대사 중복제거)/
      인터뷰/평가저장 전부 실 LLM 으로 정상. 주의: ① 플레이어는 빈 '호텔 복도'에서 시작 → 장면 이동 필요,
      ② 초기화가 배우 인상 생성 때문에 ~2분 걸림(학생에게 로딩 안내 유지).
- [ ] 연구실 Mac Studio 배포 (시범 5명). 동시 세션은 `MAX_SESSIONS`(기본 8)로 제한 —
      `MAX_SESSIONS=10 PORT=5055 python web_server.py`. 학생은 키 입력 없이 서버의 `api_key.py`(내 키)로 과금됨.
      → OpenAI 대시보드에서 월 예산 한도 설정 권장.

## 원격

- `origin` = 이 레포 (작업용)
- `upstream` = https://github.com/OpenDFM/ibsen (원본, 참고용)
