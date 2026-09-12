"""
Gradio web interface for the Medical Multi-Tool AI Agent.

USAGE:
    python app.py

Then open the local Gradio URL shown in the terminal.

Make sure you've already run, in order:
    1. python scripts/download_and_inspect.py
    2. python scripts/build_databases.py

Also make sure your .env file contains the required API keys.
"""

import gradio as gr
from dotenv import load_dotenv

load_dotenv()  # Load environment variables before importing the agent.

from agent.main_agent import ask, build_agent, final_answer_text  # noqa: E402

# Build the agent once when the application starts.
agent = build_agent()


def chat_with_agent(message: str, history: list) -> str:
    """Send the user's message to the medical agent and return its answer."""

    if not message.strip():
        return "Please enter a question."

    result = ask(agent, message)

    return final_answer_text(result)


demo = gr.ChatInterface(
    fn=chat_with_agent,
    title="🩺 Medical Multi-Tool AI Agent",
    description=(
        "Ask questions about the medical datasets or general medical "
        "knowledge. The agent automatically selects the appropriate tool."
    ),
    textbox=gr.Textbox(
        placeholder="Ask a medical question...",
        container=True,
    ),
)


if __name__ == "__main__":
    demo.launch()
