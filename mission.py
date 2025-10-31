import json
from openai import OpenAI

def generate_mission(client):
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
            temperature=1.2,
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
