"""Local extension settings (Skills & MCP servers), opened by the user; nothing is installed by a model tool."""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QFontDatabase, QIcon
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFrame, QHBoxLayout, QLineEdit, QMessageBox,
    QPlainTextEdit, QVBoxLayout, QWidget,
)
from orneosui import Banner, Card, Disclosure, Header, Segments, button, hairline, label, page, tokens
import ornis_extensions as extensions

TEXT = {
    "fr": [
        "Skills et serveurs MCP",
        "Skills",
        "Serveurs MCP",
        "Importer un dossier…",
        "Retirer",
        "Enregistrer",
        "Fermer",
        "Un Skill est un dossier contenant SKILL.md (et des fichiers de référence éventuels). Ses instructions sont lues à la demande par Ornis ; aucun script ne s'exécute à l'import.",
        "Étendez Ornis sur cet ordinateur avec vos instructions métier (Skills) et vos outils locaux (MCP).",
        "Configuration enregistrée. Aucun serveur n'a été lancé.",
        "Retirer cette extension ?",
        "Aucun Skill installé pour l'instant.",
    ],
    "en": [
        "Skills and MCP servers",
        "Skills",
        "MCP servers",
        "Import folder…",
        "Remove",
        "Save",
        "Close",
        "A Skill is a folder containing SKILL.md (and optional reference files). Its instructions are read on demand by Ornis; importing never runs a script.",
        "Extend Ornis on this computer with your domain instructions (Skills) and local tools (MCP).",
        "Configuration saved. No server was started.",
        "Remove this extension?",
        "No skills installed yet.",
    ],
    "de": [
        "Skills und MCP-Server",
        "Skills",
        "MCP-Server",
        "Ordner importieren…",
        "Entfernen",
        "Speichern",
        "Schließen",
        "Ein Skill ist ein Ordner mit SKILL.md (und optionalen Referenzdateien). Seine Anweisungen werden bei Bedarf von Ornis gelesen; beim Import startet kein Skript.",
        "Erweitern Sie Ornis auf diesem Computer mit eigenen Fachanweisungen (Skills) und lokalen Werkzeugen (MCP).",
        "Konfiguration gespeichert. Kein Server wurde gestartet.",
        "Diese Erweiterung entfernen?",
        "Noch keine Skills installiert.",
    ],
}

