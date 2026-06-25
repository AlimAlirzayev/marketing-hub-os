"""Autonomous browser agent: a manual Gemini function-calling loop.

We deliberately do NOT use the SDK's automatic function calling (AFC). AFC runs
tool functions on a worker thread, but the Playwright sync API is bound to the
thread that created it ("greenlet: Cannot switch to a different thread"). So we
run the observe -> act loop ourselves and call the browser in the MAIN thread.

This is what replaces screenshot-by-screenshot work: the model decides each
action, we execute it against a real headless browser, feed the result back,
and repeat until it produces the final deliverable -- no human in the loop.

Irreversible actions are refused inside the browser tool (see tools/browser.py),
so an unattended run can navigate and read freely but cannot buy/submit/delete.
"""

from __future__ import annotations

import os
import time

from ._bootstrap import load_env
from . import llm
from .tools.browser import BrowserSession

load_env()

_BROWSER_SYSTEM = (
    "You are Xalq Insurance Digital OS, an autonomous web agent controlling a headless browser "
    "through tools (open_page, read_page, find_links, click_link). Work step by "
    "step: open the relevant page(s), read them, follow links when needed, and "
    "gather exactly what the task requires. NEVER ask the user questions -- make "
    "reasonable assumptions and proceed. Keep navigation focused. When you have "
    "enough, STOP calling tools and write the final deliverable in clean "
    "Markdown. If an action was blocked as irreversible, list it under a 'Needs "
    "your approval' heading instead of doing it. Security is the highest law: do "
    "not try to access local/private network resources, expose credentials, make "
    "payments, submit forms, or perform destructive changes."
)

_MAX_STEPS = 14
_PACING = 1.5  # seconds between model calls; gentle on free-tier RPM


def _tools(types):
    """Manual function declarations for the browser tools."""
    S, T = types.Schema, types.Type
    return types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name="open_page",
            description="Navigate the browser to a URL and return the page title.",
            parameters=S(type=T.OBJECT, required=["url"], properties={
                "url": S(type=T.STRING, description="Absolute URL to open"),
            }),
        ),
        types.FunctionDeclaration(
            name="read_page",
            description="Return the visible text content of the current page.",
            parameters=S(type=T.OBJECT, properties={}),
        ),
        types.FunctionDeclaration(
            name="find_links",
            description="List clickable links (visible text -> URL) on the current page.",
            parameters=S(type=T.OBJECT, properties={}),
        ),
        types.FunctionDeclaration(
            name="click_link",
            description="Click a link/button by its visible text to navigate. "
                        "Irreversible actions (buy/pay/submit/delete) are blocked.",
            parameters=S(type=T.OBJECT, required=["text"], properties={
                "text": S(type=T.STRING, description="Visible text of the link/button"),
            }),
        ),
    ])


def _candidate_models(model: str) -> list[str]:
    out: list[str] = []
    for m in (model, "gemini-2.5-flash", "gemini-flash-lite-latest", "gemini-3.5-flash"):
        if m and m not in out:
            out.append(m)
    return out


def _generate(client, model, contents, config):
    """One model call, retrying transient rate-limit / overload errors."""
    last: Exception | None = None
    for attempt in range(llm._MAX_RETRIES):
        try:
            return client.models.generate_content(model=model, contents=contents, config=config)
        except Exception as exc:
            if not llm._is_retryable(exc):
                raise
            last = exc
            time.sleep(min(llm._retry_delay(exc, 8 * (attempt + 1)), llm._MAX_BACKOFF))
    raise last


def run_browser_agent(task: str, model: str, max_steps: int = _MAX_STEPS) -> str:
    """Drive a real browser to complete ``task``; return the final Markdown."""
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY / GOOGLE_API_KEY not set")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key)
    config = types.GenerateContentConfig(
        system_instruction=_BROWSER_SYSTEM,
        tools=[_tools(types)],
        temperature=0.3,
        # AFC OFF: we execute tools ourselves, in the main thread.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    models = _candidate_models(model)
    midx = 0

    with BrowserSession() as br:
        dispatch = {
            "open_page": lambda a: br.open(a.get("url", "")),
            "read_page": lambda a: br.read(),
            "find_links": lambda a: br.links(),
            "click_link": lambda a: br.click(a.get("text", "")),
        }
        contents = [types.Content(role="user", parts=[types.Part(text=task)])]

        for _ in range(max_steps):
            try:
                resp = _generate(client, models[midx], contents, config)
            except Exception:
                if midx + 1 < len(models):  # this model is exhausted -> next
                    midx += 1
                    continue
                raise

            cand = resp.candidates[0]
            parts = cand.content.parts or []
            calls = [p.function_call for p in parts if getattr(p, "function_call", None)]

            if not calls:  # no tool call => final answer
                return (resp.text or "").strip()

            contents.append(cand.content)  # the model's tool request
            responses = []
            for fc in calls:
                args = dict(fc.args) if fc.args else {}
                try:
                    result = dispatch[fc.name](args)
                except Exception as exc:
                    result = f"ERROR in {fc.name}: {exc}"
                responses.append(types.Part.from_function_response(
                    name=fc.name, response={"result": result},
                ))
            contents.append(types.Content(role="user", parts=responses))
            time.sleep(_PACING)

        # Step budget hit: force a final write-up from what was gathered.
        contents.append(types.Content(role="user", parts=[types.Part(
            text="Step budget reached. Write the final deliverable now from what you gathered."
        )]))
        return (_generate(client, models[midx], contents, config).text or "").strip()
