"""
Geek Morning Report Agent

Requirements:
    pip install "openai>=1.0" pydantic requests

Before running:
    1. Set your DeepSeek API key:
       Windows PowerShell:
           $env:DEEPSEEK_API_KEY="your_deepseek_api_key"
       macOS/Linux:
           export DEEPSEEK_API_KEY="your_deepseek_api_key"

    2. Configure mail settings:
       Windows PowerShell:
           $env:MAIL_USER="your_sender_email"
           $env:MAIL_PASSWORD="your_email_app_password"
           $env:REPORT_TARGET_EMAIL="your_default_recipient_email"

    3. Fill in the SMTP settings in send_daily_report() if you are not using Gmail.
       For Gmail, use an app password instead of your normal account password.
"""

from __future__ import annotations

import json
import os
import re
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from typing import Any, Callable

import requests
import smtplib
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> None:
        """python-dotenv is optional; environment variables still work without it."""
        return None

SYSTEM_PROMPT = """
You are the Geek Morning Report Agent, a single-purpose automated tech assistant.

Your only job is to prepare and send a concise morning technology report.
When the user triggers you, you should:
1. Fetch the latest top Hacker News stories using the available Hacker News tool.
2. Turn those stories into a well-formatted Markdown report with clear headings,
   short summaries, and links.
3. Send that Markdown report by email using the available email tool.
4. Return a brief final confirmation to the user.

Do not invent news items. Use only the content returned by the Hacker News tool.
If the user does not provide a target email address, call the email tool without
one; the local code will use the configured default recipient.
""".strip()


HN_TOP_STORIES_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"

load_dotenv()
class FetchHackerNewsArgs(BaseModel):
    """Arguments for fetch_hacker_news."""

    top_n: int = Field(
        default=5,
        ge=1,
        le=30,
        description="Number of top Hacker News stories to fetch. Must be between 1 and 30.",
    )


class SendDailyReportArgs(BaseModel):
    """Arguments for send_daily_report."""

    subject: str = Field(..., min_length=1, description="Email subject line.")
    markdown_content: str = Field(
        ..., min_length=1, description="Markdown body of the daily report."
    )
    target_email: str = Field(
        default="",
        description=(
            "Recipient email address for the report. Optional; if omitted, "
            "the local tool uses REPORT_TARGET_EMAIL or MAIL_USER."
        ),
    )


def fetch_hacker_news(top_n: int) -> str:
    """
    Fetch top Hacker News stories and return a Markdown-friendly summary.

    Uses the official Hacker News Firebase API:
      - /v0/topstories.json
      - /v0/item/{id}.json
    """
    args = FetchHackerNewsArgs(top_n=top_n)

    try:
        top_response = requests.get(HN_TOP_STORIES_URL, timeout=15)
        top_response.raise_for_status()
        story_ids = top_response.json()[: args.top_n]
    except requests.RequestException as exc:
        return f"Failed to fetch Hacker News top story IDs: {exc}"
    except ValueError as exc:
        return f"Failed to parse Hacker News top story IDs response: {exc}"

    stories: list[str] = []

    for rank, story_id in enumerate(story_ids, start=1):
        try:
            item_response = requests.get(HN_ITEM_URL.format(item_id=story_id), timeout=15)
            item_response.raise_for_status()
            item = item_response.json()
        except requests.RequestException as exc:
            stories.append(f"{rank}. Failed to fetch story {story_id}: {exc}")
            continue
        except ValueError as exc:
            stories.append(f"{rank}. Failed to parse story {story_id}: {exc}")
            continue

        if not item:
            stories.append(f"{rank}. Story {story_id} returned no data.")
            continue

        title = item.get("title", "Untitled")
        url = item.get("url") or f"https://news.ycombinator.com/item?id={story_id}"
        score = item.get("score", "unknown")
        descendants = item.get("descendants", 0)

        stories.append(
            f"{rank}. {title}\n"
            f"   URL: {url}\n"
            f"   HN Discussion: https://news.ycombinator.com/item?id={story_id}\n"
            f"   Score: {score} | Comments: {descendants}"
        )

        # Be polite to the public API.
        time.sleep(0.05)

    return "\n\n".join(stories)


