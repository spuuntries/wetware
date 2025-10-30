from gevent import monkey

monkey.patch_all()

import os, json, sys, signal
from dotenv import load_dotenv
from flask import Flask, render_template_string, session
from flask_socketio import SocketIO, emit, disconnect
from openai import OpenAI, OpenAIError
from gevent import signal_handler

load_dotenv()

# --- 1. Setup OpenAI Client ---
try:
    client = OpenAI(api_key=os.getenv("API_KEY"), base_url=os.getenv("BASE_URL"))
    if not client.api_key:
        raise OpenAIError("API_KEY not set in environment.")
except OpenAIError as e:
    print(f"!!! OpenAI Error: {e}")
    print("--- please set your API_KEY ---")
    exit()

# --- 2. Flask and SocketIO ---
app = Flask(__name__)
app.config["SECRET_KEY"] = "this-is-required-for-sessions-omg"
socketio = SocketIO(app, async_mode="gevent")


# --- 3. Mission Generator ---
def generate_mission():
    print("[GameMaster] generating a new mission...")

    generator_prompt = """
You are a **scenario designer** for a realistic helpdesk simulation game.
Your task is to generate a new "mission" for a player acting as a helpful assistant.

You must invent:
1.  A **realistic persona** (e.g., "a college student," "a busy parent," "a gamer," "a freelance artist," "an office worker").
2.  A simple, concrete **technical_goal**.
3.  A **personality_trait** that creates the *real* difficulty. You **must** choose a personality from one of these distinct categories:
    * **Impatient/Rude**
    * **Anxious/Cautious**
    * **Suspicious/Argumentative**
    * **Terminally Online/Slang**
    * **Overly Formal/Pedantic**
    * **Extremely Vague/Scatterbrained**
4.  The **first_message** the persona sends, which *strongly* reflects both their goal and their personality.

**RULES:**
* **NO FANTASY.** Keep it realistic.
* **YOUR #1 RULE IS DIVERSITY. YOU MUST RANDOMLY SELECT A *DIFFERENT* CATEGORY FROM THE PERSONALITY LIST FOR EACH GENERATION.**
* **DO NOT** just pick "Suspicious" or "Anxious" every time. You **must** use "Terminally Online," "Pedantic," and "Vague" just as often.

**Format:**
Respond in a **single JSON object** only.

**Example 1 (Terminally Online):**
```json
{
  "persona": "a gamer trying to update their drivers.",
  "technical_goal": "wants to update their graphics card (GPU) drivers.",
  "personality_trait": "Terminally Online/Slang. Uses gamer/streamer slang.",
  "first_message": "yo, my frames are *so* chalked rn. i'm getting massive Ls in every match. my buddy said i need to 'update my... thingy?' to get more fps? how do i do that without bricking my whole rig?"
}
```

**Example 2 (Scatterbrained):**
```json
{
  "persona": "a student trying to write an essay.",
  "technical_goal": "wants to change the line spacing in their document (e.g., to double-spaced).",
  "personality_trait": "Extremely vague and scatterbrained. keeps getting distracted.",
  "first_message": "hi! ok, so my professor—he has a red car, super weird—he said my essay 'looks wrong.' he wants more 'air' between the... you know... the *words*. the lines. i tried pressing enter but that just makes it... bigger? anyway, what was i asking? oh yeah, help."
}
```

Now, generate a new, unique mission. **REMEMBER THE DIVERSITY RULE.**
"""

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": generator_prompt}],
            response_format={"type": "json_object"},
            temperature=1.2,  # high randomness!
        )
        response_json = completion.choices[0].message.content
        mission = json.loads(response_json)

        if "technical_goal" not in mission:
            mission["technical_goal"] = mission.get("secret_goal", "unknown goal")
        if "personality_trait" not in mission:
            mission["personality_trait"] = "normal"

        print("[GameMaster] mission created successfully.")
        return mission

    except Exception as e:
        print(f"!!! error generating mission: {e}")
        return {
            "persona": "a busy office worker.",
            "technical_goal": "wants to 'zip' a folder to email it.",
            "personality_trait": "impatient",
            "first_message": "hi, i need to send this folder, but the email machine says it's 'too big.' how do i make it smaller? and quick, i'm on a deadline.",
        }


