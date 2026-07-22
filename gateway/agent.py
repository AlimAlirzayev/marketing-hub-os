"""Autonomous browser agent — Claude-first (subscription), Gemini fallback.

Two reasoning engines drive the SAME headless browser (gateway.tools.browser):

  * _run_browser_claude — the operator's Claude subscription (gateway.claude_bridge)
    reasons over a plain-TEXT ReAct transcript: each turn Claude emits ONE JSON
    action, we execute it against the real browser, feed the observation back, and
    repeat until it emits {"action":"finish"}. claude_bridge is stdlib-only and
    stateless, so this needs no API key and never touches the Playwright thread
    (claude -p runs in its own subprocess).
  * _run_browser_gemini — the original manual Gemini function-calling loop, kept as
    the resilience fallback for when every Claude rung is capped.

Public entry run_browser_agent() tries Claude first (the 2026-07-19 directive: the
subscription is the brain, not a billed API) and falls to Gemini on any failure, so
the executor's browser lane is unchanged.

Irreversible actions are refused inside the browser tools (buy/pay/submit/delete,
and password fields), so an unattended run navigates, searches and reads freely but
cannot transact or enter credentials.
"""

from __future__ import annotations

import json
import os
import re
import time

from ._bootstrap import load_env
from . import llm
from .tools.browser import BrowserSession

load_env()

_BROWSER_SYSTEM = (
    "You are Xalq Insurance Digital OS, an autonomous web agent controlling a headless browser "
    "through tools (open_page, read_page, find_links, click_link, type_text, "
    "submit_search, scroll). Work step by step: open the relevant page(s), read "
    "them, follow links, type into search boxes and scroll when needed, and gather "
    "exactly what the task requires. NEVER ask the user questions -- make reasonable "
    "assumptions and proceed. Keep navigation focused. When you have enough, STOP "
    "and write the final deliverable in clean Markdown. If an action was blocked as "
    "irreversible, list it under a 'Needs your approval' heading instead of doing "
    "it. Security is the highest law: do not access local/private network "
    "resources, expose credentials, log in, make payments, submit forms, or perform "
    "destructive changes."
)

_MAX_STEPS = 14
_PACING = 1.5  # seconds between model calls; gentle on free-tier RPM


# --- shared browser tool dispatch (both engines use these names) --------------
def _dispatch(br: BrowserSession) -> dict:
    return {
        "open_page": lambda a: br.open(a.get("url", "")),
        "read_page": lambda a: br.read(),
        "find_links": lambda a: br.links(),
        "click_link": lambda a: br.click(a.get("text", "")),
        "type_text": lambda a: br.type_text(a.get("text", ""), a.get("into", "")),
        "submit_search": lambda a: br.submit_search(),
        "scroll": lambda a: br.scroll(a.get("direction", "down")),
    }


# =====================================================================
# Claude-driven ReAct loop (subscription brain)
# =====================================================================
_CLAUDE_SYSTEM = (
    "You are the PLANNING module of an autonomous browser agent. YOU HAVE NO TOOLS "
    "and you CANNOT browse, fetch, open URLs, or run anything yourself. Do NOT use "
    "WebFetch or any tool — you have none. A SEPARATE executor performs your actions "
    "against a real headless browser and returns the observation. Your ONLY job, "
    "each turn, is to decide the single next browser action and output it as JSON.\n\n"
    + _BROWSER_SYSTEM +
    "\n\nOUTPUT PROTOCOL — strict. On EVERY turn reply with ONE JSON object and "
    "NOTHING else (no prose, no code fence, no tool call):\n"
    '  {"thought": "<one short sentence>", "action": "<name>", "args": {<...>}}\n'
    "Valid actions: open_page{url}, read_page{}, find_links{}, click_link{text}, "
    "type_text{text, into?}, submit_search{}, scroll{direction}, and when you have "
    'gathered enough: {"action":"finish","answer":"<the full Markdown deliverable>"}.\n'
    "Always read_page after opening or searching before you conclude. Do not repeat "
    "the same failing action twice — adapt."
)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_action(text: str) -> dict | None:
    """Extract the JSON action from a model reply, tolerant of stray prose / fences.
    Returns a dict with at least 'action', or None if nothing parseable is found."""
    if not text:
        return None
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw[raw.find("{"):] if "{" in raw else raw
    for candidate in (raw, (_JSON_RE.search(raw).group(0) if _JSON_RE.search(raw) else "")):
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict) and obj.get("action"):
                return obj
        except Exception:
            continue
    return None


