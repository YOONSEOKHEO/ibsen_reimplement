"""
IBSEN - clean terminal frontend (한국어 진행 화면).

원본 terminal_frontend.py 는 그대로 두고, 초기화 노이즈를 숨기고 대사를
읽기 쉽게 포맷한 평가용 프론트엔드입니다.

실행:
    conda run -n ibsen --no-capture-output python play.py

내부 동작을 다시 보고 싶으면:  IBSEN_DEBUG=1 python play.py
"""
import copy
import logging
import os
import warnings

# 프레임워크를 import 하기 전에 시끄러운 라이브러리부터 잠재운다.
if not os.environ.get("IBSEN_DEBUG"):
    logging.disable(logging.WARNING)      # faiss / langchain WARNING 로그 억제
    warnings.filterwarnings("ignore")

import guidance

from api_key import OPENAI_API_KEY
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

from server.actor import GenerativeActor
from server.stage import GenerativeStage, Player
from server import display as d

LLM_NAME = "gpt-4o-mini"
SCRIPT_PATH = "data/script/hedda_gabler_kr.json"
PLAYER_NAME = "Edward Helson"

guidance.llm = guidance.llms.OpenAI(LLM_NAME, chat_mode=True)


def load_stage() -> GenerativeStage:
    print(f"{d.DIM}배우들이 배역과 기억을 준비하는 중입니다... (약 1분 소요){d.RESET}")
    with d.suppress_stdout():
        stage = GenerativeStage(SCRIPT_PATH, default_llm=LLM_NAME)
    print(f"{d.GREEN}준비 완료!{d.RESET}")
    return stage


stage = load_stage()
player = Player(PLAYER_NAME)
stage.add_player(player)


def prompt_player_input() -> bool:
    print("\n" + d.rule(f"{player.name} · 현재 장면: {player.current_act}"))
    act_dict = {i + 1: name for i, name in enumerate(stage.current_act_names)}
    print(f"{d.BOLD}무엇을 하시겠어요?{d.RESET}")
    for k, v in act_dict.items():
        print(f"  {d.GREEN}[{k}]{d.RESET} 장면 이동 → {v}")
    print(f"  {d.GREEN}[0]{d.RESET} 아무것도 안 하고 한 턴 진행")
    print(f"  {d.GREEN}[-1]{d.RESET} 극을 멈추고 캐릭터 인터뷰")
    print(f"  {d.DIM}또는 하고 싶은 말을 그대로 입력하면 지금 장면의 배우들에게 말을 겁니다.{d.RESET}")
    user_input = input(f"{d.BOLD}> {d.RESET}")
    try:
        number_input = int(user_input)
        if number_input == 0:
            player.action = {"action": "none", "moveTo": player.current_act, "utterance": ""}
            return True
        elif number_input == -1:
            prompt_guide_interview()
            return False
        elif number_input in act_dict:
            player.action = {"action": "move", "moveTo": act_dict[number_input], "utterance": ""}
            print(d.rule(f"{act_dict[number_input]}(으)로 이동"))
            return True
        else:
            raise ValueError
    except ValueError:
        string_input = str(user_input)
        # 플레이어 발화를 먼저 화면에 보여준다.
        print(d.format_dialogue(player.name, string_input))
        player.action = {"action": "talk", "moveTo": player.current_act, "utterance": string_input}
        return True


def prompt_guide_interview():
    def prompt_interview(actor: GenerativeActor):
        print(f"{d.DIM}극을 멈추고 {actor.name} 에게 직접 질문합니다. (끝내려면 0){d.RESET}")
        while True:
            question = input(f"{d.BOLD}질문 > {d.RESET}")
            if question == "0":
                actor.interview_history.clear()
                return
            response = actor.interview(question)
            print(d.format_dialogue(actor.name, response))

    actor_dict = {i + 1: name for i, name in enumerate(stage.actors)}
    while True:
        print("\n" + d.rule("인터뷰"))
        for k, v in actor_dict.items():
            print(f"  {d.GREEN}[{k}]{d.RESET} {v}")
        print(f"  {d.GREEN}[0]{d.RESET} 인터뷰 종료")
        user_input = input(f"{d.BOLD}> {d.RESET}")
        try:
            number_input = int(user_input)
            if number_input == 0:
                return
            elif number_input in actor_dict:
                actor_name = actor_dict[number_input]
                actor = stage.actors[actor_name]
                actor.interview_history = copy.deepcopy(actor.dialogue_history.active_history)
                actor.interview_history.append({
                    "role": "Narration",
                    "content": f"(Director has paused the play. Now please continue to answer the questions of user as the role of {actor.name}.)"
                })
                prompt_interview(actor)
            else:
                raise ValueError
        except ValueError:
            pass


def main():
    print(d.banner(stage.script.title, stage.script.intro))
    input(f"\n{d.DIM}[Enter 를 누르면 극이 시작됩니다]{d.RESET}")
    stage.load_next_act()

    finished = False
    while not finished:
        has_input = False
        while not has_input:
            has_input = prompt_player_input()
        stage.step()
        finished = stage.finished

    print(d.banner("극이 끝났습니다", "이제 등장인물에게 자유롭게 질문할 수 있습니다."))
    prompt_guide_interview()


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print(f"\n{d.DIM}플레이를 종료합니다.{d.RESET}")
