from gevent import monkey

monkey.patch_all()

import os, json, sys, signal
from dotenv import load_dotenv
from flask import Flask, render_template, session

from flask_socketio import SocketIO, emit, disconnect
from openai import OpenAI, OpenAIError
from gevent import signal_handler

from agents import PersonaAgent, JudgeAgent
from mission import generate_mission

load_dotenv()

# OpenAI client setup
try:
    client = OpenAI(api_key=os.getenv("API_KEY"), base_url=os.getenv("BASE_URL"))
    if not client.api_key:
        raise OpenAIError("API_KEY not set in environment.")
except OpenAIError as e:
    print(f"!!! OpenAI Error: {e}")
    print("--- please set your API_KEY ---")
    exit()

# Flask and SocketIO setup
app = Flask(__name__)
app.config["SECRET_KEY"] = "this-is-required-for-sessions-omg"
socketio = SocketIO(app, async_mode="gevent")


# Game logic routes
MAX_TURNS = 5
judge = JudgeAgent(client)


@app.route("/")
def index():
    return render_template("menu.html")


@app.route("/game")
def game():
    return render_template("game.html")


@socketio.on("connect")
def handle_connect():
    print("client connected!")
    mission = generate_mission(client)

    session["technical_goal"] = mission["technical_goal"]
    session["personality_trait"] = mission["personality_trait"]
    session["turn_count"] = 0

    agent = PersonaAgent(
        mission["persona"],
        mission["technical_goal"],
        mission["personality_trait"],
        client,
    )
    agent.history.append({"role": "assistant", "content": mission["first_message"]})
    session["persona_history"] = agent.history
    session["judge_history"] = [
        {"role": "assistant", "content": mission["first_message"]}
    ]

    emit(
        "initial_mission",
        {
            "persona": f"{mission['persona']} (Personality: {mission['personality_trait']})",
            "first_message": mission["first_message"],
            "max_turns": MAX_TURNS,
        },
    )


@socketio.on("player_message")
def handle_player_message(data):
    goal = session.get("technical_goal")
    trait = session.get("personality_trait")
    p_history = session.get("persona_history")
    j_history = session.get("judge_history")
    turn = session.get("turn_count", 0)

    if not goal:
        emit(
            "game_over",
            {"win": False, "message": "error: no game state found. pls refresh."},
        )
        return

    player_input = data["message"]
    j_history.append({"role": "user", "content": player_input})

    win_check = judge.check_if_solved(j_history, goal)

    agent = PersonaAgent("from_history", goal, trait, client)
    agent.history = p_history

    if win_check.get("solved", False):
        print("game won!")
        final_msg = agent.get_final_reply(win=True)
        emit("game_over", {"win": True, "message": final_msg, "score": turn + 1})
        session.clear()
    else:
        turn += 1
        if turn >= MAX_TURNS:
            print("game lost - too many turns")
            final_msg = agent.get_final_reply(win=False)
            emit("game_over", {"win": False, "message": final_msg})
            session.clear()
        else:
            print(f"turn {turn} continuing")
            bot_reply = agent.get_reply(player_input)
            j_history.append({"role": "assistant", "content": bot_reply})

            session["persona_history"] = agent.history
            session["judge_history"] = j_history
            session["turn_count"] = turn

            emit(
                "new_bot_message",
                {"message": bot_reply, "turn": turn + 1, "max_turns": MAX_TURNS},
            )


@socketio.on("disconnect")
def handle_disconnect():
    print("client disconnected.")
    session.clear()


# Run server
if __name__ == "__main__":

    def shutdown():
        print("\n[server] shutting down...")
        sys.exit(0)

    signal_handler(signal.SIGINT, shutdown)
    print("server running on http://127.0.0.1:5000")
    socketio.run(app, host="0.0.0.0", port=5000)
