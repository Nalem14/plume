"""Notebook inventory and bounded, fixed context suggestions. No contents are logged."""
from pathlib import Path
CATALOGUE = {'agents_large': {'fr': {'label': 'Alléger le guide du projet', 'prompt': 'Examine uniquement AGENTS.md / CLAUDE.md / ORNIS.md. Propose un tri ou un résumé sans perdre les règles utiles. Ne modifie rien sans mon accord. Ne touche ni aux secrets, ni aux permissions, ni au bac à sable.'}, 'en': {'label': 'Shorten the project guide', 'prompt': 'Review only AGENTS.md / CLAUDE.md / ORNIS.md. Propose cleanup or a summary without losing useful rules. Change nothing without my approval. Do not touch secrets, permissions or the sandbox.'}, 'de': {'label': 'Projektleitfaden kürzen', 'prompt': 'Prüfe nur AGENTS.md / CLAUDE.md / ORNIS.md. Schlage eine Bereinigung oder Zusammenfassung vor, ohne nützliche Regeln zu verlieren. Ändere nichts ohne meine Zustimmung. Geheimnisse, Berechtigungen und Sandbox bleiben unangetastet.'}}, 'rules_large': {'fr': {'label': 'Alléger les règles', 'prompt': 'Examine uniquement .ornis/rules.md / .ornis/rules.local.md. Propose un tri ou un résumé sans perdre les règles utiles. Ne modifie rien sans mon accord. Ne touche ni aux secrets, ni aux permissions, ni au bac à sable.'}, 'en': {'label': 'Shorten the rules', 'prompt': 'Review only .ornis/rules.md / .ornis/rules.local.md. Propose cleanup or a summary without losing useful rules. Change nothing without my approval. Do not touch secrets, permissions or the sandbox.'}, 'de': {'label': 'Regeln kürzen', 'prompt': 'Prüfe nur .ornis/rules.md / .ornis/rules.local.md. Schlage eine Bereinigung oder Zusammenfassung vor, ohne nützliche Regeln zu verlieren. Ändere nichts ohne meine Zustimmung. Geheimnisse, Berechtigungen und Sandbox bleiben unangetastet.'}}, 'soul_large': {'fr': {'label': 'Alléger les préférences personnelles', 'prompt': 'Examine uniquement SOUL.md. Propose un tri ou un résumé sans perdre les règles utiles. Ne modifie rien sans mon accord. Ne touche ni aux secrets, ni aux permissions, ni au bac à sable.'}, 'en': {'label': 'Shorten personal preferences', 'prompt': 'Review only SOUL.md. Propose cleanup or a summary without losing useful rules. Change nothing without my approval. Do not touch secrets, permissions or the sandbox.'}, 'de': {'label': 'Persönliche Vorgaben kürzen', 'prompt': 'Prüfe nur SOUL.md. Schlage eine Bereinigung oder Zusammenfassung vor, ohne nützliche Regeln zu verlieren. Ändere nichts ohne meine Zustimmung. Geheimnisse, Berechtigungen und Sandbox bleiben unangetastet.'}}, 'memory_large': {'fr': {'label': 'Trier les souvenirs du projet', 'prompt': 'Examine uniquement .ornis/memory/. Propose un tri ou un résumé sans perdre les règles utiles. Ne modifie rien sans mon accord. Ne touche ni aux secrets, ni aux permissions, ni au bac à sable.'}, 'en': {'label': 'Review project memories', 'prompt': 'Review only .ornis/memory/. Propose cleanup or a summary without losing useful rules. Change nothing without my approval. Do not touch secrets, permissions or the sandbox.'}, 'de': {'label': 'Projekterinnerungen ordnen', 'prompt': 'Prüfe nur .ornis/memory/. Schlage eine Bereinigung oder Zusammenfassung vor, ohne nützliche Regeln zu verlieren. Ändere nichts ohne meine Zustimmung. Geheimnisse, Berechtigungen und Sandbox bleiben unangetastet.'}}, 'tmp_pile': {'fr': {'label': 'Trier les sorties temporaires', 'prompt': 'Examine uniquement .ornis/tmp/. Propose un tri ou un résumé sans perdre les règles utiles. Ne modifie rien sans mon accord. Ne touche ni aux secrets, ni aux permissions, ni au bac à sable.'}, 'en': {'label': 'Review temporary output', 'prompt': 'Review only .ornis/tmp/. Propose cleanup or a summary without losing useful rules. Change nothing without my approval. Do not touch secrets, permissions or the sandbox.'}, 'de': {'label': 'Temporäre Ausgaben ordnen', 'prompt': 'Prüfe nur .ornis/tmp/. Schlage eine Bereinigung oder Zusammenfassung vor, ohne nützliche Regeln zu verlieren. Ändere nichts ohne meine Zustimmung. Geheimnisse, Berechtigungen und Sandbox bleiben unangetastet.'}}, 'instructions_heavy': {'fr': {'label': 'Alléger les consignes', 'prompt': 'Examine uniquement AGENTS.md / .ornis/rules.md. Propose un tri ou un résumé sans perdre les règles utiles. Ne modifie rien sans mon accord. Ne touche ni aux secrets, ni aux permissions, ni au bac à sable.'}, 'en': {'label': 'Shorten instructions', 'prompt': 'Review only AGENTS.md / .ornis/rules.md. Propose cleanup or a summary without losing useful rules. Change nothing without my approval. Do not touch secrets, permissions or the sandbox.'}, 'de': {'label': 'Anweisungen kürzen', 'prompt': 'Prüfe nur AGENTS.md / .ornis/rules.md. Schlage eine Bereinigung oder Zusammenfassung vor, ohne nützliche Regeln zu verlieren. Ändere nichts ohne meine Zustimmung. Geheimnisse, Berechtigungen und Sandbox bleiben unangetastet.'}}, 'tools_heavy': {'fr': {'label': 'Examiner les outils chargés', 'prompt': 'Examine uniquement tools / MCP. Propose un tri ou un résumé sans perdre les règles utiles. Ne modifie rien sans mon accord. Ne touche ni aux secrets, ni aux permissions, ni au bac à sable.'}, 'en': {'label': 'Review loaded tools', 'prompt': 'Review only tools / MCP. Propose cleanup or a summary without losing useful rules. Change nothing without my approval. Do not touch secrets, permissions or the sandbox.'}, 'de': {'label': 'Geladene Werkzeuge prüfen', 'prompt': 'Prüfe nur tools / MCP. Schlage eine Bereinigung oder Zusammenfassung vor, ohne nützliche Regeln zu verlieren. Ändere nichts ohne meine Zustimmung. Geheimnisse, Berechtigungen und Sandbox bleiben unangetastet.'}}, 'guides_dup': {'fr': {'label': 'Vérifier les guides en double', 'prompt': 'Examine uniquement AGENTS.md / CLAUDE.md / ORNIS.md. Propose un tri ou un résumé sans perdre les règles utiles. Ne modifie rien sans mon accord. Ne touche ni aux secrets, ni aux permissions, ni au bac à sable.'}, 'en': {'label': 'Review duplicate guides', 'prompt': 'Review only AGENTS.md / CLAUDE.md / ORNIS.md. Propose cleanup or a summary without losing useful rules. Change nothing without my approval. Do not touch secrets, permissions or the sandbox.'}, 'de': {'label': 'Doppelte Leitfäden prüfen', 'prompt': 'Prüfe nur AGENTS.md / CLAUDE.md / ORNIS.md. Schlage eine Bereinigung oder Zusammenfassung vor, ohne nützliche Regeln zu verlieren. Ändere nichts ohne meine Zustimmung. Geheimnisse, Berechtigungen und Sandbox bleiben unangetastet.'}}}

