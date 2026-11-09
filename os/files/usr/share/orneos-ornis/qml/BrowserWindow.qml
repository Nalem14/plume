// The browser of one owner (« you », or a bot): its tabs, its own profile (cookies and sign-ins kept on this computer,
// apart from the person's and the other bots'), the screen size it simulates, and Annoter. A window of its own: the
// Navigateur panel embeds it (WindowContainer) to watch or take over. Otherwise it works unseen, as a window of one
// transparent pixel that lets clicks through: Chromium gives a hidden window a page of 0 × 0 (every site would lay
// out for no screen), a shown one gets the size of the page's item, here a real screen (09/11, tested). On macOS a
// tool window hides when Plume is not in front: a plain frameless one there.
import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtWebEngine

Window {
    id: win
    property string owner: ""
    property string startUrl: "about:blank"
    property var views: []
    property int current: -1
    property int devW: 0                       // the simulated screen (0: the panel's size)
    property int devH: 0
    property bool mobile: false
    property string baseUA: ""
    property string uploadPath: ""             // a file the agent chose for the next file field it clicks
    property bool annotating: false
    property var waiters: []
    property bool embedded: false              // in the Navigateur panel: a real window, the person can use it
    onEmbeddedChanged: if (!embedded) { width = 1; height = 1 }
    readonly property var view: current >= 0 && current < views.length ? views[current] : null
    width: 1; height: 1
    visible: true
    color: embedded ? "#ffffff" : "transparent"
    opacity: embedded ? 1 : 0
    flags: embedded ? Qt.Window
           : (host.mac ? Qt.Window : Qt.Tool) | Qt.FramelessWindowHint | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus
    title: "Ornis — " + owner

    WebEngineProfile {
        id: prof
        storageName: "ornis-browser-" + win.owner.replace(/[^a-z0-9_-]/gi, "_")
        offTheRecord: false
        persistentCookiesPolicy: WebEngineProfile.AllowPersistentCookies
        httpCacheType: WebEngineProfile.DiskHttpCache
        downloadPath: host.downloadDir(win.owner)
        onDownloadRequested: download => { download.accept(); host.downloaded(win.owner, download.downloadFileName) }
        Component.onCompleted: win.baseUA = httpUserAgent
    }

    Component {
        id: tabComponent
        WebEngineView {
            id: web
            property var logs: []
            anchors.fill: parent
            visible: win.view === web
            profile: prof
            settings.javascriptCanOpenWindows: true
            settings.javascriptCanAccessClipboard: false
            settings.pluginsEnabled: false
            settings.screenCaptureEnabled: false
            settings.localContentCanAccessFileUrls: false
            onLoadingChanged: info => win.changed()
            onTitleChanged: win.changed()
            onUrlChanged: win.changed()
            onJavaScriptConsoleMessage: (level, message, line, source) => {
                logs.push({ level: ["info", "warning", "error"][level] || "info", text: String(message).slice(0, 500),
                            at: String(source).split("/").pop() + ":" + line })
                if (logs.length > 200) logs.shift()
            }
            onJavaScriptDialogRequested: request => {   // nobody to answer a page's alert: it goes through, noted
                request.accepted = true
                logs.push({ level: "dialog", text: String(request.message).slice(0, 300), at: "" })
                if (request.type === JavaScriptDialogRequest.DialogTypePrompt) request.dialogReject()
                else request.dialogAccept()
            }
            onNewWindowRequested: request => win.addTab(request.requestedUrl.toString())
            onPermissionRequested: permission => permission.deny()
            onFileDialogRequested: request => {
                if (win.uploadPath !== "") {
                    request.accepted = true
                    request.dialogAccept([win.uploadPath])
                    win.uploadPath = ""
                } else if (win.owner !== "you") {
                    request.accepted = true
                    request.dialogReject()
                }
            }
        }
    }

    function changed() {
        host.pageChanged(owner, JSON.stringify(state()))
    }
    function state() {
        return { owner: owner, current: current, url: view ? view.url.toString() : "", title: view ? view.title : "",
                 loading: view ? view.loading : false, canBack: view ? view.canGoBack : false,
                 canForward: view ? view.canGoForward : false, devW: devW, devH: devH, mobile: mobile,
                 annotating: annotating,
                 tabs: views.map((v, i) => ({ index: i, url: v.url.toString(), title: v.title, current: i === current })) }
    }
    function addTab(url) {
        const v = tabComponent.createObject(stage, { url: url || "about:blank" })
        views = views.concat([v])
        current = views.length - 1
        changed()
        return current
    }
    function closeTab(i) {
        if (i < 0 || i >= views.length) return
        const v = views[i]
        views = views.filter((_, k) => k !== i)
        v.destroy()
        if (views.length === 0) addTab("about:blank")
        current = Math.min(current, views.length - 1)
        changed()
    }

    // ---- what the agent asks: one command, one answer (once the page has settled) ---------------------------------
    function settle(cid, make, minMs, maxMs) {
        waiters = waiters.concat([{ cid: cid, make: make, from: Date.now(), min: minMs || 350, max: maxMs || 15000 }])
        tick.start()
    }
    Timer {
        id: tick
        interval: 120; repeat: true
        onTriggered: {
            const now = Date.now(), keep = []
            for (const w of win.waiters) {
                const busy = win.view && win.view.loading
                if (now - w.from >= w.min && (!busy || now - w.from >= w.max)) {
                    let out
                    try { out = w.make() } catch (e) { out = JSON.stringify({ error: String(e) }) }
                    host.done(w.cid, typeof out === "string" ? out : JSON.stringify(out))
                } else keep.push(w)
            }
            win.waiters = keep
            if (keep.length === 0) stop()
        }
    }
    function agentJs(cid, code, minMs) {
        if (!view) { host.done(cid, JSON.stringify({ error: "no tab" })); return }
        view.runJavaScript(code, WebEngineScript.ApplicationWorld, result => {
            const out = result === undefined || result === null ? JSON.stringify({ error: "the page did not answer" }) : String(result)
            settle(cid, () => out, minMs === undefined ? 350 : minMs)
        })
    }
    Connections {
        target: host
        function onCommand(who, cid, action, raw) {
            if (who !== win.owner) return
            const a = raw ? JSON.parse(raw) : {}
            if (!win.view && action !== "newtab") win.addTab("about:blank")
            switch (action) {
            case "js": win.agentJs(cid, a.code, a.min); break
            case "navigate":
                win.view.url = a.url
                win.settle(cid, () => win.state(), 600, 25000); break
            case "back": win.view.goBack(); win.settle(cid, () => win.state(), 500); break
            case "forward": win.view.goForward(); win.settle(cid, () => win.state(), 500); break
            case "reload": win.view.reload(); win.settle(cid, () => win.state(), 600); break
            case "stop": win.view.stop(); host.done(cid, JSON.stringify(win.state())); break
            case "state": host.done(cid, JSON.stringify(win.state())); break
            case "newtab": win.addTab(a.url || "about:blank"); win.settle(cid, () => win.state(), 600, 25000); break
            case "closetab": win.closeTab(a.index === undefined ? win.current : a.index); host.done(cid, JSON.stringify(win.state())); break
            case "switchtab":
                if (a.index >= 0 && a.index < win.views.length) win.current = a.index
                win.changed(); host.done(cid, JSON.stringify(win.state())); break
            case "resize":
                win.devW = a.w || 0; win.devH = a.h || 0; win.mobile = !!a.mobile
                prof.httpUserAgent = win.mobile
                    ? "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
                    : win.baseUA
                win.view.zoomFactor = a.zoom || 1
                win.changed()
                win.settle(cid, () => win.state(), 300); break
            case "console":
                host.done(cid, JSON.stringify({ logs: win.view.logs.slice(-(a.limit || 50)) })); break
            case "upload": win.uploadPath = a.path; win.agentJs(cid, a.code); break
            case "annotate": win.annotating = !!a.on; win.changed(); host.done(cid, JSON.stringify(win.state())); break
            case "screenshot":
                stage.grabToImage(r => host.done(cid, JSON.stringify({ ok: r.saveToFile(a.path), path: a.path })))
                break
            default: host.done(cid, JSON.stringify({ error: "unknown action " + action }))
            }
        }
    }

    // ---- the page, at the simulated size ----------------------------------------------------------------------------
    Rectangle { anchors.fill: parent; visible: win.embedded; color: win.devW > 0 ? "#e9ecf2" : "#ffffff" }
    Item {
        id: stage
        readonly property real fit: win.devW > 0 && win.embedded
                                    ? Math.min(1, (win.width - 24) / win.devW, (win.height - 24) / Math.max(1, win.devH)) : 1
        width: win.devW > 0 ? win.devW : win.embedded ? win.width : 1280
        height: win.devH > 0 ? win.devH : win.embedded ? win.height : 860
        scale: fit
        transformOrigin: Item.TopLeft
        x: win.devW > 0 && win.embedded ? Math.max(0, (win.width - width * fit) / 2) : 0
        y: win.devW > 0 && win.embedded ? 12 : 0
    }

    // ---- Annoter: point at an element, say what to change -----------------------------------------------------------
    Rectangle {
        id: hoverBox
        visible: win.annotating && width > 0
        color: "#2a002FA7"; border.color: "#002FA7"; border.width: 2; radius: 3
        z: 10
    }
    MouseArea {
        anchors.fill: stage
        z: 11
        visible: win.annotating
        hoverEnabled: true
        cursorShape: Qt.CrossCursor
        property real lastAsk: 0
        function boxFor(r) {
            hoverBox.x = stage.x + r.x * stage.fit; hoverBox.y = stage.y + r.y * stage.fit
            hoverBox.width = r.w * stage.fit; hoverBox.height = r.h * stage.fit
        }
        onPositionChanged: mouse => {
            if (!win.view || Date.now() - lastAsk < 90 || note.visible) return
            lastAsk = Date.now()
            const x = Math.round(mouse.x / stage.fit), y = Math.round(mouse.y / stage.fit)
            win.view.runJavaScript(host.agentCall("rect", [x, y]), WebEngineScript.ApplicationWorld, r => { if (r) boxFor(JSON.parse(r)) })
        }
        onClicked: mouse => {
            if (!win.view) return
            const x = Math.round(mouse.x / stage.fit), y = Math.round(mouse.y / stage.fit)
            win.view.runJavaScript(host.agentCall("pick", [x, y]), WebEngineScript.ApplicationWorld, r => {
                note.picked = r ? JSON.parse(r) : ({})
                if (note.picked.rect) boxFor(note.picked.rect)
                note.x = Math.min(win.width - note.width - 8, hoverBox.x)
                note.y = Math.min(win.height - note.height - 8, hoverBox.y + hoverBox.height + 6)
                note.visible = true
                noteText.forceActiveFocus()
            })
        }
    }
    Rectangle {
        id: note
        property var picked: ({})
        visible: false
        z: 12
        width: 320; height: 128; radius: 10
        color: "#ffffff"; border.color: "#c9d1de"
        Column {
            anchors.fill: parent; anchors.margins: 10; spacing: 8
            Text { text: (note.picked.role || note.picked.tag || "") + (note.picked.name ? " « " + note.picked.name.slice(0, 40) + " »" : "")
                   font.pixelSize: 12; color: "#5b6577"; elide: Text.ElideRight; width: parent.width }
            TextField { id: noteText; width: parent.width; placeholderText: host.label("browser_annotate_ph")
                        onAccepted: sendNote.clicked() }
            Row {
                spacing: 8; anchors.right: parent.right
                Button { text: host.label("cancel"); flat: true; onClicked: { note.visible = false; noteText.text = "" } }
                Button {
                    id: sendNote
                    text: host.label("browser_annotate_send")
                    onClicked: {
                        host.annotated(win.owner, JSON.stringify({ url: win.view ? win.view.url.toString() : "",
                                                                   size: { w: stage.width, h: stage.height, mobile: win.mobile },
                                                                   element: note.picked, note: noteText.text }))
                        note.visible = false; noteText.text = ""; hoverBox.width = 0
                    }
                }
            }
        }
    }

    // in the panel, the focus is often in the page: the shortcuts of Annoter work there too
    Shortcut { sequence: "Ctrl+Shift+D"; enabled: win.embedded; onActivated: { win.annotating = !win.annotating; win.changed() } }
    Shortcut { sequence: "Escape"; enabled: win.embedded && win.annotating && !note.visible
               onActivated: { win.annotating = false; hoverBox.width = 0; win.changed() } }

    Component.onCompleted: addTab(startUrl)
}
