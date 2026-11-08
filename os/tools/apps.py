#!/usr/bin/env python3
"""Orneos cloud apps in the start menu: one icon (site sprite glyph on its family tile) and one .desktop
launcher per app, opened through the cloud's single sign-on.

Order and colours follow the cloud rail (nextcloud/apps/orneos/js/orneos.js, css/orneos.css): one colour per group,
the rail colour of that group — Essentials Klein, Documents vert-de-gris, Organize safran, Photos teal, Tools Prusse,
Workspace prune (Config::appFamily on the site).

The same list goes to usr/share/orneos/apps.json, for the grid of apps of Plume (the cloud apps it has no
module for open in the browser, signed in), with the icons in usr/share/icons/hicolor/scalable/apps.

Usage: apps.py <public_html/assets/img/icons.svg> <dest root>
"""
import json
import re
import sys
from pathlib import Path

from icons import tile          # the tile shared by every Orneos app icon

CLOUD = "https://app.orneos.eu"
SSO = CLOUD + "/apps/user_oidc/login/1?redirectUrl="   # Config::cloudLink(), OIDC_PROVIDER_ID = 1

# group, key, cloud path or full URL, names en / fr / de, family, sprite id when it differs from the key
APPS = [
    ("home", "mail", "/apps/mail/", "Mail", "Courrier", "E-Mail", "communicate", None),
    ("home", "calendar", "/apps/calendar/", "Calendar", "Agenda", "Kalender", "communicate", None),
    ("home", "meet", "/apps/spreed/", "Meet", "Meet", "Meet", "communicate", None),
    ("home", "contacts", "/apps/contacts/", "Contacts", "Contacts", "Kontakte", "communicate", None),
    ("docs", "office-text", "/apps/office/text-md", "Text", "Texte", "Text", "docs", "notes"),
    ("docs", "office-docs", "/apps/office/documents", "Docs", "Docs", "Docs", "docs", "files"),
    ("docs", "office-sheets", "/apps/office/spreadsheets", "Sheets", "Calcul", "Tabellen", "docs", "tables"),
    ("docs", "office-slides", "/apps/office/presentations", "Slides", "Diapos", "Folien", "docs", "presentation"),
    ("docs", "office-board", "/apps/office/whiteboard-whiteboard", "Board", "Tableau", "Board", "docs", "whiteboard"),
    ("docs", "files", "/apps/files/", "Drive", "Drive", "Drive", "docs", None),
    ("organize", "notes", "/apps/notes/", "Notes", "Notes", "Notizen", "organize", None),
    ("organize", "tasks", "/apps/tasks/", "Tasks", "Tâches", "Aufgaben", "organize", None),
    ("organize", "deck", "/apps/deck/", "Deck", "Deck", "Deck", "organize", None),
    ("organize", "appointments", "/apps/appointments/", "Appointments", "Rendez-vous", "Termine", "organize", None),
    ("organize", "forms", "/apps/forms/", "Forms", "Formulaires", "Formulare", "organize", None),
    ("organize", "tables", "/apps/tables/", "Spreadsheet", "Tableur", "Tabellen", "organize", None),
    ("media", "photos", "/apps/photos/", "Photos", "Photothèque", "Fotos", "media", None),
    ("media", "memories", "/apps/memories/", "Memories", "Souvenirs", "Erinnerungen", "media", None),
    ("tools", "assistant", "/apps/assistant/", "Ornis", "Ornis", "Ornis", "tools", "ornis"),
    ("tools", "passwords", "/apps/passwords/", "Passwords", "Mots de passe", "Passwörter", "tools", None),
    ("tools", "bookmarks", "/apps/bookmarks/", "Favourites", "Favoris", "Favoriten", "tools", None),
    ("tools", "news", "/apps/news/", "News", "News", "News", "tools", None),
    ("tools", "analytics", "/apps/analytics/", "Analytics", "Analytics", "Analytics", "tools", None),
    ("tools", "search", "https://search.orneos.eu/", "Search", "Recherche", "Suche", "tools", None),
    ("space", "activity", "/apps/activity/", "Activity", "Activité", "Aktivität", "space", None),
    ("space", "announcements", "/apps/announcementcenter/", "Announcements", "Centre d'annonces", "Ankündigungen", "space", None),
]

# Rail colours of the cloud (css/orneos.css, light theme): tile background, glyph
FAMILY = {
    "communicate": ("#002FA7", "#FFFFFF"),
    "organize": ("#8A5A00", "#FFFFFF"),
    "docs": ("#2F7D6D", "#FFFFFF"),
    "media": ("#1A5F7A", "#FFFFFF"),
    "tools": ("#0F2440", "#FFFFFF"),
    "space": ("#7A3B6E", "#FFFFFF"),
}
GROUPS = {
    "home": ("Essentials", "Essentiel", "Wichtig"),
    "docs": ("Documents", "Documents", "Dokumente"),
    "organize": ("Organize", "Organiser", "Organisieren"),
    "media": ("Photos", "Photos", "Fotos"),
    "tools": ("Tools", "Outils", "Werkzeuge"),
    "space": ("Workspace", "Espace", "Arbeitsbereich"),
}


