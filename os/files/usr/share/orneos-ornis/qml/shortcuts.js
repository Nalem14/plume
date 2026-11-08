.pragma library
// Ornis's keyboard shortcuts: one list, shown in the settings and by Ctrl+/ (Shortcuts.qml). The keys are bound in
// OrnisView.qml (and Composer.qml, Sidebar.qml): change both together. Close to ChatGPT's where it has one.

function rows(t, voice) {
    const out = [
        ["Ctrl+N", t.sc_new],
        ["Ctrl+F", t.sc_search],
        ["Shift+Esc", t.sc_focus],
        ["Ctrl+Shift+C", t.sc_copy_last],
        ["Ctrl+Shift+;", t.sc_copy_code]
    ]
    if (voice && voice.canSpeak)
        out.push(["Ctrl+Shift+L", t.sc_read])
    if (voice && voice.available)
        out.push(["Ctrl+Shift+Space", t.sc_dictate])
    return out.concat([
        ["Esc", t.sc_stop],
        ["↑", t.sc_edit],
        ["Ctrl+Shift+Backspace", t.sc_delete],
        ["Shift+Tab", t.sc_mode],
        ["F2 · Delete", t.sc_list],
        ["Ctrl+B", t.sc_sidebar],
        ["Ctrl+Shift+S", t.sc_scheduled],
        ["F5", t.sc_refresh],
        ["Ctrl+,", t.sc_settings],
        ["Ctrl+/", t.shortcuts]
    ])
}

// The keys as written on the keyboard of the language (Maj, Strg…), ⌘ ⇧ on a Mac (Plume)
function keyName(keys, lang, mac) {
    if (mac)
        return keys.replace(/Ctrl\+/g, "⌘").replace(/Shift\+/g, "⇧").replace("Backspace", "⌫").replace("Space", "␣")
    const names = { "fr": { "Shift": "Maj", "Esc": "Échap", "Delete": "Suppr", "Backspace": "Retour arrière", "Space": "Espace" },
                    "de": { "Ctrl": "Strg", "Shift": "Umschalt", "Delete": "Entf", "Backspace": "Rücktaste", "Space": "Leertaste" } }[lang] || {}
    return keys.replace(/[A-Za-z]+/g, word => names[word] || word)
}
