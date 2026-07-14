"""Guard: no subprocess pipe may be decoded with the LOCALE default.

Why (2026-07-14 — the letter that killed the premium brain): every prompt, commit
subject and log line in this system is Azerbaijani. `subprocess.run(text=True)`
with no explicit encoding decodes with the locale default, which on the Windows
twin is cp1252 — an alphabet with no 'ı' (U+0131). So `claude -p` raised
UnicodeEncodeError on ordinary Azerbaijani, claude_bridge was marked "unavailable",
and the ENTIRE system silently fell back to the free Groq model. The premium brain
was never down; it was never reachable. Same trap sat in the git/sync/codex paths.

The bug is invisible: it degrades quality instead of failing loudly, and it never
reproduces on the Linux twin (UTF-8 locale). So it needs a structural test, not a
behavioural one — this walks the AST and fails on ANY reintroduction.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_DIRS = ("gateway", "scripts", "orchestrator")
_CALLS = {"subprocess.run", "subprocess.Popen", "subprocess.check_output"}


def _offenders() -> list[str]:
    bad: list[str] = []
    for d in _DIRS:
        for path in sorted((ROOT / d).glob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:  # not ours to police here
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if ast.unparse(node.func) not in _CALLS:
                    continue
                named = {k.arg for k in node.keywords if k.arg}
                # a **mapping (e.g. **_TEXT_IO) may carry encoding — accept it
                splatted = any(k.arg is None for k in node.keywords)
                text_mode = "text" in named or "universal_newlines" in named
                if text_mode and "encoding" not in named and not splatted:
                    bad.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")
    return bad


class SubprocessEncodingGuard(unittest.TestCase):
    def test_no_locale_decoded_pipes(self):
        bad = _offenders()
        self.assertEqual(
            bad, [],
            "subprocess call(s) decode with the locale default (cp1252 on Windows) "
            "and will crash on Azerbaijani text — pass encoding='utf-8', "
            "errors='replace':\n  " + "\n  ".join(bad),
        )


if __name__ == "__main__":
    unittest.main()
