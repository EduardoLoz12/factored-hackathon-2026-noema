with open("api/main.py") as f:
    text = f.read()

# Replace the orchestrator draft
text = text.replace(
    """    def redactar(_attempt: int, _previous) -> str:
        return _draft_orchestrated_response(turn)""",
    '''    def redactar(_attempt: int, _previous) -> str:
        context = _draft_orchestrated_response(turn)
        prompt = f"""You are a helpful banking assistant. Draft a natural, conversational response to the customer based on this verified system information:
System Information: "{context}"
Customer Message: "{request.message}"
IMPORTANT: Do not invent any numbers. Only use the numbers and facts provided in the System Information.
"""
        draft = _generate_with_llm(prompt)
        if draft:
            return draft
        return context''',
)

# Replace the fallback routes
old_fallback = """    response = ChatResponse(
        response=core_result["msg"],"""
new_fallback = '''    final_msg = core_result["msg"]
    prompt = f"""You are a helpful banking assistant. Draft a natural, conversational response to the customer based on this verified system information:
System Information: "{final_msg}"
Customer Message: "{request.message}"
IMPORTANT: Do not invent any numbers or facts. Only use the facts provided in the System Information. Rewrite the system information to be more empathetic and human-like.
"""
    draft = _generate_with_llm(prompt)
    if draft:
        final_msg = draft

    response = ChatResponse(
        response=final_msg,'''

text = text.replace(old_fallback, new_fallback)

# Replace the escalation route (it was inside a block returning early)
old_esc = """        response = ChatResponse(
            response="I am transferring you to a human expert who can better assist you right away.","""
new_esc = '''        final_msg = "I am transferring you to a human expert who can better assist you right away."
        prompt = f"""You are a helpful banking assistant. Draft a natural, conversational response to the customer based on this verified system information:
System Information: "{final_msg}"
Customer Message: "{request.message}"
IMPORTANT: Do not invent any numbers or facts. Only use the facts provided in the System Information. Rewrite the system information to be more empathetic and human-like.
"""
        draft = _generate_with_llm(prompt)
        if draft:
            final_msg = draft

        response = ChatResponse(
            response=final_msg,'''

text = text.replace(old_esc, new_esc)

# Replace the "orchestrator unavailable" block
old_unavail = """            response = ChatResponse(
                response="No pude completar el turno con el orquestador real. Me abstengo de dar una decisión bancaria y puedo derivarte con un asesor.","""
new_unavail = '''            final_msg = "No pude completar el turno con el orquestador real. Me abstengo de dar una decisión bancaria y puedo derivarte con un asesor."
            prompt = f"""You are a helpful banking assistant. Draft a natural, conversational response to the customer based on this verified system information:
System Information: "{final_msg}"
Customer Message: "{request.message}"
IMPORTANT: Do not invent any numbers or facts. Only use the facts provided in the System Information. Rewrite the system information to be more empathetic and human-like.
"""
            draft = _generate_with_llm(prompt)
            if draft:
                final_msg = draft

            response = ChatResponse(
                response=final_msg,'''

text = text.replace(old_unavail, new_unavail)


with open("api/main.py", "w") as f:
    f.write(text)
