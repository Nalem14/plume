// The file panel on the right: a file or a folder of this computer that a message names (a link, a path, a picture),
// opened here instead of in another app. A folder: its entries, in a list or a grid of vignettes when it holds
// pictures; a folder goes into it, a file shows. A picture: shown in large (« Agrandir » over the window); Markdown
// drawn (or its text); a text file: its numbered lines; anything else: a card to open it with its app. Every file
// can be saved elsewhere (the system's picker), its folder opened here, shown in the file manager, its path copied.
// Used by the Chat (Conversation.qml), the groups of bots (GroupView.qml) and Code/Bots outside their folder
// (CodeView.qml); everything it reads comes from app.localInfo / app.localFolder (ornis_core/app.py).
import QtCore as Std               // StandardPaths only: its Settings would hide ours
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "components"

Rectangle {
    id: pane
    objectName: "filePane"
    property bool open: false
    property string path: ""
    property var info: ({})
    property var entries: []
    property var history: []                 // the paths shown before, for ← (a folder entered, a file opened)
    property bool mentionable: false         // Code: « Mentionner » writes @path in the message
    property string mdTab: "render"
    property bool grid: false
    property bool gridChosen: false          // the person chose list or grid: kept while browsing
    property bool closable: true
    signal closeRequested()
    signal mentionRequested(string path)
    readonly property var c: theme.c
    readonly property bool isDir: !!info.dir
    readonly property int imageCount: entries.filter(e => e.kind === "image").length
    readonly property var images: entries.filter(e => e.kind === "image")
    color: c.chrome
    visible: open
    clip: true

    function show(target, keepHistory) {
        if (!target) return
        if (open && path !== "" && path !== target && !keepHistory) history = history.concat([path])
        path = target
        reload()
        open = true
    }
    function reload() {
        info = app.localInfo(path)
        entries = info.dir ? app.localFolder(path) : []
        mdTab = "render"
        if (info.dir && !gridChosen) grid = entries.length > 0 && imageCount >= Math.max(3, entries.length / 2)
        list.positionViewAtBeginning(); gridView.positionViewAtBeginning()
    }
    function back() {
        if (!history.length) return
        const last = history[history.length - 1]
        history = history.slice(0, -1)
        show(last, true)
    }
    function up() { if (info.parent) show(info.parent) }
    function close() { open = false; history = []; closeRequested() }
    function saveAs() { saver.selectedFile = saver.currentFolder + "/" + encodeURIComponent(info.name || "fichier"); saver.open() }
    // the picture before / after this one in its folder (← → in large)
    function siblingImage(step) {
        const list = app.localFolder(info.parent || "").filter(e => e.kind === "image")
        const at = list.findIndex(e => e.path === path)
        if (list.length < 2 || at < 0) return
        show(list[(at + step + list.length) % list.length].path, true)
    }

    Rectangle { anchors { left: parent.left; top: parent.top; bottom: parent.bottom } width: 1; color: pane.c.line; z: 2 }

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: 1
        spacing: 0

        // ---- the head: back, what it is, its actions ---------------------------------------------------------------
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 56
            color: "transparent"
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: pane.c.hairline }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8; anchors.rightMargin: 8
                spacing: 4
                OButton { visible: pane.history.length > 0; kind: "quiet"; iconName: "chevronLeft"; iconSize: 15; height_: 30
                          tip: app.t.lp_back; onClicked: pane.back() }
                Item { visible: pane.history.length === 0; implicitWidth: 6 }
                Rectangle {
                    implicitWidth: 30; implicitHeight: 30; radius: 8
                    color: pane.isDir ? pane.c.tint : Qt.alpha(glyphColor(pane.info.kind), 0.12)
                    Icon { anchors.centerIn: parent; name: glyphIcon(pane.info.kind); size: 16
                           color: pane.isDir ? pane.c.tintText : glyphColor(pane.info.kind) }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 6
                    spacing: 0
                    Text {
                        Layout.fillWidth: true
                        text: pane.info.name || ""
                        elide: Text.ElideMiddle
                        textFormat: Text.PlainText
                        font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
                        color: pane.c.text
                    }
                    RowLayout {                 // how much, then where (the start of a long path given up first)
                        Layout.fillWidth: true
                        spacing: 0
                        Text {
                            text: (pane.isDir ? app.plural("lp_items", pane.entries.length) : pane.info.sizeText || "") + "  ·  "
                            textFormat: Text.PlainText
                            font.family: "Schibsted Grotesk"; font.pixelSize: 11
                            color: pane.c.muted
                        }
                        Text {
                            Layout.fillWidth: true
                            text: pane.isDir ? pane.path : pane.info.parent || ""
                            elide: Text.ElideLeft
                            textFormat: Text.PlainText
                            font.family: "Schibsted Grotesk"; font.pixelSize: 11
                            color: pane.c.muted
                        }
                    }
                }
                OButton { visible: !pane.isDir && pane.info.kind !== "image" && pane.width >= 360; kind: "quiet"; iconName: "download"; iconSize: 15; height_: 30
                          objectName: "fileSave"; tip: app.t.lp_save; onClicked: pane.saveAs() }
                OButton { visible: !pane.isDir && pane.info.kind !== "image" && pane.width >= 360; kind: "quiet"; iconName: "folder"; iconSize: 15; height_: 30
                          tip: app.t.lp_folder; onClicked: pane.up() }
                OButton { visible: pane.isDir && !!pane.info.parent; kind: "quiet"; iconName: "chevronDown"; rotation: 180; iconSize: 15; height_: 30
                          tip: app.t.lp_up; onClicked: pane.up() }
                OButton { id: moreBtn; kind: "quiet"; iconName: "more"; iconSize: 15; height_: 30; tip: app.t.more || "…"
                          onClicked: { moreMenu.x = moreBtn.mapToItem(pane, 0, 0).x + moreBtn.width - moreMenu.implicitWidth
                                       moreMenu.y = moreBtn.mapToItem(pane, 0, 0).y + moreBtn.height + 4; moreMenu.open() } }
                OButton { visible: pane.closable; kind: "quiet"; iconName: "close"; iconSize: 15; height_: 30; tip: app.t.lp_close; onClicked: pane.close() }
            }
        }

        // ---- a folder ------------------------------------------------------------------------------------------------
        RowLayout {
            visible: pane.isDir && pane.entries.length > 0
            Layout.fillWidth: true
            Layout.leftMargin: 14; Layout.rightMargin: 10; Layout.topMargin: 8; Layout.bottomMargin: 4
            spacing: 6
            Item { Layout.fillWidth: true }
            OButton { kind: pane.grid ? "quiet" : "secondary"; iconName: "listBullet"; iconSize: 14; height_: 26; tip: app.t.lp_list
                      onClicked: { pane.grid = false; pane.gridChosen = true } }
            OButton { kind: pane.grid ? "secondary" : "quiet"; iconName: "grid"; iconSize: 14; height_: 26; tip: app.t.lp_grid
                      onClicked: { pane.grid = true; pane.gridChosen = true } }
        }
        Item {
            visible: pane.isDir
            Layout.fillWidth: true
            Layout.fillHeight: true
            ListView {
                id: list
                anchors.fill: parent
                visible: !pane.grid
                clip: true
                model: pane.isDir ? pane.entries : []
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                topMargin: 4; bottomMargin: 10
                delegate: AbstractButton {
                    id: row
                    required property var modelData
                    width: ListView.view.width
                    implicitHeight: modelData.kind === "image" ? 44 : 34
                    hoverEnabled: true
                    onClicked: pane.show(modelData.path)
                    Accessible.name: modelData.name
                    TapHandler { acceptedButtons: Qt.RightButton; onTapped: event => entryMenu.openFor(row.modelData, row, event.position.x, event.position.y) }
                    background: Rectangle { x: 6; width: parent.width - 12; radius: 7; color: row.hovered ? pane.c.hover : "transparent" }
                    contentItem: RowLayout {
                        spacing: 10
                        Item { implicitWidth: 6 }
                        Item {
                            implicitWidth: row.modelData.kind === "image" ? 34 : 18; implicitHeight: implicitWidth
                            Image {
                                visible: row.modelData.kind === "image"
                                anchors.fill: parent
                                source: row.modelData.url || ""
                                sourceSize: Qt.size(96, 96)
                                fillMode: Image.PreserveAspectCrop
                                asynchronous: true
                                layer.enabled: false
                                Rectangle { anchors.fill: parent; color: "transparent"; radius: 6; border.width: 1; border.color: pane.c.line }
                            }
                            Icon { visible: row.modelData.kind !== "image"; anchors.centerIn: parent; name: glyphIcon(row.modelData.kind); size: 15
                                   color: row.modelData.dir ? pane.c.famCommunicate : glyphColor(row.modelData.kind) }
                        }
                        Text {
                            Layout.fillWidth: true
                            text: row.modelData.name
                            elide: Text.ElideMiddle
                            textFormat: Text.PlainText
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13
                            color: pane.c.text
                        }
                        Text {
                            text: row.modelData.sizeText
                            font.family: "JetBrains Mono"; font.pixelSize: 11
                            color: pane.c.faint
                        }
                        Icon { visible: row.modelData.dir; name: "chevronRight"; size: 12; color: pane.c.faint }
                        Item { implicitWidth: 8 }
                    }
                }
            }
            GridView {
                id: gridView
                anchors.fill: parent
                anchors.leftMargin: 10; anchors.rightMargin: 4
                visible: pane.grid
                clip: true
                model: pane.isDir ? pane.entries : []
                readonly property int columns: Math.max(2, Math.floor(width / 128))
                cellWidth: Math.floor(width / columns)
                cellHeight: cellWidth + 26
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                topMargin: 4; bottomMargin: 10
                delegate: AbstractButton {
                    id: tile
                    required property var modelData
                    width: GridView.view.cellWidth; height: GridView.view.cellHeight
                    hoverEnabled: true
                    onClicked: pane.show(modelData.path)
                    Accessible.name: modelData.name
                    TapHandler { acceptedButtons: Qt.RightButton; onTapped: event => entryMenu.openFor(tile.modelData, tile, event.position.x, event.position.y) }
                    background: Rectangle { anchors.fill: parent; anchors.margins: 3; radius: 10; color: tile.hovered ? pane.c.hover : "transparent" }
                    contentItem: ColumnLayout {
                        spacing: 4
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: width
                            Layout.margins: 6
                            Layout.bottomMargin: 0
                            radius: 8
                            color: tile.modelData.kind === "image" ? pane.c.field : Qt.alpha(glyphColor(tile.modelData.kind), 0.10)
                            border.width: 1; border.color: pane.c.line
                            clip: true
                            Image {
                                visible: tile.modelData.kind === "image"
                                anchors.fill: parent; anchors.margins: 1
                                source: tile.modelData.url || ""
                                sourceSize: Qt.size(256, 256)
                                fillMode: Image.PreserveAspectCrop
                                asynchronous: true
                            }
                            Icon { visible: tile.modelData.kind !== "image"; anchors.centerIn: parent; name: glyphIcon(tile.modelData.kind); size: 28
                                   color: tile.modelData.dir ? pane.c.famCommunicate : glyphColor(tile.modelData.kind) }
                        }
                        Text {
                            Layout.fillWidth: true
                            Layout.leftMargin: 6; Layout.rightMargin: 6
                            text: tile.modelData.name
                            horizontalAlignment: Text.AlignHCenter
                            elide: Text.ElideMiddle
                            textFormat: Text.PlainText
                            font.family: "Schibsted Grotesk"; font.pixelSize: 12
                            color: pane.c.text
                        }
                    }
                }
            }
            EmptyState {
                anchors.fill: parent
                visible: pane.entries.length === 0
                color: "transparent"
                iconName: "folder"
                title: app.t.lp_empty
            }
        }

        // ---- a picture -------------------------------------------------------------------------------------------------
        Item {
            visible: pane.info.kind === "image"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Rectangle {                         // a soft stage behind it (a transparent PNG still reads)
                anchors.fill: parent; anchors.margins: 14
                radius: 12
                color: pane.c.field
                border.width: 1; border.color: pane.c.line
            }
            Image {
                id: picture
                anchors.fill: parent; anchors.margins: 22
                source: pane.info.kind === "image" ? pane.info.url : ""
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                smooth: true; mipmap: true
                sourceSize: Qt.size(Math.max(512, width * 2), Math.max(512, height * 2))
                MouseArea {
                    anchors.centerIn: parent; width: parent.paintedWidth; height: parent.paintedHeight
                    cursorShape: Qt.PointingHandCursor
                    onClicked: large.open()
                }
            }
            BusyIndicator { anchors.centerIn: parent; running: picture.status === Image.Loading }
            Row {                                // its actions, under the picture
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom; anchors.bottomMargin: 26
                spacing: 6
                OButton { kind: "secondary"; iconName: "download"; iconSize: 14; height_: 30; text: pane.width >= 380 ? app.t.lp_save : ""
                          tip: app.t.lp_save; onClicked: pane.saveAs() }
                OButton { kind: "secondary"; iconName: "folder"; iconSize: 14; height_: 30; text: pane.width >= 460 ? app.t.lp_folder : ""
                          tip: app.t.lp_folder; onClicked: pane.up() }
                OButton { kind: "secondary"; iconName: "maximize"; iconSize: 14; height_: 30; text: pane.width >= 380 ? app.t.lp_enlarge : ""
                          tip: app.t.lp_enlarge; onClicked: large.open() }
            }
        }

        // ---- Markdown: drawn, or its text ------------------------------------------------------------------------------
        RowLayout {
            visible: pane.info.kind === "markdown"
            Layout.leftMargin: 14; Layout.topMargin: 10; Layout.bottomMargin: 4
            spacing: 2
            Repeater {
                model: [{ key: "render", label: app.t.lp_render }, { key: "source", label: app.t.lp_source }]
                OButton {
                    required property var modelData
                    kind: pane.mdTab === modelData.key ? "secondary" : "quiet"; height_: 26
                    text: modelData.label
                    onClicked: pane.mdTab = modelData.key
                }
            }
        }
        Flickable {
            id: mdFlick
            visible: pane.info.kind === "markdown" && pane.mdTab === "render"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentHeight: mdText.implicitHeight + 32
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            TextEdit {
                id: mdText
                x: 18; y: 12
                width: mdFlick.width - 36
                readOnly: true
                selectByMouse: true
                textFormat: TextEdit.RichText
                wrapMode: Text.Wrap
                text: mdFlick.visible ? app.markdown(pane.info.text || (pane.info.lines || []).join("\n"), pane.c.accent, 14, pane.c.line, pane.c.field) : ""
                font.family: "Schibsted Grotesk"; font.pixelSize: 14
                color: pane.c.body
                selectionColor: pane.c.accentLine
                onLinkActivated: link => app.openLink(link)
            }
        }

        // ---- a text file: its lines ------------------------------------------------------------------------------------
        ListView {
            id: lines
            visible: pane.info.kind === "text" || (pane.info.kind === "markdown" && pane.mdTab === "source")
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: visible ? (pane.info.lines || []) : []
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            topMargin: 8; bottomMargin: 10
            readonly property real gutter: Math.max(30, String(count).length * 8 + 16)
            delegate: Row {
                required property string modelData
                required property int index
                width: ListView.view.width
                Text {
                    width: lines.gutter; rightPadding: 10
                    horizontalAlignment: Text.AlignRight
                    text: index + 1
                    font.family: "JetBrains Mono"; font.pixelSize: 11
                    color: pane.c.faint
                    topPadding: 1
                }
                Text {
                    width: parent.width - lines.gutter - 10
                    text: modelData === "" ? " " : modelData
                    textFormat: Text.PlainText
                    wrapMode: Text.WrapAnywhere
                    font.family: "JetBrains Mono"; font.pixelSize: 12
                    color: pane.c.text
                }
            }
            footer: Text {
                visible: !!pane.info.truncated
                width: lines.width; height: visible ? 30 : 0
                leftPadding: lines.gutter; verticalAlignment: Text.AlignVCenter
                text: app.t.lp_truncated
                font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.italic: true
                color: pane.c.muted
            }
        }

        // ---- a PDF: Chromium's viewer, when it is there ----------------------------------------------------------------
        Loader {
            id: pdfLoader
            objectName: "pdfLoader"
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: active && status === Loader.Ready
            active: pane.open && pane.info.kind === "pdf"
            source: "PdfWeb.qml"
            onLoaded: item.file = Qt.binding(() => pane.info.kind === "pdf" ? pane.info.url : "")
        }

        // ---- anything else: a card to open it, or save it -------------------------------------------------------------
        Item {
            visible: !pane.isDir && (pane.info.kind === "other" || pane.info.kind === "pdf" && !pdfLoader.visible) || !!pane.info.missing
            Layout.fillWidth: true
            Layout.fillHeight: true
            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(parent.width - 48, 340)
                spacing: 10
                Rectangle {
                    Layout.alignment: Qt.AlignHCenter
                    implicitWidth: 72; implicitHeight: 72; radius: 18
                    color: Qt.alpha(glyphColor(pane.info.kind), 0.12)
                    Icon { anchors.centerIn: parent; name: glyphIcon(pane.info.kind); size: 32; color: glyphColor(pane.info.kind) }
                }
                Text {
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    text: pane.info.missing ? app.t.path_missing.replace("%1", pane.info.name || "") : app.t.lp_no_preview
                    wrapMode: Text.Wrap
                    font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.weight: Font.DemiBold
                    color: pane.c.text
                }
                Text {
                    visible: !pane.info.missing
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    text: [pane.info.ext ? pane.info.ext.toUpperCase() : "", pane.info.sizeText, app.t.lp_modified.replace("%1", pane.info.modified || "")].filter(x => !!x).join("  ·  ")
                          + "\n" + app.t.lp_no_preview_sub
                    wrapMode: Text.Wrap
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                    color: pane.c.muted
                }
                ColumnLayout {
                    visible: !pane.info.missing
                    Layout.alignment: Qt.AlignHCenter
                    Layout.topMargin: 6
                    spacing: 8
                    OButton { Layout.fillWidth: true; kind: "primary"; iconName: "openExternal"; iconSize: 14; text: app.t.lp_open; onClicked: app.openLocalApp(pane.path) }
                    OButton { Layout.fillWidth: true; kind: "secondary"; iconName: "download"; iconSize: 14; text: app.t.lp_save; onClicked: pane.saveAs() }
                    OButton { Layout.fillWidth: true; kind: "quiet"; iconName: "folder"; iconSize: 14; text: app.t.lp_folder; onClicked: pane.up() }
                }
            }
        }
    }

    function glyphIcon(kind) {
        return kind === "dir" ? "folder" : kind === "image" ? "image" : kind === "pdf" ? "pdf" : kind === "markdown" ? "note"
             : kind === "text" ? "code" : "clip"
    }
    function glyphColor(kind) {
        return kind === "dir" ? pane.c.famCommunicate : kind === "image" ? pane.c.famMedia : kind === "pdf" ? pane.c.danger
             : kind === "markdown" ? pane.c.famDocs : kind === "text" ? pane.c.famCommunicate : pane.c.muted
    }

    // ---- menus ---------------------------------------------------------------------------------------------------------
    OMenu {
        id: moreMenu
        OMenuItem { visible: !pane.isDir; text: app.t.lp_save; iconName: "download"; onTriggered: pane.saveAs() }
        OMenuItem { visible: !pane.isDir; text: app.t.lp_folder; iconName: "folder"; onTriggered: pane.up() }
        OMenuItem { visible: !pane.isDir; text: app.t.lp_open; iconName: "openExternal"; onTriggered: app.openLocalApp(pane.path) }
        OMenuItem { text: app.t.lp_reveal; iconName: "export"; onTriggered: app.revealLocal(pane.path) }
        OMenuItem { visible: pane.mentionable; text: app.t.lp_mention; iconName: "hash"; onTriggered: pane.mentionRequested(pane.path) }
        OMenuItem { text: app.t.lp_copy_path; iconName: "copy"; onTriggered: app.copy(pane.path) }
    }
    OMenu {
        id: entryMenu
        property var entry: ({})
        function openFor(e, item, px, py) {
            entry = e
            const p = item.mapToItem(pane, px, py)
            x = Math.min(p.x, pane.width - implicitWidth - 8); y = Math.min(p.y, pane.height - implicitHeight - 8)
            open()
        }
        OMenuItem { text: entryMenu.entry.dir ? app.t.lp_folder : app.t.lp_title; iconName: entryMenu.entry.dir ? "folder" : "eye"
                    onTriggered: pane.show(entryMenu.entry.path) }
        OMenuItem { visible: !entryMenu.entry.dir; text: app.t.lp_save; iconName: "download"
                    onTriggered: { pane.show(entryMenu.entry.path); pane.saveAs() } }
        OMenuItem { visible: !entryMenu.entry.dir; text: app.t.lp_open; iconName: "openExternal"; onTriggered: app.openLocalApp(entryMenu.entry.path) }
        OMenuItem { text: app.t.lp_reveal; iconName: "export"; onTriggered: app.revealLocal(entryMenu.entry.path) }
        OMenuItem { visible: pane.mentionable; text: app.t.lp_mention; iconName: "hash"; onTriggered: pane.mentionRequested(entryMenu.entry.path) }
        OMenuItem { text: app.t.lp_copy_path; iconName: "copy"; onTriggered: app.copy(entryMenu.entry.path) }
    }

    // « Enregistrer sous… »: the system's picker, in Téléchargements with the file's name
    FileDialog {
        id: saver
        title: app.t.lp_save
        fileMode: FileDialog.SaveFile
        currentFolder: Std.StandardPaths.writableLocation(Std.StandardPaths.DownloadLocation)
        onAccepted: app.saveLocalCopy(pane.path, String(selectedFile))
    }

    // a picture in large, over the whole window (as Meet's): ← → the other pictures of its folder
    Popup {
        id: large
        objectName: "fileLarge"
        parent: Overlay.overlay
        x: 0; y: 0
        width: parent ? parent.width : 800
        height: parent ? parent.height : 600
        modal: true
        focus: true
        padding: 0
        closePolicy: Popup.CloseOnEscape
        Overlay.modal: Rectangle { color: Qt.alpha("#0A192F", 0.88) }
        background: Item {}
        contentItem: Item {
            focus: true
            Keys.onLeftPressed: pane.siblingImage(-1)
            Keys.onRightPressed: pane.siblingImage(1)
            MouseArea { anchors.fill: parent; onClicked: large.close() }
            Image {
                anchors.fill: parent
                anchors.margins: 64; anchors.topMargin: 72
                source: large.opened && pane.info.kind === "image" ? pane.info.url : ""
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                smooth: true; mipmap: true
                MouseArea { anchors.centerIn: parent; width: parent.paintedWidth; height: parent.paintedHeight }
            }
            RowLayout {
                anchors { top: parent.top; left: parent.left; right: parent.right; margins: 16 }
                spacing: 8
                Text {
                    Layout.fillWidth: true
                    text: pane.info.name || ""
                    elide: Text.ElideMiddle
                    textFormat: Text.PlainText
                    font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.weight: Font.DemiBold; color: "white"
                }
                OButton { kind: "secondary"; iconName: "download"; text: app.t.lp_save; onClicked: pane.saveAs() }
                OButton { kind: "secondary"; iconName: "folder"; text: app.t.lp_folder; onClicked: { large.close(); pane.up() } }
                OButton { kind: "secondary"; iconName: "openExternal"; text: app.t.lp_open; onClicked: { large.close(); app.openLocalApp(pane.path) } }
                OButton { kind: "secondary"; iconName: "close"; tip: app.t.lp_close; onClicked: large.close() }
            }
            OButton { anchors.left: parent.left; anchors.leftMargin: 12; anchors.verticalCenter: parent.verticalCenter
                      kind: "secondary"; iconName: "chevronLeft"; tip: app.t.lp_back; onClicked: pane.siblingImage(-1) }
            OButton { anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter
                      kind: "secondary"; iconName: "chevronRight"; onClicked: pane.siblingImage(1) }
        }
    }
}
