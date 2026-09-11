"""
STEP 7: Test the agent on representative questions covering all 4 tools,
printing which tool got called (the routing decision) and the final
answer. Requires a real OPENAI_API_KEY (and built databases) since this
makes real LLM calls — unlike tests/, which uses a fake LLM and needs no key.

Run with: python scripts/test_queries.py
"""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

from agent.main_agent import ask, build_agent, final_answer_text

TEST_CASES = [
    ("What is the average age of patients with heart disease?", "heart_disease_db_tool"),
    ("How many patients have a resting blood pressure above 140?", "heart_disease_db_tool"),
    ("How many patients in the dataset were diagnosed with cancer?", "cancer_db_tool"),
    ("What is the average BMI of smokers in the cancer dataset?", "cancer_db_tool"),
    ("How many patients have a glucose level over 140?", "diabetes_db_tool"),
    ("What is the average BMI of diabetic patients in the dataset?", "diabetes_db_tool"),
    ("What are the symptoms of diabetes?", "medical_web_search_tool"),
    ("What causes heart disease?", "medical_web_search_tool"),
]


def get_called_tools(result: dict) -> list:
    called = []
    for msg in result["messages"]:
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            called.extend(call["name"] for call in tool_calls)
    return called


def main():
    agent = build_agent()

    for question, expected_tool in TEST_CASES:
        print("\n" + "=" * 70)
        print("QUESTION:", question)
        print("EXPECTED TOOL:", expected_tool)

        result = ask(agent, question)
        called_tools = get_called_tools(result)

        print("ACTUAL TOOL(S) CALLED:", called_tools)
        match = expected_tool in called_tools
        print("ROUTING CORRECT:", "YES" if match else "NO -- check tool descriptions/system prompt")
        print("ANSWER:", final_answer_text(result))


if __name__ == "__main__":
    main()
