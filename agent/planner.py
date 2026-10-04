# agent/planner.py
from agent.prompts import SYSTEM_PROMPT

def generate_plan(goal: str, profile: dict, inspect=None, answers=None) -> dict:
    """
    Takes the user goal and CSV profile, and returns a structured plan.
    """
    # Verify that we have a goal and column profile
    columns = profile.get("columns", [])
    
    # Simple logic returning a structured plan
    operations = []
    
    if "trim" in goal.lower() or "space" in goal.lower():
        operations.append({
            "id": "op_001",
            "operation": "trim_whitespace",
            "columns": columns,
            "reason": "User requested trimming spaces."
        })
        
    if "duplicate" in goal.lower():
        operations.append({
            "id": "op_002",
            "operation": "remove_duplicates",
            "columns": columns,
            "reason": "User requested removing duplicate rows."
        })

    return {
        "operations": operations,
        "clarification_questions": []
    }