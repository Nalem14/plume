// The browser of one owner (« you », or a bot): its tabs, its own profile (cookies and sign-ins kept on this computer,
// apart from the person's and the other bots'), the screen size it simulates, Annoter, and who drives it. A window of
// its own: the Navigateur panel embeds it (WindowContainer) to watch or take over. Otherwise it works unseen, as a
// window of one transparent pixel that lets clicks through: Chromium gives a hidden window a page of 0 × 0 (every site
// would lay out for no screen), a shown one gets the size of the page's item, here a real screen (09/11, tested). On
// macOS a tool window hides when Plume is not in front: a plain frameless one there.
// Who drives (browser.py): once the agent acts, it holds the page — the person sees it work under a veil, with
// « Prendre le contrôle » in the middle; once the person takes it, the agent's actions wait for them.
// Everything drawn here is a native window over Plume's: Ornis's components and colours (`theme`, `app` given by
// browser.py), never the default controls.
import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Effects
import QtWebEngine
import "components"

Window {
    id: win
    property string owner: ""
    property string who: ""                    // its name, as the person knows it (Ornis, Orla…)
    property string startUrl: "about:blank"
    property var views: []
    property int current: -1
    property int devW: 0                       // the simulated screen (0: the panel's size)
    property int devH: 0
    property bool mobile: false
    property string baseUA: ""
    property string uploadPath: ""             // a file the agent chose for the next file field it clicks
    property string uploadCid: ""              // the agent's browser_upload, until the page asks for the file
    property string uploadName: ""
    property bool pressing: false              // a real click of the agent passes through the veil
    property var fileRequest: null             // a file field the person clicked, until the panel's picker answers
    property bool annotating: false
    property var waiters: []
    property var dialogs: []                   // what the pages asked while the agent drove, until it reads them
    property string control: ""                // "agent" | "person" | "" (nobody holds it)
    property bool embedded: false              // in the Navigateur panel: a real window, the person can use it
    onEmbeddedChanged: if (!embedded) { width = 1; height = 1 }
    readonly property var view: current >= 0 && current < views.length ? views[current] : null
    readonly property var c: theme.c
    readonly property bool agentDrives: embedded && control === "agent"
    readonly property real zoom: view ? view.zoomFactor : 1
    width: 1; height: 1
    visible: true
    color: embedded ? c.field : "transparent"
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
        // a plain Chrome to sites: « QtWebEngine/6.x » made some treat it as an unknown browser
        Component.onCompleted: { win.baseUA = httpUserAgent.replace(/ ?QtWebEngine\/[\d.]+/, ""); httpUserAgent = win.baseUA }
    }

    Component {
        id: tabComponent
        WebEngineView {
            id: web
            property var logs: []
            // a video in a format this Chromium lacks (H.264, AAC: not in Qt WebEngine as Plume ships it, patents):
            // Instagram, many sites. Nothing simple adds them; the panel says so and offers your own browser.
            property bool mediaFailed: false
            Component.onCompleted: {
                const script = WebEngine.script()          // a WebEngineScript (Qt 6: a value made by the singleton)
                script.name = "ornis-media"
                script.worldId = WebEngineScript.ApplicationWorld
                script.runsOnSubFrames = true
                script.injectionPoint = WebEngineScript.DocumentReady
                script.sourceCode = "(function(){if(window.__ornisMedia)return;window.__ornisMedia=1;"
                    + "function bad(t){return t&&(t.tagName==='VIDEO'||t.tagName==='AUDIO')&&t.error&&(t.error.code===3||t.error.code===4)}"
                    + "document.addEventListener('error',function(e){if(bad(e.target))console.warn('ornis:media-unsupported')},true);"
                    + "setTimeout(function(){if(Array.prototype.some.call(document.querySelectorAll('video,audio'),bad))console.warn('ornis:media-unsupported')},1500)})()"
                userScripts.insert(script)
            }
            anchors.fill: parent
            visible: win.view === web
            profile: prof
            settings.javascriptCanOpenWindows: true
            settings.javascriptCanAccessClipboard: false
            settings.pluginsEnabled: false
            settings.screenCaptureEnabled: false
            settings.localContentCanAccessFileUrls: false
            onLoadingChanged: info => win.changed()
            onLoadProgressChanged: if (win.view === web) win.changed()
            onTitleChanged: win.changed()
            onUrlChanged: { mediaFailed = false; win.changed() }
            onIconChanged: win.changed()
            onJavaScriptConsoleMessage: (level, message, line, source) => {
                if (message === "ornis:media-unsupported") {
                    if (!mediaFailed) { mediaFailed = true; logs.push({ level: "warning", at: "",
                        text: "A video or audio of this page cannot play in this browser (format not included: H.264/AAC)." }); win.changed() }
                    return
                }
                logs.push({ level: ["info", "warning", "error"][level] || "info", text: String(message).slice(0, 500),
                            at: String(source).split("/").pop() + ":" + line })
                if (logs.length > 200) logs.shift()
            }
            onJavaScriptDialogRequested: request => {
                // the person drives (or nobody does) and sees the page: the site asks them, as any browser would
                if (win.embedded && win.control !== "agent") return
                // nobody to answer the agent's page: it goes through, and the agent is told
                request.accepted = true
                const text = String(request.message).slice(0, 300)
                logs.push({ level: "dialog", text: text, at: "" })
                const prompt = request.type === JavaScriptDialogRequest.DialogTypePrompt
                win.dialogs = win.dialogs.concat([{ text: text, answer: prompt ? "dismissed" : "answered OK" }]).slice(-5)
                if (prompt) request.dialogReject()
                else request.dialogAccept()
            }
            onNewWindowRequested: request => win.addTab(request.requestedUrl.toString(),
                                                        request.destination === WebEngineNewWindowRequest.InNewBackgroundTab)
            onPermissionRequested: permission => permission.deny()
            onFileDialogRequested: request => {
                request.accepted = true
                if (win.uploadPath !== "") {
                    request.dialogAccept([win.uploadPath])
                    win.uploadPath = ""
                    uploadWait.stop()
                    win.view.runJavaScript(host.agentCall("unaim", []), WebEngineScript.ApplicationWorld)
                    if (win.uploadCid !== "") {
                        const cid = win.uploadCid
                        win.uploadCid = ""
                        win.settle(cid, () => JSON.stringify({ ok: true, uploaded: String(win.uploadName) }), 600)
                    }
                } else if (win.embedded && win.control !== "agent") {
                    // the person clicked « Ajouter un fichier »: Qt's own dialog, child of this window embedded in
                    // the panel, is made but never shown (13/11, Instagram, X…). The panel opens Plume's picker, over
                    // Plume's window, and gives the files back (chooseFiles).
                    if (win.fileRequest) win.fileRequest.dialogReject()
                    win.fileRequest = request
                    host.askFiles(win.owner, request.mode, request.acceptedMimeTypes || [], request.defaultFileName || "")
                } else request.dialogReject()      // the agent's page, nobody to choose: browser_upload says which
            }
        }
    }

    function changed() {
        host.pageChanged(owner, JSON.stringify(state()))
    }
    function state() {
        return { owner: owner, current: current, url: view ? view.url.toString() : "", title: view ? view.title : "",
                 loading: view ? view.loading : false, progress: view ? view.loadProgress : 100,
                 canBack: view ? view.canGoBack : false,
                 canForward: view ? view.canGoForward : false, devW: devW, devH: devH, mobile: mobile,
                 zoom: Math.round(zoom * 100), fit: Math.round(stage.fit * 100), annotating: annotating,
                 marks: marks.length, media: view ? view.mediaFailed : false,
                 tabs: views.map((v, i) => ({ index: i, url: v.url.toString(), title: v.title, current: i === current,
                                              loading: v.loading, icon: v.icon.toString() })) }
    }
    function addTab(url, background) {
        const v = tabComponent.createObject(stage, { url: url || "about:blank" })
        views = views.concat([v])
        if (!background || current < 0) current = views.length - 1
        changed()
        return current
    }
    function closeTab(i) {
        if (i < 0 || i >= views.length) return
        const v = views[i]
        views = views.filter((_, k) => k !== i)
        v.destroy()
        if (views.length === 0) addTab("about:blank")
        current = Math.min(i < current ? current - 1 : current, views.length - 1)
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
            if (out.indexOf('"box"') >= 0) {                 // an action: the person sees where it happened
                try { const o = JSON.parse(out); if (o.box) cursor.show(o.at, o.box, out.indexOf('"clicked"') >= 0) } catch (e) {}
            }
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
            case "closetab": win.closeTab(a.index === undefined || a.index === null ? win.current : a.index); host.done(cid, JSON.stringify(win.state())); break
            case "switchtab":
                if (a.index >= 0 && a.index < win.views.length) win.current = a.index
                win.changed(); host.done(cid, JSON.stringify(win.state())); break
            case "resize":
                win.devW = a.w || 0; win.devH = a.h || 0; win.mobile = !!a.mobile
                // a phone: Chrome on Android, not Safari on iPhone — sites send an iPhone H.264 videos only, which
                // Plume's Chromium (Qt WebEngine from PyPI) cannot play; Android Chrome often gets VP9 (09/11)
                prof.httpUserAgent = win.mobile
                    ? win.baseUA.replace(/\([^)]*\)/, "(Linux; Android 14; Pixel 8)").replace(/ Safari\//, " Mobile Safari/")
                    : win.baseUA
                if (a.zoom) win.view.zoomFactor = a.zoom
                win.changed()
                win.settle(cid, () => win.state(), 300); break
            case "zoom": {
                const steps = [0.5, 0.67, 0.75, 0.8, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2]
                let i = steps.findIndex(z => z >= win.view.zoomFactor - 0.001)
                if (i < 0) i = steps.length - 1
                win.view.zoomFactor = a.step === 0 ? 1 : steps[Math.max(0, Math.min(steps.length - 1, i + a.step))]
                win.changed(); host.done(cid, JSON.stringify(win.state())); break
            }
            case "console":
                host.done(cid, JSON.stringify({ logs: win.view.logs.slice(-(a.limit || 50)) })); break
            case "dialogs":
                host.done(cid, JSON.stringify({ dialogs: win.dialogs })); win.dialogs = []; break
            case "control":
                win.control = a.mode || ""
                if (a.who) win.who = a.who
                host.done(cid, "{}"); break
            case "files":                          // the panel's picker answered (no file: cancelled)
                if (win.fileRequest) {
                    if (a.files && a.files.length) win.fileRequest.dialogAccept(a.files)
                    else win.fileRequest.dialogReject()
                    win.fileRequest = null
                }
                host.done(cid, "{}"); break
            case "upload": {
                // a real click where the field is: Chromium opens a file chooser only for one (a script's click opens
                // nothing, 13/11), and onFileDialogRequested gives it the file
                if (!win.view) { host.done(cid, JSON.stringify({ error: "no tab" })); break }
                if (win.uploadCid !== "") host.done(win.uploadCid, JSON.stringify({ error: "replaced by another upload" }))
                win.uploadPath = a.path; win.uploadName = a.name || ""; win.uploadCid = cid
                win.view.runJavaScript(host.agentCall("aim", [a.ref]), WebEngineScript.ApplicationWorld, r => {
                    let o = null
                    try { o = JSON.parse(String(r)) } catch (e) {}
                    if (!o || o.error || !o.at) {
                        win.uploadPath = ""; win.uploadCid = ""
                        host.done(cid, JSON.stringify({ error: o && o.error ? o.error : "the page did not answer" }))
                        return
                    }
                    if (o.box) cursor.show(o.at, o.box, true)
                    win.pressing = true
                    const at = win.view.mapToItem(null, o.at.x * win.zoom, o.at.y * win.zoom)
                    host.press(win, at.x, at.y)
                    win.pressing = false
                    uploadWait.restart()
                })
                break
            }
            case "annotate": win.setAnnotating(!!a.on); host.done(cid, JSON.stringify(win.state())); break
            case "screenshot":
                stage.grabToImage(r => host.done(cid, JSON.stringify({ ok: r.saveToFile(a.path), path: a.path })))
                break
            default: host.done(cid, JSON.stringify({ error: "unknown action " + action }))
            }
        }
    }

    // ---- the page, at the simulated size, in a device when it is a phone or a tablet -------------------------------
    readonly property int margin: devW > 0 && embedded ? (mobile ? 28 : 16) : 0
    Rectangle {                                 // the device around the page
        visible: win.embedded && win.devW > 0 && win.mobile
        x: stage.x - bezel; y: stage.y - bezel
        width: stage.width * stage.fit + 2 * bezel; height: stage.height * stage.fit + 2 * bezel
        readonly property real bezel: Math.max(6, 11 * stage.fit)
        radius: bezel + Math.max(4, 12 * stage.fit)      // the page keeps square corners: a frame barely rounder than them
        color: win.c.night0
        border.width: 1; border.color: win.c.overlayLine
        Rectangle {                             // the camera
            anchors.horizontalCenter: parent.horizontalCenter
            y: Math.max(2, (parent.bezel - height) / 2)
            width: Math.max(4, parent.bezel * 0.45); height: width; radius: width / 2
            color: win.c.night2
        }
    }
    Rectangle {                                 // a desktop size: a plain card with its edge
        visible: win.embedded && win.devW > 0 && !win.mobile
        x: stage.x - 1; y: stage.y - 1
        width: stage.width * stage.fit + 2; height: stage.height * stage.fit + 2
        radius: 4; color: "transparent"; border.color: win.c.line
    }
    Text {                                      // 393 × 852 · 72 %
        visible: win.embedded && win.devW > 0
        anchors.horizontalCenter: parent.horizontalCenter
        y: stage.y + stage.height * stage.fit + win.margin * 0.55
        text: win.devW + " × " + win.devH + (stage.fit < 0.995 ? "  ·  " + Math.round(stage.fit * 100) + " %" : "")
        font.family: "Schibsted Grotesk"; font.pixelSize: 11; color: win.c.muted
    }
    Item {
        id: stage
        readonly property real fit: win.devW > 0 && win.embedded
                                    ? Math.min(1, (win.width - 2 * win.margin) / win.devW,
                                               (win.height - 2 * win.margin - 14) / Math.max(1, win.devH)) : 1
        width: win.devW > 0 ? win.devW : win.embedded ? win.width : 1280
        height: win.devH > 0 ? win.devH : win.embedded ? win.height : 860
        scale: fit
        transformOrigin: Item.TopLeft
        x: win.devW > 0 && win.embedded ? Math.max(0, (win.width - width * fit) / 2) : 0
        y: win.devW > 0 && win.embedded ? win.margin : 0
        Keys.onPressed: event => win.pageKey(event)
    }
    // a point of the page (CSS pixels) in this window
    function wx(px) { return stage.x + px * zoom * stage.fit }
    function wy(py) { return stage.y + py * zoom * stage.fit }

    // ---- the agent's hand: where it clicks and types, while the person watches ---------------------------------------
    Item {
        id: cursor
        objectName: "agentCursor"
        z: 25
        visible: win.embedded && opacity > 0
        opacity: 0
        Behavior on opacity { NumberAnimation { duration: 220 } }
        Behavior on x { enabled: cursor.opacity > 0; NumberAnimation { duration: 380; easing.type: Easing.OutCubic } }
        Behavior on y { enabled: cursor.opacity > 0; NumberAnimation { duration: 380; easing.type: Easing.OutCubic } }
        function show(at, box, click) {
            if (!win.embedded) return
            target.x = win.wx(box.x) - 3; target.y = win.wy(box.y) - 3
            target.width = box.w * win.zoom * stage.fit + 6; target.height = box.h * win.zoom * stage.fit + 6
            target.opacity = 1
            const p = at || { x: box.x + box.w / 2, y: box.y + box.h / 2 }
            x = win.wx(p.x); y = win.wy(p.y)
            opacity = 1
            if (click) ripple.start()
            hide.restart()
        }
        Timer { id: hide; interval: 2600; onTriggered: { cursor.opacity = 0; target.opacity = 0 } }
        Rectangle {                             // the click
            id: ring
            x: -width / 2; y: -height / 2
            width: 10; height: 10; radius: width / 2
            color: "transparent"; border.width: 2; border.color: win.c.action
            opacity: 0
            ParallelAnimation {
                id: ripple
                NumberAnimation { target: ring; property: "width"; from: 8; to: 46; duration: 520; easing.type: Easing.OutCubic }
                NumberAnimation { target: ring; property: "height"; from: 8; to: 46; duration: 520; easing.type: Easing.OutCubic }
                NumberAnimation { target: ring; property: "opacity"; from: 0.9; to: 0; duration: 520 }
            }
        }
        Canvas {                                // an arrow, Klein with a white edge
            id: arrow
            width: 22; height: 24
            onPaint: {
                const g = getContext("2d")
                g.reset()
                g.beginPath()
                g.moveTo(2, 1); g.lineTo(2, 19); g.lineTo(7, 14.5); g.lineTo(10.5, 22); g.lineTo(13.5, 20.6)
                g.lineTo(10, 13.2); g.lineTo(16.5, 13.2); g.closePath()
                g.fillStyle = String(win.c.action); g.strokeStyle = "#FFFFFF"; g.lineWidth = 1.6; g.lineJoin = "round"
                g.fill(); g.stroke()
            }
            Connections { target: theme; function onChanged() { arrow.requestPaint() } }
        }
        Rectangle {                             // its name
            x: 16; y: 20
            width: whoText.implicitWidth + 16; height: 22; radius: 11
            color: win.c.action
            Text { id: whoText; anchors.centerIn: parent; text: win.who
                   font.family: "Schibsted Grotesk"; font.pixelSize: 11; font.weight: Font.DemiBold; color: win.c.actionText }
        }
    }
    Rectangle {                                 // the element it acts on
        id: target
        z: 24
        visible: win.embedded && opacity > 0
        opacity: 0
        Behavior on opacity { NumberAnimation { duration: 260 } }
        radius: 5; color: "transparent"; border.width: 2; border.color: win.c.action
    }

    // ---- who drives: the agent holds the page, the person can take it ------------------------------------------------
    Timer {                                    // the agent's click opened no file chooser: it is told so
        id: uploadWait
        interval: 2500
        onTriggered: {
            win.uploadPath = ""
            if (win.view) win.view.runJavaScript(host.agentCall("unaim", []), WebEngineScript.ApplicationWorld)
            if (win.uploadCid !== "") {
                host.done(win.uploadCid, JSON.stringify({ error: "the click opened no file chooser: give the ref of the file field, or of the button that adds a file" }))
                win.uploadCid = ""
            }
        }
    }
    // What the agent is doing (« Ornis clique »), and whether one of its actions waits for the person
    onAgentDrivesChanged: {
        if (agentDrives && !annotating) veil.forceActiveFocus()
        else if (embedded && !annotating && view) view.forceActiveFocus()
    }
    property string doing: ""
    property bool waiting: false
    Connections {
        target: host
        function onChanged() { win.doing = host.doingOf(win.owner); win.waiting = host.waitingFor(win.owner) }
    }
    Timer { interval: 1000; repeat: true; running: win.embedded && win.control !== ""
            onTriggered: { win.doing = host.doingOf(win.owner); win.waiting = host.waitingFor(win.owner) } }

    // The agent drives: the page in a living frame of its colour, a light veil (the page reads well, takes no click),
    // and at the bottom its presence (who, what it does now) with « Prendre le contrôle » (or Échap).
    Item {
        id: veil
        anchors.fill: parent
        z: 30
        visible: opacity > 0
        opacity: win.agentDrives && !win.annotating ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: win.motion ? 220 : 0 } }
        focus: win.agentDrives && !win.annotating
        Keys.onPressed: event => {                               // the page gets no key while the agent drives
            if (event.key === Qt.Key_Escape) host.takeControl(win.owner)
            event.accepted = true
        }
        Rectangle {                             // a light veil: someone else drives
            x: stage.x; y: stage.y
            width: stage.width * stage.fit; height: stage.height * stage.fit
            color: Qt.rgba(win.ink.r, win.ink.g, win.ink.b, 0.035)
        }
        Rectangle {                             // its frame, breathing
            id: liveFrame
            x: stage.x; y: stage.y
            width: stage.width * stage.fit; height: stage.height * stage.fit
            color: "transparent"; border.width: 2; border.color: win.ink
            SequentialAnimation on opacity {
                running: veil.visible && win.motion; loops: Animation.Infinite
                NumberAnimation { to: 0.45; duration: 1400; easing.type: Easing.InOutSine }
                NumberAnimation { to: 1; duration: 1400; easing.type: Easing.InOutSine }
            }
            Rectangle { anchors.fill: parent; anchors.margins: 2; color: "transparent"
                        border.width: 6; border.color: win.tint(0.10) }
        }
        MouseArea {
            anchors.fill: parent
            enabled: !win.pressing
            acceptedButtons: Qt.AllButtons
            hoverEnabled: true
            onWheel: wheel => wheel.accepted = true
        }
        RectangularShadow {
            anchors.fill: pill
            radius: pill.radius
            blur: 32; offset.y: 12
            color: win.c.shadow
        }
        Rectangle {
            id: pill
            objectName: "browserVeil"
            x: (win.width - width) / 2
            y: win.height - height - (win.agentDrives ? 18 : 2)
            Behavior on y { NumberAnimation { duration: win.motion ? 260 : 0; easing.type: Easing.OutCubic } }
            width: Math.min(pillRow.implicitWidth + 16, win.width - 24); height: 60; radius: 30
            color: win.c.overlay
            border.width: 1; border.color: win.c.overlayLine
            clip: true
            Row {
                id: pillRow
                anchors.verticalCenter: parent.verticalCenter
                x: 8
                spacing: 12
                Item {                          // who drives: its mark, with a ring that goes out like a pulse
                    width: 44; height: 44
                    anchors.verticalCenter: parent.verticalCenter
                    Rectangle {
                        id: pulse
                        anchors.centerIn: parent
                        width: 44; height: 44; radius: width / 2
                        color: "transparent"; border.width: 2; border.color: win.ink
                        SequentialAnimation {
                            running: veil.visible && win.motion; loops: Animation.Infinite
                            ParallelAnimation {
                                NumberAnimation { target: pulse; property: "scale"; from: 0.8; to: 1.25; duration: 1400; easing.type: Easing.OutCubic }
                                NumberAnimation { target: pulse; property: "opacity"; from: 0.7; to: 0; duration: 1400 }
                            }
                            PauseAnimation { duration: 300 }
                        }
                    }
                    Rectangle {
                        anchors.centerIn: parent
                        width: 36; height: 36; radius: 18
                        color: win.ink
                        Icon { anchors.centerIn: parent; visible: win.owner === "you"; name: "ornis"; size: 19; color: win.c.actionText }
                        Text { anchors.centerIn: parent; visible: win.owner !== "you"
                               text: (win.who || "?").charAt(0).toUpperCase()
                               font.family: "Schibsted Grotesk"; font.pixelSize: 16; font.weight: Font.Bold; color: win.c.actionText }
                    }
                }
                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2
                    Text { text: (app.t.browser_control_agent || "%1 a le contrôle").replace("%1", win.who)
                           font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold; color: win.c.text }
                    Text { text: win.doing || app.t.browser_control_hint || ""
                           width: Math.min(implicitWidth, Math.max(120, win.width - 360)); elide: Text.ElideRight
                           font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: win.c.muted }
                }
                OButton {
                    objectName: "browserTake"; pill: true
                    anchors.verticalCenter: parent.verticalCenter
                    kind: "primary"; iconName: "hand"; iconSize: 16; height_: 44
                    text: app.t.browser_control_take || "Prendre le contrôle"
                    tip: (app.t.browser_control_take || "Prendre le contrôle") + "  (Échap)"
                    onClicked: host.takeControl(win.owner)
                }
            }
        }
    }

    // The person took it: the page is theirs again, a small bar says the agent waits and gives it back in one click.
    RectangularShadow {
        anchors.fill: handBar
        visible: handBar.visible
        opacity: handBar.opacity
        z: 29
        radius: handBar.radius
        blur: 26; offset.y: 10
        color: win.c.shadow
    }
    Rectangle {
        id: handBar
        objectName: "browserHandBar"
        z: 29.5
        visible: opacity > 0
        opacity: win.embedded && win.control === "person" && !win.annotating ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: win.motion ? 200 : 0 } }
        x: (win.width - width) / 2
        y: win.height - height - 18
        width: Math.min(handRow.implicitWidth + 14 + 6, win.width - 24); height: 48; radius: 24
        color: win.c.overlay
        border.width: 1; border.color: win.c.overlayLine
        clip: true
        Row {
            id: handRow
            anchors.verticalCenter: parent.verticalCenter
            x: 14
            spacing: 10
            Rectangle { width: 9; height: 9; radius: 5; color: win.c.ok; anchors.verticalCenter: parent.verticalCenter }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                Text { text: app.t.browser_control_you || "Vous avez le contrôle"
                       font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold; color: win.c.text }
                Text { visible: win.waiting
                       text: (app.t.browser_doing_wait || "%1 attend que vous rendiez le contrôle").replace("%1", win.who)
                       font.family: "Schibsted Grotesk"; font.pixelSize: 11; color: win.c.muted }
            }
            Row {                               // it waits: three dots
                visible: win.waiting
                anchors.verticalCenter: parent.verticalCenter
                spacing: 3
                Repeater {
                    model: 3
                    Rectangle {
                        required property int index
                        width: 5; height: 5; radius: 3; color: win.ink
                        SequentialAnimation on opacity {
                            running: handBar.visible && win.waiting && win.motion; loops: Animation.Infinite
                            PauseAnimation { duration: index * 160 }
                            NumberAnimation { to: 0.2; duration: 380 }
                            NumberAnimation { to: 1; duration: 380 }
                            PauseAnimation { duration: (2 - index) * 160 }
                        }
                    }
                }
            }
            OButton {
                objectName: "browserGiveInPage"; pill: true
                anchors.verticalCenter: parent.verticalCenter
                kind: win.waiting ? "primary" : "secondary"; iconName: "ornis"; iconSize: 15; height_: 36
                text: (app.t.browser_control_give || "Rendre à %1").replace("%1", win.who)
                onClicked: host.releaseControl(win.owner)
            }
        }
    }

    // ---- Annoter: point at places (or frame a zone), say what to change, send them together -------------------------
    // The page is framed in the colour of the action, the element under the pointer is outlined with its name (as a
    // browser's inspector does), each place gets a numbered pin, its note a card pointing at it, and a bar at the bottom
    // holds the batch. Alt picks the exact element under the pointer (else: the button or link it belongs to).
    property var marks: []                      // [{ element, note, box }]: the places annotated, numbered
    property int editing: -1                    // the mark whose note is open (marks.length: a new one)
    property var picked: ({})
    readonly property color ink: c.action
    readonly property bool motion: Qt.styleHints.reduceMotion !== true
    function tint(a) { return Qt.rgba(ink.r, ink.g, ink.b, a) }
    function setAnnotating(on) {
        annotating = on
        if (!on) { note.visible = false; editing = -1; hoverBox.width = 0; zone.active = false }
        // while annotating, the keys are ours (the page would keep Échap); then the page's again
        if (embedded) { if (on) annotKeys.forceActiveFocus(); else if (view) view.forceActiveFocus() }
        changed()
    }
    Item {
        id: annotKeys
        Keys.onPressed: event => win.pageKey(event)
    }
    function describeEl(el) {                   // « button · Se connecter », « Zone · 320 × 140 »
        if (!el) return ""
        if (el.kind === "area") return (app.t.browser_annotate_zone || "Zone") + "  ·  " + el.rect.w + " × " + el.rect.h
        const kind = el.role || el.tag || ""
        const name = (el.name || el.text || "").trim()
        return kind + (name ? (kind ? "  ·  " : "") + name : "")
    }
    function openNote(i, element) {
        editing = i
        picked = element
        noteText.text = i < marks.length ? marks[i].note : ""
        placeNote()
        note.visible = true
        noteIn.restart()
        noteText.forceActiveFocus()
    }
    function placeNote() {                      // under the place, else above it; the caret points at its middle
        if (editing < 0) return
        const b = editing < marks.length ? marks[editing].box : picked.rect
        if (!b) return
        const bx = wx(b.x), by = wy(b.y), bw = b.w * zoom * stage.fit, bh = b.h * zoom * stage.fit
        const below = by + bh + 14 + note.height < win.height - 80 || by - note.height - 14 < 8
        note.x = Math.max(12, Math.min(win.width - note.width - 12, bx + bw / 2 - 40))
        note.y = below ? Math.min(win.height - note.height - 8, by + bh + 14) : by - note.height - 14
        note.below = below
        note.aim = Math.max(18, Math.min(note.width - 18, bx + Math.min(bw, 80) / 2 - note.x))
    }
    function keepNote() {                       // the open note joins the batch (an empty new one is dropped)
        const text = noteText.text.trim()
        if (editing >= 0) {
            if (editing < marks.length) marks = marks.map((m, k) => k === editing ? Object.assign({}, m, { note: text }) : m)
            else if (text) marks = marks.concat([{ element: picked, note: text, box: picked.rect }])
        }
        note.visible = false; noteText.text = ""; editing = -1; hoverBox.width = 0
        if (annotating) annotKeys.forceActiveFocus(); else if (view) view.forceActiveFocus()
        changed()
    }
    function dropNote() {
        if (editing >= 0 && editing < marks.length) marks = marks.filter((_, k) => k !== editing)
        note.visible = false; noteText.text = ""; editing = -1
        if (annotating) annotKeys.forceActiveFocus(); else if (view) view.forceActiveFocus()
        changed()
    }
    function sendMarks() {
        keepNote()
        if (!marks.length) return
        host.annotated(owner, JSON.stringify({ url: view ? view.url.toString() : "",
                                               size: { w: stage.width, h: stage.height, mobile: mobile },
                                               items: marks.map(m => ({ element: m.element, note: m.note })) }))
        marks = []
        setAnnotating(false)
    }
    Timer {                                     // the marks follow their elements (the page scrolls, moves)
        interval: 300; repeat: true
        running: win.annotating && win.marks.length > 0 && !!win.view
        onTriggered: win.view.runJavaScript(host.agentCall("rects", [win.marks.map(m => m.element.selector || "")]),
                                            WebEngineScript.ApplicationWorld, r => {
            if (!r) return
            const boxes = JSON.parse(r)
            if (!Array.isArray(boxes) || boxes.length !== win.marks.length) return
            win.marks = win.marks.map((m, i) => boxes[i] ? Object.assign({}, m, { box: boxes[i] }) : m)
            if (note.visible && win.editing < win.marks.length) win.placeNote()
        })
    }

    Rectangle {                                 // Annoter is on: the page framed in the action's colour
        z: 9
        x: stage.x; y: stage.y
        width: stage.width * stage.fit; height: stage.height * stage.fit
        color: "transparent"
        border.width: 2; border.color: win.tint(0.55)
        opacity: win.annotating ? 1 : 0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: 180 } }
        Rectangle {                             // a soft glow inside the edge
            anchors.fill: parent; anchors.margins: 2
            color: "transparent"; border.width: 4; border.color: win.tint(0.10)
        }
    }
    Rectangle {                                 // what the pointer is on
        id: hoverBox
        objectName: "annotationHover"
        property string label: ""
        property bool moving: false             // no glide from nothing: it appears where it is
        visible: win.annotating && width > 0 && !zone.active
        z: 10
        color: win.tint(0.07); border.color: win.ink; border.width: 1.5; radius: 6
        Behavior on x { enabled: hoverBox.moving && win.motion; NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }
        Behavior on y { enabled: hoverBox.moving && win.motion; NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }
        Behavior on width { enabled: hoverBox.moving && win.motion; NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }
        Behavior on height { enabled: hoverBox.moving && win.motion; NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }
        Rectangle {                             // its name and size, as an inspector shows them
            visible: hoverBox.label !== "" && !note.visible
            x: Math.min(0, win.width - hoverBox.x - width - 8)
            y: hoverBox.y > height + 8 ? -height - 6 : hoverBox.height + 6
            width: Math.min(tagRow.implicitWidth + 16, 360); height: 24; radius: 7
            color: win.ink
            clip: true
            Row {
                id: tagRow
                anchors.verticalCenter: parent.verticalCenter
                x: 8
                spacing: 8
                Text { text: hoverBox.label; color: win.c.actionText
                       font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold }
                Text { text: Math.round(hoverBox.width / win.zoom / stage.fit) + " × " + Math.round(hoverBox.height / win.zoom / stage.fit)
                       color: win.c.actionText; opacity: 0.7
                       font.family: "JetBrains Mono"; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter }
            }
        }
    }
    Rectangle {                                 // a zone being framed
        id: zone
        property bool active: false
        property real x0: 0
        property real y0: 0
        visible: active
        z: 10
        color: win.tint(0.10); radius: 4
        border.width: 1.5; border.color: win.ink
    }
    MouseArea {
        x: stage.x; y: stage.y
        width: stage.width * stage.fit; height: stage.height * stage.fit
        z: 11
        visible: win.annotating
        hoverEnabled: true
        cursorShape: Qt.CrossCursor
        property real lastAsk: 0
        property bool pressedHere: false
        function boxFor(r) {
            if (!r || r.w === undefined) return
            hoverBox.moving = hoverBox.width > 0
            hoverBox.x = win.wx(r.x); hoverBox.y = win.wy(r.y)
            hoverBox.width = r.w * win.zoom * stage.fit; hoverBox.height = r.h * win.zoom * stage.fit
            if (r.label !== undefined) hoverBox.label = r.label
        }
        function css(m) { return [Math.round(m.x / stage.fit / win.zoom), Math.round(m.y / stage.fit / win.zoom)] }
        function exact(m) { return !!(m.modifiers & Qt.AltModifier) }
        onPressed: mouse => {
            pressedHere = !note.visible
            zone.x0 = mouse.x + x; zone.y0 = mouse.y + y
        }
        onPositionChanged: mouse => {
            if (pressed && pressedHere) {
                const px = mouse.x + x, py = mouse.y + y
                if (!zone.active && Math.abs(px - zone.x0) + Math.abs(py - zone.y0) > 10) zone.active = true
                if (zone.active) {
                    zone.x = Math.min(px, zone.x0); zone.y = Math.min(py, zone.y0)
                    zone.width = Math.abs(px - zone.x0); zone.height = Math.abs(py - zone.y0)
                }
                return
            }
            if (!win.view || Date.now() - lastAsk < 70 || note.visible) return
            lastAsk = Date.now()
            win.view.runJavaScript(host.agentCall("rect", css(mouse).concat([exact(mouse)])), WebEngineScript.ApplicationWorld,
                                   r => { if (r) boxFor(JSON.parse(r)) })
        }
        onExited: if (!note.visible) hoverBox.width = 0
        onReleased: mouse => {
            if (!win.view) return
            if (zone.active) {                  // a zone: what is in it
                zone.active = false
                const sx = (zone.x - stage.x) / stage.fit / win.zoom, sy = (zone.y - stage.y) / stage.fit / win.zoom
                const sw = zone.width / stage.fit / win.zoom, sh = zone.height / stage.fit / win.zoom
                win.view.runJavaScript(host.agentCall("area", [sx, sy, sw, sh]), WebEngineScript.ApplicationWorld, r => {
                    const el = r ? JSON.parse(r) : ({})
                    if (!el.rect) return
                    boxFor({ x: el.rect.x, y: el.rect.y, w: el.rect.w, h: el.rect.h, label: "" })
                    win.openNote(win.marks.length, el)
                })
                return
            }
            if (!pressedHere) { if (note.visible) win.keepNote(); return }   // a click elsewhere keeps the note
            win.view.runJavaScript(host.agentCall("pick", css(mouse).concat([exact(mouse)])), WebEngineScript.ApplicationWorld, r => {
                const el = r ? JSON.parse(r) : ({})
                if (!el.rect) return
                boxFor(el.rect)
                win.openNote(win.marks.length, el)
            })
        }
    }
    Repeater {                                  // the numbered places
        model: win.annotating ? win.marks : []
        Item {
            id: mark
            required property var modelData
            required property int index
            readonly property bool current: win.editing === index
            z: current ? 12.5 : 12
            x: win.wx(modelData.box.x); y: win.wy(modelData.box.y)
            width: modelData.box.w * win.zoom * stage.fit; height: modelData.box.h * win.zoom * stage.fit
            Rectangle {
                anchors.fill: parent
                radius: 6; color: win.tint(mark.current ? 0.10 : 0.05)
                border.width: 1.5; border.color: win.ink
                opacity: mark.current || pinMouse.containsMouse ? 1 : 0.65
            }
            RectangularShadow {
                anchors.fill: pin
                radius: pin.radius; blur: 10; offset.y: 3
                color: win.c.shadow
                scale: pin.scale
            }
            Rectangle {
                id: pin
                objectName: "annotationPin"
                x: -13; y: -13
                width: 26; height: 26; radius: 13
                color: win.ink
                border.width: 2; border.color: win.c.overlay
                scale: pinMouse.containsMouse ? 1.12 : 1
                Behavior on scale { enabled: win.motion; NumberAnimation { duration: 140; easing.type: Easing.OutBack } }
                NumberAnimation on scale { running: win.motion; from: 0.3; to: 1; duration: 280; easing.type: Easing.OutBack }
                Text { anchors.centerIn: parent; text: mark.index + 1
                       font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.Bold; color: win.c.actionText }
                MouseArea { id: pinMouse; anchors.fill: parent; anchors.margins: -4; hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: { win.keepNote(); win.openNote(mark.index, mark.modelData.element) } }
            }
            Rectangle {                         // its note, under the pointer
                visible: pinMouse.containsMouse && !mark.current && mark.modelData.note !== ""
                x: 20; y: -13
                width: Math.min(280, peek.implicitWidth + 22); height: peek.implicitHeight + 14; radius: 9
                color: win.c.night1
                Text { id: peek; x: 11; y: 7; width: Math.min(258, implicitWidth); wrapMode: Text.Wrap; maximumLineCount: 4
                       elide: Text.ElideRight; text: mark.modelData.note; color: win.c.onNight
                       font.family: "Schibsted Grotesk"; font.pixelSize: 12 }
            }
        }
    }

    // ---- the note of one place: a card pointing at it ----------------------------------------------------------------
    RectangularShadow {
        anchors.fill: note
        visible: note.visible
        opacity: note.opacity
        z: 12.8
        radius: note.radius
        blur: 36; offset.y: 14
        color: win.c.shadow
    }
    Rectangle {                                 // the caret, half under the card
        visible: note.visible
        opacity: note.opacity
        z: 12.9
        width: 14; height: 14; rotation: 45
        x: note.x + note.aim - 7
        y: note.below ? note.y - 7 : note.y + note.height - 7
        color: win.c.overlay
        border.width: 1; border.color: win.c.overlayLine
    }
    Rectangle {
        id: note
        objectName: "annotationNote"
        property bool below: true
        property real aim: 24
        visible: false
        z: 13
        width: Math.min(400, win.width - 24); height: noteCol.implicitHeight + 28
        radius: 14
        color: win.c.overlay
        border.width: 1; border.color: win.c.overlayLine
        transformOrigin: below ? Item.Top : Item.Bottom
        onHeightChanged: if (visible) win.placeNote()
        ParallelAnimation {
            id: noteIn
            NumberAnimation { target: note; property: "opacity"; from: 0; to: 1; duration: win.motion ? 160 : 0 }
            NumberAnimation { target: note; property: "scale"; from: 0.96; to: 1; duration: win.motion ? 200 : 0; easing.type: Easing.OutCubic }
        }
        Rectangle {                             // the card's caret is covered by its fill: the edge stays visible
            x: note.aim - 8; y: note.below ? 0 : note.height - 1
            width: 16; height: 1; color: win.c.overlay
        }
        Column {
            id: noteCol
            x: 14; y: 14
            width: parent.width - 28
            spacing: 12
            Row {
                width: parent.width
                spacing: 10
                Rectangle {
                    width: 28; height: 28; radius: 14; color: win.ink
                    anchors.verticalCenter: parent.verticalCenter
                    Text { anchors.centerIn: parent; text: win.editing + 1
                           font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.Bold; color: win.c.actionText }
                }
                Column {
                    width: parent.width - 28 - 10 - 34
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 1
                    Text {
                        width: parent.width
                        text: win.describeEl(win.editing < win.marks.length ? win.marks[win.editing].element : win.picked)
                        elide: Text.ElideRight
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold; color: win.c.text
                    }
                    Text {
                        readonly property var el: win.editing >= 0 && win.editing < win.marks.length ? win.marks[win.editing].element : win.picked
                        width: parent.width
                        visible: text !== ""
                        text: el ? (el.kind === "area" ? (el.within || "") : (el.selector || "")) : ""
                        elide: Text.ElideMiddle
                        font.family: "JetBrains Mono"; font.pixelSize: 11; color: win.c.faint
                    }
                }
                OButton { kind: "quiet"; iconName: "close"; iconSize: 13; height_: 28; tip: app.t.cancel
                          anchors.verticalCenter: parent.verticalCenter
                          onClicked: win.editing < win.marks.length ? win.keepNote() : win.dropNote() }
            }
            OTextArea {
                id: noteText
                objectName: "annotationText"
                width: parent.width
                height: Math.max(84, Math.min(170, implicitHeight))
                font.pixelSize: 14
                placeholderText: app.t.browser_annotate_ph
                Keys.onReturnPressed: event => {
                    if (event.modifiers & Qt.ShiftModifier) { event.accepted = false; return }
                    win.sendMarks()
                }
                Keys.onEnterPressed: event => win.sendMarks()
                Keys.onEscapePressed: event => win.editing < win.marks.length ? win.keepNote() : win.dropNote()
            }
            Item {
                width: parent.width; height: 34
                OButton {
                    anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
                    visible: win.editing < win.marks.length
                    kind: "quiet"; iconName: "trash"; iconSize: 14; height_: 32; text: app.t.browser_annotate_remove
                    onClicked: win.dropNote()
                }
                OButton {
                    objectName: "annotationMore"
                    anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
                    visible: win.editing >= win.marks.length
                    kind: "quiet"; iconName: "plus"; iconSize: 14; height_: 32
                    text: app.t.browser_annotate_add
                    enabled: noteText.text.trim() !== ""
                    onClicked: win.keepNote()
                }
                Text {
                    anchors.right: sendBtn.left; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
                    visible: parent.width > 330
                    text: "⏎"
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: win.c.faint
                }
                OButton {
                    id: sendBtn
                    objectName: "annotationSend"
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    kind: "primary"; iconName: "send"; iconSize: 14; height_: 32
                    readonly property int count: win.marks.length + (win.editing >= win.marks.length && noteText.text.trim() !== "" ? 1 : 0)
                    text: (app.t.browser_annotate_send_to || "Envoyer à %1").replace("%1", win.who || "Ornis") + (count > 1 ? "  ·  " + count : "")
                    enabled: count > 0
                    onClicked: win.sendMarks()
                }
            }
        }
    }

    // ---- the bar of Annoter: what to do, the batch, send -------------------------------------------------------------
    RectangularShadow {
        anchors.fill: tray
        visible: tray.visible
        opacity: tray.opacity
        z: 13
        radius: tray.radius
        blur: 32; offset.y: 12
        color: win.c.shadow
    }
    Rectangle {
        id: tray
        objectName: "annotationTray"
        visible: opacity > 0
        opacity: win.annotating ? 1 : 0
        z: 13.5
        x: (win.width - width) / 2
        y: win.height - height - (win.annotating ? 18 : 2)
        Behavior on opacity { NumberAnimation { duration: win.motion ? 180 : 0 } }
        Behavior on y { NumberAnimation { duration: win.motion ? 240 : 0; easing.type: Easing.OutCubic } }
        width: Math.min(trayRow.implicitWidth + 16, win.width - 24); height: 56; radius: 28
        color: win.c.overlay
        border.width: 1; border.color: win.c.overlayLine
        clip: true
        Row {
            id: trayRow
            anchors.verticalCenter: parent.verticalCenter
            x: 8
            spacing: 10
            Rectangle {
                width: 40; height: 40; radius: 20
                color: win.tint(0.12)
                Icon { anchors.centerIn: parent; name: "edit"; size: 17; color: win.ink }
            }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                spacing: 1
                Text {
                    text: win.marks.length === 0 ? app.t.browser_annotate
                          : (win.marks.length === 1 ? app.t.browser_annotate_one : app.t.browser_annotate_many.replace("%1", win.marks.length))
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold; color: win.c.text
                }
                Text {
                    text: app.t.browser_annotate_hint || app.t.browser_annotate_start
                    visible: win.width > 640 || win.marks.length === 0
                    font.family: "Schibsted Grotesk"; font.pixelSize: 11; color: win.c.muted
                }
            }
            Row {                               // the places, small: one click opens a note again
                anchors.verticalCenter: parent.verticalCenter
                visible: win.marks.length > 0
                spacing: -6
                leftPadding: 4
                Repeater {
                    model: Math.min(win.marks.length, 6)
                    Rectangle {
                        required property int index
                        width: 24; height: 24; radius: 12
                        color: win.editing === index ? win.c.actionHover : win.ink
                        border.width: 2; border.color: win.c.overlay
                        Text { anchors.centerIn: parent; text: parent.index + 1
                               font.family: "Schibsted Grotesk"; font.pixelSize: 11; font.weight: Font.Bold; color: win.c.actionText }
                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                    onClicked: { win.keepNote(); win.openNote(parent.index, win.marks[parent.index].element) } }
                    }
                }
            }
            Rectangle { width: 1; height: 26; color: win.c.line; anchors.verticalCenter: parent.verticalCenter
                        visible: win.marks.length > 0 }
            OButton { pill: true; visible: win.marks.length > 0 && !note.visible; kind: "quiet"; height_: 36; text: app.t.browser_annotate_clear
                      anchors.verticalCenter: parent.verticalCenter
                      onClicked: { win.marks = []; win.changed() } }
            OButton { objectName: "annotationTraySend"; pill: true
                      visible: win.marks.length > 0 && !note.visible; kind: "primary"; iconName: "send"; iconSize: 14; height_: 40
                      anchors.verticalCenter: parent.verticalCenter
                      text: (app.t.browser_annotate_send_to || "Envoyer à %1").replace("%1", win.who || "Ornis")
                      onClicked: win.sendMarks() }
            OButton { pill: true; kind: "quiet"; iconName: "close"; iconSize: 14; height_: 40; tip: app.t.browser_annotate_quit
                      anchors.verticalCenter: parent.verticalCenter
                      onClicked: win.setAnnotating(false) }
        }
    }

    // In the panel, the focus is mostly in the page. A Shortcut of this embedded window never fires there (seen on X,
    // 10/11), but Chromium hands the keys a page did not use to the view's parent item: the stage takes them here.
    readonly property bool personKeys: embedded && control !== "agent"
    function pageKey(event) {
        const ctrl = event.modifiers & Qt.ControlModifier, shift = event.modifiers & Qt.ShiftModifier,
              alt = event.modifiers & Qt.AltModifier, k = event.key
        let done = true
        if (ctrl && shift && k === Qt.Key_D) setAnnotating(!annotating)
        else if (k === Qt.Key_Escape && annotating && !note.visible) setAnnotating(false)
        else if (!personKeys) done = false
        else if (ctrl && !shift && k === Qt.Key_L || alt && k === Qt.Key_D) host.focusAddress(owner)
        else if (ctrl && !shift && k === Qt.Key_T) host.act(owner, "newtab")
        else if (ctrl && !shift && k === Qt.Key_W) host.act(owner, "closetab")
        else if (ctrl && !shift && k === Qt.Key_R || k === Qt.Key_F5) host.act(owner, "reload")
        else if (alt && k === Qt.Key_Left) host.act(owner, "back")
        else if (alt && k === Qt.Key_Right) host.act(owner, "forward")
        else if (ctrl && (k === Qt.Key_Equal || k === Qt.Key_Plus)) host.zoom(owner, 1)
        else if (ctrl && k === Qt.Key_Minus) host.zoom(owner, -1)
        else if (ctrl && k === Qt.Key_0) host.zoom(owner, 0)
        else done = false
        event.accepted = done
    }

    Component.onCompleted: addTab(startUrl)
}
