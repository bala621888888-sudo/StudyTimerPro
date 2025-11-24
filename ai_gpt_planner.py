import json
from pathlib import Path
from openai import OpenAI
from ai_integration import create_ai_prompt, create_comprehensive_data_file
from secrets_util import get_secret
from config_paths import app_paths

def generate_study_plan_via_gpt4o_mini():
    """
    Use gpt-4o-mini model to create study plan and save it to plans.json
    """

    # Create prompt and data
    create_comprehensive_data_file()
    prompt = create_ai_prompt()

    ai_data_file = Path(app_paths.appdata_dir) / "ai_data_feed" / "ALL_DATA_FOR_AI.txt"
    ai_data = ai_data_file.read_text(encoding="utf-8")
    full_prompt = f"{prompt}\n\n{ai_data}"

    # Get API key from Secret Manager
    api_key = get_secret("AI_API")
    if not api_key:
        raise RuntimeError("❌ AI_API key not found in secrets!")

    # Init OpenAI client
    client = OpenAI(api_key=api_key)

    # Call GPT-4o mini
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a study planner AI. Return only valid JSON for plans.json."},
            {"role": "user", "content": full_prompt}
        ],
        temperature=0.7
    )

    reply = response.choices[0].message.content.strip()

    # Save output to plans.json
    plans_path = Path(app_paths.appdata_dir) / "plans.json"
    try:
        parsed = json.loads(reply)
        plans_path.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
        return f"✅ Plan saved to {plans_path}"
    except Exception:
        # If JSON parsing fails, save raw
        debug_path = Path(app_paths.appdata_dir) / "plans_raw_output.txt"
        debug_path.write_text(reply, encoding="utf-8")
        raise RuntimeError(f"⚠ Invalid JSON from AI. Raw saved to {debug_path}")
