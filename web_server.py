"""
IBSEN 한국어 웹 서버 (학생별 세션 격리).

- 학생 한 명 = GenerativeStage 인스턴스 하나 (SessionManager 로 격리).
- play.py 의 진행 로직(장면 이동 / 말 걸기 / 진행 / 인터뷰)을 REST 로 옮긴 것.
- 배역 이름은 코드 매칭 때문에 영어 유지, UI 표시명만 한글로 매핑.
- 세션 종료 시 대사 로그 + 간단 설문을 data/eval 에 수집.

실행:
    conda run -n ibsen --no-capture-output python web_server.py
    # 외부 공개(학생 접속)는 별도 터미널에서:  bash serve_tunnel.sh

디버그(감독/기억 로그까지):  IBSEN_DEBUG=1 python web_server.py
"""
import copy
import glob
import json
import logging
import os
import threading
import uuid
import warnings
from datetime import datetime, timezone

# 프레임워크 import 전에 시끄러운 라이브러리부터 잠재운다(play.py 와 동일).
if not os.environ.get("IBSEN_DEBUG"):
    logging.disable(logging.WARNING)
    warnings.filterwarnings("ignore")

import guidance
from flask import Flask, jsonify, render_template, request

from api_key import OPENAI_API_KEY
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

from server.stage import GenerativeStage, Player
from server import display

LLM_NAME = "gpt-4o-mini"
DEFAULT_PLAYER = {"name": "Edward Helson", "display": "에드워드 헬슨 (나)"}
SCRIPT_DIR = "data/script"
EVAL_DIR = "data/eval"

# 동시에 진행 가능한 세션(학생) 수 상한. 공개 URL 남용/과금 폭주 방지용.
# 5명 시범이면 여유롭게 8. 필요하면 실행 시  MAX_SESSIONS=10  으로 조절.
MAX_SESSIONS = int(os.environ.get("MAX_SESSIONS", "8"))

guidance.llm = guidance.llms.OpenAI(LLM_NAME, chat_mode=True)

# --- 배역 한글 표시명 (코드는 영어명으로 매칭, 화면만 한글) ---
DISPLAY_NAMES = {
    "Hedda Gai": "헤다 가이",
    "George Dai": "게오르그 다이",
    "Brack": "브라크 판사",
    "Berta": "베르타",
    "John": "존 기자",
    "Peter": "피터 기자",
    "Mary": "메리 기자",
    "Edward Helson": "에드워드 헬슨 (나)",
    "Narration": "지문",
}

# --- 장면명 한글화 (예: "Act 1 - Press conference hall" -> "1막 · 기자회견장") ---
PLACE_LABELS = {
    "Hotel corridor": "호텔 복도",
    "Hotel lobby": "호텔 로비",
    "Press conference hall": "기자회견장",
    "Press conference backstage": "회견장 무대 뒤",
}


def scene_label(act_name: str) -> str:
    # "Act 3 - Press conference hall" -> "3막 · 기자회견장"  /  "Act 2 - 서재" -> "2막 · 서재"
    try:
        left, right = act_name.split(" - ", 1)
        act_no = left.replace("Act", "").strip()
        place = PLACE_LABELS.get(right.strip(), right.strip())
        return f"{act_no}막 · {place}"
    except ValueError:
        return act_name


def build_displays(data: dict) -> dict:
    """스크립트에서 배역 한글 표시명 맵을 만든다.
    우선순위: 스크립트 actor 의 'display' > 전역 DISPLAY_NAMES > 영어 원명."""
    disp = {"Narration": "지문"}
    for role, info in data.get("actors", {}).items():
        disp[role] = info.get("display") or DISPLAY_NAMES.get(role, role)
    player = data.get("player") or DEFAULT_PLAYER
    disp[player["name"]] = player.get("display", player["name"])
    return disp