# --- Persona Agent ---
class PersonaAgent:
    def __init__(self, persona, technical_goal, personality_trait):
        self.persona = persona
        self.technical_goal = technical_goal
        self.personality_trait = personality_trait
        self.history = [
            {
                "role": "system",
                "content": f"""
You are a game character. You are *not* an AI assistant.
Your persona: {persona}
Your technical goal: {technical_goal}
Your personality: {personality_trait}

Your job is to act out this persona and personality *perfectly*.
The player is an assistant trying to help you.
DO NOT reveal your technical goal. Just act confused.
**Based on your personality, you might reject a correct answer if it's not delivered well.**
(e.g., if you are 'impatient', you hate long answers. if you are 'anxious', you hate technical jargon.)
""",
            }
        ]

    def get_reply(self, player_message):
        print(f"[PersonaAgent] thinking... (persona: {self.persona})")
        self.history.append({"role": "user", "content": player_message})
        try:
            completion = client.chat.completions.create(
                model="gpt-4o-mini", messages=self.history
            )
            reply = completion.choices[0].message.content
            self.history.append({"role": "assistant", "content": reply})
            return reply
        except Exception as e:
            print(f"!!! persona error: {e}")
            return "uhhh what? try again?"

    def get_final_reply(self, win=True):
        print("[PersonaAgent] generating final message...")
        final_prompt = (
            "The player *just* solved your problem. Write a final message gratefully (or grumpily) ending the chat."
            if win
            else "The player has failed. Write a final message getting frustrated and rage-quitting."
        )
        temp_history = self.history + [{"role": "system", "content": final_prompt}]
        try:
            completion = client.chat.completions.create(
                model="gpt-4o-mini", messages=temp_history
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"!!! final reply error: {e}")
            return "fine, whatever. i'm leaving."


# --- Judge Agent ---
class JudgeAgent:
    def __init__(self):
        self.system_prompt = """
You are a strict game referee. Your only job is to determine if the player has won.
Respond with ONLY a JSON object: {"solved": true} or {"solved": false}
"""

    def check_if_solved(self, chat_history, secret_goal):
        print("[JudgeAgent] checking for win condition...")
        history_json = json.dumps(chat_history, indent=2)
        prompt = f"**Secret Goal:**\n{secret_goal}\n\n**Chat History:**\n{history_json}\n\n---\nHas the player's *last* message solved the goal?"
        try:
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
            )
            result = json.loads(completion.choices[0].message.content)
            return result
        except Exception as e:
            print(f"!!! judge error: {e}")
            return {"solved": False}


