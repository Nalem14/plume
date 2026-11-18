"""The colours of a file's text in the Code panel (Fichiers: to read and to edit), as an editor's: keywords, strings,
comments, numbers, names of functions and types, tags. A QSyntaxHighlighter set on the QML text's own document
(bench.highlight), so the same colours stay while typing. Rules by family of languages, by regular expressions: no
parser, fast enough for the panel's files (MAX_PREVIEW). The colours come from QML (the theme's tokens)."""
import re

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat

C_LIKE = {"c", "h", "cc", "cpp", "cxx", "hpp", "hh", "m", "mm", "java", "kt", "kts", "go", "rs", "swift", "cs", "scala",
          "dart", "zig", "groovy", "gradle"}
JS = {"js", "mjs", "cjs", "jsx", "ts", "tsx", "mts", "cts", "qml", "vue", "svelte", "astro"}
FAMILY = {**{e: "c" for e in C_LIKE}, **{e: "js" for e in JS},
          "py": "py", "pyw": "py", "pyi": "py", "rb": "rb", "rake": "rb", "php": "php", "phtml": "php",
          "sh": "sh", "bash": "sh", "zsh": "sh", "fish": "sh", "ksh": "sh", "command": "sh", "env": "sh",
          "ps1": "ps", "psm1": "ps", "bat": "bat", "cmd": "bat",
          "css": "css", "scss": "css", "sass": "css", "less": "css",
          "html": "html", "htm": "html", "xml": "html", "svg": "html", "xhtml": "html", "plist": "html", "ui": "html",
          "json": "json", "jsonc": "json", "json5": "json", "geojson": "json", "ipynb": "json",
          "yaml": "yaml", "yml": "yaml", "toml": "ini", "ini": "ini", "cfg": "ini", "conf": "ini", "properties": "ini",
          "desktop": "ini", "service": "ini",
          "md": "md", "markdown": "md", "mdx": "md",
          "sql": "sql", "lua": "lua", "pl": "sh", "r": "py", "jl": "py", "ex": "rb", "exs": "rb", "nix": "sh",
          "dockerfile": "sh", "makefile": "sh", "mk": "sh", "cmake": "sh", "tf": "c", "hcl": "c", "proto": "c",
          "graphql": "js", "gql": "js", "diff": "diff", "patch": "diff"}
# whole names (no extension)
NAMES = {"dockerfile": "sh", "containerfile": "sh", "makefile": "sh", "gnumakefile": "sh", "justfile": "sh",
         "gemfile": "rb", "rakefile": "rb", "vagrantfile": "rb", ".bashrc": "sh", ".zshrc": "sh", ".profile": "sh",
         ".gitignore": "sh", ".env": "sh", ".editorconfig": "ini", ".gitconfig": "ini", "cmakelists.txt": "sh"}

KEYWORDS = {
    "c": "auto break case catch char class const constexpr continue default defer delete do double else enum explicit "
         "export extends extern false final finally float fn for func go goto if impl implements import in inline int "
         "interface let long loop match mod move mut namespace new nil null nullptr override package private protected "
         "pub public return self Self short signed sizeof static struct super switch template this throw throws trait "
         "true try type typedef typename union unsafe unsigned use using var virtual void volatile where while async await "
         "val when object data sealed open internal guard defer protocol extension init deinit let fileprivate",
    "js": "as async await break case catch class const continue debugger default delete do else enum export extends "
          "false finally for from function get if implements import in instanceof interface let new null of package "
          "private protected public readonly return set static super switch this throw true try type typeof undefined "
          "var void while with yield property signal required alias component pragma keyof declare namespace abstract "
          "satisfies infer never unknown any",
    "py": "False None True and as assert async await break class continue def del elif else except finally for from "
          "global if import in is lambda match case nonlocal not or pass raise return try while with yield self cls",
    "rb": "BEGIN END alias and begin break case class def defined? do else elsif end ensure false for if in module next "
          "nil not or redo rescue retry return self super then true undef unless until when while yield require "
          "attr_accessor attr_reader private protected public",
    "php": "abstract and array as break callable case catch class clone const continue declare default do echo else "
           "elseif empty enddeclare endfor endforeach endif endswitch endwhile enum extends final finally fn for foreach "
           "function global goto if implements include include_once instanceof insteadof interface isset list match "
           "namespace new null or print private protected public readonly require require_once return static switch "
           "throw trait true false try unset use var while xor yield self parent int string bool float void mixed",
    "sh": "if then else elif fi case esac for while until do done in function return local export readonly declare "
          "source alias unset shift exit break continue set echo cd test FROM RUN CMD COPY ADD ENV ARG WORKDIR ENTRYPOINT "
          "EXPOSE USER LABEL VOLUME ONBUILD HEALTHCHECK SHELL STOPSIGNAL",
    "ps": "begin break catch class continue data define do dynamicparam else elseif end exit filter finally for foreach "
          "from function if in param process return switch throw trap try until using var while",
    "bat": "echo set if else goto call exit for in do not exist defined errorlevel setlocal endlocal rem",
    "sql": "select from where and or not insert into values update set delete create table alter drop index primary key "
           "foreign references join left right inner outer on group by order having limit offset as distinct union all "
           "null is in like between case when then else end default unique view begin commit rollback transaction "
           "int integer varchar text boolean date datetime timestamp float double decimal returning exists",
    "lua": "and break do else elseif end false for function goto if in local nil not or repeat return then true until while",
    "css": "", "html": "", "json": "true false null", "yaml": "true false null yes no on off", "ini": "true false",
    "md": "", "diff": "",
}