def list_scenarios():
    """data/script/*.json 을 훑어 시나리오 목록을 만든다."""
    scenarios = []
    for path in sorted(glob.glob(os.path.join(SCRIPT_DIR, "*.json"))):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        sid = os.path.splitext(os.path.basename(path))[0]
        intro = data.get("intro", "")
        # 한글이 섞였는지로 언어를 대충 판정
        lang = "ko" if any(ord(c) > 0x3000 for c in intro) else "en"
        scenarios.append({
            "id": sid,
            "path": path,
            "title": data.get("title", sid),
            "intro": intro,
            "lang": lang,
            "player": data.get("player") or DEFAULT_PLAYER,
            "displays": build_displays(data),
        })
    # 한국어 시나리오를 위로
    scenarios.sort(key=lambda s: (s["lang"] != "ko", s["id"]))
    return scenarios


SCENARIOS = {s["id"]: s for s in list_scenarios()}


class Session:
    """학생 한 명의 극 상태를 담는다. GenerativeStage 인스턴스를 독점한다."""

    def __init__(self, sid: str, scenario_id: str, student_name: str):
        self.sid = sid
        self.scenario_id = scenario_id
        self.student_name = student_name
        self.created_at = datetime.now(timezone.utc).isoformat()

        scenario = SCENARIOS[scenario_id]
        self.player_name = scenario["player"]["name"]      # 시나리오별 플레이어 배역명(영어)
        self.player_display = scenario["player"]["display"]
        self._disp = scenario["displays"]                  # 배역 -> 한글 표시명

        self.stage: GenerativeStage | None = None
        self.player: Player | None = None
        self.status = "initializing"          # initializing | ready | finished | error
        self.error = None

        self.lock = threading.Lock()          # step/interview 직렬화(한 세션 내)
        self._cursors: dict[str, int] = {}    # act_name -> 표시 완료한 대사 개수
        self.transcript: list[dict] = []      # 플레이어가 지금까지 본 대사 전체
        self.awaiting = False                 # 감독이 플레이어에게 발언권을 준 상태
        self.finished = False

    # --- 초기화(약 1분 소요) : 백그라운드 스레드에서 실행 ---
    def build(self):
        try:
            scenario = SCENARIOS[self.scenario_id]
            with display.suppress_stdout():
                stage = GenerativeStage(scenario["path"], default_llm=LLM_NAME)
                player = Player(self.player_name)
                stage.add_player(player)
                stage.load_next_act()
                # 시작 장면이 실제 극(배우·목표 있음)이면 플레이어를 참여자로 등록해
                # 감독이 플레이어의 존재를 인지하고 발언권도 줄 수 있게 한다.
                # (헤다처럼 빈 복도에서 시작하는 경우엔 director.active=False 라 자동 스킵)
                start_director = stage.directors.get(player.current_act)
                if start_director is not None and start_director.active:
                    start_director.add_player(player.name)
            self.stage = stage
            self.player = player
            self._drain()                     # 시작 지문(배경) 수집
            self.status = "ready"
        except Exception as exc:              # noqa: BLE001 - 학생에게 상태만 전달
            self.error = f"{type(exc).__name__}: {exc}"
            self.status = "error"

    # --- 플레이어 현재 장면의 새 대사만 뽑아 transcript 에 누적 ---
    def _drain(self) -> list[dict]:
        act = self.player.current_act
        director = self.stage.directors.get(act)
        if director is None:
            return []
        hist = director.dialogue_logger.dialogue_history
        seen = self._cursors.get(act, 0)
        out = []
        for entry in hist[seen:]:
            content = entry.get("content", "")
            if content == "!<Await>!":        # 플레이어 차례 표시용 sentinel
                continue
            # 감독에게 "플레이어가 아무것도 안 함"을 알리는 내부 영어 지문은 화면에서 숨긴다.
            if entry["role"] == "Narration" and content == f"{self.player_name} does nothing.":
                continue
            line = {
                "role": entry["role"],
                "display": self._disp.get(entry["role"], entry["role"]),
                "content": content,
                "is_narration": entry["role"] == "Narration",
                "is_player": entry["role"] == self.player_name,
            }
            out.append(line)
            self.transcript.append(line)
        self._cursors[act] = len(hist)
        return out

    # --- 한 턴 진행 ---
    def do_action(self, action_type: str, move_to: str = "", utterance: str = "") -> list[dict]:
        with self.lock:
            if self.status == "finished" or self.finished:
                return []
            p = self.player
            if action_type == "talk":
                p.action = {"action": "talk", "moveTo": p.current_act, "utterance": utterance}
            elif action_type == "move":
                p.action = {"action": "move", "moveTo": move_to, "utterance": ""}
            else:  # "none" = 그냥 진행
                p.action = {"action": "none", "moveTo": p.current_act, "utterance": ""}

            with display.suppress_stdout():
                act_status = self.stage.step()

            new_lines = self._drain()
            self.finished = self.stage.finished
            if self.finished:
                self.status = "finished"

            # 감독이 플레이어에게 발언권을 줬는지 확인
            cur = self.player.current_act
            st = act_status.get(cur)
            self.awaiting = bool(st and st["next_script"]["role"] == self.player_name)

            # 플레이어 자신의 발화는 프론트가 이미(낙관적으로) 표시했으므로 중복 방지.
            # (transcript 에는 그대로 남겨 새로고침 시 복원되게 함.)
            return [line for line in new_lines if not line["is_player"]]

    # --- 인터뷰(극을 멈추고 배우에게 직접 질문) ---
    def interview(self, actor_name: str, question: str) -> str:
        with self.lock:
            actor = self.stage.actors.get(actor_name)
            if actor is None:
                raise KeyError(actor_name)
            if not getattr(actor, "interview_history", None):
                actor.interview_history = copy.deepcopy(actor.dialogue_history.active_history)
                actor.interview_history.append({
                    "role": "Narration",
                    "content": f"(Director has paused the play. Now please continue to answer "
                               f"the questions of user as the role of {actor.name}.)",
                })
            with display.suppress_stdout():
                return actor.interview(question)

    def end_interview(self, actor_name: str):
        with self.lock:
            actor = self.stage.actors.get(actor_name)
            if actor is not None and getattr(actor, "interview_history", None):
                actor.interview_history.clear()

    # --- 프론트로 보낼 상태 스냅샷 ---
    def state(self) -> dict:
        scenario = SCENARIOS[self.scenario_id]
        scenes, actors, current_act = [], [], ""
        if self.stage is not None:
            current_act = self.player.current_act
            scenes = [
                {"name": name, "label": scene_label(name), "current": name == current_act}
                for name in self.stage.current_act_names
            ]
            actors = [
                {"role": name, "display": self._disp.get(name, name)}
                for name in self.stage.actors
            ]
        return {
            "sid": self.sid,
            "status": self.status,
            "error": self.error,
            "title": scenario["title"],
            "intro": scenario["intro"],
            "player": {"name": self.player_name, "display": self.player_display},
            "current_act": scene_label(current_act) if current_act else "",
            "scenes": scenes,
            "actors": actors,
            "transcript": self.transcript,
            "awaiting": self.awaiting,
            "finished": self.finished,
        }


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def active_count(self) -> int:
        # 진행 중(초기화/플레이)인 세션만 자리를 차지한다. 종료·오류 세션은 제외.
        with self._lock:
            return sum(1 for s in self._sessions.values()
                       if s.status in ("initializing", "ready"))

    def create(self, scenario_id: str, student_name: str) -> Session | None:
        if self.active_count() >= MAX_SESSIONS:
            return None                       # 정원 초과
        sid = uuid.uuid4().hex[:12]
        session = Session(sid, scenario_id, student_name)
        with self._lock:
            self._sessions[sid] = session
        threading.Thread(target=session.build, daemon=True).start()
        return session

    def get(self, sid: str) -> Session | None:
        with self._lock:
            return self._sessions.get(sid)


