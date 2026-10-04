# test_agent.py
from agent.planner import generate_plan

# 1. Create a dummy CSV profile (simulating Member 2's output)
dummy_profile = {
    "columns": ["customer_name", "email", "registration_date"]
}

# 2. Test goal 1
goal_1 = "Please trim whitespace from names and remove duplicate rows."
plan_1 = generate_plan(goal=goal_1, profile=dummy_profile)

print("--- PLAN 1 RESULT ---")
print(plan_1)