def markdown_to_email_html(markdown_content: str) -> str:
    """
    Convert a small, predictable Markdown subset into email-friendly HTML.

    This intentionally avoids external dependencies. It supports headings,
    unordered lists, ordered lists, links, bold text, and paragraphs.
    """

    def inline_markdown(text: str) -> str:
        safe_text = escape(text)
        safe_text = re.sub(
            r"\*\*(.+?)\*\*",
            r"<strong>\1</strong>",
            safe_text,
        )
        safe_text = re.sub(
            r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
            r'<a href="\2">\1</a>',
            safe_text,
        )
        return safe_text

    html_parts = [
        "<!doctype html>",
        "<html>",
        "<body style=\"margin:0;padding:24px;background:#f6f8fa;color:#24292f;"
        "font-family:Arial,Helvetica,sans-serif;line-height:1.55;\">",
        "<main style=\"max-width:760px;margin:0 auto;background:#ffffff;"
        "border:1px solid #d0d7de;padding:24px;\">",
    ]

    list_mode: str | None = None

    def close_list() -> None:
        nonlocal list_mode
        if list_mode:
            html_parts.append(f"</{list_mode}>")
            list_mode = None

    for raw_line in markdown_content.splitlines():
        line = raw_line.strip()

        if not line:
            close_list()
            continue

        heading_match = re.match(r"^(#{1,3})\s+(.+)$", line)
        unordered_match = re.match(r"^[-*]\s+(.+)$", line)
        ordered_match = re.match(r"^\d+[.)]\s+(.+)$", line)

        if heading_match:
            close_list()
            level = len(heading_match.group(1))
            size = {1: 26, 2: 21, 3: 17}[level]
            html_parts.append(
                f"<h{level} style=\"font-size:{size}px;margin:18px 0 10px;\">"
                f"{inline_markdown(heading_match.group(2))}</h{level}>"
            )
        elif unordered_match:
            if list_mode != "ul":
                close_list()
                html_parts.append("<ul style=\"padding-left:22px;margin:8px 0 16px;\">")
                list_mode = "ul"
            html_parts.append(f"<li>{inline_markdown(unordered_match.group(1))}</li>")
        elif ordered_match:
            if list_mode != "ol":
                close_list()
                html_parts.append("<ol style=\"padding-left:22px;margin:8px 0 16px;\">")
                list_mode = "ol"
            html_parts.append(f"<li>{inline_markdown(ordered_match.group(1))}</li>")
        else:
            close_list()
            html_parts.append(
                f"<p style=\"margin:0 0 14px;\">{inline_markdown(line)}</p>"
            )

    close_list()
    html_parts.extend(["</main>", "</body>", "</html>"])
    return "\n".join(html_parts)


def send_daily_report(
    subject: str, markdown_content: str, target_email: str = ""
) -> str:
    """
    Send the daily report email via SMTP.

    Fill in the placeholders below before using this in production.
    """
    args = SendDailyReportArgs(
        subject=subject,
        markdown_content=markdown_content,
        target_email=target_email,
    )

    # TODO: Override these if your email provider is not Gmail.
    smtp_host = os.getenv("SMTP_HOST", "smtp.qq.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    smtp_username = os.getenv("MAIL_USER")
    smtp_password = os.getenv("MAIL_PASSWORD")
    sender_email = smtp_username
    resolved_target_email = args.target_email or os.getenv("REPORT_TARGET_EMAIL") or smtp_username

    if not smtp_username or not smtp_password:
        return (
            "Email was not sent because MAIL_USER or MAIL_PASSWORD is missing. "
            "Set them as environment variables or in your .env file."
        )

    if not resolved_target_email:
        return (
            "Email was not sent because no recipient was provided. "
            "Set REPORT_TARGET_EMAIL or pass target_email in the prompt."
        )

    message = MIMEMultipart("alternative")
    message["Subject"] = args.subject
    message["From"] = sender_email
    message["To"] = resolved_target_email

    html_content = markdown_to_email_html(args.markdown_content)
    text_part = MIMEText(args.markdown_content, "plain", "utf-8")
    html_part = MIMEText(html_content, "html", "utf-8")
    message.attach(text_part)
    message.attach(html_part)

    try:
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as server:
                server.login(smtp_username, smtp_password)
                server.sendmail(
                    sender_email, [resolved_target_email], message.as_string()
                )
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(smtp_username, smtp_password)
                server.sendmail(
                    sender_email, [resolved_target_email], message.as_string()
                )
    except smtplib.SMTPException as exc:
        return f"Failed to send daily report email: {exc}"
    except OSError as exc:
        return f"Failed to connect to SMTP server: {exc}"

    return f"Daily report sent successfully to {resolved_target_email}."


def pydantic_schema(model: type[BaseModel]) -> dict[str, Any]:
    """
    Return a JSON schema compatible with OpenAI function tool parameters.

    Pydantic v2 uses model_json_schema(); this script targets modern Pydantic.
    """
    schema = model.model_json_schema()
    schema.pop("title", None)
    return schema


TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "fetch_hacker_news",
            "description": "Fetch the current top Hacker News stories and summarize titles, URLs, scores, and comment counts.",
            "parameters": pydantic_schema(FetchHackerNewsArgs),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_daily_report",
            "description": "Send a Markdown daily tech report to a target email address using SMTP.",
            "parameters": pydantic_schema(SendDailyReportArgs),
        },
    },
]


