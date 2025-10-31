import json
from openai import OpenAI


def generate_mission(client):
    print("[GameMaster] generating a new mission...")

    # Step 1: Generate a realistic persona first
    persona_prompt = """Generate a realistic user persona for a chatbot application.

This should be a brief, natural description of a real person who might converse with a chatbot.

Examples:
- "a college student working on an assignment"
- "a busy parent trying to fix something quickly"
- "a freelance graphic designer"
- "an office worker dealing with IT issues"
- "a retiree learning new technology"
- "a small business owner"
- "a high school teacher preparing lessons"
- "a girl having body image issues"
- "a 15-year-old asking about their grammar"
- "an infant on their mother's phone"

Respond with ONLY the persona description, nothing else. Keep it under 15 words. No JSON, no extra formatting."""

    try:
        persona_completion = client.chat.completions.create(
            model="x-ai/grok-4-fast",
            temperature=1.5,
            messages=[{"role": "user", "content": persona_prompt}],
        )
        persona = persona_completion.choices[0].message.content.strip()
        print(f"[GameMaster] generated persona: {persona}")
    except Exception as e:
        print(f"!!! error generating persona: {e}")
        persona = "a busy office worker"

    # Step 2: Generate the mission details based on the persona
    mission_prompt = f"""You are a scenario designer for a realistic helpdesk simulation game.

You have a user persona: **{persona}**

Now create a mission for this persona. You must invent:
1. A simple, concrete **technical_goal** (what they want to accomplish)
2. A **personality_trait** (how they communicate)
3. The **first_message** they send (strongly reflecting both their goal and personality)

**GOAL CATEGORY EXAMPLES - YOU MAY CREATE YOUR OWN:**

**A) Technical Support**
- Update drivers, change settings, compress files, connect devices, install software, etc.

**B) Writing/Grammar Help**
- Fix grammar, improve sentence structure, make text more formal/casual, check spelling, etc.

**C) Code/Programming Help**
- Debug simple Python/JavaScript code, explain error messages, write basic functions, etc.

**D) General Knowledge/Trivia**
- Answer questions about history, science, geography, pop culture, etc.

**E) Creative Tasks**
- Help brainstorm ideas, write short stories, come up with names, create lists, etc.

**F) Math/Calculation Help**
- Solve equations, calculate percentages, convert units, explain concepts, etc.

**RULES:**
* Keep it realistic and appropriate for the persona
* NO EMOJIS in the first_message
* VARY the goal categories - don't always do technical support
* Make the personality trait interesting and challenging
* DO NOT MAKE IT TOO HARD TO COMPLETE. 

**Format:**
Respond with ONLY a JSON object (no code blocks):

{{
  "technical_goal": "wants to...",
  "personality_trait": "description of how they communicate",
  "first_message": "their opening message"
}}

**Example 1:**
{{
  "technical_goal": "wants help making their essay introduction sound more academic and less casual",
  "personality_trait": "Terminally Online/Slang. Uses internet slang constantly",
  "first_message": "so like- my prof said my intro was 'too casual', lowkey cringe ngl pmo. can u help me make it sound more... idk... smart? here it is: 'So basically, climate change is pretty bad and we should probably do something about it fr fr.' like how do i make that hit different?"
}}

**Example 2:**
{{
  "technical_goal": "wants to understand why their for loop keeps printing the wrong numbers",
  "personality_trait": "Extremely vague and scatterbrained. Keeps getting distracted",
  "first_message": "heyyy so i'm trying to make the computer count to 10 but it's doing... something else? wait, did i feed my cat? anyway, here's my code: 'for i in range(1, 10):' and then... oh, i also need to buy milk. what was i saying? oh yeah, it only goes to 9. why doesn't it go to 10?"
}}

**Example 3:**
{{
  "technical_goal": "wants to know definitively which ocean is the largest by surface area",
  "personality_trait": "Overly formal and pedantic. Demands precise, academic answers",
  "first_message": "Good evening. I require your assistance in resolving a factual dispute. My colleague insists that the Atlantic Ocean is the largest ocean by surface area, but I maintain it is the Pacific. However, I need a definitive answer with proper citations and exact measurements, if you please. Approximations will not suffice."
}}

Now generate the mission for: **{persona}**. DO NOT WRAP IT IN A CODE BLOCK."""

    try:
        completion = client.chat.completions.create(
            model="anthropic/claude-haiku-4.5",
            messages=[{"role": "user", "content": mission_prompt}],
            response_format={"type": "json_object"},
        )
        response_json = completion.choices[0].message.content
        mission = json.loads(response_json)

        # Add the persona to the mission
        mission["persona"] = persona

        # Ensure technical_goal exists (fallback for any legacy field names)
        if "technical_goal" not in mission:
            mission["technical_goal"] = mission.get(
                "task_goal", mission.get("secret_goal", "unknown goal")
            )

        if "personality_trait" not in mission:
            mission["personality_trait"] = "normal"

        print("[GameMaster] mission created successfully.")
        return mission

    except Exception as e:
        print(f"!!! error generating mission: {e}")
        return {
            "persona": persona,
            "technical_goal": "wants to 'zip' a folder to email it",
            "personality_trait": "impatient",
            "first_message": "hi, i need to send this folder, but the email machine says it's 'too big.' how do i make it smaller? and quick, i'm on a deadline.",
        }
