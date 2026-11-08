// The terminals of the Code panel, drawn by xterm.js in Chromium (terminal/terminal.html). Loaded on demand by
// BenchPanel: without QtWebEngine, the panel offers the computer's own terminal instead. The page reaches the shells
// through window.bridge (code.terminals, ornis_core/terminal.py); the colours follow the app's theme.
import QtQuick
import QtWebChannel
import QtWebEngine

WebEngineView {
    id: web
    property string pending: ""
    readonly property var c: theme.c
    backgroundColor: c.bg
    url: Qt.resolvedUrl("terminal/terminal.html")
    webChannel: channel
    profile: WebEngineProfile {
        offTheRecord: true
        httpCacheType: WebEngineProfile.MemoryHttpCache
        persistentCookiesPolicy: WebEngineProfile.NoPersistentCookies
    }
    settings.localContentCanAccessFileUrls: true          // its own scripts, next to it
    settings.localContentCanAccessRemoteUrls: false
    settings.javascriptCanOpenWindows: false
    settings.javascriptCanAccessClipboard: true           // copy and paste in the terminal
    settings.javascriptCanPaste: true
    settings.pluginsEnabled: false
    settings.focusOnNavigationEnabled: true

    WebChannel { id: channel }
    Component.onCompleted: channel.registerObject("bridge", code.terminals)

    // the theme of the app, in xterm's terms (ANSI colours readable on either background)
    function palette() {
        const dark = theme.dark
        return {
            background: String(c.bg), foreground: String(c.text), cursor: String(c.accent), cursorAccent: String(c.bg),
            selectionBackground: dark ? "#2A3F7A" : "#C9D5F5", line: String(c.line),
            black: dark ? "#1B2333" : "#2E3440", red: dark ? "#FF7A85" : "#C4293B", green: dark ? "#6FD39B" : "#1E7A4C",
            yellow: dark ? "#F2C66D" : "#9A6700", blue: dark ? "#8AA8FF" : "#2142B8", magenta: dark ? "#D49BEA" : "#8E3FA6",
            cyan: dark ? "#6CCFD8" : "#16707B", white: dark ? "#C9D1E0" : "#5B6578",
            brightBlack: dark ? "#5B6578" : "#7A8396", brightRed: dark ? "#FF9AA2" : "#E0384D", brightGreen: dark ? "#8DE6B2" : "#279A61",
            brightYellow: dark ? "#FFD98A" : "#B98200", brightBlue: dark ? "#A9BFFF" : "#3557D4", brightMagenta: dark ? "#E2B4F2" : "#A752C4",
            brightCyan: dark ? "#8FE0E7" : "#1C8C99", brightWhite: dark ? "#F2F5FA" : "#1B2333"
        }
    }
    function applyTheme() { runJavaScript("theme(" + JSON.stringify(palette()) + "); window.ended = " + JSON.stringify(app.t.bench_term_ended)) }
    function showTerm(id) {
        pending = id
        if (!loading) runJavaScript("show(" + JSON.stringify(id) + ")")
    }
    function dropTerm(id) { runJavaScript("drop(" + JSON.stringify(id) + ")") }

    onLoadingChanged: request => {
        if (request.status === WebEngineView.LoadSucceededStatus) {
            applyTheme()
            if (pending) runJavaScript("show(" + JSON.stringify(pending) + ")")
        }
    }
    Connections {
        target: theme
        function onChanged() { web.applyTheme() }
    }
    onNavigationRequested: request => {
        const url = request.url.toString()
        if (url.split("?")[0] === web.url.toString().split("?")[0]) return
        request.reject()
        if (request.navigationType === WebEngineNavigationRequest.LinkClickedNavigation) app.openLink(url)
    }
    onNewWindowRequested: request => app.openLink(request.requestedUrl.toString())
    onPermissionRequested: permission => permission.deny()
}