EXTRA = {
    "fr": {
        "new_skill": "Créer ou modifier un Skill",
        "skill_name": "Identifiant du Skill (ex: mon-projet, revue-code)",
        "skill_content": "Contenu de SKILL.md",
        "skill_save": "Enregistrer le Skill",
        "skill_saved": "Skill « {name} » enregistré.",
        "skill_edit": "Afficher / modifier",
        "skill_files": "{n} fichier(s) joint(s)",
        "mcp_lead": "Un serveur MCP exécute du code avec vos droits locaux. Ajoutez uniquement des sources de confiance. Chaque appel demande votre accord sur cet ordinateur.",
        "mcp_none": "Aucun serveur MCP configuré.",
        "mcp_add_title": "Ajouter un serveur MCP",
        "mcp_name": "Nom du serveur (ex: filesystem, github, sqlite)",
        "mcp_stdio": "Commande locale (stdio)",
        "mcp_http": "Serveur distant (HTTPS)",
        "mcp_cmd": "Commande et arguments (ex: npx -y @modelcontextprotocol/server-filesystem /home/...)",
        "mcp_env": "Variables d'environnement transmises (ex: GITHUB_TOKEN=GITHUB_TOKEN)",
        "mcp_url": "URL du serveur (https://... ou http://127.0.0.1:...)",
        "mcp_token": "Jeton ou clé d'API (optionnel, gardé dans le trousseau ; $NOM pour une variable d'environnement)",
        "mcp_add_btn": "Ajouter le serveur",
        "mcp_test": "Tester",
        "mcp_testing": "Test de « {name} » en cours…",
        "mcp_test_ok": "« {name} » répond : {count} outil(s) disponible(s) ({tools}).",
        "mcp_enable": "Activer",
        "mcp_disable": "Désactiver",
        "mcp_disabled": "Désactivé",
        "mcp_advanced": "Configuration JSON avancée ▸",
        "catalog_skills": "Catalogue en 1 clic",
        "catalog_mcp": "Serveurs MCP prêts à l’emploi",
        "install_btn": "Installer",
        "installed_btn": "Installé",
    },
    "en": {
        "new_skill": "Create or edit a Skill",
        "skill_name": "Skill identifier (e.g. my-project, code-review)",
        "skill_content": "SKILL.md content",
        "skill_save": "Save Skill",
        "skill_saved": "Skill “{name}” saved.",
        "skill_edit": "View / edit",
        "skill_files": "{n} supporting file(s)",
        "mcp_lead": "An MCP server runs code with your local permissions. Add trusted sources only. Every call asks for your consent on this computer.",
        "mcp_none": "No MCP servers configured.",
        "mcp_add_title": "Add an MCP server",
        "mcp_name": "Server name (e.g. filesystem, github, sqlite)",
        "mcp_stdio": "Local command (stdio)",
        "mcp_http": "Remote server (HTTPS)",
        "mcp_cmd": "Command and arguments (e.g. npx -y @modelcontextprotocol/server-filesystem /home/...)",
        "mcp_env": "Environment variables to pass (e.g. GITHUB_TOKEN=GITHUB_TOKEN)",
        "mcp_url": "Server URL (https://... or http://127.0.0.1:...)",
        "mcp_token": "Token or API key (optional, kept in the keychain; $NAME for an environment variable)",
        "mcp_add_btn": "Add server",
        "mcp_test": "Test",
        "mcp_testing": "Testing “{name}”…",
        "mcp_test_ok": "“{name}” responded: {count} tool(s) available ({tools}).",
        "mcp_enable": "Enable",
        "mcp_disable": "Disable",
        "mcp_disabled": "Disabled",
        "mcp_advanced": "Advanced JSON configuration ▸",
        "catalog_skills": "1-click Skill gallery",
        "catalog_mcp": "Ready-to-use MCP servers",
        "install_btn": "Install",
        "installed_btn": "Installed",
    },
    "de": {
        "new_skill": "Skill erstellen oder bearbeiten",
        "skill_name": "Skill-Kennung (z. B. mein-projekt, code-review)",
        "skill_content": "Inhalt von SKILL.md",
        "skill_save": "Skill speichern",
        "skill_saved": "Skill „{name}“ gespeichert.",
        "skill_edit": "Anzeigen / bearbeiten",
        "skill_files": "{n} Begleitdatei(en)",
        "mcp_lead": "Ein MCP-Server führt Code mit Ihren lokalen Rechten aus. Fügen Sie nur vertrauenswürdige Quellen hinzu. Jeder Aufruf fragt auf diesem Computer nach Ihrer Zustimmung.",
        "mcp_none": "Kein MCP-Server konfiguriert.",
        "mcp_add_title": "MCP-Server hinzufügen",
        "mcp_name": "Servername (z. B. filesystem, github, sqlite)",
        "mcp_stdio": "Lokaler Befehl (stdio)",
        "mcp_http": "Remote-Server (HTTPS)",
        "mcp_cmd": "Befehl und Argumente (z. B. npx -y @modelcontextprotocol/server-filesystem /home/...)",
        "mcp_env": "Übergebene Umgebungsvariablen (z. B. GITHUB_TOKEN=GITHUB_TOKEN)",
        "mcp_url": "Server-URL (https://... or http://127.0.0.1:...)",
        "mcp_token": "Token oder API-Schlüssel (optional, im Schlüsselbund gespeichert; $NAME für eine Umgebungsvariable)",
        "mcp_add_btn": "Server hinzufügen",
        "mcp_test": "Testen",
        "mcp_testing": "Teste „{name}“…",
        "mcp_test_ok": "„{name}“ antwortet: {count} Werkzeug(e) verfügbar ({tools}).",
        "mcp_enable": "Aktivieren",
        "mcp_disable": "Deaktivieren",
        "mcp_disabled": "Deaktiviert",
        "mcp_advanced": "Erweiterte JSON-Konfiguration ▸",
        "catalog_skills": "1-Klick-Skill-Katalog",
        "catalog_mcp": "Fertige MCP-Server",
        "install_btn": "Installieren",
        "installed_btn": "Installiert",
    },
}

SKILL_TEMPLATE = """---
name: {name}
description: Instructions métier pour Ornis
---

# {name}

Décrivez ici les conventions, commandes ou procédures que vous souhaitez qu'Ornis suive lorsqu'il utilise ce Skill.
"""


class _Bridge(QObject):
    tested = Signal(str, bool, str)