def inventory(folder):
    root = Path(folder)
    names = [".ornis/rules.local.md", ".ornis/rules.md", "ORNIS.md", "AGENTS.md", "CLAUDE.md", ".ornis/SOUL.md", "SOUL.md", ".ornis/memory/MEMORY.md"]
    for sub in ("memory", "plans"):
        try:
            names += [str(p.relative_to(root)) for p in sorted((root / ".ornis" / sub).glob("*.md"))[:100] if str(p.relative_to(root)) not in names]
        except OSError:
            pass
    files = []
    for name in names:
        p = root / name
        try:
            if p.resolve().is_relative_to(root.resolve()) and p.is_file() and not p.is_symlink():
                files.append({"name": name, "bytes": p.stat().st_size})
        except OSError:
            pass
    count, size = 0, 0
    try:
        for p in (root / ".ornis/tmp").iterdir():
            if p.is_file() and not p.is_symlink():
                count += 1
                size += p.stat().st_size
    except OSError:
        pass
    try:
        import system
        global_soul = system.CONFIG / "SOUL.md"
        if global_soul.is_file() and not global_soul.is_symlink() and global_soul.stat().st_size and global_soul.read_text(encoding="utf-8", errors="replace").strip():
            files.append({"name": "SOUL.md (global)", "bytes": global_soul.stat().st_size})
    except OSError:
        pass
    files.append({"name": ".ornis/tmp/", "bytes": size, "count": count})
    return files


def tips(files, parts, lang="fr", dismissed=()):
    found = []
    for f in files:
        n, size = f["name"], f["bytes"]
        key = ("soul_large" if (n.endswith("SOUL.md") or n == "SOUL.md (global)") and size > 4000 else
               "rules_large" if "rules" in n and size > 8000 else
               "agents_large" if n in ("ORNIS.md", "AGENTS.md", "CLAUDE.md") and size > 8000 else
               "memory_large" if "/memory/" in n and size > 6000 else
               "tmp_pile" if n == ".ornis/tmp/" and (size > 10000000 or f.get("count", 0) > 40) else "")
        if key and key not in found: found.append(key)
    if parts.get("instructions", 0) > 12000: found.append("instructions_heavy")
    if parts.get("tools", 0) > 12000: found.append("tools_heavy")
    if {"AGENTS.md", "CLAUDE.md"}.issubset({f["name"] for f in files}): found.append("guides_dup")
    return [dict(key=k, **CATALOGUE[k].get(lang, CATALOGUE[k]["fr"])) for k in found if k not in dismissed][:3]
