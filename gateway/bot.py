"""Telegram front-end: receive tasks (text OR voice) from the OWNER only,
enqueue them, reply instantly. The worker executes jobs and pushes results
back to the chat.

SECURITY (inbound hard shell):
  * Only the owner chat may issue commands. Fail-closed: if no owner id is
    configured (TELEGRAM_OWNER_CHAT_ID, or legacy GATEWAY_OWNER_ID), every
    message is rejected — the reply tells the owner how to lock the bot to
    themselves, but nothing is ever executed for an unknown chat.

Voice: a voice note is transcribed by Gemini (best for Azerbaijani), with the
local whisper-stt server (WHISPER_URL) as a fallback, before being queued.

Long-polling = outbound HTTPS only, so no port/webhook/public IP is needed.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import requests

from ._bootstrap import load_env
from . import engine_sync, keyvault, mic, queue, sense, telegram, voice

load_env()

_ROOT = Path(__file__).resolve().parent.parent
_SYNC = _ROOT / "scripts" / "sync_engine.py"

_WHISPER_URL = os.getenv(
    "WHISPER_URL", "http://127.0.0.1:8787/v1/audio/transcriptions"
)
_STT_GEMINI_MODEL = os.getenv("STT_GEMINI_MODEL", "gemini-2.5-flash")
_STT_PROMPT = (
    "Transcribe this voice message verbatim. It is most likely in Azerbaijani "
    "(may also contain Russian, Turkish or English words). Return ONLY the exact "
    "transcript text — no quotes, no translation, no commentary."
)

_HELP = (
    "Ramin-OS background agent.\n"
    "Send me any task (text or voice) and I'll run it in the background, "
    "then send the result.\n\n"
    "Commands:\n"
    "  /status     - did everything ship? git + queue + costs (owner only)\n"
    "  /jobs       - list recent jobs\n"
    "  /approve N  - approve a parked risky job (owner only)\n"
    "  /reject N   - reject a parked risky job (owner only)\n"
    "  /danis TEXT - speak TEXT in the owner's own cloned voice (owner only)\n"
    "  /update     - pull the latest engine from GitHub (owner only)\n"
    "  /setkey     - blocked; secrets are local-terminal only\n"
    "  /setfile    - blocked; secret files never cross Telegram\n"
    "  /keys       - masked status of critical keys (owner only)\n"
    "  /help       - this message"
)


def _owner_source() -> tuple[str | None, str | None]:
    """(owner_id, which_env_var). TELEGRAM_OWNER_CHAT_ID is the canonical name
    across both friend-systems; GATEWAY_OWNER_ID is honored as the legacy fleet
    name so an already-locked box never silently unlocks. Returning the source
    lets a rejection name the culprit — e.g. a fleet GATEWAY_OWNER_ID that bled
    into the corporate bot and locked out the real owner."""
    for var in ("TELEGRAM_OWNER_CHAT_ID", "GATEWAY_OWNER_ID"):
        v = (os.getenv(var) or "").strip()
        if v:
            return v, var
    return None, None


def _owner_id() -> str | None:
    """The single chat allowed to talk to this bot, or None if unconfigured."""
    return _owner_source()[0]


def _is_owner(chat_id) -> bool:
    """Fail-closed owner check: no configured owner => reject everyone."""
    owner = _owner_id()
    if not owner:
        return False
    return str(chat_id) == owner


def _run_sync() -> str:
    """Run the shared sync brain and return its one-line summary for the reply."""
    try:
        proc = subprocess.run(
            [sys.executable, str(_SYNC)],
            cwd=str(_ROOT),
            capture_output=True,
            text=True,
            timeout=60, encoding="utf-8", errors="replace")
        out = (proc.stdout or proc.stderr or "").strip()
        return out or "sync finished (no changes)."
    except subprocess.TimeoutExpired:
        return "sync timed out reaching GitHub — try again shortly."
    except Exception as exc:  # never crash the bot on an ops command
        return f"sync could not run: {exc.__class__.__name__}"


# --- voice -> text (Gemini first, local whisper fallback) -------------------

def _transcribe_gemini(audio: bytes) -> str | None:
    """Transcribe via Gemini — far better than local whisper for Azerbaijani."""
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        return None
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key)
    resp = client.models.generate_content(
        model=_STT_GEMINI_MODEL,
        contents=[
            _STT_PROMPT,
            types.Part.from_bytes(data=audio, mime_type="audio/ogg"),
        ],
    )
    return (resp.text or "").strip() or None


def _transcribe_whisper(audio: bytes) -> str | None:
    """Fallback: local whisper-stt server."""
    resp = requests.post(
        _WHISPER_URL,
        files={"file": ("voice.ogg", audio, "audio/ogg")},
        timeout=120,
    )
    resp.raise_for_status()
    return (resp.json().get("text") or "").strip() or None


def _transcribe(file_id: str) -> str | None:
    """Download a Telegram voice file and transcribe it (Gemini -> whisper)."""
    try:
        audio = telegram.download_file_by_id(file_id)
    except Exception as exc:
        sense.emit("stt", f"voice download failed: {exc}")
        return None
    if not audio:
        return None
    # One cascade lives in gateway.voice now: ElevenLabs Scribe (best Azerbaijani)
    # -> Groq whisper-large-v3 -> Gemini. The legacy Gemini/whisper helpers below
    # are kept only as an explicit last-ditch fallback if the module import fails.
    text = voice.transcribe(audio)
    if text:
        return text
    try:
        return _transcribe_gemini(audio)
    except Exception as exc:
        sense.emit("stt", f"legacy gemini stt failed: {exc}")
        return None


def _block_telegram_secret(chat_id: int, msg: dict, command: str) -> None:
    """Fail closed when a secret is pasted or attached in Telegram.

    Deleting the carrier is only damage reduction: Telegram has already
    transported it. Nothing is downloaded, parsed, staged, written to .env or
    stored in the vault.
    """
    try:
        telegram.delete_message(chat_id, msg["message_id"])
    except Exception:
        pass
    sense.emit("security", f"blocked Telegram secret courier ({command})")
    telegram.send_message(
        chat_id,
        "🔒 Telegram ilə açar və auth faylı qəbulu tam bağlıdır. "
        "Məzmun endirilmədi və saxlanmadı; daşıyıcı mesajı silməyə çalışdım.\n\n"
        "Açar üçün bu maşının terminalında işlət:\n"
        "  SECURE_KEY.bat AÇAR_ADI\n"
        "və ya:\n"
        "  python scripts/secure_key.py AÇAR_ADI",
    )


def _render_house_voice(chat_id: int, say: str) -> None:
    """Clone the house voice (audio-studio default ref) for `say` and deliver it
    as a Telegram voice note. Honest on failure: the free Space has a daily
    ZeroGPU quota and can be down — the error is reported, never swallowed."""
    import json as _json
    try:
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(_ROOT / "audio-studio" / "audio_studio.py"),
             "clone", say, "--lang", "az", "--json"],
            capture_output=True, text=True, encoding="utf-8", timeout=420, cwd=str(_ROOT),
        )
        result = {}
        for line in (proc.stdout or "").strip().splitlines()[::-1]:
            if line.startswith("{"):
                try:
                    result = _json.loads(line)
                except Exception:
                    pass
                break
        path = result.get("path")
        if not path or not Path(path).is_file():
            detail = (proc.stderr or proc.stdout or "").strip()[-300:]
            sense.emit("tts", "house-voice clone failed", {"detail": detail})
            telegram.send_message(
                chat_id,
                "⚠️ Səs klonu alınmadı (pulsuz Space növbəsi/limiti ola bilər).\n"
                f"Texniki səbəb: {detail or 'naməlum'}",
            )
            return
        ogg = voice.file_to_ogg(path)
        if ogg:
            telegram.send_voice(chat_id, ogg, caption="🎙 Sənin səsinlə")
        else:
            # ffmpeg missing/failed — still deliver the audio as a document.
            telegram.send_document(chat_id, path, caption="🎙 Sənin səsinlə (wav)")
        sense.emit("tts", "house-voice note delivered", {"chars": len(say)})
    except Exception as exc:  # noqa: BLE001 — a voice failure must never kill the bot
        sense.emit("tts", f"house-voice error: {exc}")
        try:
            telegram.send_message(chat_id, f"⚠️ Səs hazırlanarkən xəta: {exc}")
        except Exception:
            pass


def _extract_task(msg: dict) -> tuple[str | None, bool]:
    """Return (task_text, was_voice). Text wins; else transcribe voice/audio."""
    text = (msg.get("text") or "").strip()
    if text:
        return text, False
    media = msg.get("voice") or msg.get("audio") or msg.get("video_note")
    if media and media.get("file_id"):
        return _transcribe(media["file_id"]), True
    return None, False


def _handle_message(msg: dict, *, ingress_key: str | None = None) -> None:
    chat_id = msg["chat"]["id"]

    # ---- inbound hard shell: owner-only, fail-closed --------------------
    # The rejection is SELF-DOCUMENTING on purpose: a bare "Unauthorized" is what
    # made the owner-id mix-up so hard to debug. Now every rejection tells you
    # your chat id, the configured owner, WHICH env var supplied it, and the
    # exact one-line fix — so a wrong owner is diagnosable from the phone.
    if not _is_owner(chat_id):
        sense.emit("security", f"rejected non-owner chat_id={chat_id}")
        owner, src = _owner_source()
        if owner:
            reply = (
                f"⛔ Unauthorized — İcazə yoxdur.\n"
                f"Sizin chat id: {chat_id}\n"
                f"Bu botun təyin olunmuş sahibi: {owner} (mənbə: {src})\n"
            )
            if src == "GATEWAY_OWNER_ID":
                reply += ("Diqqət: sahib köhnə GATEWAY_OWNER_ID-dən gəlir. "
                          f"TELEGRAM_OWNER_CHAT_ID={chat_id} onu əvəz edəcək.\n")
            reply += (
                f"Siz sahibsinizsə: bu maşının .env faylında "
                f"TELEGRAM_OWNER_CHAT_ID={chat_id} yazıb prosesi restart edin."
            )
        else:
            # Locked because NO owner is configured yet. Tell the (probable)
            # owner how to claim the bot — but execute nothing until then.
            reply = (
                f"⛔ Bot kilidlidir — sahib təyin olunmayıb.\n"
                f"Sahibsinizsə: .env faylına TELEGRAM_OWNER_CHAT_ID={chat_id} "
                "yazıb prosesi restart edin."
            )
        try:
            telegram.send_message(chat_id, reply)
        except Exception:
            pass
        return

    # Secret-bearing files never cross Telegram. Ordinary document understanding
    # is a separate future capability and must not silently become a credential
    # courier.
    doc = msg.get("document")
    if doc and doc.get("file_id"):
        caption = (msg.get("caption") or "").strip()
        if caption.split(maxsplit=1)[0].casefold() == "/setfile" if caption else False:
            _block_telegram_secret(chat_id, msg, "/setfile")
        else:
            telegram.send_message(
                chat_id,
                "📎 Sənəd qəbulu hələ agent tapşırığına qoşulmayıb. "
                "Secret/auth faylıdırsa Telegram-a göndərmə; lokal terminal yolundan istifadə et.",
            )
        return

    task, was_voice = _extract_task(msg)

    if was_voice:
        if not task:
            telegram.send_message(chat_id, "\U0001f3a4 Səsi tanıya bilmədim, bir də cəhd et.")
            return
        telegram.send_message(chat_id, f"\U0001f3a4 Eşitdim: “{task[:300]}”")

    if not task:
        telegram.send_message(chat_id, "Mətn və ya səs tapşırığı göndər.")
        return

    text = task  # commands below operate on the (possibly transcribed) text

    if text in ("/start", "/help"):
        telegram.send_message(chat_id, _HELP + f"\n\nYour chat id: {chat_id}")
        return

    if text.split()[0] in ("/update", "/pull", "/sync"):
        if not _is_owner(chat_id):
            telegram.send_message(chat_id, "Not authorized for ops commands.")
            return
        telegram.send_message(chat_id, "🔄 Pulling the latest engine from GitHub...")
        summary = _run_sync()
        telegram.send_message(chat_id, f"✅ {summary}")
        return

    if text == "/jobs":
        jobs = queue.list_jobs(limit=10)
        if not jobs:
            telegram.send_message(chat_id, "No jobs yet.")
        else:
            mark = {"awaiting_approval": "⏸", "done": "✅", "error": "⚠️", "rejected": "🚫"}
            lines = [f"{mark.get(j.status, '·')} #{j.id} [{j.status}] {j.task[:50]}" for j in jobs]
            telegram.send_message(chat_id, "\n".join(lines))
        return

    # /danis: speak the given text in the OWNER's own cloned voice (the house
    # reference in audio-studio/voices/) and send it back as a voice note.
    # Runs in a background thread because the free clone Space takes ~1-2 min —
    # the polling loop must keep serving other messages meanwhile.
    if text.split()[0] in ("/danis", "/speak"):
        if not _is_owner(chat_id):
            telegram.send_message(chat_id, "Not authorized for ops commands.")
            return
        say = text.split(None, 1)[1].strip() if len(text.split(None, 1)) > 1 else ""
        if not say:
            telegram.send_message(chat_id, "İstifadə: /danis <söyləniləcək mətn>")
            return
        telegram.send_message(
            chat_id, "🎙 Sənin səsinlə hazırlayıram (pulsuz klon ~1-2 dəq çəkir)...")
        import threading
        threading.Thread(target=_render_house_voice, args=(chat_id, say), daemon=True).start()
        return

    # A secret has already crossed Telegram before deletion can run, therefore
    # this path is permanently fail-closed (no break-glass environment flag).
    if text.split()[0] == "/setkey":
        _block_telegram_secret(chat_id, msg, "/setkey")
        return

    # The "getdim, amma arxayınam" command: one message from the phone answers
    # "did my work actually ship, and is anything stuck?"
    if text == "/status":
        if not _is_owner(chat_id):
            telegram.send_message(chat_id, "Not authorized for ops commands.")
            return
        s = sense.snapshot()
        g, q, llm = s.get("git", {}), s.get("queue", {}), s.get("llm", {})
        ahead, behind = g.get("ahead"), g.get("behind")
        ship = []
        ship.append("⚠️ commit edilməmiş dəyişiklik VAR (yarımçıq iş bu maşındadır)"
                    if g.get("dirty") else "✅ hər şey commit olunub")
        if ahead:
            ship.append(f"📮 push gözləyən {ahead} commit (növbəti sync göndərəcək)")
        elif ahead == 0:
            ship.append("✅ hamısı poçtdadır (push olunub)")
        if behind:
            ship.append(f"⬇️ qarşı tərəfdən {behind} yenilik çəkilməyi gözləyir")
        lines = [
            "📊 Status:",
            f"git {g.get('head', '?')} — " + " · ".join(ship),
            f"növbə: {q.get('queued', 0)} gözləyir · {q.get('running', 0)} işləyir · "
            f"{q.get('awaiting_approval', 0)} təsdiq gözləyir · {q.get('error', 0)} xəta",
            f"LLM bu gün: {llm.get('calls_today', 0)} çağırış, ${llm.get('cost_usd_today', 0)}",
            "seyf: " + (f"açıq ({len(keyvault.names())} açar səyahətdə)"
                        if keyvault.enabled() else "bağlı"),
        ]
        parked = queue.list_jobs(status="awaiting_approval", limit=5)
        for j in parked:
            lines.append(f"⏸ #{j.id} təsdiq gözləyir: {j.task[:60]} → /approve {j.id}")
        telegram.send_message(chat_id, "\n".join(lines))
        return

    if text == "/keys":
        if not _is_owner(chat_id):
            telegram.send_message(chat_id, "Not authorized for ops commands.")
            return
        rows = sense.env_status()
        lines = [("🟢" if v.startswith("SET") else "🔴") + f" {k}: {v}" for k, v in rows.items()]
        if keyvault.enabled():
            synced = keyvault.names()
            lines.append(f"🧰 Seyf: açıq — səyahət edən açarlar: {', '.join(synced) or 'hələ yoxdur'}")
        else:
            lines.append("🧰 Seyf: bağlı (/setkey KEY_VAULT_SECRET <parol> ilə aç)")
        telegram.send_message(chat_id, "Bu maşının açar vəziyyəti (maskalı):\n" + "\n".join(lines))
        return

    # Plain-language approval. The owner should not have to type "/approve 3" — he
    # answers the way a person answers. This IS the checkpoint, so it stays strict:
    # owner only, and exactly one job parked. Zero parked -> it is just conversation
    # and falls through; more than one -> we ask which, rather than guess at a live
    # ad account. A match is either the WHOLE message being a yes/no word, or a SHORT
    # (<=3-word) reply that STARTS with one — so natural "hə göndər" / "yox, lazım
    # deyil" work, while a longer sentence that merely contains "ok"/"hə" mid-thought
    # falls through to conversation instead of firing an outward action. Any misread
    # is immediately visible: the bot echoes exactly what it approved/cancelled.
    _YES = {"hə", "he", "bəli", "beli", "təsdiq", "tesdiq", "təsdiqlə", "təsdiqləyirəm",
            "təsdiq edirəm", "razıyam", "raziyam", "ok", "okey", "oldu", "yes", "davam",
            "göndər", "gonder"}
    _NO = {"yox", "xeyr", "ləğv", "legv", "imtina", "etmə", "etme", "no", "dayan",
           "saxla", "lazım deyil", "lazim deyil"}
    _plain = text.strip().lower().rstrip(".!?")
    _tokens = _plain.split()
    # Strip punctuation glued to the first word so "yox," / "hə," still match.
    _first = _tokens[0].strip(",.!?;:—-") if _tokens else ""
    _short = len(_tokens) <= 3
    _said_yes = _plain in _YES or (_short and _first in _YES)
    _said_no = _plain in _NO or (_short and _first in _NO)
    if _is_owner(chat_id) and (_said_yes or _said_no):
        parked = queue.list_jobs(status="awaiting_approval", limit=5)
        if len(parked) == 1:
            j = parked[0]
            if _said_yes:
                queue.approve(j.id)
                telegram.send_message(chat_id, f"✅ Oldu — “{j.task[:60]}” icra edirəm.")
            else:
                queue.reject(j.id)
                telegram.send_message(chat_id, f"🚫 Ləğv etdim — “{j.task[:60]}” toxunmadım.")
            return
        if len(parked) > 1:
            lines = ["Hansını nəzərdə tutursan?"]
            lines += [f"#{j.id} — {j.task[:60]}" for j in parked]
            lines.append("\nNömrə ilə de: /approve <nömrə>")
            telegram.send_message(chat_id, "\n".join(lines))
            return

    # The human checkpoint's other half: the operator decides a parked job's fate.
    parts = text.split()
    if parts[0] in ("/approve", "/reject") and len(parts) >= 2 and parts[1].isdigit():
        if not _is_owner(chat_id):
            telegram.send_message(chat_id, "Not authorized for ops commands.")
            return
        job_id = int(parts[1])
        if parts[0] == "/approve":
            ok = queue.approve(job_id)
            telegram.send_message(
                chat_id,
                f"✅ Job #{job_id} təsdiqləndi — icraya qayıtdı." if ok
                else f"Job #{job_id} təsdiq gözləmir (artıq həll olunub və ya yoxdur).",
            )
        else:
            ok = queue.reject(job_id)
            telegram.send_message(
                chat_id,
                f"🚫 Job #{job_id} imtina edildi — icra olunmayacaq." if ok
                else f"Job #{job_id} təsdiq gözləmir (artıq həll olunub və ya yoxdur).",
            )
        return

    # Pull-first: before queuing real work, equalize with the other twin (debounced,
    # so a burst of messages doesn't hammer git). A message is the entry point — its
    # first job is to check GitHub, then act.
    try:
        engine_sync.pull_if_stale()
    except Exception as exc:  # freshness is best-effort, never block a task on it
        print(f"[bot] pre-task sync skipped: {exc}")

    if ingress_key:
        job_id, created = mic.speak_once(
            text,
            source="telegram",
            chat_id=str(chat_id),
            ingress_key=ingress_key,
        )
        if not created:
            return
    else:
        job_id = mic.speak(text, source="telegram", chat_id=str(chat_id))
    if was_voice:
        # remember this turn came in by voice, so the worker answers by voice too
        voice.mark_voice_job(job_id)
    # Conversational turns get a silent "typing…" indicator — the reply IS the
    # acknowledgment (the owner hated the "Queued as job #N" service message).
    # Real work (tools/browser/research/fan-out) can run for minutes, so it
    # keeps a short receipt — but phrased like a teammate saying "on it", NOT a
    # ticket number (the owner wants Telegram to read like the Claude chat).
    from .executor import _choose_mode, _wants_fanout
    if _choose_mode(text) == "plain" and not _wants_fanout(text):
        try:
            telegram.send_chat_action(chat_id, "typing")
        except Exception:
            pass
    else:
        telegram.send_message(
            chat_id, "Aldım — üzərində işləyirəm, bir az çəkə bilər, hazır olanda yazacam."
        )


def _announce_online() -> None:
    """Tell the owner WHICH machine's bot just came alive — removes the 'is
    anything even listening?' mystery when two friend-systems exist."""
    owner = _owner_id()
    if not owner:
        return
    import platform
    name = platform.node() or "?"
    try:
        from brand import BRAND
        name = f"{BRAND.name} / {name}"
    except Exception:
        pass
    try:
        telegram.send_message(owner, f"🤖 Bot onlayn — {name}. Komandalar: /help")
    except Exception as exc:
        print(f"[bot] online announce failed: {exc}")


