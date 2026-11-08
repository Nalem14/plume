// The notes of the folder shown: pinned first, then by date (Aujourd'hui, Hier, 7 jours précédents…), each
// with its title, its date and its first words, its folder when several are mixed, its first image.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Rectangle {
    id: pane
    readonly property var c: theme.c
    property string selected
    signal picked(string key)
    signal newNote()
    signal deleteRequested(var keys)
    signal moveRequested(var keys)
    signal tasksRequested(string key)
    signal shareRequested(string key)
    signal newFrom(string template)
    signal dailyRequested()
    signal folderMenuRequested(var item)
    property bool compact: false             // the window narrow: the folders open from a button above the list
    color: c.bg

    readonly property var rows: notes.items
    readonly property bool mixed: notes.folder === "all" || notes.folder === "shared" || notes.folder.indexOf("tag:") === 0 || notes.query !== ""
    readonly property bool trash: notes.folder === "trash" && notes.query === ""

    function focusList() { view.forceActiveFocus(); if (view.currentIndex < 0 && rows.length) { view.currentIndex = 0; picked(rows[0].key) } }

    // Several notes for one action: Ctrl+click, Shift+click (a range), Ctrl+A.
    property var chosen: []
    property int anchor: -1
    function isChosen(key) { return chosen.indexOf(key) >= 0 }
    function clickRow(index, mod) {
        const r = rows[index]
        if (!r) return
        if (mod === "") {
            chosen = []
            anchor = index
            view.currentIndex = index
            picked(r.key)
            return
        }
        let out
        if (mod === "shift") {
            const from = anchor >= 0 ? anchor : Math.max(0, rows.findIndex(x => x.key === selected))
            out = rows.slice(Math.min(from, index), Math.max(from, index) + 1).map(x => x.key)
        } else {
            out = chosen.length ? chosen.slice() : (rows.some(x => x.key === selected) ? [selected] : [])
            const at = out.indexOf(r.key)
            if (at >= 0) out.splice(at, 1)
            else out.push(r.key)
            anchor = index
        }
        chosen = Array.from(new Set(out))
    }
    function targets() { return chosen.length ? chosen : (selected ? [selected] : []) }

    ListModel { id: rowModel }
    onRowsChanged: fill()
    property string shown: ""
    property int selectedAt: -1
    function fill() {
        const next = rows.map(r => ({ rk: r.key, section: r.sectionLabel }))
        for (let i = 0; i < next.length; i++) {
            if (i >= rowModel.count) rowModel.append(next[i])
            else if (rowModel.get(i).rk !== next[i].rk || rowModel.get(i).section !== next[i].section) rowModel.set(i, next[i])
        }
        if (rowModel.count > next.length)
            rowModel.remove(next.length, rowModel.count - next.length)
        const id = notes.folder + "|" + notes.query
        const same = id === shown
        if (!same) {
            shown = id
            chosen = []
            anchor = -1
            view.positionViewAtBeginning()
        } else if (chosen.length) {
            chosen = chosen.filter(k => rows.some(r => r.key === k))
        }
        const at = rows.findIndex(r => r.key === selected)
        if (same && at < 0 && selectedAt >= 0 && selected !== "" && rows.length) {
            const key = rows[Math.min(selectedAt, rows.length - 1)].key
            Qt.callLater(() => pane.picked(key))
        } else if (same && at < 0 && selected !== "" && !rows.length) {
            Qt.callLater(() => pane.picked(""))
        }
        view.currentIndex = at
        selectedAt = at
    }
    onSelectedChanged: { view.currentIndex = rows.findIndex(r => r.key === selected); selectedAt = view.currentIndex }
    Component.onCompleted: fill()

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // the heading: the folder, large, then its figures in the data face (offline: when the notes date from)
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 78
            color: "transparent"
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 18; anchors.rightMargin: 10; anchors.topMargin: 6
                spacing: 4
                OButton {
                    id: foldersButton
                    visible: pane.compact
                    kind: "quiet"; implicitWidth: 34; iconName: "sidebar"; tip: app.t.folders
                    onClicked: pane.folderMenuRequested(foldersButton)
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Text {
                        Layout.fillWidth: true
                        text: notes.heading
                        elide: Text.ElideRight
                        font.family: "Schibsted Grotesk"; font.pixelSize: 24; font.weight: Font.Bold; font.letterSpacing: -0.4
                        color: pane.c.text
                        Accessible.role: Accessible.Heading
                    }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 8
                        Text {
                            height: 20; verticalAlignment: Text.AlignVCenter
                            text: app.plural(notes.query !== "" ? "results_count" : "notes_count", pane.rows.length)
                            font.family: "JetBrains Mono"; font.pixelSize: 12
                            color: pane.c.muted
                        }
                        SyncBadge { implicitHeight: 20 }
                    }
                }
                OButton {
                    id: sortButton
                    visible: !pane.trash
                    kind: "quiet"; implicitWidth: 34; iconName: "sort"; tip: app.t.view_options
                    onClicked: sortMenu.open()
                    OMenu {
                        id: sortMenu
                        y: sortButton.height + 6
                        implicitWidth: 260
                        heading: app.t.sort_by
                        OMenuItem { text: app.t.sort_modified; iconName: app.prefs.sort === "modified" ? "check" : ""; onTriggered: app.setPref("sort", "modified") }
                        OMenuItem { text: app.t.sort_created; iconName: app.prefs.sort === "created" ? "check" : ""; onTriggered: app.setPref("sort", "created") }
                        OMenuItem { text: app.t.sort_title; iconName: app.prefs.sort === "title" ? "check" : ""; onTriggered: app.setPref("sort", "title") }
                        Rectangle { width: parent.width; height: 1; color: pane.c.hairline }
                        OMenuItem { text: app.t.group_dates; switchable: true; on: !!app.prefs.group_dates; onTriggered: app.setPref("group_dates", !app.prefs.group_dates) }
                    }
                }
                OButton {
                    visible: !pane.trash
                    kind: "quiet"; implicitWidth: 34; iconName: "compose"; tip: app.t.new_note + "  (Ctrl+N)"
                    onClicked: pane.newNote()
                }
                // the other ways to start one: the note of the day, a template
                OButton {
                    id: moreNew
                    visible: !pane.trash
                    kind: "quiet"; implicitWidth: 22; iconName: "chevronDown"; iconSize: 13; tip: app.t.new_more
                    onClicked: newMenu.open()
                    OMenu {
                        id: newMenu
                        y: moreNew.height + 6
                        x: moreNew.width - width
                        implicitWidth: 290
                        OMenuItem { text: app.t.new_note + "   Ctrl+N"; iconName: "compose"; onTriggered: pane.newNote() }
                        OMenuItem { text: app.t.daily_note + "   Ctrl+Maj+D"; iconName: "today"; onTriggered: pane.dailyRequested() }
                        Rectangle { width: parent.width; height: 1; color: pane.c.hairline }
                        Text {
                            leftPadding: 10; topPadding: 6; bottomPadding: 4
                            text: app.t.from_template
                            font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                            font.capitalization: Font.AllUppercase; font.letterSpacing: 0.8
                            color: pane.c.muted
                        }
                        Repeater {
                            model: notes.templates
                            OMenuItem {
                                required property var modelData
                                text: modelData.title
                                iconName: modelData.own ? "note" : "sparkle"
                                onTriggered: pane.newFrom(modelData.id)
                            }
                        }
                        Text {
                            width: parent.width
                            leftPadding: 10; rightPadding: 10; topPadding: 4; bottomPadding: 6
                            text: app.t.templates_lead
                            wrapMode: Text.WordWrap
                            font.family: "Schibsted Grotesk"; font.pixelSize: 12
                            color: pane.c.faint
                        }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.margins: 12; Layout.bottomMargin: 2
            visible: pane.trash
            implicitHeight: trashLead.implicitHeight + 20
            radius: 8
            color: pane.c.card
            border.width: 1; border.color: pane.c.line
            Text {
                id: trashLead
                anchors.left: parent.left; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                anchors.margins: 12
                text: notes.online ? app.t.trash_lead : app.t.trash_offline
                wrapMode: Text.WordWrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                color: pane.c.muted
                lineHeight: 1.2
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 16; Layout.rightMargin: 10
            Layout.topMargin: 8; Layout.bottomMargin: 4
            visible: pane.chosen.length > 0
            spacing: 4
            Text {
                Layout.fillWidth: true
                text: app.plural("selected_count", pane.chosen.length)
                elide: Text.ElideRight
                font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                color: pane.c.text
            }
            // pin them all, or unpin them when they all are
            OButton {
                readonly property bool allPinned: pane.chosen.length > 0 && pane.chosen.every(k => (pane.rows.find(r => r.key === k) || {}).pinned)
                visible: !pane.trash; kind: "quiet"; height_: 28; implicitWidth: 30; iconName: "pushpin"; iconSize: 16
                tip: allPinned ? app.t.unpin : app.t.pin
                onClicked: { notes.pinMany(pane.chosen, !allPinned); pane.chosen = [] }
            }
            OButton { visible: !pane.trash; kind: "quiet"; height_: 28; implicitWidth: 30; iconName: "move"; iconSize: 16; tip: app.t.move_to; onClicked: pane.moveRequested(pane.chosen) }
            OButton { visible: !pane.trash; kind: "quiet"; height_: 28; implicitWidth: 30; iconName: "link"; iconSize: 16; tip: app.t.link_copy; onClicked: notes.copyLinks(pane.chosen) }
            OButton { visible: pane.trash; kind: "quiet"; height_: 28; iconName: "restore"; iconSize: 16; text: app.t.restore; onClicked: { notes.restore(pane.chosen); pane.chosen = [] } }
            OButton { kind: "quiet"; height_: 28; implicitWidth: 30; iconName: "trash"; iconSize: 16; danger: true; tip: pane.trash ? app.t.delete_forever : app.t.delete_note; onClicked: pane.deleteRequested(pane.chosen) }
            OButton { kind: "quiet"; height_: 28; implicitWidth: 28; iconName: "close"; iconSize: 14; tip: app.t.select_clear; onClicked: pane.chosen = [] }
        }

        ListView {
            id: view
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.topMargin: 4
            clip: true
            model: rowModel
            currentIndex: -1
            keyNavigationEnabled: true
            highlightMoveDuration: 0
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            section.property: "section"
            section.criteria: ViewSection.FullString
            section.delegate: Item {
                required property string section
                width: ListView.view.width
                height: section === "" ? 0 : 32
                visible: section !== ""
                Text {
                    x: 18; anchors.bottom: parent.bottom; anchors.bottomMargin: 6
                    text: parent.section
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.Bold
                    color: pane.c.text
                }
            }
            onCurrentIndexChanged: {
                if (activeFocus && currentIndex >= 0 && currentIndex < pane.rows.length && pane.rows[currentIndex].key !== pane.selected)
                    pane.picked(pane.rows[currentIndex].key)
            }
            Keys.onReturnPressed: if (currentIndex >= 0) pane.picked(pane.rows[currentIndex].key)
            Keys.onDeletePressed: pane.deleteRequested(pane.targets())
            Keys.onEscapePressed: event => { event.accepted = pane.chosen.length > 0; pane.chosen = [] }
            Keys.onPressed: event => {
                if (event.key === Qt.Key_A && (event.modifiers & Qt.ControlModifier)) {
                    pane.chosen = pane.rows.map(r => r.key)
                    event.accepted = true
                }
            }

            delegate: AbstractButton {
                id: row
                required property int index
                readonly property var r: pane.rows[index] || ({})
                readonly property bool chosen: pane.chosen.length > 0 && pane.isChosen(r.key)
                readonly property bool current: pane.chosen.length > 0 ? chosen : r.key === pane.selected
                readonly property bool strong: false        // the chosen note keeps its ink: a wash and the band mark it
                readonly property color ink: strong ? pane.c.actionText : pane.c.text
                readonly property color soft: strong ? pane.c.actionText : pane.c.muted
                // a hairline between the notes of a section, as on macOS
                readonly property bool lastOfSection: index + 1 >= pane.rows.length || (pane.rows[index + 1] || {}).sectionLabel !== r.sectionLabel
                width: ListView.view.width
                height: (pane.mixed && !r.trashed ? 76 : 64) + (notes.folder === "shared" && (r.sharedWho || "") !== "" ? 18 : 0)
                hoverEnabled: true
                focusPolicy: Qt.NoFocus
                Accessible.name: r.title || ""
                onClicked: { view.forceActiveFocus(); pane.clickRow(index, app.modifier()) }
                background: Item {
                    Rectangle {
                        anchors.fill: parent
                        anchors.leftMargin: 8; anchors.rightMargin: 8; anchors.topMargin: 1; anchors.bottomMargin: 1
                        radius: 8
                        color: row.current ? (view.activeFocus ? pane.c.card : Qt.tint(pane.c.card, Qt.alpha(pane.c.famDocs, theme.dark ? 0.12 : 0.06)))
                             : (row.hovered ? pane.c.hover : "transparent")
                        border.width: row.current && view.activeFocus ? 1.5 : 0
                        border.color: Qt.alpha(pane.c.famDocs, 0.55)
                        Band {
                            visible: row.current
                            anchors { left: parent.left; top: parent.top; bottom: parent.bottom; topMargin: 10; bottomMargin: 10 }
                            radius: 1.5
                            color: pane.c.famDocs
                        }
                    }
                    Rectangle {
                        visible: !row.lastOfSection && !row.current
                        x: 18; anchors.bottom: parent.bottom
                        width: parent.width - 36; height: 1
                        color: pane.c.hairline
                    }
                }
                contentItem: RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 18; anchors.rightMargin: 16
                    spacing: 10
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            Icon { visible: !!row.r.pinned && notes.folder !== "trash"; name: "pushpin"; size: 13; color: row.strong ? pane.c.actionText : pane.c.saffron }
                            Text {
                                Layout.fillWidth: true
                                text: row.r.title || ""
                                elide: Text.ElideRight
                                font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.weight: Font.DemiBold
                                color: row.ink
                            }
                            Rectangle {
                                visible: !!row.r.pending && !row.r.trashed
                                implicitWidth: 7; implicitHeight: 7; radius: 3.5
                                color: pane.c.saffron
                                ToolTip.text: app.t.pending_one
                                ToolTip.visible: pendingHover.hovered
                                HoverHandler { id: pendingHover }
                            }
                            Icon {
                                visible: !!row.r.sharedKind
                                name: row.r.sharedKind === "out" && row.r.sharedWho === app.t.public_link ? "link" : "people"
                                size: 14; color: row.soft
                            }
                            Icon { visible: !!row.r.readonly && !row.r.trashed; name: "lock"; size: 13; color: row.soft }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8
                            Text {
                                text: row.r.trashed ? "" : app.short(row.r.modified)
                                visible: text !== ""
                                font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                                color: row.soft
                            }
                            Text {
                                Layout.fillWidth: true
                                text: row.r.preview || ""
                                elide: Text.ElideRight
                                maximumLineCount: 1
                                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                                color: row.soft
                                opacity: row.strong ? 0.85 : 1
                            }
                            Text {
                                visible: row.r.checks !== ""
                                text: row.r.checks || ""
                                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                                color: row.soft
                            }
                        }
                        RowLayout {
                            visible: pane.mixed && !row.r.trashed
                            spacing: 5
                            Icon { name: "folder"; size: 13; color: row.soft }
                            Text {
                                text: row.r.folderName || ""
                                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                                color: row.soft
                            }
                        }
                        // in « Partagées »: with whom, or who shared it
                        RowLayout {
                            visible: notes.folder === "shared" && (row.r.sharedWho || "") !== ""
                            Layout.fillWidth: true
                            spacing: 5
                            Icon { name: row.r.sharedKind === "in" ? "user" : "people"; size: 13; color: row.soft }
                            Text {
                                Layout.fillWidth: true
                                text: (row.r.sharedKind === "in" ? app.t.shared_from_short : app.t.shared_with_short).replace("%1", row.r.sharedWho || "")
                                elide: Text.ElideRight
                                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                                color: row.soft
                            }
                        }
                    }
                    Rectangle {
                        visible: (row.r.thumb || "") !== ""
                        implicitWidth: 44; implicitHeight: 44; radius: 8
                        color: pane.c.card
                        border.width: 1; border.color: pane.c.line
                        clip: true
                        Image {
                            anchors.fill: parent; anchors.margins: 1
                            source: row.r.thumb || ""
                            fillMode: Image.PreserveAspectCrop
                            asynchronous: true
                            sourceSize.width: 96
                        }
                    }
                }
                TapHandler {
                    acceptedButtons: Qt.RightButton
                    onTapped: rowMenu.openFor(row.r, row)
                }
                // dragged onto a folder of the sidebar: moved there (the whole selection when it is part of it);
                // into a note, onto a task (Tâches) or elsewhere: a link to it
                readonly property var keys: row.chosen ? pane.chosen : [r.key]
                DragHandler { id: dragger; target: null; enabled: !row.r.trashed }
                Drag.active: dragger.active
                Drag.dragType: Drag.Automatic
                Drag.supportedActions: Qt.MoveAction | Qt.CopyAction | Qt.LinkAction
                Drag.mimeData: row.hovered ? notes.dragData(row.keys) : ({ "orneos/notes": row.keys.join(",") })
                Drag.source: row
                Drag.onDragStarted: notes.dragStarted()
                Drag.onDragFinished: notes.dragEnded()
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: pane.rows.length === 0
            ColumnLayout {
                anchors.centerIn: parent
                width: parent.width - 48
                spacing: 8
                Icon {
                    Layout.alignment: Qt.AlignHCenter
                    name: notes.query !== "" ? "search" : pane.trash ? "trash" : notes.folder.indexOf("tag:") === 0 ? "hash" : "note"
                    size: 30; color: pane.c.faint
                }
                Text {
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                    text: notes.query !== "" ? app.t.empty_search : pane.trash ? app.t.empty_trash : app.t.empty_folder
                    font.family: "Schibsted Grotesk"; font.pixelSize: 14
                    color: pane.c.muted
                    lineHeight: 1.25
                }
            }
        }
    }

    OMenu {
        id: rowMenu
        property var row: ({})
        property bool many: false
        function openFor(r, item) {
            row = r
            many = pane.chosen.length > 1 && pane.isChosen(r.key)
            const p = item.mapToItem(pane, Math.min(item.width - 280, 120), item.height - 6)
            x = p.x; y = p.y
            open()
        }
        readonly property var keys: many ? pane.chosen : [row.key]
        OMenuItem { visible: !rowMenu.row.trashed; text: rowMenu.row.pinned ? app.t.unpin : app.t.pin; iconName: "pushpin"; onTriggered: rowMenu.many ? notes.pinMany(rowMenu.keys, !rowMenu.row.pinned) : notes.togglePin(rowMenu.row.key) }
        OMenuItem { visible: !rowMenu.row.trashed && !rowMenu.row.readonly; text: app.t.move_to + "…"; iconName: "move"; onTriggered: pane.moveRequested(rowMenu.keys) }
        OMenuItem { visible: !rowMenu.row.trashed && !rowMenu.many; text: app.t.duplicate; iconName: "duplicate"; onTriggered: pane.picked(notes.duplicate(rowMenu.row.key)) }
        OMenuItem { visible: !rowMenu.row.trashed; text: app.t.link_copy; iconName: "link"; onTriggered: notes.copyLinks(rowMenu.keys) }
        OMenuItem { visible: !rowMenu.row.trashed && !rowMenu.many && (!rowMenu.row.readonly || rowMenu.row.sharedKind === "in"); text: app.t.share_people; iconName: "people"; enabled: notes.online; onTriggered: pane.shareRequested(rowMenu.row.key) }
        OMenuItem { visible: !rowMenu.row.trashed && !rowMenu.many; text: app.t.share_link; iconName: "link"; enabled: notes.online; onTriggered: notes.shareLink(rowMenu.row.key) }
        OMenuItem { visible: !rowMenu.row.trashed && !rowMenu.many; text: app.t.share_mail; iconName: "mail"; onTriggered: notes.mail(rowMenu.row.key) }
        OMenuItem { visible: !rowMenu.row.trashed && !rowMenu.many; text: app.t.share_tasks; iconName: "bell"; onTriggered: pane.tasksRequested(rowMenu.row.key) }
        OMenuItem { visible: !rowMenu.row.trashed && !rowMenu.many; text: app.t.open_cloud; iconName: "cloud"; onTriggered: notes.openInCloud(rowMenu.row.key) }
        OMenuItem { visible: !!rowMenu.row.trashed; text: app.t.restore + (rowMenu.many ? " (" + pane.chosen.length + ")" : ""); iconName: "restore"; onTriggered: { notes.restore(rowMenu.keys); pane.chosen = [] } }
        OMenuItem {
            visible: !rowMenu.row.readonly || !!rowMenu.row.trashed
            text: (rowMenu.row.trashed ? app.t.delete_forever : app.t.delete_note) + (rowMenu.many ? " (" + pane.chosen.length + ")" : "")
            iconName: "trash"
            onTriggered: pane.deleteRequested(rowMenu.keys)
        }
    }
}