manager = SessionManager()
app = Flask(__name__)


# ----------------------------- 라우트 -----------------------------

@app.route("/")
def index():
    return render_template("play.html")


@app.route("/api/scenarios")
def api_scenarios():
    return jsonify([
        {"id": s["id"], "title": s["title"], "intro": s["intro"], "lang": s["lang"]}
        for s in SCENARIOS.values()
    ])


@app.route("/api/start", methods=["POST"])
def api_start():
    body = request.get_json(force=True) or {}
    scenario_id = body.get("scenario", "")
    name = (body.get("name") or "익명").strip()[:40]
    if scenario_id not in SCENARIOS:
        return jsonify({"error": "알 수 없는 시나리오입니다."}), 400
    session = manager.create(scenario_id, name)
    if session is None:
        return jsonify({
            "error": f"지금 접속 인원이 가득 찼습니다(최대 {MAX_SESSIONS}명). "
                     f"잠시 후 다시 시도해주세요."
        }), 429
    return jsonify({"sid": session.sid})


def _require(sid: str):
    session = manager.get(sid)
    if session is None:
        return None, (jsonify({"error": "세션을 찾을 수 없습니다."}), 404)
    return session, None


@app.route("/api/state")
def api_state():
    session, err = _require(request.args.get("sid", ""))
    if err:
        return err
    return jsonify(session.state())


