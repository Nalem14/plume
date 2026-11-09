// The Code panel on the right of a session, as Cursor's: Fichiers (the folder's tree, a file to read, dragged into the
// message as @path), Modifications (this turn, not committed, the commits, each file's diff), Plan (the plan of the
// Plan mode, run in one click) and Terminal (the user's own shell in the folder). Its tab is chosen by the icons of the
// session's head (CodeView); everything it reads comes from bench.py (code.bench) and terminal.py (code.terminals).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Rectangle {
    id: bench
    property string tab: "files"            // routines | files | changes | plan | terminal | browser
    property bool maximized: false
    signal closeRequested()
    signal maximizeRequested()
    signal mentionRequested(string path)
    signal commitRequested()
    readonly property var c: theme.c
    readonly property var b: code.bench
    readonly property bool narrow: width < 360
    readonly property bool compact: width < 600            // the tabs not chosen: their icon only
    // StackLayout order is fixed; the Routines tab button only appears for bots.
    readonly property var tabKeys: ["routines", "files", "changes", "plan", "terminal", "browser"]
    color: c.chrome
    clip: true

    // Routines only on a bot; Plan never on a bot (always the classic Agent): both fall back on Fichiers
    function allowed(name) { return code.bot === "" ? name !== "routines" : name !== "plan" }
    function show(name) {
        if (!allowed(name)) name = "files"
        tab = name
        if (name === "terminal") termPane.ensure()
    }
    onTabChanged: if (!allowed(tab)) show("files")
    Connections {
        target: code
        function onChanged() { if (!bench.allowed(bench.tab)) bench.show("files") }
    }
    // from the conversation: a file to read, or what changed in it (a turn's card, a tool's card)
    function openFile(path) { show("files"); filesPane.open(path) }
    function openDiff(scope, ref, path) { show("changes"); changesPane.scope = scope === "turn" ? 0 : scope === "work" ? 1 : 2; changesPane.openDiff(scope, ref, path) }

    Rectangle {
        anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
        width: 1; color: bench.c.hairline; z: 2
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: 1
        spacing: 0

        // ---- the tabs ---------------------------------------------------------------------------------------------
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 56
            color: "transparent"
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: bench.c.hairline }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 10; anchors.rightMargin: 8
                spacing: 2
                Repeater {
                    model: {
                        const rows = []
                        if (code.bot !== "")
                            rows.push({ key: "routines", label: app.t.bots_routines, icon: "clock",
                                        badge: routinesPane.count, dot: false })
                        rows.push(
                            { key: "files", label: app.t.bench_files, icon: "folder", badge: 0, dot: false },
                            { key: "changes", label: app.t.bench_changes, icon: "history",
                              badge: bench.b.status.length || (bench.b.turn.files || []).length, dot: false },
                            { key: "plan", label: app.t.bench_plan, icon: "list", badge: 0, dot: code.planReady },
                            { key: "terminal", label: app.t.bench_terminal, icon: "terminal", badge: 0, dot: false }
                        )
                        if (browser)
                            rows.push({ key: "browser", label: app.t.bench_browser, icon: "globe", badge: 0, dot: false })
                        return code.bot !== "" ? rows.filter(r => r.key !== "plan") : rows   // bots: no Plan mode
                    }
                    AbstractButton {
                        id: tabBtn
                        required property var modelData
                        readonly property bool on: bench.tab === modelData.key
                        Layout.preferredHeight: 32
                        implicitWidth: tabRow.implicitWidth + 20
                        hoverEnabled: true
                        onClicked: bench.show(modelData.key)
                        Accessible.role: Accessible.PageTab
                        Accessible.name: modelData.label
                        Accessible.selected: on
                        ToolTip.visible: (bench.narrow || bench.compact && !on) && hovered
                        ToolTip.text: modelData.label
                        ToolTip.delay: 400
                        background: Rectangle {
                            radius: 9
                            color: tabBtn.on ? bench.c.card : tabBtn.hovered ? bench.c.hover : "transparent"
                            border.width: tabBtn.on ? 1 : 0; border.color: bench.c.line
                            Behavior on color { ColorAnimation { duration: 120 } }
                        }
                        contentItem: Item {
                            Row {
                                id: tabRow
                                anchors.centerIn: parent
                                spacing: 6
                                Item {
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: 16; height: 16
                                    Icon { anchors.centerIn: parent; name: tabBtn.modelData.icon; size: 15
                                           color: tabBtn.on ? bench.c.famCommunicate : bench.c.muted }
                                    Rectangle {
                                        visible: tabBtn.modelData.dot
                                        x: 11; y: -2; width: 7; height: 7; radius: 3.5
                                        color: bench.c.saffron
                                        border.width: 1.5; border.color: bench.c.chrome
                                    }
                                }
                                Text {
                                    visible: !bench.narrow && (tabBtn.on || !bench.compact)
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: tabBtn.modelData.label
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                                    font.weight: tabBtn.on ? Font.DemiBold : Font.Medium
                                    color: tabBtn.on ? bench.c.text : bench.c.muted
                                }
                                Rectangle {
                                    visible: tabBtn.modelData.badge > 0
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: Math.max(18, badgeText.implicitWidth + 10); height: 18; radius: 9
                                    color: tabBtn.on ? bench.c.tint : bench.c.hover
                                    Text {
                                        id: badgeText
                                        anchors.centerIn: parent
                                        text: tabBtn.modelData.badge > 99 ? "99+" : tabBtn.modelData.badge
                                        font.family: "Schibsted Grotesk"; font.pixelSize: 11; font.weight: Font.DemiBold
                                        font.features: { "tnum": 1 }
                                        color: tabBtn.on ? bench.c.tintText : bench.c.muted
                                    }
                                }
                            }
                        }
                    }
                }
                Item { Layout.fillWidth: true }
                OButton { kind: "quiet"; iconName: bench.maximized ? "minimize" : "maximize"; iconSize: 15; height_: 30
                          tip: bench.maximized ? app.t.bench_restore : app.t.bench_maximize; onClicked: bench.maximizeRequested() }
                OButton { kind: "quiet"; iconName: "close"; iconSize: 15; height_: 30; tip: app.t.bench_close; onClicked: bench.closeRequested() }
            }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: Math.max(0, bench.tabKeys.indexOf(bench.tab))

            // ---- Routines (bots only) -------------------------------------------------------------------------------
            RoutinesPanel {
                id: routinesPane
                botId: code.bot
            }

            // ---- Fichiers -------------------------------------------------------------------------------------------
            Item {
                id: filesPane
                property var expanded: []
                property string query: ""
                property string openPath: ""
                property var preview: ({})
                property bool showDiff: false
                readonly property var rows: { bench.b.fileCount; bench.b.status; return bench.b.rows(filesPane.expanded, filesPane.query) }
                function toggle(path) {
                    const at = expanded.indexOf(path)
                    expanded = at >= 0 ? expanded.filter(p => p !== path) : expanded.concat([path])
                }
                function open(path) {
                    openPath = path
                    preview = bench.b.read(path)
                    const changed = bench.b.status.some(s => s.path === path)
                    showDiff = false
                    if (changed) bench.b.loadDiff("work", "", path)
                }
                Connections {
                    target: code.bench
                    function onChanged() { if (filesPane.openPath) filesPane.preview = bench.b.read(filesPane.openPath) }
                }

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0
                    visible: filesPane.openPath === ""
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.margins: 10
                        Layout.bottomMargin: 6
                        spacing: 4
                        OTextField {
                            Layout.fillWidth: true
                            iconName: "search"
                            placeholderText: app.t.bench_filter
                            onTextChanged: filesPane.query = text
                            Keys.onEscapePressed: text = ""
                        }
                        OButton { kind: "quiet"; iconName: "refresh"; iconSize: 15; height_: 32; tip: app.t.bench_refresh; onClicked: bench.b.refresh() }
                        OButton { kind: "quiet"; iconName: "openExternal"; iconSize: 15; height_: 32; tip: app.t.bench_reveal; onClicked: bench.b.reveal("") }
                    }
                    RowLayout {                      // the folder, how many files, its branch
                        Layout.fillWidth: true
                        Layout.leftMargin: 14; Layout.rightMargin: 14; Layout.bottomMargin: 4
                        spacing: 6
                        Text {
                            Layout.fillWidth: true
                            text: code.folderName + "  ·  " + app.plural("bench_files_count", bench.b.fileCount)
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold
                            color: bench.c.muted
                        }
                        Rectangle {
                            visible: bench.b.branch !== ""
                            implicitWidth: branchRow.implicitWidth + 14; implicitHeight: 20; radius: 10
                            color: bench.c.tint
                            Row {
                                id: branchRow
                                anchors.centerIn: parent
                                spacing: 4
                                Icon { anchors.verticalCenter: parent.verticalCenter; name: "branch"; size: 11; color: bench.c.tintText }
                                Text { anchors.verticalCenter: parent.verticalCenter; text: bench.b.branch
                                       font.family: "JetBrains Mono"; font.pixelSize: 11; color: bench.c.tintText }
                            }
                        }
                    }
                    ListView {
                        id: tree
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: filesPane.rows
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                        bottomMargin: 8
                        delegate: AbstractButton {
                            id: node
                            required property var modelData
                            width: ListView.view.width
                            implicitHeight: 28
                            hoverEnabled: true
                            onClicked: modelData.dir ? filesPane.toggle(modelData.path) : filesPane.open(modelData.path)
                            Accessible.name: modelData.path
                            ToolTip.visible: hovered && filesPane.query !== ""
                            ToolTip.text: modelData.path
                            ToolTip.delay: 600
                            // a file dragged onto the message box becomes @path there
                            Drag.dragType: Drag.Automatic
                            Drag.supportedActions: Qt.CopyAction
                            Drag.mimeData: ({ "application/x-ornis-path": modelData.path, "text/plain": "@" + modelData.path })
                            Drag.active: dragger.active
                            DragHandler { id: dragger; target: null }
                            TapHandler {
                                acceptedButtons: Qt.RightButton
                                onTapped: event => { fileMenu.path = node.modelData.path; fileMenu.isDir = node.modelData.dir
                                                     fileMenu.x = Math.min(event.position.x, node.width - fileMenu.implicitWidth)
                                                     fileMenu.y = node.mapToItem(filesPane, 0, event.position.y).y; fileMenu.open() }
                            }
                            background: Rectangle {
                                x: 6; width: parent.width - 12; radius: 6
                                color: node.hovered ? bench.c.hover : "transparent"
                            }
                            contentItem: RowLayout {
                                spacing: 6
                                Item { implicitWidth: 6 + node.modelData.depth * 14 }
                                Icon {
                                    visible: node.modelData.dir
                                    name: "chevronDown"; size: 11; color: bench.c.faint
                                    rotation: node.modelData.open ? 0 : -90
                                }
                                Item { visible: !node.modelData.dir; implicitWidth: 11 }
                                FileGlyph { dir: node.modelData.dir; open: node.modelData.open; ext: node.modelData.ext }
                                Text {
                                    Layout.fillWidth: true
                                    text: filesPane.query && !node.modelData.dir ? node.modelData.path : node.modelData.name
                                    elide: filesPane.query ? Text.ElideLeft : Text.ElideRight
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                                    color: node.modelData.status === "D" ? bench.c.muted : bench.c.text
                                    font.strikeout: node.modelData.status === "D"
                                }
                                Rectangle {
                                    visible: node.modelData.dirty
                                    implicitWidth: 6; implicitHeight: 6; radius: 3
                                    color: bench.c.saffron
                                }
                                StatusLetter { status: node.modelData.status }
                                Item { implicitWidth: 8 }
                            }
                        }
                        Column {
                            anchors.centerIn: parent
                            visible: tree.count === 0
                            spacing: 8
                            BusyIndicator { anchors.horizontalCenter: parent.horizontalCenter; visible: bench.b.loading; running: visible }
                            Text {
                                text: bench.b.loading ? app.t.bench_loading : filesPane.query ? app.t.no_results : app.t.bench_empty_folder
                                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                                color: bench.c.muted
                            }
                        }
                    }
                }

                // a file opened: its lines (numbered), or what changed in it
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0
                    visible: filesPane.openPath !== ""
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.margins: 8
                        spacing: 4
                        OButton { kind: "quiet"; iconName: "chevronLeft"; iconSize: 15; height_: 30; tip: app.t.bench_back
                                  onClicked: { filesPane.openPath = ""; bench.b.closeDiff() } }
                        FileGlyph { ext: filesPane.openPath.indexOf(".") >= 0 ? filesPane.openPath.split(".").pop().toLowerCase() : "" }
                        Text {
                            Layout.fillWidth: true
                            text: filesPane.openPath
                            elide: Text.ElideLeft
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                            color: bench.c.text
                        }
                        OButton { kind: "quiet"; text: "@"; height_: 30; tip: app.t.bench_mention; onClicked: bench.mentionRequested(filesPane.openPath) }
                        OButton { kind: "quiet"; iconName: "openExternal"; iconSize: 15; height_: 30; tip: app.t.bench_open; onClicked: bench.b.openFile(filesPane.openPath) }
                    }
                    Segmented {                      // Fichier | Modifications, when it changed
                        visible: bench.b.status.some(s => s.path === filesPane.openPath)
                        Layout.leftMargin: 12; Layout.bottomMargin: 8
                        items: [app.t.bench_show_file, app.t.bench_show_diff]
                        current: filesPane.showDiff ? 1 : 0
                        onPicked: i => filesPane.showDiff = i === 1
                    }
                    Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: bench.c.hairline }
                    DiffList {
                        visible: filesPane.showDiff
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        diff: bench.b.diff
                    }
                    Item {
                        visible: !filesPane.showDiff
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        ListView {
                            id: lines
                            anchors.fill: parent
                            visible: !!filesPane.preview.lines
                            clip: true
                            model: filesPane.preview.lines || []
                            boundsBehavior: Flickable.StopAtBounds
                            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                            topMargin: 6; bottomMargin: 10
                            readonly property real gutter: Math.max(28, String(count).length * 8 + 14)
                            delegate: Row {
                                required property string modelData
                                required property int index
                                width: ListView.view.width
                                Text {
                                    width: lines.gutter; rightPadding: 10
                                    horizontalAlignment: Text.AlignRight
                                    text: index + 1
                                    font.family: "JetBrains Mono"; font.pixelSize: 11
                                    color: bench.c.faint
                                    topPadding: 1
                                }
                                Text {
                                    width: parent.width - lines.gutter - 8
                                    text: modelData === "" ? " " : modelData
                                    textFormat: Text.PlainText
                                    wrapMode: Text.WrapAnywhere
                                    font.family: "JetBrains Mono"; font.pixelSize: 12
                                    color: bench.c.text
                                }
                            }
                            footer: Text {
                                visible: !!filesPane.preview.truncated
                                width: lines.width; height: visible ? 30 : 0
                                leftPadding: lines.gutter; verticalAlignment: Text.AlignVCenter
                                text: app.t.bench_truncated
                                font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.italic: true
                                color: bench.c.muted
                            }
                        }
                        Image {
                            anchors.fill: parent
                            anchors.margins: 16
                            visible: !!filesPane.preview.image
                            source: filesPane.preview.image || ""
                            fillMode: Image.PreserveAspectFit
                            asynchronous: true
                        }
                        Text {
                            anchors.centerIn: parent
                            visible: !!filesPane.preview.binary || !!filesPane.preview.missing
                            text: app.t.bench_binary
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13
                            color: bench.c.muted
                        }
                    }
                }

                OMenu {
                    id: fileMenu
                    property string path: ""
                    property bool isDir: false
                    OMenuItem { text: app.t.bench_mention; iconName: "hash"; onTriggered: bench.mentionRequested(fileMenu.path) }
                    OMenuItem { visible: !fileMenu.isDir; text: app.t.bench_open; iconName: "openExternal"; onTriggered: bench.b.openFile(fileMenu.path) }
                    OMenuItem { text: app.t.bench_reveal; iconName: "folder"; onTriggered: bench.b.reveal(fileMenu.path) }
                    OMenuItem { text: app.t.bench_copy_path; iconName: "copy"; onTriggered: app.copy(fileMenu.path) }
                }
            }

            // ---- Modifications ----------------------------------------------------------------------------------------
            Item {
                id: changesPane
                property int scope: bench.b.turn.files ? 0 : bench.b.isGit ? 1 : 0     // Ce tour | Non validé | Commits
                property string detail: ""          // a file shown (its diff)
                function openDiff(kind, ref, path) { detail = path; bench.b.loadDiff(kind, ref, path) }

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0
                    visible: changesPane.detail === ""
                    Segmented {
                        Layout.margins: 10; Layout.bottomMargin: 8
                        Layout.fillWidth: true
                        fill: true
                        items: [app.t.bench_scope_turn,
                                app.t.bench_scope_work + (bench.b.status.length ? "  " + bench.b.status.length : ""),
                                app.t.bench_scope_commits]
                        current: changesPane.scope
                        onPicked: i => changesPane.scope = i
                    }

                    // Ce tour: what Ornis changed in its last turn, to look at or take back
                    ColumnLayout {
                        visible: changesPane.scope === 0
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: 0
                        RowLayout {
                            visible: !!bench.b.turn.files
                            Layout.fillWidth: true
                            Layout.leftMargin: 14; Layout.rightMargin: 10; Layout.bottomMargin: 6
                            spacing: 8
                            Text {
                                Layout.fillWidth: true
                                text: app.plural("code_files_changed", (bench.b.turn.files || []).length)
                                font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                                color: bench.c.text
                            }
                            PlusMinus { added: bench.b.turn.added || 0; removed: bench.b.turn.removed || 0 }
                            OButton { iconName: "restore"; text: app.t.code_undo; height_: 28; enabled: !code.busy
                                      tip: app.t.code_undo_tip; onClicked: code.rewind(bench.b.turn.rev) }
                        }
                        FileList {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            files: bench.b.turn.files || []
                            reverted: bench.b.turn.reverted || []
                            empty: app.t.bench_turn_none
                            undoable: true
                            onChosen: path => changesPane.openDiff("turn", bench.b.turn.rev, path)
                            onUndo: path => code.rewindFile(bench.b.turn.rev, path)
                        }
                    }

                    // Non validé: the working tree against the last commit, then « Valider… »
                    ColumnLayout {
                        visible: changesPane.scope === 1
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: 0
                        FileList {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            files: bench.b.isGit ? bench.b.status : []
                            empty: bench.b.isGit ? app.t.bench_work_none : app.t.bench_no_git
                            onChosen: path => changesPane.openDiff("work", "", path)
                        }
                        Rectangle {
                            visible: bench.b.isGit && bench.b.status.length > 0
                            Layout.fillWidth: true
                            Layout.preferredHeight: 56
                            color: "transparent"
                            Rectangle { width: parent.width; height: 1; color: bench.c.hairline }
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 14; anchors.rightMargin: 10
                                spacing: 8
                                Icon { name: "branch"; size: 13; color: bench.c.muted }
                                Text {
                                    Layout.fillWidth: true
                                    text: bench.b.branch
                                    elide: Text.ElideRight
                                    font.family: "JetBrains Mono"; font.pixelSize: 12
                                    color: bench.c.muted
                                }
                                PlusMinus {
                                    added: bench.b.status.reduce((n, s) => n + (s.added || 0), 0)
                                    removed: bench.b.status.reduce((n, s) => n + (s.removed || 0), 0)
                                }
                                OButton { kind: "primary"; iconName: "check"; text: app.t.code_commit + "…"; height_: 32
                                          enabled: !code.busy; onClicked: bench.commitRequested() }
                            }
                        }
                    }

                    // Commits: the history, a commit unfolded into its files
                    ListView {
                        id: commitList
                        visible: changesPane.scope === 2
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: bench.b.isGit ? bench.b.commits : []
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                        bottomMargin: 10
                        delegate: Column {
                            id: commitRow
                            required property var modelData
                            required property int index
                            readonly property bool open: bench.b.commit.sha === modelData.sha
                            width: ListView.view.width
                            AbstractButton {
                                id: commitHead
                                width: parent.width
                                implicitHeight: 54
                                hoverEnabled: true
                                onClicked: bench.b.loadCommit(commitRow.modelData.sha)
                                Accessible.name: commitRow.modelData.subject
                                background: Rectangle {
                                    x: 6; width: parent.width - 12; radius: 8
                                    color: commitRow.open ? bench.c.card : commitHead.hovered ? bench.c.hover : "transparent"
                                    border.width: commitRow.open ? 1 : 0; border.color: bench.c.line
                                }
                                contentItem: RowLayout {
                                    spacing: 10
                                    Item {                   // the history's line, a dot per commit
                                        Layout.leftMargin: 10
                                        implicitWidth: 12; Layout.fillHeight: true
                                        Rectangle { anchors.horizontalCenter: parent.horizontalCenter; width: 2
                                                    y: commitRow.index === 0 ? parent.height / 2 : 0
                                                    height: commitRow.index === commitList.count - 1 ? parent.height / 2 : parent.height
                                                    color: bench.c.line }
                                        Rectangle { anchors.centerIn: parent; width: 10; height: 10; radius: 5
                                                    color: commitRow.index === 0 ? bench.c.famCommunicate : bench.c.chrome
                                                    border.width: 2; border.color: commitRow.index === 0 ? bench.c.famCommunicate : bench.c.muted }
                                    }
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 2
                                        Text {
                                            Layout.fillWidth: true
                                            text: commitRow.modelData.subject
                                            elide: Text.ElideRight
                                            font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.Medium
                                            color: bench.c.text
                                        }
                                        RowLayout {
                                            spacing: 6
                                            Text { text: commitRow.modelData.short; font.family: "JetBrains Mono"; font.pixelSize: 11; color: bench.c.accent }
                                            Text {
                                                Layout.fillWidth: true
                                                text: commitRow.modelData.author + " · " + commitRow.modelData.ago
                                                elide: Text.ElideRight
                                                font.family: "Schibsted Grotesk"; font.pixelSize: 11
                                                color: bench.c.muted
                                            }
                                        }
                                    }
                                    Rectangle {          // HEAD -> main, a tag
                                        visible: commitRow.modelData.refs !== ""
                                        Layout.maximumWidth: 110
                                        implicitWidth: refText.implicitWidth + 12; implicitHeight: 18; radius: 9
                                        color: bench.c.tint
                                        Text { id: refText; anchors.centerIn: parent; width: Math.min(implicitWidth, 98)
                                               text: commitRow.modelData.refs.replace("HEAD -> ", ""); elide: Text.ElideRight
                                               font.family: "JetBrains Mono"; font.pixelSize: 10; color: bench.c.tintText }
                                    }
                                    Item { implicitWidth: 8 }
                                }
                            }
                            Repeater {
                                model: commitRow.open ? (bench.b.commit.files || []) : []
                                FileRow {
                                    width: commitRow.width
                                    indent: 34
                                    entry: modelData
                                    onChosen: changesPane.openDiff("commit", commitRow.modelData.sha, modelData.path)
                                }
                            }
                        }
                        Text {
                            anchors.centerIn: parent
                            width: parent.width - 40
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.Wrap
                            visible: commitList.count === 0
                            text: bench.b.isGit ? app.t.bench_commits_none : app.t.bench_no_git
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13
                            color: bench.c.muted
                        }
                    }
                }

                ColumnLayout {                       // a file's diff
                    anchors.fill: parent
                    spacing: 0
                    visible: changesPane.detail !== ""
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.margins: 8
                        spacing: 6
                        OButton { kind: "quiet"; iconName: "chevronLeft"; iconSize: 15; height_: 30; tip: app.t.bench_back
                                  onClicked: { changesPane.detail = ""; bench.b.closeDiff() } }
                        FileGlyph { ext: changesPane.detail.indexOf(".") >= 0 ? changesPane.detail.split(".").pop().toLowerCase() : "" }
                        Text {
                            Layout.fillWidth: true
                            text: changesPane.detail
                            elide: Text.ElideLeft
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                            color: bench.c.text
                        }
                        PlusMinus { added: bench.b.diff.added || 0; removed: bench.b.diff.removed || 0 }
                        OButton { kind: "quiet"; iconName: "openExternal"; iconSize: 15; height_: 30; tip: app.t.bench_open; onClicked: bench.b.openFile(changesPane.detail) }
                    }
                    Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: bench.c.hairline }
                    DiffList { Layout.fillWidth: true; Layout.fillHeight: true; diff: bench.b.diff }
                }
            }

            // ---- Plan -------------------------------------------------------------------------------------------------
            Flickable {
                id: planPane
                clip: true
                contentHeight: planCol.implicitHeight + 32
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                readonly property var doc: bench.b.planDoc
                readonly property bool built: (app.prefs.plans_built || []).indexOf(doc.path || "") >= 0
                readonly property string rel: doc.path ? doc.path.slice(code.folder.length + 1) : ""
                function run() {
                    if (!doc.path) return
                    app.setPref("plans_built", (app.prefs.plans_built || []).filter(p => p !== doc.path).concat([doc.path]).slice(-100))
                    if (code.planReady) code.runPlan()
                    else { code.setPlanMode(false); code.send(app.t.bench_run_plan_file.replace("%1", planPane.rel)) }
                }
                ColumnLayout {
                    id: planCol
                    x: 16; y: 16
                    width: planPane.width - 32
                    spacing: 14

                    // the steps Ornis follows now (Vibe's plan, live)
                    Rectangle {
                        visible: code.plan.length > 0
                        Layout.fillWidth: true
                        implicitHeight: liveCol.implicitHeight + 24
                        radius: 12
                        color: bench.c.card
                        border.width: 1; border.color: bench.c.line
                        ColumnLayout {
                            id: liveCol
                            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                            spacing: 8
                            RowLayout {
                                spacing: 8
                                Text { text: app.t.bench_plan_live; font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold; color: bench.c.muted }
                                Text {
                                    text: code.plan.filter(e => e.status === "completed").length + " / " + code.plan.length
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: bench.c.faint
                                    font.features: { "tnum": 1 }
                                }
                            }
                            Rectangle {              // how far along
                                Layout.fillWidth: true
                                implicitHeight: 4; radius: 2
                                color: bench.c.hover
                                Rectangle {
                                    width: parent.width * (code.plan.length ? code.plan.filter(e => e.status === "completed").length / code.plan.length : 0)
                                    height: parent.height; radius: 2
                                    color: bench.c.famCommunicate
                                    Behavior on width { NumberAnimation { duration: 300; easing.type: Easing.OutCubic } }
                                }
                            }
                            Repeater {
                                model: code.plan
                                RowLayout {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    spacing: 9
                                    StepMark { mark: modelData.status === "completed" ? "done" : modelData.status === "in_progress" ? "now" : "todo" }
                                    Text {
                                        Layout.fillWidth: true
                                        text: modelData.content || ""
                                        wrapMode: Text.Wrap
                                        font.family: "Schibsted Grotesk"; font.pixelSize: 13
                                        font.strikeout: modelData.status === "completed"
                                        color: modelData.status === "completed" ? bench.c.muted : bench.c.text
                                    }
                                }
                            }
                        }
                    }

                    // the plan written in Plan mode: read it, run it
                    Rectangle {
                        visible: !!planPane.doc.path
                        Layout.fillWidth: true
                        implicitHeight: docCol.implicitHeight + 28
                        radius: 14
                        color: bench.c.card
                        border.width: 1; border.color: code.planReady ? bench.c.saffron : bench.c.line
                        ColumnLayout {
                            id: docCol
                            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 14 }
                            spacing: 10
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                Rectangle {
                                    implicitWidth: 30; implicitHeight: 30; radius: 9
                                    color: code.planReady ? bench.c.saffronTint : bench.c.tint
                                    Icon { anchors.centerIn: parent; name: "list"; size: 15; color: code.planReady ? bench.c.saffronInk : bench.c.tintText }
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 1
                                    Text {
                                        Layout.fillWidth: true
                                        text: planPane.doc.title || ""
                                        wrapMode: Text.Wrap
                                        font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.weight: Font.DemiBold
                                        color: bench.c.text
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: ".ornis/plans/" + (planPane.doc.name || "")
                                        elide: Text.ElideMiddle
                                        font.family: "JetBrains Mono"; font.pixelSize: 11
                                        color: bench.c.faint
                                    }
                                }
                                Rectangle {          // where it stands
                                    implicitWidth: stateText.implicitWidth + 16; implicitHeight: 22; radius: 11
                                    color: code.planReady ? bench.c.saffronTint : planPane.built ? bench.c.okTint : bench.c.hover
                                    Text {
                                        id: stateText
                                        anchors.centerIn: parent
                                        text: code.planReady ? app.t.bench_plan_ready : planPane.built ? "✓ " + app.t.bench_plan_done : ""
                                        font.family: "Schibsted Grotesk"; font.pixelSize: 11; font.weight: Font.DemiBold
                                        color: code.planReady ? bench.c.saffronInk : bench.c.okInk
                                    }
                                    visible: stateText.text !== ""
                                }
                            }
                            Text {
                                visible: (planPane.doc.steps || []).length > 0
                                text: app.t.bench_plan_steps
                                font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold
                                color: bench.c.muted
                            }
                            Repeater {
                                model: planPane.doc.steps || []
                                RowLayout {
                                    required property var modelData
                                    required property int index
                                    Layout.fillWidth: true
                                    spacing: 10
                                    Rectangle {
                                        Layout.alignment: Qt.AlignTop
                                        implicitWidth: 22; implicitHeight: 22; radius: 11
                                        color: modelData.done ? bench.c.okTint : bench.c.hover
                                        Text { anchors.centerIn: parent; text: modelData.done ? "✓" : index + 1
                                               font.family: "Schibsted Grotesk"; font.pixelSize: 11; font.weight: Font.DemiBold
                                               color: modelData.done ? bench.c.okInk : bench.c.muted }
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        topPadding: 2
                                        text: modelData.text
                                        wrapMode: Text.Wrap
                                        font.family: "Schibsted Grotesk"; font.pixelSize: 13
                                        color: bench.c.text
                                    }
                                }
                            }
                            AbstractButton {         // the whole text, folded
                                id: wholeBtn
                                property bool open: (planPane.doc.steps || []).length === 0
                                Layout.fillWidth: true
                                implicitHeight: 26
                                onClicked: open = !open
                                background: null
                                contentItem: RowLayout {
                                    spacing: 6
                                    Icon { name: "chevronDown"; size: 11; color: bench.c.muted; rotation: wholeBtn.open ? 0 : -90 }
                                    Text { text: app.t.bench_plan_text; font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.Medium; color: bench.c.muted }
                                    Item { Layout.fillWidth: true }
                                }
                            }
                            Text {
                                visible: wholeBtn.open
                                Layout.fillWidth: true
                                text: planPane.doc.text || ""
                                textFormat: Text.MarkdownText
                                wrapMode: Text.Wrap
                                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                                color: bench.c.text
                                onLinkActivated: link => app.openLink(link)
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                Layout.topMargin: 4
                                spacing: 8
                                OButton {
                                    kind: "primary"; iconName: "play"; height_: 36
                                    text: planPane.built && !code.planReady ? app.t.bench_plan_rerun : app.t.plan_run
                                    enabled: !code.busy && code.state !== "error"
                                    onClicked: planPane.run()
                                }
                                OButton { kind: "quiet"; iconName: "edit"; text: app.t.bench_plan_edit; height_: 36; onClicked: bench.b.openPlan() }
                            }
                        }
                    }

                    // nothing yet: what the Plan mode does, and the way to it
                    ColumnLayout {
                        visible: !planPane.doc.path && code.plan.length === 0
                        Layout.fillWidth: true
                        Layout.topMargin: 30
                        spacing: 12
                        Rectangle {
                            Layout.alignment: Qt.AlignHCenter
                            implicitWidth: 56; implicitHeight: 56; radius: 16
                            color: bench.c.saffronTint
                            Icon { anchors.centerIn: parent; name: "list"; size: 24; color: bench.c.saffronInk }
                        }
                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            text: app.t.bench_plan_none_title
                            font.family: "Schibsted Grotesk"; font.pixelSize: 16; font.weight: Font.DemiBold
                            color: bench.c.text
                        }
                        Text {
                            Layout.fillWidth: true
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.Wrap
                            text: app.t.bench_plan_none
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13
                            lineHeight: 1.15
                            color: bench.c.muted
                        }
                        OButton {
                            Layout.alignment: Qt.AlignHCenter
                            Layout.topMargin: 4
                            visible: !code.planMode
                            kind: "secondary"; iconName: "list"; text: app.t.bench_plan_start
                            onClicked: code.setPlanMode(true)
                        }
                    }
                }
            }

            // ---- Terminal -------------------------------------------------------------------------------------------
            Item {
                id: termPane
                property string current: ""
                readonly property var terms: code.terminals.list
                readonly property bool usable: code.terminals.available && termView.status !== Loader.Error
                function ensure() {
                    if (!usable) return
                    if (terms.length === 0) add()
                    else if (!terms.some(t => t.id === current)) choose(terms[terms.length - 1].id)
                }
                function add() {
                    const id = code.terminals.start(code.folder, 100, 30)
                    if (id) choose(id)
                }
                function choose(id) {
                    current = id
                    if (termView.item) termView.item.showTerm(id)
                }
                function close(id) {
                    if (termView.item) termView.item.dropTerm(id)
                    code.terminals.close(id)
                    if (current === id) { current = ""; if (terms.length) choose(terms[terms.length - 1].id) }
                }
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0
                    visible: termPane.usable
                    RowLayout {                      // the terminals, as tabs
                        Layout.fillWidth: true
                        Layout.margins: 8
                        Layout.bottomMargin: 6
                        spacing: 4
                        Repeater {
                            model: termPane.terms
                            AbstractButton {
                                id: tTab
                                required property var modelData
                                readonly property bool on: termPane.current === modelData.id
                                implicitHeight: 28
                                implicitWidth: tRow.implicitWidth + 16
                                hoverEnabled: true
                                onClicked: termPane.choose(modelData.id)
                                background: Rectangle { radius: 8; color: tTab.on ? bench.c.card : tTab.hovered ? bench.c.hover : "transparent"
                                                        border.width: tTab.on ? 1 : 0; border.color: bench.c.line }
                                contentItem: Item {
                                    Row {
                                        id: tRow
                                        anchors.centerIn: parent
                                        spacing: 6
                                        Rectangle { anchors.verticalCenter: parent.verticalCenter; width: 6; height: 6; radius: 3
                                                    color: tTab.modelData.alive ? bench.c.ok : bench.c.faint }
                                        Text {
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: app.t.bench_term_title.replace("%1", tTab.modelData.number)
                                            font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: tTab.on ? Font.DemiBold : Font.Medium
                                            color: tTab.on ? bench.c.text : bench.c.muted
                                        }
                                        AbstractButton {
                                            id: tClose
                                            anchors.verticalCenter: parent.verticalCenter
                                            width: 16; height: 16
                                            opacity: tTab.hovered || tTab.on ? 1 : 0
                                            onClicked: termPane.close(tTab.modelData.id)
                                            Accessible.name: app.t.bench_term_close
                                            background: Rectangle { radius: 4; color: tClose.hovered ? bench.c.hover : "transparent" }
                                            contentItem: Icon { name: "close"; size: 10; color: bench.c.muted }
                                        }
                                    }
                                }
                            }
                        }
                        OButton { kind: "quiet"; iconName: "plus"; iconSize: 14; height_: 28; tip: app.t.bench_term_new; onClicked: termPane.add() }
                        Item { Layout.fillWidth: true }
                        OButton { kind: "quiet"; iconName: "openExternal"; iconSize: 14; height_: 28; tip: app.t.code_terminal; onClicked: code.openTerminal() }
                    }
                    Loader {
                        id: termView
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        active: bench.tab === "terminal" || item !== null
                        source: "TerminalView.qml"
                        onLoaded: if (termPane.current) item.showTerm(termPane.current)
                    }
                }
                Column {                             // no built-in terminal here (no pseudo-terminal, no Chromium)
                    anchors.centerIn: parent
                    width: parent.width - 48
                    visible: !termPane.usable
                    spacing: 12
                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: 56; height: 56; radius: 16
                        color: bench.c.tint
                        Icon { anchors.centerIn: parent; name: "terminal"; size: 24; color: bench.c.tintText }
                    }
                    Text {
                        width: parent.width
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.Wrap
                        text: app.t.bench_term_none
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13
                        color: bench.c.muted
                    }
                    OButton {
                        anchors.horizontalCenter: parent.horizontalCenter
                        kind: "secondary"; iconName: "terminal"; text: app.t.code_terminal
                        onClicked: code.openTerminal()
                    }
                }
            }

            // ---- Navigateur: the browser of the bot (or the person's), live -------------------------------------------
            BrowserPane {
                shownNow: bench.visible && bench.tab === "browser"
            }
        }
    }

    // ---- the small parts ------------------------------------------------------------------------------------------
    component Segmented: Rectangle {
        id: seg
        property var items: []
        property int current: 0
        property bool fill: false                // shares the whole width (else each as wide as its word)
        signal picked(int index)
        implicitHeight: 32
        implicitWidth: fill ? 200 : segRow.implicitWidth + 6
        radius: 9
        color: bench.c.field
        border.width: 1; border.color: bench.c.line
        Row {
            id: segRow
            x: 3; y: 3
            height: parent.height - 6
            Repeater {
                model: seg.items
                AbstractButton {
                    id: segBtn
                    required property string modelData
                    required property int index
                    readonly property bool on: seg.current === index
                    width: seg.fill ? (seg.width - 6) / seg.items.length : segText.implicitWidth + 22
                    height: parent.height
                    hoverEnabled: true
                    onClicked: seg.picked(index)
                    background: Rectangle { radius: 7; color: segBtn.on ? bench.c.card : segBtn.hovered ? bench.c.hover : "transparent"
                                            border.width: segBtn.on ? 1 : 0; border.color: bench.c.line }
                    contentItem: Text {
                        id: segText
                        text: segBtn.modelData
                        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                        font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: segBtn.on ? Font.DemiBold : Font.Medium
                        color: segBtn.on ? bench.c.text : bench.c.muted
                    }
                }
            }
        }
    }

    component StatusLetter: Text {
        property string status
        visible: status !== ""
        text: status
        font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Bold
        color: status === "A" ? bench.c.okInk : status === "D" ? bench.c.danger : status === "R" ? bench.c.accent : bench.c.saffronInk
    }

    component PlusMinus: Row {
        property int added
        property int removed
        spacing: 6
        Text { visible: parent.added > 0; text: "+" + parent.added; font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.DemiBold; color: bench.c.okInk }
        Text { visible: parent.removed > 0; text: "−" + parent.removed; font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.DemiBold; color: bench.c.danger }
    }

    // a file's mark: a folder, or a tile coloured by its kind (code, text, data, picture)
    component FileGlyph: Item {
        property bool dir: false
        property bool open: false
        property string ext: ""
        readonly property string kind: dir ? "dir"
            : ["png", "jpg", "jpeg", "gif", "webp", "svg", "ico", "bmp"].indexOf(ext) >= 0 ? "image"
            : ["md", "txt", "rst", "pdf", "doc", "docx", "odt"].indexOf(ext) >= 0 ? "text"
            : ["json", "yml", "yaml", "toml", "ini", "env", "xml", "csv", "lock", "conf", "cfg"].indexOf(ext) >= 0 ? "data"
            : ext === "" ? "plain" : "code"
        implicitWidth: 16; implicitHeight: 16
        Icon {
            anchors.centerIn: parent
            name: parent.kind === "dir" ? "folder" : parent.kind === "image" ? "image" : parent.kind === "text" ? "note" : parent.kind === "data" ? "table" : parent.kind === "code" ? "code" : "note"
            size: 14
            color: parent.kind === "dir" ? (parent.open ? bench.c.famCommunicate : bench.c.muted)
                 : parent.kind === "image" ? bench.c.famMedia : parent.kind === "text" ? bench.c.famDocs
                 : parent.kind === "data" ? bench.c.famOrganize : parent.kind === "code" ? bench.c.famCommunicate : bench.c.faint
        }
    }

    component StepMark: Item {
        id: sm
        property string mark: "todo"             // todo | now | done
        implicitWidth: 18; implicitHeight: 18
        Layout.alignment: Qt.AlignTop
        Rectangle {
            anchors.centerIn: parent
            width: 16; height: 16; radius: 8
            color: sm.mark === "done" ? bench.c.okInk : "transparent"
            border.width: sm.mark === "done" ? 0 : 2
            border.color: sm.mark === "now" ? bench.c.famCommunicate : bench.c.line
            Text { anchors.centerIn: parent; visible: sm.mark === "done"; text: "✓"; font.pixelSize: 10; font.bold: true; color: bench.c.card }
            Rectangle {
                visible: sm.mark === "now"
                anchors.centerIn: parent; width: 6; height: 6; radius: 3
                color: bench.c.famCommunicate
                SequentialAnimation on opacity {
                    running: parent.visible && Qt.styleHints.reduceMotion !== true
                    loops: Animation.Infinite
                    NumberAnimation { from: 1; to: 0.25; duration: 600 }
                    NumberAnimation { from: 0.25; to: 1; duration: 600 }
                }
            }
        }
    }

    component FileRow: AbstractButton {
        id: fr
        property var entry: ({})
        property real indent: 8
        property bool undoable: false
        property bool back: false
        signal chosen()
        signal undo()
        implicitHeight: 30
        hoverEnabled: true
        onClicked: chosen()
        Accessible.name: entry.path || ""
        background: Rectangle { x: 6; width: parent.width - 12; radius: 6; color: fr.hovered ? bench.c.hover : "transparent" }
        contentItem: RowLayout {
            spacing: 7
            Item { implicitWidth: fr.indent }
            StatusLetter { status: fr.entry.status || ""; Layout.preferredWidth: 12 }
            FileGlyph { ext: (fr.entry.path || "").indexOf(".") >= 0 ? fr.entry.path.split(".").pop().toLowerCase() : "" }
            Text {
                Layout.fillWidth: true
                text: {
                    const p = fr.entry.path || ""
                    const at = p.lastIndexOf("/")
                    return at < 0 ? p : p.slice(at + 1) + "  <font color=\"" + bench.c.faint + "\">" + p.slice(0, at) + "</font>"
                }
                textFormat: Text.StyledText
                elide: Text.ElideRight
                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                color: fr.back ? bench.c.muted : bench.c.text
                font.strikeout: fr.back
            }
            PlusMinus { visible: !fr.back; added: fr.entry.added || 0; removed: fr.entry.removed || 0 }
            Text { visible: fr.back; text: app.t.code_file_undone; font.family: "Schibsted Grotesk"; font.pixelSize: 11; color: bench.c.muted }
            OButton {
                visible: fr.undoable && !fr.back && fr.hovered
                enabled: !code.busy
                kind: "quiet"; iconName: "restore"; iconSize: 13; height_: 22
                tip: app.t.code_file_undo
                onClicked: fr.undo()
            }
            Item { implicitWidth: 6 }
        }
    }

    component FileList: ListView {
        id: fl
        property var files: []
        property var reverted: []
        property string empty: ""
        property bool undoable: false
        signal chosen(string path)
        signal undo(string path)
        clip: true
        model: files
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
        delegate: FileRow {
            required property var modelData
            width: ListView.view.width
            entry: modelData
            undoable: fl.undoable
            back: fl.reverted.indexOf(modelData.path) >= 0
            onChosen: fl.chosen(modelData.path)
            onUndo: fl.undo(modelData.path)
        }
        Column {
            anchors.centerIn: parent
            width: parent.width - 48
            visible: fl.count === 0
            spacing: 10
            Icon { anchors.horizontalCenter: parent.horizontalCenter; name: "check"; size: 22; color: bench.c.faint }
            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                text: fl.empty
                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                color: bench.c.muted
            }
        }
    }

    // a diff, line by line: the numbers before and after, a tint for what was added or removed
    component DiffList: Item {
        id: dl
        property var diff: ({})
        ListView {
            id: dlist
            anchors.fill: parent
            clip: true
            model: dl.diff.lines || []
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            topMargin: 4; bottomMargin: 10
            delegate: Rectangle {
                id: dline
                required property var modelData
                width: ListView.view.width
                height: modelData.t === "@" ? 26 : dtext.implicitHeight + 2
                color: modelData.t === "+" ? bench.c.okTint : modelData.t === "-" ? bench.c.dangerTint : modelData.t === "@" ? bench.c.hover : "transparent"
                Rectangle {                          // the edge of a changed line
                    visible: dline.modelData.t === "+" || dline.modelData.t === "-"
                    width: 3; height: parent.height
                    color: dline.modelData.t === "+" ? bench.c.ok : bench.c.danger
                }
                Row {
                    anchors.fill: parent
                    visible: dline.modelData.t !== "@"
                    Text { width: 36; rightPadding: 6; topPadding: 1; horizontalAlignment: Text.AlignRight
                           text: dline.modelData.o || ""; font.family: "JetBrains Mono"; font.pixelSize: 10; color: bench.c.faint }
                    Text { width: 36; rightPadding: 6; topPadding: 1; horizontalAlignment: Text.AlignRight
                           text: dline.modelData.n || ""; font.family: "JetBrains Mono"; font.pixelSize: 10; color: bench.c.faint }
                    Text { width: 14; topPadding: 0; text: dline.modelData.t === " " ? "" : dline.modelData.t
                           font.family: "JetBrains Mono"; font.pixelSize: 12; font.weight: Font.Bold
                           color: dline.modelData.t === "+" ? bench.c.okInk : bench.c.danger }
                    Text {
                        id: dtext
                        width: parent.width - 86
                        text: dline.modelData.s === "" ? " " : dline.modelData.s
                        textFormat: Text.PlainText
                        wrapMode: Text.WrapAnywhere
                        font.family: "JetBrains Mono"; font.pixelSize: 12
                        color: bench.c.text
                    }
                }
                Text {
                    visible: dline.modelData.t === "@"
                    anchors.verticalCenter: parent.verticalCenter
                    x: 12; width: parent.width - 24
                    text: dline.modelData.s === "binary" ? app.t.bench_binary : dline.modelData.s.replace(/^@@ .*? @@ ?/, "⋯ ")
                    elide: Text.ElideRight
                    font.family: "JetBrains Mono"; font.pixelSize: 11
                    color: bench.c.muted
                }
            }
        }
        BusyIndicator { anchors.centerIn: parent; visible: !!dl.diff.loading; running: visible }
        Text {
            anchors.centerIn: parent
            visible: !dl.diff.loading && dlist.count === 0 && !!dl.diff.key
            text: app.t.bench_work_none
            font.family: "Schibsted Grotesk"; font.pixelSize: 13
            color: bench.c.muted
        }
    }
}
