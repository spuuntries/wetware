import json
from openai import OpenAI


class PersonaAgent:
    def __init__(self, persona, technical_goal, personality_trait, client):
        self.persona = persona
        self.technical_goal = technical_goal
        self.personality_trait = personality_trait
        self.client = client
        self.history = [
            {
                "role": "system",
                "content": f"""You are a game character. You are *not* an AI assistant.
Your persona: {persona}
Your technical goal: {technical_goal}
Your personality: {personality_trait}

Your job is to act out this persona and personality *perfectly*.
The player is an assistant trying to help you.
DO NOT reveal your technical goal. Just act confused.
**Based on your personality, you might reject a correct answer if it's not delivered well.**
(e.g., if you are 'impatient', you hate long answers. if you are 'anxious', you hate technical jargon.)""",
            }
        ]

    def get_reply(self, player_message):
        print(f"[PersonaAgent] thinking... (persona: {self.persona})")
        self.history.append({"role": "user", "content": player_message})
        try:
            completion = self.client.chat.completions.create(
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
            completion = self.client.chat.completions.create(
                model="gpt-4o-mini", messages=temp_history
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"!!! final reply error: {e}")
            return "fine, whatever. i'm leaving."


class JudgeAgent:
    def __init__(self, client):
        self.client = client
        self.system_prompt = """
_You are a strict game referee. Your only job is to determine if the player has won._
_Respond with ONLY a JSON object: {"solved": true} or {"solved": false}_
"""

    def check_if_solved(self, chat_history, secret_goal):
        print("[JudgeAgent] checking for win condition...")
        history_json = json.dumps(chat_history, indent=2)
        prompt = f"**Secret Goal:**\n{secret_goal}\n\n**Chat History:**\n{history_json}\n\n---\n_Has the player's *last* message solved the goal?_"
        try:
            completion = self.client.chat.completions.create(
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
