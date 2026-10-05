import json

with open(
    "/Users/federicovargas/.gemini/antigravity/brain/a856c8e3-cf7b-4d8b-ae25-ac4c641e56c8/.system_generated/logs/transcript_full.jsonl"
) as f:
    for line in f:
        data = json.loads(line)
        content = data.get("content", "")
        if "_run_orchestrator_turn" in content and "def " in content:
            print("FOUND A MATCH! Length:", len(content))
            with open("recovered_chunk2.py", "a") as out:
                out.write("\n# --- CHUNK ---\n")
                out.write(content)