# --- 4. HTML Interface ---
HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>wetware v0.3 :: neural helpdesk</title>
  <script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.6.0/dist/confetti.browser.min.js"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-primary: #0a0a0f;
      --bg-secondary: #13131d;
      --bg-tertiary: #1a1a28;
      --bg-chat: #0f0f17;
      
      --accent-primary: #00d9ff;
      --accent-secondary: #a855f7;
      --accent-tertiary: #ec4899;
      
      --text-primary: #f0f0f5;
      --text-secondary: #a8a8b8;
      --text-muted: #6b6b7b;
      
      --success: #10b981;
      --error: #ef4444;
      --warning: #f59e0b;
      
      --border: rgba(255, 255, 255, 0.08);
      --shadow-sm: rgba(0, 0, 0, 0.3);
      --shadow-md: rgba(0, 0, 0, 0.5);
      --shadow-lg: rgba(0, 0, 0, 0.7);
      
      --glass-bg: rgba(26, 26, 40, 0.7);
      --glass-border: rgba(255, 255, 255, 0.1);
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--bg-primary);
      color: var(--text-primary);
      display: flex;
      flex-direction: column;
      height: 100vh;
      overflow: hidden;
      position: relative;
    }

    /* Animated Background */
    body::before {
      content: '';
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: 
        radial-gradient(circle at 20% 50%, rgba(0, 217, 255, 0.15) 0%, transparent 50%),
        radial-gradient(circle at 80% 80%, rgba(168, 85, 247, 0.15) 0%, transparent 50%),
        radial-gradient(circle at 40% 20%, rgba(236, 72, 153, 0.1) 0%, transparent 50%);
      animation: gradientShift 15s ease infinite;
      pointer-events: none;
      z-index: 0;
    }

    @keyframes gradientShift {
      0%, 100% {
        opacity: 1;
        transform: scale(1);
      }
      50% {
        opacity: 0.8;
        transform: scale(1.1);
      }
    }

    /* Header */
    header {
      background: var(--glass-bg);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border-bottom: 1px solid var(--glass-border);
      padding: 1.5rem 2.5rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
      box-shadow: 0 8px 32px var(--shadow-md);
      z-index: 100;
      position: relative;
    }

    .header-left {
      display: flex;
      align-items: center;
      gap: 1.25rem;
    }

    .header-icon {
      font-size: 2.2rem;
      filter: drop-shadow(0 0 20px rgba(0, 217, 255, 0.5));
      animation: float 3s ease-in-out infinite;
    }

    @keyframes float {
      0%, 100% { transform: translateY(0px); }
      50% { transform: translateY(-5px); }
    }

    .header-title-group {
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
    }

    .header-title {
      font-size: 1.5rem;
      font-weight: 800;
      letter-spacing: 0.5px;
      background: linear-gradient(135deg, #00d9ff 0%, #a855f7 50%, #ec4899 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }

    .header-subtitle {
      font-size: 0.8rem;
      color: var(--text-muted);
      font-family: 'JetBrains Mono', monospace;
      text-transform: uppercase;
      letter-spacing: 1px;
    }

    .connection-status {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      padding: 0.75rem 1.25rem;
      background: var(--glass-bg);
      backdrop-filter: blur(10px);
      border: 1px solid var(--glass-border);
      border-radius: 30px;
      font-size: 0.85rem;
      font-family: 'JetBrains Mono', monospace;
      font-weight: 600;
      box-shadow: 0 4px 12px var(--shadow-sm);
    }

    .status-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--success);
      box-shadow: 0 0 12px var(--success);
      animation: pulse-dot 2s ease-in-out infinite;
    }

    @keyframes pulse-dot {
      0%, 100% { 
        transform: scale(1);
        opacity: 1;
      }
      50% { 
        transform: scale(1.2);
        opacity: 0.7;
      }
    }

    /* Main Container */
    #main_container {
      display: flex;
      flex: 1;
      overflow: hidden;
      gap: 0;
      position: relative;
      z-index: 1;
    }

    /* Chat Section */
    #chat_section {
      flex: 1;
      display: flex;
      flex-direction: column;
      background: transparent;
      position: relative;
    }

    #chat_window {
      flex: 1;
      overflow-y: auto;
      padding: 2.5rem;
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
    }

    /* Message Bubbles */
    .message {
      display: flex;
      align-items: flex-start;
      gap: 1rem;
      max-width: 75%;
      animation: slideIn 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    }

    @keyframes slideIn {
      from {
        opacity: 0;
        transform: translateY(20px) scale(0.95);
      }
      to {
        opacity: 1;
        transform: translateY(0) scale(1);
      }
    }

    .message.user {
      margin-left: auto;
      flex-direction: row-reverse;
    }

    .message-avatar {
      width: 42px;
      height: 42px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.3rem;
      flex-shrink: 0;
      box-shadow: 0 4px 16px var(--shadow-md);
      position: relative;
    }

    .user .message-avatar {
      background: linear-gradient(135deg, #00d9ff 0%, #0ea5e9 100%);
    }

    .user .message-avatar::after {
      content: '';
      position: absolute;
      inset: -2px;
      border-radius: 50%;
      background: linear-gradient(135deg, #00d9ff 0%, #0ea5e9 100%);
      z-index: -1;
      opacity: 0.3;
      filter: blur(8px);
    }

    .bot .message-avatar {
      background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
    }

    .system .message-avatar {
      background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
    }

    .message-content-wrapper {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      flex: 1;
    }

    .message-content {
      background: var(--glass-bg);
      backdrop-filter: blur(10px);
      padding: 1.25rem 1.5rem;
      border-radius: 20px;
      line-height: 1.7;
      position: relative;
      border: 1px solid var(--glass-border);
      box-shadow: 0 4px 16px var(--shadow-sm);
      font-size: 0.95rem;
    }

    .user .message-content {
      background: linear-gradient(135deg, rgba(0, 217, 255, 0.15) 0%, rgba(14, 165, 233, 0.15) 100%);
      border: 1px solid rgba(0, 217, 255, 0.3);
      border-bottom-right-radius: 6px;
    }

    .bot .message-content {
      background: linear-gradient(135deg, rgba(99, 102, 241, 0.15) 0%, rgba(139, 92, 246, 0.15) 100%);
      border: 1px solid rgba(99, 102, 241, 0.3);
      border-bottom-left-radius: 6px;
    }

    .message-timestamp {
      font-size: 0.7rem;
      color: var(--text-muted);
      font-family: 'JetBrains Mono', monospace;
      padding: 0 0.5rem;
    }

    .user .message-timestamp {
      text-align: right;
    }

    .system {
      text-align: center;
      width: 100%;
      max-width: 100%;
      justify-content: center;
    }

    .system .message-content {
      background: rgba(245, 158, 11, 0.1);
      color: var(--text-muted);
      font-style: italic;
      font-size: 0.9rem;
      border: 1px solid rgba(245, 158, 11, 0.2);
    }

    .win, .lose {
      width: 100%;
      max-width: 100%;
      justify-content: center;
      margin: 1.5rem 0;
    }

    .win .message-content {
      background: linear-gradient(135deg, rgba(16, 185, 129, 0.25) 0%, rgba(5, 150, 105, 0.25) 100%);
      border: 2px solid var(--success);
      color: var(--success);
      font-weight: 700;
      font-size: 1.2rem;
      box-shadow: 0 0 30px rgba(16, 185, 129, 0.4);
      animation: victoryPulse 0.6s ease-out;
    }

    @keyframes victoryPulse {
      0% { transform: scale(0.9); opacity: 0; }
      50% { transform: scale(1.05); }
      100% { transform: scale(1); opacity: 1; }
    }

    .lose .message-content {
      background: linear-gradient(135deg, rgba(239, 68, 68, 0.25) 0%, rgba(220, 38, 38, 0.25) 100%);
      border: 2px solid var(--error);
      color: var(--error);
      font-weight: 700;
      font-size: 1.2rem;
      box-shadow: 0 0 30px rgba(239, 68, 68, 0.4);
    }

    /* Typing Indicator */
    .typing-indicator {
      display: flex;
      gap: 0.4rem;
      padding: 1rem 1.5rem;
    }

    .typing-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--accent-secondary);
      animation: typing 1.4s ease-in-out infinite;
    }

    .typing-dot:nth-child(2) {
      animation-delay: 0.2s;
    }

    .typing-dot:nth-child(3) {
      animation-delay: 0.4s;
    }

    @keyframes typing {
      0%, 60%, 100% {
        transform: translateY(0);
        opacity: 0.4;
      }
      30% {
        transform: translateY(-12px);
        opacity: 1;
      }
    }

    /* Input Section */
    #input_box {
      padding: 2rem 2.5rem;
      background: var(--glass-bg);
      backdrop-filter: blur(20px);
      border-top: 1px solid var(--glass-border);
      display: flex;
      gap: 1.25rem;
      align-items: flex-end;
      box-shadow: 0 -8px 32px var(--shadow-md);
      position: relative;
    }

    .input-wrapper {
      flex: 1;
      position: relative;
    }

    #response_text {
      width: 100%;
      background: rgba(26, 26, 40, 0.8);
      border: 2px solid var(--border);
      border-radius: 16px;
      padding: 1.25rem 1.5rem;
      padding-right: 4rem;
      color: var(--text-primary);
      font-family: 'Inter', sans-serif;
      font-size: 1rem;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      resize: none;
      min-height: 56px;
      max-height: 150px;
    }

    #response_text:focus {
      outline: none;
      border-color: var(--accent-primary);
      background: rgba(26, 26, 40, 0.95);
      box-shadow: 0 0 0 4px rgba(0, 217, 255, 0.15), 0 8px 24px var(--shadow-sm);
    }

    #response_text::placeholder {
      color: var(--text-muted);
    }

    .char-counter {
      position: absolute;
      bottom: 0.75rem;
      right: 1.5rem;
      font-size: 0.7rem;
      color: var(--text-muted);
      font-family: 'JetBrains Mono', monospace;
      pointer-events: none;
    }

    #send_button {
      padding: 1.25rem 2.5rem;
      background: linear-gradient(135deg, #00d9ff 0%, #a855f7 100%);
      color: #000;
      border: none;
      border-radius: 16px;
      cursor: pointer;
      font-weight: 700;
      font-size: 1rem;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      text-transform: uppercase;
      letter-spacing: 1px;
      box-shadow: 0 8px 24px rgba(0, 217, 255, 0.4);
      min-width: 120px;
      position: relative;
      overflow: hidden;
    }

    #send_button::before {
      content: '';
      position: absolute;
      inset: 0;
      background: linear-gradient(135deg, #a855f7 0%, #ec4899 100%);
      opacity: 0;
      transition: opacity 0.3s ease;
    }

    #send_button:hover:not(:disabled)::before {
      opacity: 1;
    }

    #send_button:hover:not(:disabled) {
      transform: translateY(-3px);
      box-shadow: 0 12px 32px rgba(0, 217, 255, 0.5);
    }

    #send_button:active:not(:disabled) {
      transform: translateY(-1px);
    }

    #send_button:disabled {
      opacity: 0.4;
      cursor: not-allowed;
      transform: none;
    }

    #send_button span {
      position: relative;
      z-index: 1;
    }

    /* Info Panel */
    #info_panel {
      width: 420px;
      background: var(--glass-bg);
      backdrop-filter: blur(20px);
      border-left: 1px solid var(--glass-border);
      padding: 2.5rem;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 2rem;
      box-shadow: -8px 0 32px var(--shadow-md);
    }

    .info_card {
      background: rgba(26, 26, 40, 0.5);
      border-radius: 20px;
      padding: 2rem;
      border: 1px solid var(--glass-border);
      box-shadow: 0 4px 16px var(--shadow-sm);
      transition: all 0.3s ease;
    }

    .info_card:hover {
      border-color: rgba(255, 255, 255, 0.15);
      transform: translateY(-2px);
      box-shadow: 0 8px 24px var(--shadow-sm);
    }

    .info_card h2 {
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 2px;
      color: var(--text-muted);
      margin-bottom: 1.5rem;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }

    .info_card h2::before {
      content: '';
      width: 4px;
      height: 16px;
      background: linear-gradient(180deg, var(--accent-primary) 0%, var(--accent-secondary) 100%);
      border-radius: 2px;
    }

    /* Turn Counter with Circular Progress */
    .turn-counter-wrapper {
      display: flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 1.5rem;
    }

    .circular-progress {
      position: relative;
      width: 140px;
      height: 140px;
    }

    .circular-progress svg {
      transform: rotate(-90deg);
    }

    .circular-progress-bg {
      fill: none;
      stroke: rgba(255, 255, 255, 0.05);
      stroke-width: 8;
    }

    .circular-progress-bar {
      fill: none;
      stroke: url(#progressGradient);
      stroke-width: 8;
      stroke-linecap: round;
      transition: stroke-dashoffset 0.5s cubic-bezier(0.4, 0, 0.2, 1);
    }

    .turn-counter-text {
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      text-align: center;
    }

    .turn-counter-current {
      font-size: 2.5rem;
      font-weight: 800;
      background: linear-gradient(135deg, #00d9ff 0%, #a855f7 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      font-family: 'JetBrains Mono', monospace;
      line-height: 1;
    }

    .turn-counter-max {
      font-size: 0.9rem;
      color: var(--text-muted);
      font-family: 'JetBrains Mono', monospace;
      margin-top: 0.25rem;
    }

    .status_badge {
      display: inline-flex;
      align-items: center;
      gap: 0.75rem;
      padding: 0.75rem 1.5rem;
      border-radius: 30px;
      font-size: 0.85rem;
      font-weight: 700;
      font-family: 'JetBrains Mono', monospace;
      text-transform: uppercase;
      letter-spacing: 1px;
      width: 100%;
      justify-content: center;
    }

    .status-indicator {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      animation: pulse-status 2s ease-in-out infinite;
    }

    @keyframes pulse-status {
      0%, 100% { 
        transform: scale(1);
        opacity: 1;
      }
      50% { 
        transform: scale(1.3);
        opacity: 0.7;
      }
    }

    .status_active {
      background: rgba(16, 185, 129, 0.2);
      color: var(--success);
      border: 2px solid var(--success);
    }

    .status_active .status-indicator {
      background: var(--success);
      box-shadow: 0 0 12px var(--success);
    }

    .status_waiting {
      background: rgba(245, 158, 11, 0.2);
      color: var(--warning);
      border: 2px solid var(--warning);
    }

    .status_waiting .status-indicator {
      background: var(--warning);
      box-shadow: 0 0 12px var(--warning);
    }

    .status_ended {
      background: rgba(239, 68, 68, 0.2);
      color: var(--error);
      border: 2px solid var(--error);
    }

    .status_ended .status-indicator {
      background: var(--error);
      box-shadow: 0 0 12px var(--error);
    }

    /* Mission Briefing */
    .mission-briefing {
      background: linear-gradient(135deg, rgba(0, 217, 255, 0.1) 0%, rgba(168, 85, 247, 0.1) 100%);
      border: 2px solid rgba(0, 217, 255, 0.3);
      border-radius: 16px;
      padding: 1.5rem;
      margin-bottom: 1rem;
    }

    .mission-label {
      font-size: 0.7rem;
      text-transform: uppercase;
      letter-spacing: 1.5px;
      color: var(--accent-primary);
      font-weight: 700;
      margin-bottom: 0.75rem;
    }

    .mission-text {
      color: var(--text-primary);
      font-size: 1rem;
      line-height: 1.6;
      font-weight: 500;
    }

    .persona_detail {
      color: var(--text-secondary);
      font-size: 0.95rem;
      line-height: 1.7;
      padding: 1.25rem;
      background: rgba(99, 102, 241, 0.1);
      border-radius: 12px;
      border-left: 4px solid var(--accent-secondary);
    }

    .objective_text {
      color: var(--text-secondary);
      font-size: 0.9rem;
      line-height: 1.7;
      margin-bottom: 1.25rem;
    }

    .tip_box {
      background: rgba(0, 217, 255, 0.1);
      border: 1px solid rgba(0, 217, 255, 0.3);
      border-radius: 12px;
      padding: 1rem 1.25rem;
      display: flex;
      align-items: flex-start;
      gap: 0.75rem;
      margin-top: 1rem;
    }

    .tip-icon {
      font-size: 1.2rem;
      flex-shrink: 0;
    }

    .tip-text {
      color: var(--text-secondary);
      font-size: 0.85rem;
      line-height: 1.5;
    }

    .tip-text strong {
      color: var(--accent-primary);
      font-weight: 600;
    }

    /* Scrollbar */
    ::-webkit-scrollbar {
      width: 12px;
      height: 12px;
    }

    ::-webkit-scrollbar-track {
      background: transparent;
    }

    ::-webkit-scrollbar-thumb {
      background: rgba(255, 255, 255, 0.1);
      border-radius: 6px;
      border: 3px solid transparent;
      background-clip: padding-box;
    }

    ::-webkit-scrollbar-thumb:hover {
      background: rgba(255, 255, 255, 0.2);
      background-clip: padding-box;
    }

    /* Responsive */
    @media (max-width: 1200px) {
      #info_panel {
        width: 360px;
      }
    }

    @media (max-width: 1024px) {
      #info_panel {
        width: 320px;
        padding: 2rem;
      }

      .message {
        max-width: 85%;
      }
    }

    @media (max-width: 768px) {
      #main_container {
        flex-direction: column;
      }

      #info_panel {
        width: 100%;
        border-left: none;
        border-top: 1px solid var(--glass-border);
        max-height: 45vh;
        padding: 1.5rem;
      }

      .message {
        max-width: 95%;
      }

      header {
        padding: 1.25rem 1.5rem;
      }

      .header-title {
        font-size: 1.2rem;
      }

      .header-icon {
        font-size: 1.8rem;
      }

      #chat_window {
        padding: 1.5rem;
      }

      #input_box {
        padding: 1.5rem;
      }

      #send_button {
        padding: 1rem 1.5rem;
        min-width: 90px;
      }

      .info_card {
        padding: 1.5rem;
      }

      .circular-progress {
        width: 120px;
        height: 120px;
      }

      .turn-counter-current {
        font-size: 2rem;
      }
    }

    /* Loading skeleton */
    .skeleton {
      background: linear-gradient(90deg, 
        rgba(255, 255, 255, 0.05) 0%, 
        rgba(255, 255, 255, 0.1) 50%, 
        rgba(255, 255, 255, 0.05) 100%
      );
      background-size: 200% 100%;
      animation: shimmer 1.5s ease-in-out infinite;
      border-radius: 8px;
    }

    @keyframes shimmer {
      0% { background-position: -200% 0; }
      100% { background-position: 200% 0; }
    }
  </style>
