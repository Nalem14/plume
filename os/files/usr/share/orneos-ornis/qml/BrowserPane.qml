// The Navigateur panel: the browser of the bot open in front (or the person's, in a Code session), live. The page is
// the browser's own window (BrowserWindow.qml) embedded here: you watch the bot work, take the control back, simulate a
// phone, and Annoter places of the page to ask for changes. A tool to check renderings and let bots work, not a
// browser for everything: tabs, an address, a few keys. Closing the panel leaves the browser working unseen.
import QtCore as Std               // StandardPaths only: its Settings would hide ours
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import QtQuick.Dialogs
import "components"

Item {
    id: pane
    property bool shownNow: false
    readonly property string owner: code.bot !== "" ? code.bot : "you"
    readonly property var c: theme.c
    property var st: ({})
    property string watching: ""
    readonly property bool agentDrives: pane.st.control === "agent"
    readonly property bool personDrives: pane.st.control === "person"
    readonly property bool canDrive: !agentDrives
    property string filesFor: ""                   // whose page asked for files, until the picker answers
    readonly property var extensions: ({
        "image/*": "*.jpg *.jpeg *.png *.gif *.webp *.heic *.heif *.avif *.bmp *.tif *.tiff *.svg",
        "video/*": "*.mp4 *.mov *.webm *.mkv *.avi *.m4v *.3gp", "audio/*": "*.mp3 *.m4a *.aac *.ogg *.opus *.wav *.flac",
        "image/jpeg": "*.jpg *.jpeg", "image/png": "*.png", "image/gif": "*.gif", "image/webp": "*.webp",
        "image/heic": "*.heic", "image/heif": "*.heif", "image/avif": "*.avif", "image/svg+xml": "*.svg",
        "video/mp4": "*.mp4", "video/quicktime": "*.mov", "video/webm": "*.webm", "application/pdf": "*.pdf",
        "text/plain": "*.txt", "text/csv": "*.csv", "application/zip": "*.zip" })
    // what the field accepts (accept="image/*,.pdf"), then every file: a type left unknown here never hides a file
    function filters(types) {
        const all = app.t.browser_files_all + " (*)"
        const known = []
        for (const t of types || []) {
            const k = String(t).trim().toLowerCase()
            const e = k.startsWith(".") ? "*" + k : (pane.extensions[k] || "")
            for (const one of e.split(" ")) if (one && known.indexOf(one) < 0) known.push(one)
        }
        return known.length ? [app.t.browser_files_ok + " (" + known.join(" ") + ")", all] : [all]
    }
    function filesChosen(urls) {
        const who = pane.filesFor
        pane.filesFor = ""
        if (who !== "" && browser) browser.filesChosen(who, urls.map(u => u.toString()))
    }
    function refresh() {
        st = browser ? browser.stateOf(owner) : ({})
        if (!presets.length && st.presets) presets = st.presets
        // the tabs change in place (a page loading updates the state many times a second: chips made again each
        // time would lose their hover and blink)
        const list = st.tabs || []
        for (let i = 0; i < list.length; ++i) {
            const row = { tabIndex: list[i].index, title: list[i].title || "", url: list[i].url || "", on: !!list[i].current,
                          loading: !!list[i].loading, favicon: list[i].icon || "" }
            if (i < tabsModel.count) tabsModel.set(i, row); else tabsModel.append(row)
        }
        while (tabsModel.count > list.length) tabsModel.remove(tabsModel.count - 1)
    }
    ListModel { id: tabsModel }
    property var presets: []                 // read once: the menu's items are not made again at each update
    function watch() {
        if (!browser) return
        const want = shownNow ? owner : ""
        if (watching === want) return
        if (watching !== "") { frame.window = null; browser.setWatched(watching, false) }   // let go first, then hide it
        watching = want
        if (want !== "") {          // the window first (it may not exist yet), then usable, then here
            const w = browser.windowFor(want)
            browser.setWatched(want, true)
            frame.window = w
        }
        refresh()
    }
    onShownNowChanged: watch()
    onOwnerChanged: watch()
    Component.onDestruction: if (browser && watching !== "") browser.setWatched(watching, false)
    Connections {
        target: browser
        function onChanged() { pane.refresh() }
        // a file field clicked in the page: the picker opens here, over Plume's window (the page's own window is a
        // child of the panel, a dialog made from it never shows), and the files go back to the field
        function onFilesWanted(who, mode, types, name) {
            pane.filesFor = who
            if (mode === 2) { folderPicker.open(); return }
            filePicker.fileMode = mode === 3 ? FileDialog.SaveFile : mode === 1 ? FileDialog.OpenFiles : FileDialog.OpenFile
            filePicker.nameFilters = pane.filters(types)
            filePicker.selectedFile = mode === 3 && name ? filePicker.currentFolder + "/" + name : ""
            filePicker.open()
        }
        function onAddressWanted(who) { if (who === pane.owner && pane.shownNow) { address.forceActiveFocus(); address.selectAll() } }
    }
    // A dialog or menu of the window opened over the panel would be drawn under the page (a native window above the
    // window's items): the page steps aside while one is open.
    property bool covered: false
    function checkCovered() {
        const o = pane.Overlay.overlay
        let any = false
        if (o) for (let i = 0; i < o.children.length; ++i) {      // a dialog or a menu over the page (not a tooltip)
            const k = o.children[i]
            if (!k.visible || k.width < 120 || k.height < 80) continue
            const p = k.mapToItem(pane, 0, 0)
            if (p.x + k.width > 0 && p.x < pane.width && p.y + k.height > 0 && p.y < pane.height) any = true
        }
        covered = any
    }
    Timer { interval: 150; repeat: true; running: pane.shownNow; onTriggered: pane.checkCovered() }
    Timer { interval: 2000; repeat: true; running: pane.shownNow && !!pane.st.activity; onTriggered: pane.refresh() }   // it fades after 8 s
    function shortUrl(u) {
        return String(u || "").replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "")
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ---- the tabs, always (+ to open one), and who drives -------------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 8; Layout.rightMargin: 8; Layout.topMargin: 8
            spacing: 4
            Flickable {
                id: tabsFlick
                Layout.fillWidth: true
                Layout.preferredHeight: 30
                contentWidth: tabsRow.width
                clip: true
                flickableDirection: Flickable.HorizontalFlick
                boundsBehavior: Flickable.StopAtBounds
                Row {
                    id: tabsRow
                    spacing: 4
                    Repeater {
                        model: tabsModel
                        AbstractButton {
                            id: tabChip
                            objectName: "browserTab"
                            required property int tabIndex
                            required property string title
                            required property string url
                            required property bool on
                            required property bool loading
                            required property string favicon
                            height: 30
                            width: Math.max(92, Math.min(200, (tabsFlick.width - 34) / Math.max(1, tabsModel.count) - 4))
                            hoverEnabled: true
                            enabled: pane.canDrive || on
                            onClicked: if (!on) browser.switchTab(pane.owner, tabIndex)
                            ToolTip.text: title + "\n" + pane.shortUrl(url)
                            ToolTip.visible: hovered && title.length > 18
                            ToolTip.delay: 600
                            background: Rectangle {
                                radius: 8
                                color: tabChip.on ? pane.c.card : tabChip.hovered ? pane.c.hover : "transparent"
                                border.width: tabChip.on ? 1 : 0; border.color: pane.c.line
                            }
                            MouseArea {                      // the middle button closes it, as anywhere
                                anchors.fill: parent
                                acceptedButtons: Qt.MiddleButton
                                enabled: pane.canDrive
                                onClicked: browser.closeTab(pane.owner, tabChip.tabIndex)
                            }
                            contentItem: RowLayout {
                                spacing: 6
                                Item {
                                    Layout.leftMargin: 8
                                    implicitWidth: 14; implicitHeight: 14
                                    Image {
                                        id: favicon
                                        anchors.fill: parent
                                        source: tabChip.favicon
                                        sourceSize: Qt.size(28, 28)
                                        visible: !tabChip.loading && status === Image.Ready
                                    }
                                    Icon { anchors.centerIn: parent; name: "globe"; size: 13; color: pane.c.muted
                                           visible: !tabChip.loading && favicon.status !== Image.Ready }
                                    Rectangle {               // loading: a turning arc
                                        anchors.fill: parent
                                        visible: tabChip.loading
                                        radius: width / 2; color: "transparent"
                                        border.width: 2; border.color: pane.c.line
                                        Rectangle { width: 4; height: 4; radius: 2; color: pane.c.action; x: parent.width / 2 - 2; y: -1 }
                                        RotationAnimation on rotation { running: tabChip.loading; loops: Animation.Infinite
                                                                        from: 0; to: 360; duration: 900 }
                                    }
                                }
                                Text {
                                    Layout.fillWidth: true
                                    elide: Text.ElideRight
                                    text: tabChip.title || pane.shortUrl(tabChip.url) || app.t.browser_new_tab
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 12
                                    font.weight: tabChip.on ? Font.Medium : Font.Normal
                                    color: tabChip.on ? pane.c.text : pane.c.body
                                }
                                OButton {
                                    objectName: "browserTabClose"
                                    Layout.rightMargin: 3
                                    visible: (tabChip.hovered || tabChip.on) && pane.canDrive
                                    kind: "quiet"; iconName: "close"; iconSize: 10; height_: 22
                                    tip: app.t.browser_close_tab
                                    onClicked: browser.closeTab(pane.owner, tabChip.tabIndex)
                                }
                            }
                        }
                    }
                    OButton {
                        objectName: "browserNewTab"
                        kind: "quiet"; iconName: "plus"; iconSize: 14; height_: 30
                        enabled: pane.canDrive
                        tip: app.t.browser_new_tab + "  (Ctrl+T)"
                        onClicked: browser.act(pane.owner, "newtab")
                    }
                }
            }
            // who drives, and what the agent is doing (« Orla clique ») — here, never a band over the page: the page
            // would change size at each action of the agent
            Rectangle {
                objectName: "browserControl"
                visible: pane.agentDrives || pane.personDrives || !!pane.st.activity
                Layout.preferredHeight: 30
                Layout.preferredWidth: controlRow.implicitWidth + 16
                radius: 15
                color: pane.personDrives ? pane.c.okTint : pane.c.tint
                RowLayout {
                    id: controlRow
                    anchors.centerIn: parent
                    spacing: 6
                    Rectangle { width: 7; height: 7; radius: 4; color: pane.personDrives ? pane.c.okInk : pane.c.action }
                    Text {
                        Layout.maximumWidth: Math.max(80, pane.width - 330)
                        elide: Text.ElideRight
                        text: pane.st.activity ? pane.st.activity
                              : pane.personDrives ? app.t.browser_control_you
                              : app.t.browser_control_agent.replace("%1", pane.st.who || "Ornis")
                        font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.Medium
                        color: pane.personDrives ? pane.c.okInk : pane.c.tintText
                    }
                    OButton {
                        visible: pane.agentDrives || pane.personDrives
                        objectName: pane.personDrives ? "browserGive" : "browserTakeBar"
                        kind: "secondary"; height_: 24
                        text: pane.personDrives ? app.t.browser_control_give.replace("%1", pane.st.who || "Ornis")
                                                : app.t.browser_control_take_short
                        onClicked: pane.personDrives ? browser.releaseControl(pane.owner) : browser.takeControl(pane.owner)
                    }
                }
            }
        }

        // ---- back, forward, reload, the address, the screen, Annoter ------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            Layout.margins: 8
            spacing: 4
            OButton { kind: "quiet"; iconName: "chevronLeft"; iconSize: 15; height_: 32; enabled: !!pane.st.canBack && pane.canDrive
                      tip: app.t.browser_back + "  (Alt+←)"; onClicked: browser.act(pane.owner, "back") }
            OButton { kind: "quiet"; iconName: "chevronRight"; iconSize: 15; height_: 32; enabled: !!pane.st.canForward && pane.canDrive
                      tip: app.t.browser_forward + "  (Alt+→)"; onClicked: browser.act(pane.owner, "forward") }
            OButton { kind: "quiet"; iconName: pane.st.loading ? "close" : "refresh"; iconSize: 15; height_: 32
                      enabled: pane.canDrive
                      tip: pane.st.loading ? app.t.browser_stop : app.t.browser_reload + "  (Ctrl+R)"
                      onClicked: browser.act(pane.owner, pane.st.loading ? "stop" : "reload") }
            OTextField {
                id: address
                objectName: "browserAddress"
                Layout.fillWidth: true
                implicitHeight: 34
                font.pixelSize: 13
                enabled: pane.canDrive
                leftPadding: 34
                placeholderText: app.t.browser_url_ph
                readonly property string url: pane.st.url && pane.st.url !== "about:blank" ? pane.st.url : ""
                readonly property bool secure: /^https:/.test(url)
                readonly property bool local: /^(https?:\/\/)?(localhost|127\.|192\.168\.|10\.|\[::1\])/.test(url) || /^file:/.test(url)
                readonly property string shown: pane.shortUrl(url)
                text: shown
                // while it has the focus: the whole address, all selected; then the short one again (a binding again)
                onActiveFocusChanged: if (activeFocus) { text = url; Qt.callLater(selectAll) }
                                      else text = Qt.binding(() => address.shown)
                onAccepted: { browser.go(pane.owner, text); focus = false }
                Keys.onEscapePressed: event => { text = url; focus = false }
                Icon {
                    x: 12; anchors.verticalCenter: parent.verticalCenter
                    name: address.url === "" || address.activeFocus ? "search" : address.secure || address.local ? "lock" : "warning"
                    size: 14
                    color: address.url !== "" && !address.secure && !address.local && !address.activeFocus ? pane.c.saffronText : pane.c.muted
                    HoverHandler { id: lockHover }
                    ToolTip.visible: lockHover.hovered && address.url !== "" && !address.activeFocus
                    ToolTip.text: address.secure ? app.t.browser_secure : address.local ? app.t.browser_local : app.t.browser_insecure
                }
            }
            OButton {
                visible: (pane.st.zoom || 100) !== 100
                kind: "quiet"; height_: 32; text: (pane.st.zoom || 100) + " %"
                tip: app.t.browser_zoom_reset + "  (Ctrl+0)"; onClicked: browser.zoom(pane.owner, 0)
            }
            OButton {
                id: sizeBtn
                objectName: "browserSize"
                enabled: pane.canDrive
                kind: pane.st.devW > 0 ? "secondary" : "quiet"; iconName: "devices"; iconSize: 15; height_: 32
                text: pane.st.devW > 0 ? pane.st.devW + "×" + pane.st.devH : ""
                tip: app.t.browser_devices
                onClicked: { sizeMenu.parent = sizeBtn; sizeMenu.x = sizeBtn.width - sizeMenu.width; sizeMenu.y = sizeBtn.height + 4
                             sizeMenu.open() }
            }
            OButton { objectName: "browserAnnotate"; kind: pane.st.annotating ? "secondary" : "quiet"; iconName: "edit"; iconSize: 15; height_: 32
                      tip: app.t.browser_annotate + "  (Ctrl+Shift+D)"; onClicked: browser.annotate(pane.owner, !pane.st.annotating) }
            OButton { kind: "quiet"; iconName: "openExternal"; iconSize: 14; height_: 32; tip: app.t.browser_external
                      enabled: !!pane.st.url && pane.st.url !== "about:blank"; onClicked: app.openLink(pane.st.url) }
        }
        OMenu {
            id: sizeMenu
            popupType: Popup.Window      // above the page: the page is a window of its own, an item would open under it
            Repeater {
                model: pane.presets
                OMenuItem {
                    required property var modelData
                    objectName: "preset-" + modelData.key
                    text: (app.t["browser_preset_" + modelData.key.replace("-", "_")] || modelData.key)
                          + (modelData.w ? "  " + modelData.w + "×" + modelData.h : "")
                    onTriggered: browser.preset(pane.owner, modelData.key)
                }
            }
            OMenuItem {
                objectName: "browserRotate"
                enabled: pane.st.devW > 0
                text: app.t.browser_rotate
                onTriggered: browser.resizeTo(pane.owner, pane.st.devH, pane.st.devW, !!pane.st.mobile)
            }
            OMenuItem {
                objectName: "browserFreeSize"
                text: app.t.browser_size_free
                onTriggered: { freeW.text = pane.st.devW > 0 ? pane.st.devW : 1280; freeH.text = pane.st.devH > 0 ? pane.st.devH : 800
                               freeMobile.checked = !!pane.st.mobile
                               freeSize.parent = sizeBtn; freeSize.x = sizeBtn.width - freeSize.width; freeSize.y = sizeBtn.height + 4
                               freeSize.open(); freeW.forceActiveFocus(); freeW.selectAll() }
            }
        }
        Popup {                                       // Taille libre: width × height, a phone or not
            id: freeSize
            popupType: Popup.Window
            width: 268
            padding: 14
            background: Rectangle { radius: 12; color: pane.c.overlay; border.width: 1; border.color: pane.c.overlayLine }
            function apply() {
                browser.resizeTo(pane.owner, parseInt(freeW.text) || 0, parseInt(freeH.text) || 0, freeMobile.checked)
                close()
            }
            contentItem: ColumnLayout {
                spacing: 10
                Text { text: app.t.browser_size_free.replace("…", ""); font.family: "Schibsted Grotesk"; font.pixelSize: 13
                       font.weight: Font.DemiBold; color: pane.c.text }
                RowLayout {
                    spacing: 6
                    OTextField { id: freeW; Layout.preferredWidth: 90; implicitHeight: 34; font.pixelSize: 13
                                 validator: IntValidator { bottom: 200; top: 4000 }
                                 onAccepted: freeSize.apply() }
                    Text { text: "×"; color: pane.c.muted; font.pixelSize: 14 }
                    OTextField { id: freeH; Layout.preferredWidth: 90; implicitHeight: 34; font.pixelSize: 13
                                 validator: IntValidator { bottom: 200; top: 4000 }
                                 onAccepted: freeSize.apply() }
                    Text { text: "px"; color: pane.c.muted; font.pixelSize: 12 }
                }
                RowLayout {
                    spacing: 8
                    OSwitch { id: freeMobile }
                    Text { Layout.fillWidth: true; text: app.t.browser_size_mobile; wrapMode: Text.Wrap
                           font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: pane.c.body }
                }
                OButton { Layout.alignment: Qt.AlignRight; kind: "primary"; height_: 32; text: app.t.browser_size_apply
                          onClicked: freeSize.apply() }
            }
        }

        Rectangle {                                   // a video this browser cannot play (H.264): your own browser can
            objectName: "browserMedia"
            Layout.fillWidth: true
            Layout.leftMargin: 8; Layout.rightMargin: 8; Layout.bottomMargin: 6
            visible: !!pane.st.media
            implicitHeight: mediaRow.implicitHeight + 12; radius: 8
            color: pane.c.saffronTint
            RowLayout {
                id: mediaRow
                anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 6
                spacing: 8
                Icon { name: "play"; size: 14; color: pane.c.saffronInk }
                Text { Layout.fillWidth: true; text: app.t.browser_media; wrapMode: Text.Wrap
                       font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: pane.c.saffronInk }
                OButton { kind: "quiet"; height_: 26; iconName: "openExternal"; iconSize: 13; text: app.t.browser_media_open
                          onClicked: app.openLink(pane.st.url) }
            }
        }

        Item {                                        // the loading, a thin line over the page
            Layout.fillWidth: true
            implicitHeight: 2
            Rectangle {
                height: 2
                width: parent.width * Math.max(0.06, (pane.st.progress || 0) / 100)
                color: pane.c.action
                visible: !!pane.st.loading
                Behavior on width { NumberAnimation { duration: 200 } }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: pane.c.field
            WindowContainer {                         // the browser itself: its own window, live
                id: frame
                objectName: "browserFrame"
                anchors.fill: parent
                visible: !pane.covered
                window: null
            }
            Column {
                anchors.centerIn: parent
                width: parent.width - 48
                spacing: 10
                visible: !browser
                Icon { anchors.horizontalCenter: parent.horizontalCenter; name: "globe"; size: 28; color: pane.c.muted }
                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                       text: app.t.browser_unavailable; font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: pane.c.muted }
            }
        }
    }
    FileDialog {
        id: filePicker
        currentFolder: Std.StandardPaths.writableLocation(Std.StandardPaths.PicturesLocation)
        title: app.t.browser_files
        onAccepted: pane.filesChosen(fileMode === FileDialog.OpenFiles ? Array.from(selectedFiles) : [selectedFile])
        onRejected: pane.filesChosen([])
    }
    FolderDialog {
        id: folderPicker
        currentFolder: Std.StandardPaths.writableLocation(Std.StandardPaths.HomeLocation)
        title: app.t.browser_folder
        onAccepted: pane.filesChosen([selectedFolder])
        onRejected: pane.filesChosen([])
    }
    // the same keys when the focus is in the panel's bar (the page's window has its own: BrowserWindow.qml)
    Shortcut { sequence: "Ctrl+Shift+D"; enabled: pane.shownNow && !!browser; onActivated: browser.annotate(pane.owner, !pane.st.annotating) }
    Shortcut { sequences: ["Ctrl+L", "Alt+D"]; enabled: pane.shownNow && pane.canDrive; onActivated: { address.forceActiveFocus(); address.selectAll() } }
    Shortcut { sequence: "Ctrl+T"; enabled: pane.shownNow && pane.canDrive; onActivated: browser.act(pane.owner, "newtab") }
}