def _clear(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            _clear(item.layout())


def _field(placeholder: str = "") -> QLineEdit:
    c = tokens()
    ed = QLineEdit()
    ed.setPlaceholderText(placeholder)
    ed.setStyleSheet(
        f"QLineEdit {{ background: {c['field']}; color: {c['text']}; border: 1px solid {c['line']}; "
        f"border-radius: 8px; padding: 7px 10px; }}"
        f"QLineEdit:focus {{ border: 2px solid {c['saffron']}; }}"
    )
    return ed


def open_dialog(parent=None):
    lang = (os.environ.get("LANG") or "fr")[:2]
    t = TEXT.get(lang, TEXT["en"])
    ex = EXTRA.get(lang, EXTRA["en"])
    c = tokens()
    mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    mono.setFamily("JetBrains Mono")
    mono.setPointSizeF(9.5)

    dialog = QDialog(parent)
    dialog.setObjectName("page")
    dialog.setWindowTitle(t[0])
    dialog.setWindowIcon(QIcon.fromTheme("eu.orneos.ornis", QIcon.fromTheme("orneos")))
    dialog.resize(620, 740)

    outer = QVBoxLayout(dialog)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    outer.addWidget(Header(t[0], t[8]))
    area, col = page()
    outer.addWidget(area, 1)

    banner = Banner()
    col.addWidget(banner)

    nav = Segments([("skills", t[1]), ("mcp", t[2])])
    nav.set_value("skills")
    col.addWidget(nav)

    # ---- Skills view -------------------------------------------------------------------------------------------
    skills_wrap = QWidget()
    skills_col = QVBoxLayout(skills_wrap)
    skills_col.setContentsMargins(0, 0, 0, 0)
    skills_col.setSpacing(14)

    skills_card = Card(t[1])
    skills_card.body.addWidget(label(t[7], "muted"))
    skills_list_box = QVBoxLayout()
    skills_list_box.setSpacing(8)
    skills_card.body.addLayout(skills_list_box)

    import_btn = button(t[3])
    skills_btn_row = QHBoxLayout()
    skills_btn_row.addWidget(import_btn)
    skills_btn_row.addStretch(1)
    skills_card.body.addLayout(skills_btn_row)
    skills_col.addWidget(skills_card)

    skill_catalog_card = Card(ex["catalog_skills"])
    skill_catalog_box = QVBoxLayout()
    skill_catalog_box.setSpacing(8)
    skill_catalog_card.body.addLayout(skill_catalog_box)
    skills_col.addWidget(skill_catalog_card)

    skill_editor_card = Card(ex["new_skill"])
    skill_name_in = _field(ex["skill_name"])
    skill_editor_card.body.addWidget(skill_name_in)
    skill_body_in = QPlainTextEdit()
    skill_body_in.setFont(mono)
    skill_body_in.setPlaceholderText(ex["skill_content"])
    skill_body_in.setFixedHeight(170)
    skill_editor_card.body.addWidget(skill_body_in)
    save_skill_btn = button(ex["skill_save"], "primary")
    skill_editor_card.body.addWidget(save_skill_btn, 0, Qt.AlignRight)
    skills_col.addWidget(skill_editor_card)
    col.addWidget(skills_wrap)

    def load_skill_into_editor(name: str):
        try:
            data = extensions.read_skill(name)
            skill_name_in.setText(name)
            skill_body_in.setPlainText(data["content"])
        except (OSError, ValueError) as error:
            banner.show_message("danger", str(error))

    def install_preset_skill_clicked(name: str):
        try:
            extensions.install_preset_skill(name, lang)
            reload_skills()
            banner.show_message("ok", ex["skill_saved"].format(name=name))
        except (OSError, ValueError) as error:
            banner.show_message("danger", str(error))

    def reload_skills():
        _clear(skills_list_box)
        _clear(skill_catalog_box)
        items = extensions.list_skills()
        for idx, p in enumerate(extensions.presets(lang)["skills"]):
            if idx:
                skill_catalog_box.addWidget(hairline())
            prow = QHBoxLayout()
            pinfo = QVBoxLayout()
            pinfo.setSpacing(2)
            pinfo.addWidget(label(f"{p['title']}  ({p['name']})", "title", wrap=False))
            pinfo.addWidget(label(p["description"], "muted"))
            prow.addLayout(pinfo, 1)
            ibtn = button(ex["installed_btn"] if p["installed"] else ex["install_btn"], "quiet" if p["installed"] else "primary")
            ibtn.setEnabled(not p["installed"])
            ibtn.clicked.connect(lambda _=False, n=p["name"]: install_preset_skill_clicked(n))
            prow.addWidget(ibtn)
            skill_catalog_box.addLayout(prow)
        if not items:
            skills_list_box.addWidget(label(t[11], "muted"))
            return
        for idx, s in enumerate(items):
            if idx:
                skills_list_box.addWidget(hairline())
            row = QHBoxLayout()
            info_col = QVBoxLayout()
            info_col.setSpacing(2)
            title_lbl = label(s["name"], "title", wrap=False)
            title_lbl.setFont(mono)
            info_col.addWidget(title_lbl)
            if s.get("description"):
                info_col.addWidget(label(s["description"], "muted"))
            if s.get("files"):
                info_col.addWidget(label(ex["skill_files"].format(n=len(s["files"])), "muted", wrap=False))
            row.addLayout(info_col, 1)
            edit_b = button(ex["skill_edit"], "quiet")
            edit_b.clicked.connect(lambda _=False, n=s["name"]: load_skill_into_editor(n))
            row.addWidget(edit_b)
            rem_b = button(t[4], "danger")
            rem_b.clicked.connect(lambda _=False, n=s["name"]: remove_skill(n))
            row.addWidget(rem_b)
            skills_list_box.addLayout(row)

    def install_skill_folder():
        source = QFileDialog.getExistingDirectory(dialog, t[3])
        if not source:
            return
        src = Path(source)
        try:
            paths = list(src.rglob("*"))
            if len(paths) > 1000 or any(p.is_symlink() for p in paths) or sum(p.stat().st_size for p in paths if p.is_file()) > 10 * 1024 * 1024:
                raise ValueError("Skill too large or containing symbolic links")
            imported = extensions.import_skill_folder(src)
            reload_skills()
            banner.show_message("ok", ex["skill_saved"].format(name=imported["name"]))
        except (OSError, ValueError) as error:
            banner.show_message("danger", str(error))

    def save_skill_editor():
        name = skill_name_in.text().strip()
        content = skill_body_in.toPlainText()
        if name and not content.strip():
            content = SKILL_TEMPLATE.format(name=name)
            skill_body_in.setPlainText(content)
        try:
            extensions.save_skill(name, content)
            reload_skills()
            banner.show_message("ok", ex["skill_saved"].format(name=name))
        except (OSError, ValueError) as error:
            banner.show_message("danger", str(error))

    def remove_skill(name: str):
        if QMessageBox.question(dialog, t[0], t[10]) == QMessageBox.StandardButton.Yes:
            try:
                extensions.delete_skill(name)
                reload_skills()
            except (OSError, ValueError) as error:
                banner.show_message("danger", str(error))

    import_btn.clicked.connect(install_skill_folder)
    save_skill_btn.clicked.connect(save_skill_editor)

    # ---- MCP servers view --------------------------------------------------------------------------------------
    mcp_wrap = QWidget()
    mcp_col = QVBoxLayout(mcp_wrap)
    mcp_col.setContentsMargins(0, 0, 0, 0)
    mcp_col.setSpacing(14)

    mcp_card = Card(t[2])
    mcp_card.body.addWidget(label(ex["mcp_lead"], "muted"))
    mcp_list_box = QVBoxLayout()
    mcp_list_box.setSpacing(8)
    mcp_card.body.addLayout(mcp_list_box)
    mcp_col.addWidget(mcp_card)

    mcp_catalog_card = Card(ex["catalog_mcp"])
    mcp_catalog_box = QVBoxLayout()
    mcp_catalog_box.setSpacing(8)
    mcp_catalog_card.body.addLayout(mcp_catalog_box)
    mcp_col.addWidget(mcp_catalog_card)

    add_mcp_card = Card(ex["mcp_add_title"])
    transport_seg = Segments([("stdio", ex["mcp_stdio"]), ("http", ex["mcp_http"])])
    transport_seg.set_value("stdio")
    add_mcp_card.body.addWidget(transport_seg)
    mcp_name_in = _field(ex["mcp_name"])
    add_mcp_card.body.addWidget(mcp_name_in)
    mcp_cmd_in = _field(ex["mcp_cmd"])
    add_mcp_card.body.addWidget(mcp_cmd_in)
    mcp_env_in = _field(ex["mcp_env"])
    add_mcp_card.body.addWidget(mcp_env_in)
    mcp_url_in = _field(ex["mcp_url"])
    mcp_url_in.setVisible(False)
    add_mcp_card.body.addWidget(mcp_url_in)
    mcp_token_in = _field(ex["mcp_token"])
    mcp_token_in.setEchoMode(QLineEdit.EchoMode.Password)
    mcp_token_in.setVisible(False)
    add_mcp_card.body.addWidget(mcp_token_in)
    add_mcp_btn = button(ex["mcp_add_btn"], "primary")
    add_mcp_card.body.addWidget(add_mcp_btn, 0, Qt.AlignRight)
    mcp_col.addWidget(add_mcp_card)

    adv = Disclosure(ex["mcp_advanced"])
    editor = QPlainTextEdit()
    editor.setFont(mono)
    editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    editor.setFixedHeight(160)
    adv.content_layout.addWidget(editor)
    apply_json_btn = button(t[5])
    adv.content_layout.addWidget(apply_json_btn, 0, Qt.AlignRight)
    mcp_col.addWidget(adv)
    mcp_wrap.setVisible(False)
    col.addWidget(mcp_wrap)

    bridge = _Bridge(dialog)

    def on_tested(name: str, ok: bool, msg: str):
        banner.show_message("ok" if ok else "danger", msg)

    bridge.tested.connect(on_tested)

    def test_mcp(name: str):
        banner.show_message("info", ex["mcp_testing"].format(name=name))

        def run_test():
            try:
                res = extensions.invoke(name, "tools/list", {})
                tools_list = (res.get("result") or {}).get("tools") or []
                names = ", ".join(str(tl.get("name") or "") for tl in tools_list[:6] if isinstance(tl, dict))
                if len(tools_list) > 6:
                    names += "…"
                bridge.tested.emit(name, True, ex["mcp_test_ok"].format(name=name, count=len(tools_list), tools=names or "—"))
            except Exception as error:
                bridge.tested.emit(name, False, f"{name}: {error}")

        threading.Thread(target=run_test, daemon=True).start()

    def install_preset_mcp_clicked(name: str):
        try:
            extensions.install_preset_mcp(name)
            reload_mcp()
            banner.show_message("ok", t[9])
        except (OSError, ValueError) as error:
            banner.show_message("danger", str(error))

    def reload_mcp():
        _clear(mcp_list_box)
        _clear(mcp_catalog_box)
        try:
            cfg = extensions.settings()
        except (OSError, ValueError) as error:
            cfg = {"mcpServers": {}}
            banner.show_message("danger", str(error))
        editor.setPlainText(json.dumps(cfg, indent=2, ensure_ascii=False))
        for idx, p in enumerate(extensions.presets(lang)["mcp"]):
            if idx:
                mcp_catalog_box.addWidget(hairline())
            prow = QHBoxLayout()
            pinfo = QVBoxLayout()
            pinfo.setSpacing(2)
            pinfo.addWidget(label(f"{p['title']}  ({p['name']})", "title", wrap=False))
            pinfo.addWidget(label(p["description"], "muted"))
            prow.addLayout(pinfo, 1)
            ibtn = button(ex["installed_btn"] if p["installed"] else ex["install_btn"], "quiet" if p["installed"] else "primary")
            ibtn.setEnabled(not p["installed"])
            ibtn.clicked.connect(lambda _=False, n=p["name"]: install_preset_mcp_clicked(n))
            prow.addWidget(ibtn)
            mcp_catalog_box.addLayout(prow)
        servers = cfg.get("mcpServers") or {}
        if not servers:
            mcp_list_box.addWidget(label(ex["mcp_none"], "muted"))
            return
        for idx, (name, item) in enumerate(servers.items()):
            if idx:
                mcp_list_box.addWidget(hairline())
            row = QHBoxLayout()
            info_col = QVBoxLayout()
            info_col.setSpacing(2)
            enabled = item.get("enabled", True) is not False
            kind = "HTTPS" if item.get("url") else "STDIO"
            head_text = f"{name}  ·  {kind}" + ("" if enabled else f"  ({ex['mcp_disabled']})")
            head_lbl = label(head_text, "title", wrap=False)
            head_lbl.setFont(mono)
            info_col.addWidget(head_lbl)
            target = item.get("url") or " ".join([str(item.get("command") or ""), *[str(a) for a in item.get("args") or []]])
            sub_lbl = label(target[:120], "muted")
            sub_lbl.setFont(mono)
            info_col.addWidget(sub_lbl)
            row.addLayout(info_col, 1)

            toggle_b = button(ex["mcp_disable"] if enabled else ex["mcp_enable"], "quiet")
            toggle_b.clicked.connect(lambda _=False, n=name, en=enabled: toggle_mcp(n, not en))
            row.addWidget(toggle_b)

            if enabled:
                test_b = button(ex["mcp_test"], "quiet")
                test_b.clicked.connect(lambda _=False, n=name: test_mcp(n))
                row.addWidget(test_b)

            rem_b = button(t[4], "danger")
            rem_b.clicked.connect(lambda _=False, n=name: remove_mcp(n))
            row.addWidget(rem_b)
            mcp_list_box.addLayout(row)

    def toggle_mcp(name: str, enabled: bool):
        try:
            cfg = extensions.settings()
            if name in cfg["mcpServers"]:
                cfg["mcpServers"][name]["enabled"] = enabled
                extensions.save(cfg)
                reload_mcp()
        except (OSError, ValueError) as error:
            banner.show_message("danger", str(error))

    def remove_mcp(name: str):
        if QMessageBox.question(dialog, t[0], t[10]) == QMessageBox.StandardButton.Yes:
            try:
                extensions.remove_extension("mcp", name)      # its token leaves the keychain too
                reload_mcp()
            except (OSError, ValueError) as error:
                banner.show_message("danger", str(error))

    def add_mcp_from_form():
        name = mcp_name_in.text().strip()
        mode = transport_seg.value()
        try:
            cfg = extensions.settings()
            entry: dict = {"enabled": True}
            if mode == "http":
                entry["url"] = mcp_url_in.text().strip()
                tok = mcp_token_in.text().strip()
                if tok.startswith("$") and len(tok) > 1:
                    entry["tokenEnv"] = tok[1:]
                elif tok:
                    entry["tokenStored"] = True          # the token itself goes to the keychain, never to the file
            else:
                parts = shlex.split(mcp_cmd_in.text().strip(), posix=os.name != "nt")
                if not parts:
                    raise ValueError("A command is required")
                entry["command"] = parts[0]
                if len(parts) > 1:
                    entry["args"] = parts[1:]
                env_raw = mcp_env_in.text().strip()
                if env_raw:
                    env_map = {}
                    for pair in re.split(r"[,;\s]+", env_raw) if "re" in globals() else env_raw.split():
                        if "=" in pair:
                            k, v = pair.split("=", 1)
                            env_map[k.strip()] = v.strip()
                        elif pair.strip():
                            env_map[pair.strip()] = pair.strip()
                    if env_map:
                        entry["env"] = env_map
            cfg["mcpServers"][name] = entry
            extensions.validate(cfg)
            if entry.get("tokenStored"):
                extensions.set_token(name, tok)
            extensions.save(cfg)
            mcp_name_in.clear()
            mcp_cmd_in.clear()
            mcp_env_in.clear()
            mcp_url_in.clear()
            mcp_token_in.clear()
            reload_mcp()
            banner.show_message("ok", t[9])
        except (OSError, ValueError) as error:
            banner.show_message("danger", str(error))

    def save_json():
        try:
            extensions.save(json.loads(editor.toPlainText()))
            reload_mcp()
            banner.show_message("ok", t[9])
        except (ValueError, OSError) as error:
            banner.show_message("danger", str(error))

    def switch_transport():
        is_http = transport_seg.value() == "http"
        mcp_cmd_in.setVisible(not is_http)
        mcp_env_in.setVisible(not is_http)
        mcp_url_in.setVisible(is_http)
        mcp_token_in.setVisible(is_http)

    def switch_tab():
        is_skills = nav.value() == "skills"
        skills_wrap.setVisible(is_skills)
        mcp_wrap.setVisible(not is_skills)

    transport_seg.group.buttonClicked.connect(lambda _b: switch_transport())
    nav.group.buttonClicked.connect(lambda _b: switch_tab())
    add_mcp_btn.clicked.connect(add_mcp_from_form)
    apply_json_btn.clicked.connect(save_json)

    col.addStretch(1)
    close_btn = button(t[6])
    close_btn.clicked.connect(dialog.accept)
    col.addWidget(close_btn, 0, Qt.AlignRight)

    try:
        reload_skills()
        reload_mcp()
    except (ValueError, OSError):
        pass
    dialog.exec()
