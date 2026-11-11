// The tab « Fichiers » of a group, in place of the chat: everything shared in the conversation (pictures and
// videos, files, voice messages, sounds, polls, places…), searched by name, author or words, filtered by kind,
// date and person, sorted, in a list by month or in a grid. A file opens in this computer's app (a picture in
// the viewer), is saved elsewhere, or is found again in the chat. Older items come on demand (Talk: 200 a call).
import QtCore as Std               // StandardPaths only: its Settings would hide ours
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "components"

Rectangle {
    id: files
    readonly property var c: theme.c
    readonly property var data_: meet.files
    readonly property bool ready: data_.loaded && data_.token === meet.current
    signal shownInChat(int id)
    color: c.bg

    property string kind: ""            // "" = every kind
    property string when: "any"
    property string who: ""
    property string sort: "newest"
    property bool grid: false

    function read() { if (visible && meet.current !== "" && !(data_.token === meet.current && (data_.loaded || data_.loading))) meet.loadFiles() }
    onVisibleChanged: read()
    Connections { target: meet; function onRoomChanged() { files.read() } }
    function focusSearch() { search.forceActiveFocus(); search.selectAll() }
    function clear() { search.text = ""; kind = ""; when = "any"; who = ""; whenBox.select("any"); whoBox.currentIndex = 0 }

    readonly property var items: ready ? (data_.items || []) : []
    // the kinds present, in the order of the details panel, with their counts
    readonly property var kinds: {
        const order = ["media", "file", "voice", "audio", "poll", "location", "deckcard", "recording", "other"]
        const counts = {}
        for (const it of items) counts[it.kind] = (counts[it.kind] || 0) + 1
        return order.filter(k => counts[k]).map(k => ({ id: k, count: counts[k] }))
    }
    readonly property var authors: {
        const seen = {}, out = [{ text: app.t.anyone, value: "" }]
        for (const it of items) if (it.actorId && !seen[it.actorId]) { seen[it.actorId] = true; out.push({ text: it.name || it.actorId, value: it.actorId }) }
        return out
    }
    function title(it) {
        const f = it.files && it.files[0]
        return f ? f.name : it.poll ? it.poll.question : it.location ? it.location.name : it.plain
    }
    readonly property var shown: {
        const q = search.text.trim().toLowerCase()
        const now = Date.now() / 1000
        const cutoff = when === "7" ? now - 7 * 86400 : when === "30" ? now - 30 * 86400
                     : when === "year" ? new Date(new Date().getFullYear(), 0, 1).getTime() / 1000 : 0
        const out = items.filter(it => (!kind || it.kind === kind) && (!who || it.actorId === who) && it.time >= cutoff
                                       && (!q || (title(it) + " " + it.name + " " + it.plain).toLowerCase().indexOf(q) >= 0))
        const size = it => (it.files && it.files[0] && it.files[0].size) || 0
        if (sort === "oldest") out.sort((a, b) => a.id - b.id)
        else if (sort === "name") out.sort((a, b) => String(title(a)).localeCompare(String(title(b))))
        else if (sort === "size") out.sort((a, b) => size(b) - size(a))
        return out
    }
    // the list: a heading for each month when sorted by date
    readonly property var rows: {
        if (sort !== "newest" && sort !== "oldest") return shown
        const out = []
        let last = ""
        for (const it of shown) {
            const d = new Date(it.time * 1000)
            const month = Qt.locale(app.lang).standaloneMonthName(d.getMonth()) + " " + d.getFullYear()
            if (month !== last) { out.push({ heading: month.charAt(0).toUpperCase() + month.slice(1) }); last = month }
            out.push(it)
        }
        return out
    }
    readonly property bool more: {
        const m = data_.more || {}
        return kind ? !!m[kind] : Object.keys(m).some(k => m[k])
    }
    readonly property bool filtered: search.text !== "" || kind !== "" || when !== "any" || who !== ""

    function open(it) {
        const f = it.files && it.files[0]
        if (!f) { files.shownInChat(it.id); return }
        if (f.preview && String(f.mime).startsWith("image/"))
            viewer.show(f, shown.filter(x => x.kind === "media").map(x => x.files[0]).filter(x => x && x.preview && String(x.mime).startsWith("image/")))
        else meet.openFile(f)
    }
    function iconFor(it) {
        const f = it.files && it.files[0]
        if (f) {
            const m = String(f.mime)
            return m.startsWith("image/") ? "image" : m.startsWith("video/") ? "play" : m.startsWith("audio/") ? "mic"
                 : m === "application/pdf" ? "pdf" : "clip"
        }
        return it.poll ? "checklist" : it.location ? "location" : it.kind === "deckcard" ? "table" : "chat"
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: 24; anchors.rightMargin: 24; anchors.topMargin: 16
        spacing: 12

        // search, date, person, order, view
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            OTextField {
                id: search
                Layout.fillWidth: true
                Layout.minimumWidth: 180
                iconName: "search"
                placeholderText: app.t.files_search
                Keys.onEscapePressed: text = ""
            }
            OComboBox {
                id: whenBox
                Layout.preferredWidth: 180
                font.pixelSize: 13
                model: [{ text: app.t.when_any, value: "any" }, { text: app.t.when_7, value: "7" },
                        { text: app.t.when_30, value: "30" }, { text: app.t.when_year, value: "year" }]
                onActivated: files.when = currentValue
            }
            OComboBox {
                id: whoBox
                visible: files.authors.length > 2
                Layout.preferredWidth: 180
                font.pixelSize: 13
                model: files.authors
                onActivated: files.who = currentValue
            }
            OComboBox {
                id: sortBox
                Layout.preferredWidth: 150
                font.pixelSize: 13
                model: [{ text: app.t.sort_newest, value: "newest" }, { text: app.t.sort_oldest, value: "oldest" },
                        { text: app.t.sort_name, value: "name" }, { text: app.t.sort_size, value: "size" }]
                onActivated: files.sort = currentValue
            }
            Row {
                spacing: 2
                OButton { kind: files.grid ? "quiet" : "secondary"; iconName: "list"; tip: app.t.view_list; onClicked: files.grid = false }
                OButton { kind: files.grid ? "secondary" : "quiet"; iconName: "grid"; tip: app.t.view_grid; onClicked: files.grid = true }
            }
        }

        // the kinds
        Flow {
            Layout.fillWidth: true
            visible: files.kinds.length > 0
            spacing: 6
            Repeater {
                model: [{ id: "", count: files.items.length }].concat(files.kinds)
                AbstractButton {
                    id: chip
                    required property var modelData
                    readonly property bool on: files.kind === modelData.id
                    implicitHeight: 30
                    implicitWidth: chipText.implicitWidth + 24
                    hoverEnabled: true
                    onClicked: files.kind = modelData.id
                    background: Rectangle {
                        radius: 15
                        color: chip.on ? files.c.tint : chip.hovered ? files.c.hover : "transparent"
                        border.width: 1; border.color: chip.on ? files.c.accentLine : files.c.hairline
                    }
                    contentItem: Text {
                        id: chipText
                        textFormat: Text.PlainText
                        text: (chip.modelData.id ? (app.t["rs_shared_" + chip.modelData.id] || app.t.rs_shared_other) : app.t.files_all)
                              + "  " + chip.modelData.count
                        font.pixelSize: 13; font.weight: chip.on ? Font.DemiBold : Font.Normal
                        color: chip.on ? files.c.tintText : files.c.text
                        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            visible: files.ready && files.items.length > 0
            Text {
                textFormat: Text.PlainText
                text: app.plural("files_count", files.shown.length)
                font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                font.capitalization: Font.AllUppercase; font.letterSpacing: 0.8
                color: files.c.faint
            }
            AbstractButton {
                visible: files.filtered
                implicitHeight: 20; implicitWidth: clearText.implicitWidth
                onClicked: files.clear()
                contentItem: Text { id: clearText; text: app.t.clear_filters; font.pixelSize: 12; color: files.c.action }
            }
            Item { Layout.fillWidth: true }
        }

        // loading, nothing, nothing that matches
        Column {
            Layout.fillWidth: true
            visible: !files.ready
            spacing: 8
            Repeater { model: 5; Skeleton { width: parent.width; height: 52 } }
        }
        EmptyState {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: files.ready && files.shown.length === 0
            iconName: files.items.length ? "search" : "folder"
            title: files.data_.failed ? app.t.offline_action : files.items.length ? app.t.files_no_match : app.t.rs_shared_none
            actionText: files.filtered ? app.t.clear_filters : ""
            onActivated: files.clear()
        }

        // the list, by month
        ListView {
            id: list
            visible: files.ready && files.shown.length > 0 && !files.grid
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: files.rows
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            spacing: 2
            delegate: Loader {
                required property var modelData
                width: ListView.view.width
                sourceComponent: modelData.heading ? heading : line
                property var it: modelData
            }
            footer: moreFooter
        }

        // the grid: pictures in squares, the rest on cards
        GridView {
            id: gridView
            visible: files.ready && files.shown.length > 0 && files.grid
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: files.shown
            readonly property int columns: Math.max(2, Math.floor(width / 190))
            cellWidth: Math.floor(width / columns)
            cellHeight: cellWidth + 44
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            delegate: AbstractButton {
                id: tile
                required property var modelData
                readonly property var file: (modelData.files && modelData.files[0]) || null
                width: gridView.cellWidth; height: gridView.cellHeight
                hoverEnabled: true
                Accessible.name: files.title(modelData)
                onClicked: files.open(modelData)
                TapHandler { acceptedButtons: Qt.RightButton; onTapped: itemMenu.openFor(tile.modelData, tile) }
                contentItem: ColumnLayout {
                    spacing: 6
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: tile.width - 10
                        Layout.margins: 5; Layout.bottomMargin: 0
                        radius: 10
                        color: files.c.card
                        border.width: tile.hovered ? 2 : 1
                        border.color: tile.hovered ? files.c.action : files.c.hairline
                        clip: true
                        Image {
                            anchors.fill: parent; anchors.margins: 1
                            visible: !!(tile.file && tile.file.preview)
                            source: tile.file && tile.file.preview ? "image://meet/preview/" + tile.file.id : ""
                            sourceSize: Qt.size(360, 360)
                            fillMode: Image.PreserveAspectCrop
                            asynchronous: true
                        }
                        Icon {
                            anchors.centerIn: parent
                            visible: !(tile.file && tile.file.preview) || String(tile.file.mime).startsWith("video/")
                            name: files.iconFor(tile.modelData); size: 30
                            color: tile.file && tile.file.preview ? "white" : files.c.muted
                        }
                    }
                    Text {
                        Layout.fillWidth: true; Layout.leftMargin: 8; Layout.rightMargin: 8
                        textFormat: Text.PlainText
                        text: files.title(tile.modelData)
                        elide: Text.ElideMiddle; font.pixelSize: 12; color: files.c.text
                    }
                    Text {
                        Layout.fillWidth: true; Layout.leftMargin: 8; Layout.rightMargin: 8
                        textFormat: Text.PlainText
                        text: tile.modelData.name + " · " + app.short(tile.modelData.time)
                        elide: Text.ElideRight; font.pixelSize: 11; color: files.c.muted
                    }
                }
                background: Item {}
            }
            footer: moreFooter
        }
    }

    Component {
        id: moreFooter
        Item {
            width: ListView.view ? ListView.view.width : (GridView.view ? GridView.view.width : 0)
            height: files.more ? 64 : 16
            OButton {
                visible: files.more
                anchors.centerIn: parent
                kind: "secondary"; iconName: "history"
                text: app.t.files_more
                onClicked: meet.loadMoreFiles(files.kind)
            }
        }
    }

    Component {
        id: heading
        Text {
            textFormat: Text.PlainText
            topPadding: 14; bottomPadding: 6; leftPadding: 4
            text: parent ? parent.it.heading : ""
            font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.weight: Font.DemiBold
            color: files.c.text
        }
    }

    Component {
        id: line
        AbstractButton {
            id: row
            readonly property var it: parent ? parent.it : ({})
            readonly property var file: (it.files && it.files[0]) || null
            implicitHeight: 58
            hoverEnabled: true
            Accessible.name: files.title(it)
            onClicked: files.open(it)
            TapHandler { acceptedButtons: Qt.RightButton; onTapped: itemMenu.openFor(row.it, row) }
            background: Rectangle { radius: 10; color: row.hovered ? files.c.hover : "transparent" }
            contentItem: RowLayout {
                spacing: 12
                Rectangle {
                    Layout.leftMargin: 6
                    implicitWidth: 42; implicitHeight: 42; radius: 8
                    color: files.c.tint
                    clip: true
                    Image {
                        anchors.fill: parent
                        visible: !!(row.file && row.file.preview)
                        source: row.file && row.file.preview ? "image://meet/preview/" + row.file.id : ""
                        sourceSize: Qt.size(84, 84)
                        fillMode: Image.PreserveAspectCrop
                        asynchronous: true
                    }
                    Icon {
                        anchors.centerIn: parent
                        visible: !(row.file && row.file.preview)
                        name: files.iconFor(row.it); size: 18; color: files.c.tintText
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 1
                    Text {
                        Layout.fillWidth: true
                        textFormat: Text.PlainText
                        text: files.title(row.it)
                        elide: Text.ElideMiddle; font.pixelSize: 14; font.weight: Font.Medium; color: files.c.text
                    }
                    Text {
                        Layout.fillWidth: true
                        textFormat: Text.PlainText
                        text: [row.it.name, app.short(row.it.time), row.file && row.file.size ? app.size(row.file.size) : "",
                               app.t["rs_shared_" + row.it.kind] || ""].filter(x => x).join(" · ")
                        elide: Text.ElideRight; font.pixelSize: 12; color: files.c.muted
                    }
                }
                Row {
                    Layout.rightMargin: 6
                    spacing: 2
                    opacity: row.hovered ? 1 : 0
                    OButton { kind: "quiet"; iconName: "chat"; height_: 30; tip: app.t.show_in_chat; onClicked: files.shownInChat(row.it.id) }
                    OButton { kind: "quiet"; iconName: "download"; height_: 30; tip: app.t.save_as; visible: !!row.file
                              onClicked: { saver.file = row.file; saver.open() } }
                    OButton { kind: "quiet"; iconName: "more"; height_: 30; tip: app.t.more; onClicked: itemMenu.openFor(row.it, row) }
                }
            }
        }
    }

    MeetMenu {
        id: itemMenu
        property var it: ({})
        readonly property var file: (it.files && it.files[0]) || null
        function openFor(x, item) { it = x; popupAt(item, true) }
        OMenuItem { text: app.t.open; iconName: "openExternal"; onTriggered: files.open(itemMenu.it) }
        OMenuItem { text: app.t.show_in_chat; iconName: "chat"; onTriggered: files.shownInChat(itemMenu.it.id) }
        OMenuItem { text: app.t.save_as; iconName: "download"; visible: !!itemMenu.file; onTriggered: { saver.file = itemMenu.file; saver.open() } }
        OMenuItem { text: app.t.copy_link_message; iconName: "link"
                    onTriggered: { app.copy(meet.room.link + "#message_" + itemMenu.it.id); app.toast(app.t.link_copied) } }
    }

    FileDialog {
        id: saver
        property var file: ({})
        fileMode: FileDialog.SaveFile
        title: app.t.save_as
        currentFolder: Std.StandardPaths.writableLocation(Std.StandardPaths.DownloadLocation)
        selectedFile: Std.StandardPaths.writableLocation(Std.StandardPaths.DownloadLocation) + "/" + encodeURIComponent(file.name || "")
        onAccepted: meet.saveFile(file, String(selectedFile))
    }
    ImageViewer { id: viewer }
}