# Courrier, Agenda and Contacts: the native apps from Plume's code (orneos-mail… = plume --edition=…)
PLUME = {
    "mail": ("orneos-mail %u", "MimeType=x-scheme-handler/mailto;\n",
             "Mail of your Orneos address and your other mailboxes, with Ornis",
             "Le courrier de votre adresse Orneos et de vos autres boîtes, avec Ornis",
             "E-Mails Ihrer Orneos-Adresse und Ihrer anderen Postfächer, mit Ornis",
             "mail;email;courrier;e-mail;inbox;plume;", ("new-message", "New message", "Nouveau message", "Neue Nachricht")),
    "calendar": ("orneos-calendar %U", "MimeType=text/calendar;\n",
                 "Your calendars, invitations and meetings",
                 "Vos agendas, invitations et réunions",
                 "Ihre Kalender, Einladungen und Besprechungen",
                 "calendar;agenda;kalender;events;rendez-vous;meeting;plume;", ("new-event", "New event", "Nouvel événement", "Neuer Termin")),
    "contacts": ("orneos-contacts", "",
                 "The people you write to, on all your devices",
                 "Les personnes à qui vous écrivez, sur tous vos appareils",
                 "Ihre Kontakte, auf allen Ihren Geräten",
                 "contacts;people;address book;carnet;kontakte;plume;", ("new-contact", "New contact", "Nouveau contact", "Neuer Kontakt")),
}
# what the system knows them as (its default mail client, calendar…)
KIND = {"mail": "Email;", "calendar": "Office;Calendar;", "contacts": "Office;ContactManagement;"}
# the native apps that take over their cloud app's entry (and dock pin)
NATIVE = {"passwords": "orneos-passwords %u", "notes": "orneos-notes", "tasks": "orneos-tasks", "assistant": "ornis",
          "photos": "orneos-photos", "meet": "orneos-meet %u"}


