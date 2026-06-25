"""Tools the autonomous executor can use to act on the real world.

Currently: a Playwright-backed browser (browser.py). The browser is exposed to
the LLM as plain Python functions so Gemini's automatic function calling can
drive a multi-step loop -- this is what replaces watching screenshots step by
step: the agent navigates and extracts on its own, then returns the result.
"""