</head>
<body>
  <header>
    <div class="header-left">
      <div class="header-icon">🧠</div>
      <div class="header-title-group">
        <div class="header-title">wetware v0.3</div>
        <div class="header-subtitle">neural helpdesk simulation</div>
      </div>
    </div>
    <div class="connection-status">
      <div class="status-dot"></div>
      <span>CONNECTED</span>
    </div>
  </header>

  <div id="main_container">
    <div id="chat_section">
      <div id="chat_window">
        <div class="message system">
          <div class="message-avatar">⚡</div>
          <div class="message-content-wrapper">
            <div class="message-content">Initializing neural chat link...</div>
          </div>
        </div>
      </div>

      <div id="input_box">
        <div class="input-wrapper">
          <textarea id="response_text" placeholder="Type your response..." autocomplete="off" disabled rows="1" maxlength="500"></textarea>
          <span class="char-counter"><span id="char_count">0</span>/500</span>
        </div>
        <button id="send_button" disabled><span>SEND</span></button>
      </div>
    </div>

    <div id="info_panel">
      <div class="info_card">
        <h2>Mission Status</h2>
        <div class="turn-counter-wrapper">
          <div class="circular-progress">
            <svg width="140" height="140">
              <defs>
                <linearGradient id="progressGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" style="stop-color:#00d9ff;stop-opacity:1" />
                  <stop offset="100%" style="stop-color:#a855f7;stop-opacity:1" />
                </linearGradient>
              </defs>
              <circle class="circular-progress-bg" cx="70" cy="70" r="62"></circle>
              <circle class="circular-progress-bar" cx="70" cy="70" r="62" 
                      stroke-dasharray="389.557" 
                      stroke-dashoffset="389.557"
                      id="progress_circle"></circle>
            </svg>
            <div class="turn-counter-text">
              <div class="turn-counter-current" id="current_turn">--</div>
              <div class="turn-counter-max">/ <span id="max_turns">--</span></div>
            </div>
          </div>
        </div>
        <div class="status_badge status_waiting" id="game_status">
          <div class="status-indicator"></div>
          <span>Waiting...</span>
        </div>
      </div>

      <div class="info_card">
        <h2>Active Persona</h2>
        <div class="mission-briefing">
          <div class="mission-label">Current Mission</div>
          <div class="mission-text" id="persona_info">Loading mission data...</div>
        </div>
        <div class="persona_detail" id="personality_info" style="display:none;">
          Personality trait will appear here
        </div>
      </div>

      <div class="info_card">
        <h2>Objective</h2>
        <p class="objective_text">
          Help the user solve their technical issue while adapting to their unique personality type. Each persona requires a different approach!
        </p>
        <div class="tip_box">
          <div class="tip-icon">💡</div>
          <div class="tip-text">
            <strong>Pro tip:</strong> Read their personality carefully. Being technically correct isn't enough – you must communicate in a way they'll accept.
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    var socket = io();
    var chatWindow = document.getElementById('chat_window');
    var responseText = document.getElementById('response_text');
    var sendButton = document.getElementById('send_button');
    var currentTurn = document.getElementById('current_turn');
    var maxTurns = document.getElementById('max_turns');
    var progressCircle = document.getElementById('progress_circle');
    var gameStatus = document.getElementById('game_status');
    var personaInfo = document.getElementById('persona_info');
    var personalityInfo = document.getElementById('personality_info');
    var charCount = document.getElementById('char_count');

    // Character counter
    responseText.addEventListener('input', function() {
      charCount.textContent = this.value.length;
      this.style.height = 'auto';
      this.style.height = Math.min(this.scrollHeight, 150) + 'px';
    });

    // Format timestamp
    function getTimestamp() {
      const now = new Date();
      return now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    }

    function addMessage(text, type = 'system', avatar = '⚡') {
      var messageDiv = document.createElement('div');
      messageDiv.className = 'message ' + type;
      
      var avatarDiv = document.createElement('div');
      avatarDiv.className = 'message-avatar';
      avatarDiv.innerText = avatar;
      
      var contentWrapper = document.createElement('div');
      contentWrapper.className = 'message-content-wrapper';
      
      var contentDiv = document.createElement('div');
      contentDiv.className = 'message-content';
      contentDiv.innerText = text;
      
      contentWrapper.appendChild(contentDiv);
      
      if (type === 'user' || type === 'bot') {
        var timestamp = document.createElement('div');
        timestamp.className = 'message-timestamp';
        timestamp.innerText = getTimestamp();
        contentWrapper.appendChild(timestamp);
      }
      
      messageDiv.appendChild(avatarDiv);
      messageDiv.appendChild(contentWrapper);
      chatWindow.appendChild(messageDiv);
      chatWindow.scrollTop = chatWindow.scrollHeight;
    }

    function updateStatus(status, cls) {
      gameStatus.className = 'status_badge ' + cls;
      gameStatus.innerHTML = '<div class="status-indicator"></div><span>' + status + '</span>';
    }

    function updateProgress(current, max) {
      var percentage = current / max;
      var circumference = 2 * Math.PI * 62; // radius = 62
      var offset = circumference - (percentage * circumference);
      progressCircle.style.strokeDashoffset = offset;
    }

    function celebrateWin() {
      // Confetti animation
      var duration = 3 * 1000;
      var animationEnd = Date.now() + duration;
      var defaults = { startVelocity: 30, spread: 360, ticks: 60, zIndex: 9999 };

      function randomInRange(min, max) {
        return Math.random() * (max - min) + min;
      }

      var interval = setInterval(function() {
        var timeLeft = animationEnd - Date.now();

        if (timeLeft <= 0) {
          return clearInterval(interval);
        }

        var particleCount = 50 * (timeLeft / duration);
        confetti(Object.assign({}, defaults, {
          particleCount,
          origin: { x: randomInRange(0.1, 0.3), y: Math.random() - 0.2 }
        }));
        confetti(Object.assign({}, defaults, {
          particleCount,
          origin: { x: randomInRange(0.7, 0.9), y: Math.random() - 0.2 }
        }));
      }, 250);
    }

    socket.on('connect', () => {
      addMessage('Neural link established. Generating mission parameters...', 'system', '⚡');
      updateStatus('Connecting...', 'status_waiting');
    });

    socket.on('initial_mission', (msg) => {
      addMessage('Mission initialized. Client connected.', 'system', '✓');
      addMessage(msg.first_message, 'bot', '👤');
      
      // Parse persona info
      var personaParts = msg.persona.split('(Personality:');
      personaInfo.innerText = personaParts[0].trim();
      
      if (personaParts.length > 1) {
        personalityInfo.innerText = '🎭 ' + personaParts[1].replace(')', '').trim();
        personalityInfo.style.display = 'block';
      }
      
      currentTurn.innerText = '1';
      maxTurns.innerText = msg.max_turns;
      updateProgress(1, msg.max_turns);
      updateStatus('Active', 'status_active');
      responseText.disabled = false;
      sendButton.disabled = false;
      responseText.focus();
    });

    socket.on('new_bot_message', (msg) => {
      // Remove typing indicator if exists
      var typingIndicator = chatWindow.querySelector('.typing-indicator');
      if (typingIndicator) {
        typingIndicator.parentElement.remove();
      }
      
      addMessage(msg.message, 'bot', '👤');
      currentTurn.innerText = msg.turn;
      updateProgress(msg.turn, msg.max_turns);
      updateStatus('Active', 'status_active');
      responseText.disabled = false;
      sendButton.disabled = false;
      responseText.focus();
    });

    socket.on('game_over', (msg) => {
      // Remove typing indicator if exists
      var typingIndicator = chatWindow.querySelector('.typing-indicator');
      if (typingIndicator) {
        typingIndicator.parentElement.remove();
      }
      
      if (msg.win) {
        addMessage('✓ Mission Complete', 'win', '🎉');
        celebrateWin();
      } else {
        addMessage('✗ Mission Failed', 'lose', '💥');
      }
      addMessage(msg.message, 'bot', '👤');
      responseText.disabled = true;
      sendButton.disabled = true;
      addMessage('Refresh page to start new mission', 'system', '🔄');
      updateStatus(msg.win ? 'Success' : 'Failed', msg.win ? 'status_active' : 'status_ended');
    });

    function sendMessage() {
      var text = responseText.value.trim();
      if (!text) return;
      
      addMessage(text, 'user', '🧑');
      socket.emit('player_message', { message: text });
      responseText.value = '';
      charCount.textContent = '0';
      responseText.style.height = 'auto';
      responseText.disabled = true;
      sendButton.disabled = true;
      updateStatus('Processing...', 'status_waiting');
      
      // Add typing indicator
      var messageDiv = document.createElement('div');
      messageDiv.className = 'message bot';
      
      var avatarDiv = document.createElement('div');
      avatarDiv.className = 'message-avatar';
      avatarDiv.innerText = '👤';
      
      var contentWrapper = document.createElement('div');
      contentWrapper.className = 'message-content-wrapper';
      
      var contentDiv = document.createElement('div');
      contentDiv.className = 'message-content typing-indicator';
      contentDiv.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';
      
      contentWrapper.appendChild(contentDiv);
      messageDiv.appendChild(avatarDiv);
      messageDiv.appendChild(contentWrapper);
      chatWindow.appendChild(messageDiv);
      chatWindow.scrollTop = chatWindow.scrollHeight;
    }

    sendButton.onclick = sendMessage;
    responseText.onkeydown = (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    };
  </script>
</body>
</html>
"""

# --- 5. Game Logic Routes ---
MAX_TURNS = 5
judge = JudgeAgent()


@app.route("/")
def index():
    return render_template_string(HTML_PAGE)


@socketio.on("connect")
def handle_connect():
    print("client connected!")
    mission = generate_mission()

    session["technical_goal"] = mission["technical_goal"]
    session["personality_trait"] = mission["personality_trait"]
    session["turn_count"] = 0

    agent = PersonaAgent(
        mission["persona"], mission["technical_goal"], mission["personality_trait"]
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

    agent = PersonaAgent("from_history", goal, trait)
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


# --- 6. Run Server ---
if __name__ == "__main__":

    def shutdown():
        print("\n[server] shutting down...")
        sys.exit(0)

    signal_handler(signal.SIGINT, shutdown)
    print("server running on http://127.0.0.1:5000")
    socketio.run(app, host="0.0.0.0", port=5000)