def main():
    sprite = Path(sys.argv[1]).read_text()
    root = Path(sys.argv[2])
    icons = root / "usr/share/icons/hicolor/scalable/apps"
    apps = root / "usr/share/applications"
    icons.mkdir(parents=True, exist_ok=True)
    apps.mkdir(parents=True, exist_ok=True)

    menus = root / "etc/xdg/menus/applications-merged"
    dirs = root / "usr/share/desktop-directories"
    menus.mkdir(parents=True, exist_ok=True)
    dirs.mkdir(parents=True, exist_ok=True)
    sub = []
    for group, (en, fr, de) in GROUPS.items():
        (dirs / f"eu.orneos.{group}.directory").write_text(
            "[Desktop Entry]\nType=Directory\n"
            f"Name={en}\nName[fr]={fr}\nName[de]={de}\nIcon=orneos\n")
        sub.append(
            "    <Menu>\n"
            f"      <Name>{en}</Name>\n"
            f"      <Directory>eu.orneos.{group}.directory</Directory>\n"
            f"      <Include><Category>X-Orneos-{group}</Category></Include>\n"
            "    </Menu>")
    (menus / "orneos.menu").write_text(
        '<!DOCTYPE Menu PUBLIC "-//freedesktop//DTD Menu 1.0//EN" '
        '"http://www.freedesktop.org/standards/menu-spec/1.0/menu.dtd">\n'
        "<Menu>\n  <Name>Applications</Name>\n  <Menu>\n    <Name>Orneos</Name>\n"
        "    <Directory>eu.orneos.directory</Directory>\n"
        + "\n".join(sub) + "\n"
        "  </Menu>\n</Menu>\n")

    # The launcher sorts apps into the same groups (eu.orneos.launcher/contents/code/families.js).
    families = (Path(__file__).resolve().parent.parent / "files/usr/share/plasma/plasmoids/eu.orneos.launcher/contents/code/families.js").read_text()
    for group, key, *_ in APPS:
        if not re.search(rf'(?:^|[\s{{,])"?{re.escape(key)}"?: "{group}"', families):
            sys.exit(f"apps.py: '{key}' is not in group '{group}' in the launcher's families.js")
    for key in list(PLUME) + list(NATIVE):
        if f'"{key}"' not in families.split("const NATIVE", 1)[1].split("\n", 1)[0]:
            sys.exit(f"apps.py: '{key}' opens on the computer but families.js shows it as a cloud app")

    for group, key, target, en, fr, de, family, glyph_id in APPS:
        glyph_id = glyph_id or key
        m = re.search(rf'<symbol id="{glyph_id}" viewBox="0 0 24 24">(.*?)</symbol>', sprite, re.S)
        if not m:
            sys.exit(f"apps.py: no '{glyph_id}' glyph in the sprite")
        bg, fg = FAMILY[family]
        glyph = re.sub(r"var\(--ai-accent, ([^)]+)\)", r"\1", m.group(1)).replace("currentColor", fg)  # Qt SVG has no var()
        if key == "meet":
            glyph = glyph.replace('<path d="M15 9l6-3v9l-6-3"/>', '<path d="M15 9l6-3v9l-6-3z" stroke="#F0A202" stroke-linejoin="round"/>')
        (icons / f"eu.orneos.{key}.svg").write_text(tile(bg, glyph, key))

        # Mail, calendar and contacts open Courrier, Agenda and Contacts; passwords, notes, tasks and photos open
        # Mots de passe, Notes, Tâches and Photos (all native, same ids as the web shortcuts were: the dock pins follow); the web
        # stays one right-click away. The others open the cloud through the single sign-on.
        web = target if target.startswith("https://") else SSO + target
        # in quotes: the « ? » of the sign-on address is a reserved character of Exec (desktop entry spec)
        quoted = '"' + web.replace("%", "%%") + '"'
        native = key in PLUME or key in NATIVE
        exec_line = f"Exec={PLUME[key][0]}" if key in PLUME else f"Exec={NATIVE[key]}" if native else f"Exec=xdg-open {quoted}"
        comment = "Comment=Orneos cloud\nComment[fr]=Cloud Orneos\nComment[de]=Orneos Cloud"
        extra = f"StartupNotify=false\nStartupWMClass=eu.orneos.{key}\n"
        cloud_action = ("Actions=cloud;\n\n[Desktop Action cloud]\nName=Open in the cloud\n"
                        f"Name[fr]=Ouvrir dans le cloud\nName[de]=In der Cloud öffnen\nExec=xdg-open {quoted}\n")
        if key in PLUME:
            _, mime, c_en, c_fr, c_de, keywords, (action, a_en, a_fr, a_de) = PLUME[key]
            comment = f"Comment={c_en}\nComment[fr]={c_fr}\nComment[de]={c_de}"
            extra = (f"StartupNotify=true\nStartupWMClass=eu.orneos.{key}\n{mime}Keywords={keywords}\n"
                     f"Actions=new;cloud;\n\n[Desktop Action new]\nName={a_en}\nName[fr]={a_fr}\nName[de]={a_de}\n"
                     f"Exec=orneos-{key} --{action}\n\n" + cloud_action.split("\n\n", 1)[1])
        elif key == "notes":
            comment = ("Comment=Notes, checklists and images, even offline\n"
                       "Comment[fr]=Notes, listes et images, même hors ligne\n"
                       "Comment[de]=Notizen, Checklisten und Bilder, auch offline")
            extra = ("StartupNotify=true\nStartupWMClass=eu.orneos.notes\n"
                     "Keywords=notes;note;notizen;memo;checklist;markdown;quick note;note rapide;\n"
                     "Actions=quick;new;cloud;\n\n[Desktop Action quick]\nName=Quick Note\nName[fr]=Note rapide\n"
                     "Name[de]=Schnelle Notiz\nExec=orneos-notes --quick\n\n[Desktop Action new]\nName=New note\n"
                     "Name[fr]=Nouvelle note\nName[de]=Neue Notiz\nExec=orneos-notes --new\n\n" + cloud_action.split("\n\n", 1)[1])
        elif key == "tasks":
            comment = ("Comment=Tasks and reminders, even offline\n"
                       "Comment[fr]=Tâches et rappels, même hors ligne\n"
                       "Comment[de]=Aufgaben und Erinnerungen, auch offline")
            extra = ("StartupNotify=true\nStartupWMClass=eu.orneos.tasks\n"
                     "Keywords=tasks;todo;to do;reminders;rappels;tâches;aufgaben;erinnerungen;checklist;\n"
                     "Actions=new;today;cloud;\n\n[Desktop Action new]\nName=New task\nName[fr]=Nouvelle tâche\n"
                     "Name[de]=Neue Aufgabe\nExec=orneos-tasks --new\n\n[Desktop Action today]\nName=Today\n"
                     "Name[fr]=Aujourd'hui\nName[de]=Heute\nExec=orneos-tasks --view=today\n\n" + cloud_action.split("\n\n", 1)[1])
        elif key == "photos":
            comment = ("Comment=Your photo library: people, places, albums and memories, even offline\n"
                       "Comment[fr]=Votre photothèque : personnes, lieux, albums et souvenirs, même hors ligne\n"
                       "Comment[de]=Ihre Mediathek: Personen, Orte, Alben und Erinnerungen, auch offline")
            extra = ("StartupNotify=true\nStartupWMClass=eu.orneos.photos\n"
                     "Keywords=photos;photo;pictures;images;albums;photothèque;fotos;bilder;mediathek;memories;souvenirs;\n"
                     "Actions=favorites;memories;cloud;\n\n[Desktop Action favorites]\nName=Favourites\nName[fr]=Favoris\n"
                     "Name[de]=Favoriten\nExec=orneos-photos --view=favorites\n\n[Desktop Action memories]\nName=Memories\n"
                     "Name[fr]=Souvenirs\nName[de]=Erinnerungen\nExec=orneos-photos --view=memories\n\n" + cloud_action.split("\n\n", 1)[1])
        elif key == "assistant":
            # the Ornis app (window); its quick panel in the top bar is eu.orneos.ornis.desktop (Meta+O)
            comment = ("Comment=Ornis acts for you: calendar, mail, notes, tasks, files\n"
                       "Comment[fr]=Ornis agit pour vous : agenda, mails, notes, tâches, fichiers\n"
                       "Comment[de]=Ornis handelt für Sie: Kalender, E-Mails, Notizen, Aufgaben, Dateien")
            extra = ("StartupNotify=true\nStartupWMClass=eu.orneos.assistant\n"
                     "Keywords=ornis;assistant;ia;ai;ki;chat;agent;\n"
                     "Actions=new;scheduled;cloud;\n\n[Desktop Action new]\nName=New conversation\nName[fr]=Nouvelle conversation\n"
                     "Name[de]=Neues Gespräch\nExec=ornis --new\n\n[Desktop Action scheduled]\nName=Scheduled tasks\n"
                     "Name[fr]=Tâches programmées\nName[de]=Geplante Aufgaben\nExec=ornis --scheduled\n\n" + cloud_action.split("\n\n", 1)[1])
        elif key == "meet":
            # the native Meet (conversations and calls of the cloud's Talk); its agent rings with the window closed
            comment = ("Comment=Chats, team conversations and video calls\n"
                       "Comment[fr]=Discussions, conversations d'équipe et visioconférence\n"
                       "Comment[de]=Chats, Team-Unterhaltungen und Videoanrufe")
            extra = ("StartupNotify=true\nStartupWMClass=eu.orneos.meet\n"
                     "Keywords=meet;talk;visio;video;call;appel;anruf;chat;discussion;réunion;meeting;\n"
                     "Actions=new;cloud;\n\n[Desktop Action new]\nName=New conversation\nName[fr]=Nouvelle conversation\n"
                     "Name[de]=Neue Unterhaltung\nExec=orneos-meet --new\n\n" + cloud_action.split("\n\n", 1)[1])
        elif native:
            comment = ("Comment=Passwords, verification codes and Wi-Fi, even offline\n"
                       "Comment[fr]=Mots de passe, codes de validation et Wi-Fi, même hors ligne\n"
                       "Comment[de]=Passwörter, Bestätigungscodes und WLAN, auch offline")
            extra = ("StartupNotify=true\nStartupWMClass=eu.orneos.passwords\nMimeType=x-scheme-handler/otpauth;\n"
                     "Keywords=password;passwords;mot de passe;passwort;2fa;totp;otp;wifi;keys;clés;\n" + cloud_action)
        (apps / f"eu.orneos.{key}.desktop").write_text(f"""[Desktop Entry]
Type=Application
Name=Orneos {en}
Name[fr]=Orneos {fr}
Name[de]=Orneos {de}
GenericName={en}
GenericName[fr]={fr}
GenericName[de]={de}
{comment}
{exec_line}
Icon=eu.orneos.{key}
Categories=Network;{KIND.get(key, '')}X-Orneos;X-Orneos-{group};
{extra}""")

    # Plume (native mail, calendar and contacts): Klein like the other essentials, the quill's barb in saffron
    plume = ('<g fill="none" stroke-width="1.5" stroke-linecap="square">'
             '<path d="M20 4C11 4 6 9 6 17M6 17c7 0 12-5 14-13M6 17l-2 3" stroke="#FFFFFF"/>'
             '<path d="M9.5 13.5h5" stroke="#F0A202"/></g>')
    (icons / "eu.orneos.plume.svg").write_text(tile(FAMILY["communicate"][0], plume, "plume"))

    # the grid of Plume: groups in order, then each app with its names, its address and its family
    catalogue = {
        "groups": [{"key": g, "names": {"en": en, "fr": fr, "de": de}} for g, (en, fr, de) in GROUPS.items()],
        "apps": [{"key": key, "group": group, "url": target, "family": family, "names": {"en": en, "fr": fr, "de": de}}
                 for group, key, target, en, fr, de, family, _ in APPS],
    }
    share = root / "usr/share/orneos"
    share.mkdir(parents=True, exist_ok=True)
    (share / "apps.json").write_text(json.dumps(catalogue, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