@app.route("/api/action", methods=["POST"])
def api_action():
    body = request.get_json(force=True) or {}
    session, err = _require(body.get("sid", ""))
    if err:
        return err
    if session.status == "initializing":
        return jsonify({"error": "아직 준비 중입니다."}), 409
    action_type = body.get("type", "none")
    if action_type not in ("none", "talk", "move"):
        return jsonify({"error": "잘못된 동작입니다."}), 400
    new_lines = session.do_action(
        action_type,
        move_to=body.get("moveTo", ""),
        utterance=(body.get("utterance") or "").strip(),
    )
    return jsonify({
        "new_lines": new_lines,
        "current_act": scene_label(session.player.current_act),
        "scenes": [
            {"name": n, "label": scene_label(n), "current": n == session.player.current_act}
            for n in session.stage.current_act_names
        ],
        "awaiting": session.awaiting,
        "finished": session.finished,
    })


@app.route("/api/interview", methods=["POST"])
def api_interview():
    body = request.get_json(force=True) or {}
    session, err = _require(body.get("sid", ""))
    if err:
        return err
    actor = body.get("actor", "")
    question = (body.get("question") or "").strip()
    if not question:
        return jsonify({"error": "질문을 입력하세요."}), 400
    try:
        answer = session.interview(actor, question)
    except KeyError:
        return jsonify({"error": "알 수 없는 배역입니다."}), 400
    return jsonify({"role": actor, "display": session._disp.get(actor, actor), "answer": answer})


@app.route("/api/interview/end", methods=["POST"])
def api_interview_end():
    body = request.get_json(force=True) or {}
    session, err = _require(body.get("sid", ""))
    if err:
        return err
    session.end_interview(body.get("actor", ""))
    return jsonify({"ok": True})


@app.route("/api/feedback", methods=["POST"])
def api_feedback():
    body = request.get_json(force=True) or {}
    session, err = _require(body.get("sid", ""))
    if err:
        return err
    os.makedirs(EVAL_DIR, exist_ok=True)
    record = {
        "sid": session.sid,
        "student_name": session.student_name,
        "scenario": session.scenario_id,
        "created_at": session.created_at,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "ratings": body.get("ratings", {}),      # {immersion, character, plot, ...} 1~5
        "comment": (body.get("comment") or "").strip(),
        "finished": session.finished,
        "transcript": session.transcript,
    }
    with open(os.path.join(EVAL_DIR, "feedback.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    print(f"[IBSEN] 웹 서버 시작 — http://127.0.0.1:{port}")
    print(f"[IBSEN] 시나리오 {len(SCENARIOS)}개 로드됨: {', '.join(SCENARIOS)}")
    print(f"[IBSEN] 동시 세션 상한(MAX_SESSIONS) = {MAX_SESSIONS}")
    app.run(host="0.0.0.0", port=port, threaded=True)
