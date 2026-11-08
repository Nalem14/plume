// The launcher's families: the same groups, order and colours as the cloud rail (Config::getAppGroups) and
// os/tools/apps.py, which checks at build time that every Orneos app below is in its group. Apps that are not
// Orneos apps (Firefox, Dolphin, anything installed later) are "system".
.pragma library

const GROUPS = ["home", "docs", "organize", "media", "tools", "space", "system"];
// group → family colour (design/tokens.json › families)
const FAMILY = {home: "communicate", docs: "docs", organize: "organize", media: "media", tools: "tools", space: "space"};
const LABELS = {
    home:     {fr: "Essentiel", en: "Essentials", de: "Wichtig"},
    docs:     {fr: "Documents", en: "Documents", de: "Dokumente"},
    organize: {fr: "Organiser", en: "Organize", de: "Organisieren"},
    media:    {fr: "Photos", en: "Photos", de: "Fotos"},
    tools:    {fr: "Outils", en: "Tools", de: "Werkzeuge"},
    space:    {fr: "Espace", en: "Workspace", de: "Arbeitsbereich"},
    system:   {fr: "Système", en: "System", de: "System"},
};
// eu.orneos.<key>.desktop → group
const APPS = {
    mail: "home", calendar: "home", meet: "home", contacts: "home", "meet-desktop": "home",
    "office-text": "docs", "office-docs": "docs", "office-sheets": "docs", "office-slides": "docs", "office-board": "docs", files: "docs",
    notes: "organize", tasks: "organize", deck: "organize", appointments: "organize", forms: "organize", tables: "organize",
    photos: "media", memories: "media",
    assistant: "tools", passwords: "tools", bookmarks: "tools", news: "tools", analytics: "tools", search: "tools",
    activity: "space", announcements: "space",
};
// Orneos apps that run on the computer; the other Orneos entries open the cloud (a small cloud mark).
const NATIVE = ["mail", "calendar", "contacts", "passwords", "notes", "tasks", "assistant", "photos", "meet"];

// "applications:eu.orneos.mail.desktop" → "mail"; "" for anything that is not an Orneos app.
function orneosKey(favoriteId) {
    const m = /(?:^|:)eu\.orneos\.([a-z-]+)\.desktop$/.exec(String(favoriteId || ""));
    return m && APPS[m[1]] ? m[1] : "";
}
function group(favoriteId) { const key = orneosKey(favoriteId); return key ? APPS[key] : "system"; }
function isWeb(favoriteId) { const key = orneosKey(favoriteId); return key !== "" && NATIVE.indexOf(key) < 0; }
function label(groupKey) { const t = LABELS[groupKey] || {}; return t[Qt.locale().name.slice(0, 2)] || t.en || groupKey; }