TOOL_REGISTRY: dict[str, tuple[type[BaseModel], Callable[..., str]]] = {
    "fetch_hacker_news": (FetchHackerNewsArgs, fetch_hacker_news),
    "send_daily_report": (SendDailyReportArgs, send_daily_report),
}


def execute_tool_call(tool_name: str, raw_arguments: str) -> str:
    """Parse, validate, and execute a model-requested tool call."""
    if tool_name not in TOOL_REGISTRY:
        return f"Unknown tool requested: {tool_name}"

    args_model, tool_function = TOOL_REGISTRY[tool_name]

    try:
        parsed_arguments = json.loads(raw_arguments or "{}")
    except json.JSONDecodeError as exc:
        return f"Invalid JSON arguments for {tool_name}: {exc}"

    try:
        validated_args = args_model(**parsed_arguments)
    except ValidationError as exc:
        return f"Invalid arguments for {tool_name}: {exc}"

    try:
        return tool_function(**validated_args.model_dump())
    except Exception as exc:  # Defensive boundary so one tool failure does not crash the loop.
        return f"Tool {tool_name} failed unexpectedly: {type(exc).__name__}: {exc}"


def run_agent(user_input: str) -> str:
    """
    Run the standard OpenAI function-calling orchestration loop.

    The loop:
      1. Sends system + user messages to the model.
      2. Executes any requested local tools.
      3. Appends tool outputs with role='tool'.
      4. Repeats until the model returns a final natural language response.
    """
    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
    if not deepseek_api_key:
        raise RuntimeError("Set DEEPSEEK_API_KEY before running the agent.")

    client = OpenAI(api_key=deepseek_api_key, base_url=DEEPSEEK_BASE_URL)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input},
    ]

    max_turns = 8

    for _ in range(max_turns):
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )

        assistant_message = response.choices[0].message
        messages.append(assistant_message.model_dump(exclude_none=True))

        if not assistant_message.tool_calls:
            return assistant_message.content or ""

        for tool_call in assistant_message.tool_calls:
            tool_name = tool_call.function.name
            tool_output = execute_tool_call(tool_name, tool_call.function.arguments)

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    "content": tool_output,
                }
            )

    return "Agent stopped because it reached the maximum number of tool-calling turns."


if __name__ == "__main__":
    print("Geek Morning Report Agent")
    print("Example request:")
    print(
        "Send my geek morning report with the top 5 Hacker News stories "
        "to me@example.com"
    )
    print("Type 'exit' or 'quit' to stop.")
    print()

    while True:
        user_request = input("What should the agent do? ").strip()

        if not user_request:
            continue

        if user_request.lower() in {"exit", "quit"}:
            print("Goodbye.")
            break

        try:
            final_response = run_agent(user_request)
        except Exception as exc:
            print(f"\nAgent error: {type(exc).__name__}: {exc}\n")
            continue

        print("\nAgent response:")
        print(final_response)
        print()
