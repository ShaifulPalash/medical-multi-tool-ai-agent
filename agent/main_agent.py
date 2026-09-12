"""
STEP 6: The main routing agent.

FRAMEWORK
---------
This project uses LangGraph's create_react_agent with Gemini as the
underlying LLM.

The main agent is responsible for deciding which of the four tools
should handle the user's question:

    1. heart_disease_db_tool
    2. cancer_db_tool
    3. diabetes_db_tool
    4. medical_web_search_tool

API-CALL OPTIMIZATION
---------------------
The tools use return_direct=True.

This means that after the agent selects and executes a tool, the
tool's result is returned directly to the user instead of sending
that result back to Gemini for another final-answer generation call.

Therefore:

Database question:

    User
      ↓
    Gemini routing                         # Call 1
      ↓
    Database tool
      ↓
    Gemini SQL generation                  # Call 2
      ↓
    SQLite
      ↓
    Direct tool result
      ↓
    User

Web question:

    User
      ↓
    Gemini routing                         # Call 1
      ↓
    Web search tool
      ↓
    Direct tool result
      ↓
    User

This preserves the multi-tool assignment architecture while avoiding
an unnecessary final Gemini call.
"""

import os

from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI

from tools.db_tools import (
    cancer_db_tool,
    diabetes_db_tool,
    heart_disease_db_tool,
)
from tools.web_search_tool import medical_web_search_tool

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are a helpful Medical Multi-Tool AI Agent.

You have four tools:

1. heart_disease_db_tool
   - Use for statistics and data from the heart disease patient dataset.
   - Examples: counts, averages, percentages, measurements, and filters
     on recorded patient records.

2. cancer_db_tool
   - Use for statistics and data from the cancer prediction dataset.
   - Examples: counts, averages, percentages, and filters on recorded
     patient records.

3. diabetes_db_tool
   - Use for statistics and data from the diabetes patient dataset.
   - Examples: counts, averages, percentages, measurements, and filters
     on recorded patient records.

4. medical_web_search_tool
   - Use for general medical knowledge.
   - Examples: definitions, symptoms, causes, prevention, and general
     treatment information.
   - Do NOT use this tool for statistics that must come from the datasets.

ROUTING RULES
-------------

1. If the question asks for a COUNT, AVERAGE, PERCENTAGE, NUMBER,
   measurement, statistic, or filter on patient records from one of
   the datasets, use the appropriate database tool.

2. If the question asks about general medical knowledge such as:
   - What is X?
   - What are the symptoms of X?
   - What causes X?
   - How is X treated?
   - How can X be prevented?

   use medical_web_search_tool.

3. Choose the database based on the medical condition mentioned:

   - Heart disease → heart_disease_db_tool
   - Cancer → cancer_db_tool
   - Diabetes → diabetes_db_tool

4. Only call ONE tool for a normal question.

5. If a question genuinely contains two distinct parts that require
   two different tools, you may call both tools.

6. Database questions must be answered using the database tool result.
   Do not invent numbers or statistics.

7. General medical questions must be answered using the web-search
   tool result.

8. Do not use a database tool to answer general medical questions
   about symptoms, causes, treatment, or definitions.

9. Do not use the web-search tool when the user is specifically asking
   for statistics from one of the provided datasets.

IMPORTANT:
The selected tool's result will be returned directly to the user.
Therefore, select the correct tool and make sure the tool receives the
user's original question accurately.

WORKED EXAMPLES
---------------

Question:
"What is the average age of patients with heart disease?"

Tool:
heart_disease_db_tool

Question:
"How many patients have a cholesterol level above 250?"

Tool:
heart_disease_db_tool

Question:
"How many patients in the dataset were diagnosed with cancer?"

Tool:
cancer_db_tool

Question:
"What is the average BMI of smokers in the cancer dataset?"

Tool:
cancer_db_tool

Question:
"How many patients have a glucose level over 140?"

Tool:
diabetes_db_tool

Question:
"What is the average BMI of diabetic patients?"

Tool:
diabetes_db_tool

Question:
"What are the symptoms of diabetes?"

Tool:
medical_web_search_tool

Question:
"What causes heart disease?"

Tool:
medical_web_search_tool

Question:
"What is cancer?"

Tool:
medical_web_search_tool
"""


# ---------------------------------------------------------------------------
# Build the main agent
# ---------------------------------------------------------------------------


def build_agent():
    """
    Create and return the main LangGraph routing agent.

    The agent has four tools:

        Heart Disease DB
        Cancer DB
        Diabetes DB
        Medical Web Search

    The tools are configured with return_direct=True in their own
    definitions where supported, so the tool result can be returned
    without an additional Gemini final-answer call.
    """

    llm = ChatGoogleGenerativeAI(
        model=os.getenv(
            "AGENT_MODEL",
            "gemini-3.6-flash",
        )
    )

    tools = [
        heart_disease_db_tool,
        cancer_db_tool,
        diabetes_db_tool,
        medical_web_search_tool,
    ]

    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
    )

    return agent


# ---------------------------------------------------------------------------
# Ask the agent
# ---------------------------------------------------------------------------


def ask(agent, question: str) -> dict:
    """
    Send one question to the main agent.

    Returns the complete LangGraph result dictionary.

    The result contains the message/tool trace, which is useful for
    testing and debugging.
    """

    return agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": question,
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# Extract the final answer
# ---------------------------------------------------------------------------


def _extract_content_text(content) -> str:
    """
    Convert LangChain/Gemini message content into plain text.

    Gemini can return content either as a normal string or as a list
    of content blocks.
    """

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        text_parts = []

        for block in content:
            if isinstance(block, dict):
                text = block.get("text", "")

                if text:
                    text_parts.append(text)

        return "".join(text_parts).strip()

    return str(content).strip()


def final_answer_text(result: dict) -> str:
    """
    Extract the most useful final text from an agent result.

    With return_direct tools, the final message can be a ToolMessage
    instead of an additional AI-generated message.

    Therefore, this function checks messages from newest to oldest
    and returns the latest meaningful textual content.
    """

    messages = result.get("messages", [])

    if not messages:
        return "No response was generated."

    # First look at the newest messages.
    for message in reversed(messages):
        content = getattr(message, "content", None)

        if content is None:
            continue

        text = _extract_content_text(content)

        if text:
            return text

    return "No response was generated."