def main() -> None:
    if not telegram.is_configured():
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN not set in .env. Create a bot via @BotFather first."
        )
    if not _owner_id():
        print("[bot] WARNING: no owner configured (TELEGRAM_OWNER_CHAT_ID) -> "
              "rejecting ALL messages (fail-closed).")
    queue.init_db()
    print("[bot] started. Long-polling for messages... (Ctrl+C to stop)")
    _announce_online()
    offset = None
    conflicts = 0
    while True:
        try:
            updates = telegram.get_updates(offset=offset)
            conflicts = 0
            for upd in updates:
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("edited_message")
                if msg:
                    _handle_message(msg)
        except KeyboardInterrupt:
            print("\n[bot] stopped.")
            break
        except telegram.ConflictError:
            # Two machines are polling ONE bot token. Hammering makes it worse:
            # back off long, warn loudly once — the fix is one bot per machine.
            conflicts += 1
            print("[bot] 409 CONFLICT: another machine is polling this bot token. "
                  "Each system needs its OWN @BotFather bot. Backing off 30s...")
            if conflicts == 3:
                owner = _owner_id()
                if owner:
                    try:
                        telegram.send_message(
                            owner,
                            "⚠️ Bu bot tokenini EYNİ anda iki sistem dinləyir (409 Conflict) "
                            "— ona görə bot 'ölü' görünür. Həll: hər sistemin ÖZ botu "
                            "olmalıdır (@BotFather-dən ikinci bot yarat, o biri maşının "
                            ".env-inə öz TELEGRAM_BOT_TOKEN-ini yaz).",
                        )
                    except Exception:
                        pass
            time.sleep(30)
        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError):
            # A long-poll that times out or drops is NORMAL churn, not an
            # incident — it was flooding journalctl as "[bot] error". Just
            # reconnect quietly.
            time.sleep(1)
        except Exception as exc:  # transient network errors -> back off, retry
            print(f"[bot] error: {exc}")
            time.sleep(3)


if __name__ == "__main__":
    main()
