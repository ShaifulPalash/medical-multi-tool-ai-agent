"""
STEP 5: MedicalWebSearchTool — general medical knowledge.

This tool handles general medical questions such as:

    - Definitions
    - Symptoms
    - Causes
    - Prevention
    - General treatment information

It should NOT be used for statistics from the project's medical datasets.

SEARCH BACKENDS
---------------
Tavily is used as the primary search backend when TAVILY_API_KEY is
available.

If Tavily is unavailable or fails at runtime, the tool falls back to
DuckDuckGo, which does not require an API key.

API-CALL OPTIMIZATION
---------------------
This tool uses:

    @tool(return_direct=True)

This tells the LangChain agent that the tool's result can be returned
directly to the user.

Therefore, after Gemini decides to use this tool, we do not need another
Gemini call just to rewrite/summarize the search result.

Flow:

    User question
          ↓
    Gemini routing              # Gemini call 1
          ↓
    Medical Web Search Tool
          ↓
    Tavily / DuckDuckGo
          ↓
    Search result + disclaimer
          ↓
    Directly returned to user

SAFETY: MEDICAL DISCLAIMER
---------------------------
Every response from this tool includes a clear disclaimer stating that
the information is general information from web sources and is not
medical advice.

The disclaimer is added inside the tool itself so it cannot accidentally
be omitted by the main agent.
"""

import os

from langchain_core.tools import tool

# ---------------------------------------------------------------------------
# Tavily API key
# ---------------------------------------------------------------------------
#
# The key is read from the environment.
#
# Expected .env entry:
#
#     TAVILY_API_KEY=your_tavily_api_key
#
# If no key is available, DuckDuckGo will be used automatically.
# ---------------------------------------------------------------------------

_TAVILY_KEY = os.getenv("TAVILY_API_KEY", "").strip()


# ---------------------------------------------------------------------------
# Medical disclaimer
# ---------------------------------------------------------------------------
#
# This disclaimer is always appended to the search result.
# ---------------------------------------------------------------------------

MEDICAL_DISCLAIMER = (
    "\n\n---\n"
    "This is general information from web sources, not medical advice. "
    "For diagnosis, treatment, or any personal health decision, please "
    "consult a qualified healthcare professional."
)


# ---------------------------------------------------------------------------
# Tavily search backend
# ---------------------------------------------------------------------------


def _search_with_tavily(query: str) -> str:
    """
    Search the web using Tavily.

    Tavily is used as the primary backend because it is designed for
    applications and LLM-based agents.
    """

    from langchain_community.tools.tavily_search import TavilySearchResults

    backend = TavilySearchResults(max_results=5)

    results = backend.invoke({"query": query})

    if not results:
        return "No results found."

    formatted_results = []

    for result in results:
        content = result.get("content", "")
        url = result.get("url", "")

        formatted_results.append(f"- {content} (source: {url})")

    return "\n\n".join(formatted_results)


# ---------------------------------------------------------------------------
# DuckDuckGo search backend
# ---------------------------------------------------------------------------


def _search_with_duckduckgo(query: str) -> str:
    """
    Search the web using DuckDuckGo.

    DuckDuckGo is used as the fallback backend because it does not require
    a Tavily API key.
    """

    from langchain_community.tools import DuckDuckGoSearchRun

    backend = DuckDuckGoSearchRun()

    result = backend.invoke(query)

    return result or "No results found."


# ---------------------------------------------------------------------------
# Main Medical Web Search Tool
# ---------------------------------------------------------------------------
#
# return_direct=True is the important API-call optimization.
#
# Once the main Gemini agent selects this tool and the tool finishes,
# LangChain can return this result directly instead of asking Gemini
# to generate another final response.
# ---------------------------------------------------------------------------


@tool(return_direct=True)
def medical_web_search_tool(query: str) -> str:
    """Use this tool for GENERAL medical knowledge questions that are NOT
    answerable from the heart disease, cancer, or diabetes datasets.

    Use this tool for:
    - Definitions
    - Symptoms
    - Causes
    - Prevention
    - General treatment information

    Examples:
    - "What are the symptoms of diabetes?"
    - "What causes heart disease?"
    - "What is cancer?"
    - "How is cancer typically treated?"

    Do NOT use this tool for questions asking for counts, averages,
    percentages, measurements, or other statistics from the patient
    datasets. Use the matching database tool for those questions.

    Every response includes a medical-information disclaimer.
    """

    # -----------------------------------------------------------------------
    # Try Tavily first when a Tavily API key is available.
    # -----------------------------------------------------------------------

    if _TAVILY_KEY:
        try:
            raw_result = _search_with_tavily(query)

        except Exception:
            # ---------------------------------------------------------------
            # Defensive fallback.
            #
            # If Tavily fails because of:
            #   - invalid API key
            #   - quota problem
            #   - network error
            #   - service error
            #
            # automatically use DuckDuckGo.
            # ---------------------------------------------------------------

            raw_result = _search_with_duckduckgo(query)

    else:
        # -------------------------------------------------------------------
        # No Tavily API key.
        # Use DuckDuckGo directly.
        # -------------------------------------------------------------------

        raw_result = _search_with_duckduckgo(query)

    # -----------------------------------------------------------------------
    # Always append the medical disclaimer.
    #
    # Because return_direct=True is enabled, this complete result can be
    # returned directly to the user.
    # -----------------------------------------------------------------------

    return raw_result + MEDICAL_DISCLAIMER