COMMENT = {"c": ("//", "/*", "*/"), "js": ("//", "/*", "*/"), "php": ("//|#", "/*", "*/"), "css": ("", "/*", "*/"),
           "py": ("#", "", ""), "rb": ("#", "=begin", "=end"), "sh": ("#", "", ""), "yaml": ("#", "", ""),
           "ini": ("[#;]", "", ""), "ps": ("#", "<#", "#>"), "bat": ("(?i:rem\\b)|::", "", ""), "sql": ("--", "/*", "*/"),
           "lua": ("--", "--[[", "]]"), "html": ("", "<!--", "-->"), "json": ("//", "/*", "*/"), "md": ("", "<!--", "-->"),
           "diff": ("", "", "")}

ROLES = ("keyword", "string", "comment", "number", "function", "type", "tag", "attr", "heading", "added", "removed")


def family(name: str) -> str:
    low = (name or "").rsplit("/", 1)[-1].lower()
    if low in NAMES:
        return NAMES[low]
    if low.startswith(("dockerfile.", "containerfile.")):
        return "sh"
    ext = low.rsplit(".", 1)[-1] if "." in low else ""
    return FAMILY.get(ext, "")


def _rules(fam: str) -> list[tuple[str, str]]:
    """(pattern, role) in the order they apply: a later one paints over an earlier one."""
    rules: list[tuple[str, str]] = []
    if fam == "md":
        return [(r"^#{1,6}\s.*$", "heading"), (r"\*\*[^*]+\*\*|__[^_]+__", "keyword"), (r"`[^`]+`", "string"),
                (r"^\s*(?:[-*+]|\d+\.)\s", "number"), (r"\[[^\]]*\]\([^)]*\)", "function"), (r"^\s*>.*$", "comment"),
                (r"^```.*$", "type")]
    if fam == "diff":
        return [(r"^\+.*$", "added"), (r"^-.*$", "removed"), (r"^@@.*@@", "type"), (r"^(?:diff|index|---|\+\+\+) .*$", "comment")]
    if fam == "html":
        return [(r"</?[A-Za-z][\w:.-]*", "tag"), (r"/?>", "tag"), (r"\s[\w:@.-]+(?==)", "attr"),
                (r"\"[^\"]*\"|'[^']*'", "string"), (r"&\w+;", "number"), (r"<!DOCTYPE[^>]*>|<\?[^?]*\?>", "comment")]
    if fam == "css":
        return [(r"[.#]?[A-Za-z_-][\w-]*(?=[^{};]*\{)", "tag"), (r"[\w-]+(?=\s*:)", "attr"),
                (r"#[0-9a-fA-F]{3,8}\b|\b\d+(?:\.\d+)?(?:px|em|rem|%|vh|vw|s|ms|deg|fr)?\b", "number"),
                (r"@[\w-]+", "keyword"), (r"\b[\w-]+(?=\()", "function"), (r"\"[^\"]*\"|'[^']*'", "string")]
    if fam == "json":
        return [(r"\b-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b", "number"), (r"\b(?:true|false|null)\b", "keyword"),
                (r"\"(?:[^\"\\]|\\.)*\"", "string"), (r"\"(?:[^\"\\]|\\.)*\"(?=\s*:)", "attr")]
    if fam == "yaml":
        return [(r"\b-?\d+(?:\.\d+)?\b", "number"), (r"\b(?:true|false|null|yes|no|on|off)\b", "keyword"),
                (r"^\s*-?\s*[\w.\-\"' /]+(?=\s*:(?:\s|$))", "attr"), (r"\"(?:[^\"\\]|\\.)*\"|'[^']*'", "string"),
                (r"^---$|^\.\.\.$", "type"), (r"[&*][\w-]+", "function")]
    if fam == "ini":
        return [(r"\b-?\d+(?:\.\d+)?\b", "number"), (r"\b(?:true|false)\b", "keyword"),
                (r"^\s*[\w.\-]+(?=\s*[=:])", "attr"), (r"^\s*\[[^\]]*\]", "heading"), (r"\"[^\"]*\"|'[^']*'", "string")]
    words = KEYWORDS.get(fam, "").split()
    rules.append((r"\b0[xX][0-9a-fA-F_]+\b|\b\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?[a-zA-Z]*\b", "number"))
    rules.append((r"\b[A-Z][A-Za-z0-9_]*\b", "type"))
    rules.append((r"\b[A-Za-z_$][\w$]*(?=\s*\()", "function"))
    if words:
        flags = "(?i)" if fam in ("sql", "bat", "ps") else ""
        rules.append((flags + r"\b(?:" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + r")\b",
                      "keyword"))
    if fam == "sh":
        rules += [(r"\$\{[^}]*\}|\$\w+|\$[@#?$!*0-9]", "attr"), (r"(?<=\s)--?[\w-]+", "attr")]
    if fam == "php":
        rules += [(r"\$\w+", "attr")]
    if fam in ("py", "js", "c", "php"):
        rules.append((r"@[\w.]+", "attr"))               # decorators, annotations, QML's signals
    if fam == "js":
        rules.append((r"`(?:[^`\\]|\\.)*`", "string"))
    if fam == "c":
        rules.append((r"^\s*#\s*\w+", "keyword"))           # #include, #define
    rules.append((r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'", "string"))
    return rules


class Highlighter(QSyntaxHighlighter):
    """Colours a QTextDocument by the rules of its file's family; block comments and Python's triple quotes run across
    lines (the block's state)."""

    def __init__(self, document, fam: str, colors: dict):
        super().__init__(document)
        self._fam = fam
        self._formats: dict = {}
        self.set_colors(colors, rehighlight=False)
        self._rules = [(QRegularExpression(p, QRegularExpression.PatternOption.MultilineOption), r) for p, r in _rules(fam)]
        line, start, end = COMMENT.get(fam, ("", "", ""))
        self._line = QRegularExpression(f"(?:^|(?<=\\s))(?:{line}).*$") if line else None
        self._start, self._end = start, end
        self._triple = fam == "py"

    def set_colors(self, colors: dict, rehighlight: bool = True):
        for role in ROLES:
            fmt = QTextCharFormat()
            value = (colors or {}).get(role)
            if value:
                fmt.setForeground(QColor(str(value)))
            if role in ("keyword", "heading"):
                fmt.setFontWeight(QFont.Weight.DemiBold)
            if role == "comment":
                fmt.setFontItalic(True)
            self._formats[role] = fmt
        if rehighlight:
            self.rehighlight()

    def _paint(self, start, length, role):
        if length > 0:
            self.setFormat(start, length, self._formats[role])

    def highlightBlock(self, text):  # noqa: N802 (Qt's name)
        if len(text) > 4000:                                  # a minified line: left plain
            self.setCurrentBlockState(self.previousBlockState() if self.previousBlockState() > 0 else 0)
            return
        for rx, role in self._rules:
            it = rx.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self._paint(m.capturedStart(), m.capturedLength(), role)
        spans = []                                            # strings found, so a « # » inside one is no comment
        for rx, role in self._rules:
            if role == "string":
                it = rx.globalMatch(text)
                while it.hasNext():
                    m = it.next()
                    spans.append((m.capturedStart(), m.capturedEnd()))
        if self._line is not None:
            it = self._line.globalMatch(text)
            while it.hasNext():
                m = it.next()
                at = m.capturedStart()
                if not any(a < at < b for a, b in spans):
                    self._paint(at, len(text) - at, "comment")
                    break
        self.setCurrentBlockState(0)
        self._span(text, self._start, self._end, 1, "comment")
        if self._triple:
            self._span(text, '"""', '"""', 2, "string")
            self._span(text, "'''", "'''", 3, "string")

    def _span(self, text, opener, closer, state, role):
        """A span that may run over several lines (/* … */, <!-- … -->, triple quotes): the block's state says
        whether the previous line left one open."""
        if not opener:
            return
        at = 0 if self.previousBlockState() == state else text.find(opener)
        skip = 0 if self.previousBlockState() == state else len(opener)
        while at >= 0:
            end = text.find(closer, at + skip)
            if end < 0:
                self.setCurrentBlockState(state)
                self._paint(at, len(text) - at, role)
                return
            length = end - at + len(closer)
            self._paint(at, length, role)
            at = text.find(opener, at + length)
            skip = len(opener)
