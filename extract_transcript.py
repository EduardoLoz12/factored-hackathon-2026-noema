import json

with open(
    "/Users/federicovargas/.gemini/antigravity/brain/a856c8e3-cf7b-4d8b-ae25-ac4c641e56c8/.system_generated/logs/transcript_full.jsonl"
) as f:
    for line in f:
        data = json.loads(line)
        if data.get("type") == "TOOL_RESPONSE" and data.get("tool_name") == "default_api:view_file":
            content = data.get("content", "")
            if (
                "class NoemaCore" in content
                or "chat_endpoint" in content
                or "_run_orchestrator_turn" in content
            ):
                print("FOUND A MATCH! Length:", len(content))
                with open("recovered_chunk.py", "a") as out:
                    out.write("\n# --- CHUNK ---\n")
                    out.write(content)