def _run_browser_claude(task: str, max_steps: int = _MAX_STEPS) -> str:
    """Drive the browser with the Claude subscription over a text ReAct transcript.
    Raises on any bridge failure so run_browser_agent() can fall back to Gemini."""
    from . import claude_bridge
    if not claude_bridge.is_available():
        raise RuntimeError("claude bridge not available")

    # Browser reasoning wants speed over depth (many short steps) -> a fast Claude
    # ladder for the duration of this loop; restored afterwards so the rest of the
    # process keeps its default (top-model-first) ladder.
    prev_ladder = os.environ.get("CLAUDE_CHAT_LADDER")
    os.environ["CLAUDE_CHAT_LADDER"] = os.getenv(
        "BROWSER_CLAUDE_LADDER", "claude-haiku-4-5-20251001,claude-sonnet-5,claude-fable-5")
    _preamble = (
        "You are the planner; you cannot act yourself. Decide the NEXT browser "
        "action for the executor to run. Output ONLY the JSON action.\n\n"
        f"OPERATOR TASK: {task}\n\nTRANSCRIPT SO FAR:"
    )
    transcript: list[str] = []
    try:
        with BrowserSession() as br:
            dispatch = _dispatch(br)
            for _ in range(max_steps):
                body = "\n".join(transcript) if transcript else "(nothing yet — start here)"
                prompt = (_preamble + "\n" + body +
                          "\n\nNext action as ONE JSON object (JSON only, no tools):")
                reply, _model = claude_bridge.complete(
                    prompt, system=_CLAUDE_SYSTEM,
                    timeout=int(os.getenv("BROWSER_CLAUDE_TIMEOUT", "150")))
                act = _parse_action(reply)
                if act is None:
                    # First turn with no JSON = the model rejected the planner
                    # role (e.g. Claude Code refusing the injected persona), not a
                    # gathered deliverable -> fall back to the Gemini planner.
                    if not transcript:
                        raise RuntimeError("browser planner returned no action on first turn")
                    return reply.strip()  # later turn: prose after gathering = final answer
                name = act.get("action")
                if name == "finish":
                    return (act.get("answer") or "").strip() or "\n".join(transcript)
                fn = dispatch.get(name)
                if fn is None:
                    obs = f"ERROR: unknown action {name!r}. Valid: {list(dispatch)} or finish."
                else:
                    try:
                        obs = fn(act.get("args", {}) or {})
                    except Exception as exc:  # noqa: BLE001
                        obs = f"ERROR in {name}: {exc}"
                transcript.append(f"ACTION: {json.dumps(act.get('args', {}), ensure_ascii=False)} "
                                  f"via {name}")
                transcript.append(f"OBSERVATION: {obs}")
                time.sleep(_PACING)
            # Step budget hit: ask for the final write-up from what was gathered.
            prompt = (_preamble + "\n" + "\n".join(transcript) +
                      "\n\nStep budget reached. Reply with a finish action whose "
                      "answer is the final Markdown deliverable from what you gathered.")
            reply, _ = claude_bridge.complete(prompt, system=_CLAUDE_SYSTEM, timeout=150)
            act = _parse_action(reply)
            if act and act.get("action") == "finish":
                return (act.get("answer") or "").strip()
            return reply.strip()
    finally:
        if prev_ladder is None:
            os.environ.pop("CLAUDE_CHAT_LADDER", None)
        else:
            os.environ["CLAUDE_CHAT_LADDER"] = prev_ladder


# =====================================================================
# Gemini function-calling loop (resilience fallback)
# =====================================================================
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
        types.FunctionDeclaration(
            name="type_text",
            description="Type text into a search/input field. 'into' optionally names "
                        "the field (placeholder/label). Password fields are refused.",
            parameters=S(type=T.OBJECT, required=["text"], properties={
                "text": S(type=T.STRING, description="Text to type"),
                "into": S(type=T.STRING, description="Optional field hint"),
            }),
        ),
        types.FunctionDeclaration(
            name="submit_search",
            description="Press Enter to run a search from the current input (search/filter only).",
            parameters=S(type=T.OBJECT, properties={}),
        ),
        types.FunctionDeclaration(
            name="scroll",
            description="Scroll the page (direction: down|up) to reveal more content.",
            parameters=S(type=T.OBJECT, properties={
                "direction": S(type=T.STRING, description="down or up"),
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


def _run_browser_gemini(task: str, model: str, max_steps: int = _MAX_STEPS) -> str:
    """Drive a real browser to complete ``task`` with Gemini; return final Markdown."""
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
        dispatch = _dispatch(br)
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


# =====================================================================
# Public entry: Claude-first, Gemini fallback
# =====================================================================
def run_browser_agent(task: str, model: str, max_steps: int = _MAX_STEPS,
                      prefer: str = "claude") -> str:
    """Drive a real browser to complete ``task``; return the final Markdown.

    The subscription (Claude) reasons by default; on any Claude failure/cap it
    falls back to the Gemini function-calling loop so a browser job never stalls.
    Set prefer='gemini' (or BROWSER_BRAIN=gemini) to force the free path.
    """
    want = (os.getenv("BROWSER_BRAIN") or prefer or "claude").strip().lower()
    if want != "gemini":
        try:
            return _run_browser_claude(task, max_steps=max_steps)
        except Exception:
            pass  # capped / not authed / parse trouble -> Gemini fallback below
    return _run_browser_gemini(task, model, max_steps=max_steps)
