"""What a command does, in a few words, for its card in Ornis Code (« Lancer les tests », « Vérifier la syntaxe de
a.php »), as Claude Code shows it (18/11/2026).

The model writes it itself: a first line `# <what it does>` in its command (the Code prompt asks for it; Vibe's bash
tool has no field for it and drops any argument it does not know). Without one, it is read from the shared table
command-notes.json (the same file as the editor extension, ide/src/describe.js, which tests that they are equal).
Light on purpose: no Qt, imported by the app and by ornis_shell."""
import json
import re
from pathlib import Path

_RULES = None
SKIP = {"sudo", "env", "time", "nice", "nohup", "command", "exec", "builtin"}
NOT_COMMANDS = {"cd", "pushd", "popd", "export", "set", "source", ".", "true"}
MAX_ARG = 40
ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
COMMENT = re.compile(r"^\s*#(?!!)")


def _rules() -> list:
    global _RULES
    if _RULES is None:
        try:
            _RULES = json.loads((Path(__file__).with_name("command-notes.json")).read_text(encoding="utf-8")).get("rules") or []
        except (OSError, ValueError):
            _RULES = []
    return _RULES


def split_note(command: str) -> tuple[str, str]:
    """(the model's note from the leading `# …` lines, the command without them). `#!` is not a note."""
    lines = str(command or "").split("\n")
    notes = []
    while lines and COMMENT.match(lines[0]):
        notes.append(re.sub(r"^\s*#+\s*", "", lines.pop(0)).strip())
    while lines and not lines[0].strip():
        lines.pop(0)
    return " ".join(n for n in notes if n)[:160], "\n".join(lines)


def _words(segment: str) -> list[str]:
    out = []
    for m in re.finditer(r'"((?:\\.|[^"\\])*)"|\'([^\']*)\'|(\S+)', segment):
        out.append(next(g for g in m.groups() if g is not None))
    return out


def _program(word: str) -> str:
    if re.search(r"(^|/)vendor/bin/phpunit$", word or ""):
        return "vendor/bin/phpunit"
    base = str(word or "").replace("\\", "/").split("/")[-1].lower()
    base = re.sub(r"\.exe$", "", base)
    m = re.match(r"^(php|python|pip)(\d[\d.]*)$", base)
    return ("python3" if m.group(1) == "python" else m.group(1)) if m else base


def _short(value: str) -> str:
    text = str(value or "").strip()
    if re.match(r"(?i)^https?://", text):
        rest = re.sub(r"(?i)^https?://", "", text).split("?")[0].split("#")[0]
        host, _, path = rest.partition("/")
        text = host + ("/" + path if path else "")
    elif re.search(r"[\\/]", text) and not re.search(r"\s", text):
        text = [p for p in re.split(r"[\\/]", text.rstrip("\\/")) if p][-1:] or [text]
        text = text[0]
    return text if len(text) <= MAX_ARG else text[:MAX_ARG - 1] + "…"


def _segment(words: list[str], lang: str) -> str:
    at = 0
    while at < len(words) and (ASSIGN.match(words[at]) or words[at] in SKIP):
        at += 1
    if at < len(words) and words[at] == "timeout":
        at += 2
    rest = words[at:]
    if not rest:
        return ""
    head = [_program(rest[0])]
    i = 1
    while i < len(rest):                         # redirections and their target say nothing
        word = rest[i]
        if re.match(r"^\d?[<>]{1,2}$|^&>$", word):
            i += 2
            continue
        if not re.match(r"^\d?[<>]{1,2}\S|^&>\S", word):
            head.append(word)
        i += 1
    code = lang if lang in ("fr", "en", "de") else "fr"
    for rule in _rules():
        cmd = rule.get("cmd") or []
        if len(cmd) > len(head) or head[:len(cmd)] != cmd:
            continue
        text = rule.get(code) or rule.get("fr") or ""
        if "{arg}" not in text:
            return text
        args = [w for w in head[len(cmd):] if w and not w.startswith("-")]
        arg = (args[0] if rule.get("pick") == "first" else args[-1]) if args else ""
        if arg:
            shown = _short(arg)
            if code == "fr" and re.match(r"(?i)^[aeiouyhéèêàâîôû]", shown):
                text = re.sub(r"\bde \{arg\}", "d’{arg}", text)
            return text.replace("{arg}", shown)
        return rule.get(code + "0") or re.sub(r"\s*[«“„]?\s*\{arg\}\s*[»”“]?", "", text).strip()
    return ""


def describe(command: str, lang: str = "fr") -> str:
    """A few words for a command in the person's language ('' when it says nothing known)."""
    note, body = split_note(command)
    if note:
        return note
    for segment in (s.strip() for s in re.split(r"\n|&&|\|\||;|\|", body)):
        if not segment:
            continue
        words = _words(segment)
        first = _program(next((w for w in words if not ASSIGN.match(w)), ""))
        if first in NOT_COMMANDS:
            continue
        return _segment(words, lang)
    return ""
