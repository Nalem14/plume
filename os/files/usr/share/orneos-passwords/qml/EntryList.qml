// The list of the selected category: by letter (or most recent first), the security review by kind of
// problem, the trash, or the Wi-Fi networks of this computer.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Rectangle {
    id: pane
    readonly property var c: theme.c
    property string selected
    signal picked(string id)
    signal ornisPlan()
    color: c.bg

    readonly property string category: vault.category
    readonly property bool isWifi: category === "wifi" && vault.query === ""
    readonly property bool isSecurity: category === "security" && vault.query === ""
    readonly property var review: vault.security

    // rows of the list, with the section they show under
    readonly property var rows: {
        if (isWifi)
            return wifi.networks.map(n => ({ id: n.uuid, label: n.name, username: app.t.wifi_saved, section: "", wifi: true, initial: "", tile: "#1A5F7A", icon: "", issue: "" }))
        if (isSecurity) {
            let out = []
            for (const kind of ["breached", "reused", "weak", "old", "twofa"])
                for (const r of review[kind] || [])
                    out.push(Object.assign({}, r, { section: kind, key: kind + r.id }))
            return out
        }
        const byName = app.prefs.sort !== "recent" && category !== "trash" && vault.query === ""
        return vault.items.map(r => Object.assign({}, r, { section: byName ? r.letter : "" }))
    }

    function focusList() { view.forceActiveFocus(); if (view.currentIndex < 0 && rows.length) view.currentIndex = 0 }

    // Several entries picked for one action: Ctrl+click adds or removes one, Shift+click takes a range,
    // Ctrl+A all of them. Delete, the bar above the list or the right click then act on all.
    property var chosen: []
    property int anchor: -1
    function isChosen(id) { return chosen.indexOf(id) >= 0 }
    function clickRow(index, key) {
        const r = rows[index]
        if (!r)
            return
        if (key === "" || r.wifi) {
            chosen = []
            anchor = index
            view.currentIndex = index
            picked(r.id)
            return
        }
        let out
        if (key === "shift") {
            const from = anchor >= 0 ? anchor : Math.max(0, rows.findIndex(x => x.id === selected))
            out = rows.slice(Math.min(from, index), Math.max(from, index) + 1).map(x => x.id)
        } else {
            out = chosen.length ? chosen.slice() : (rows.some(x => x.id === selected) ? [selected] : [])
            const at = out.indexOf(r.id)
            if (at >= 0)
                out.splice(at, 1)
            else
                out.push(r.id)
            anchor = index
        }
        chosen = Array.from(new Set(out))
    }
    function chooseAll() { if (!isWifi) chosen = Array.from(new Set(rows.map(r => r.id))) }
    // Delete: the chosen entries, else the selected one (from the trash: for good, after a question)
    function removeChosen() {
        const ids = chosen.length ? chosen : (selected && !isWifi ? [selected] : [])
        if (!ids.length)
            return
        if (category === "trash" && vault.query === "") {
            emptyTrash.ask(ids.length > 1 ? app.plural("delete_forever_many", ids.length) : app.t.delete_forever_title,
                           app.t.delete_forever_text,
                           [{ id: "cancel", text: app.t.cancel }, { id: "yes", text: app.t.delete_forever, kind: "danger" }],
                           () => { vault.purgeMany(ids); pane.chosen = [] })
            return
        }
        vault.trashMany(ids)
        chosen = []
    }

    // sections need roles: the rows go through a ListModel (only what the sections and the count need).
    // It is changed in place, not refilled: the list keeps its scroll when an entry leaves or changes.
    ListModel { id: rowModel }
    onRowsChanged: fill()
    property string shown: ""             // what the rows are a list of: another one starts at the top
    property int selectedAt: -1           // the selected entry's line, for its neighbour when it leaves
    function fill() {
        const next = rows.map(r => ({ rid: r.id, section: r.section }))
        for (let i = 0; i < next.length; i++) {
            if (i >= rowModel.count)
                rowModel.append(next[i])
            else if (rowModel.get(i).rid !== next[i].rid || rowModel.get(i).section !== next[i].section)
                rowModel.set(i, next[i])
        }
        if (rowModel.count > next.length)
            rowModel.remove(next.length, rowModel.count - next.length)
        const key = category + "|" + vault.query + "|" + app.prefs.sort
        const same = key === shown
        if (!same) {
            shown = key
            chosen = []
            anchor = -1
            view.positionViewAtBeginning()
        } else if (chosen.length) {
            chosen = chosen.filter(id => rows.some(r => r.id === id))
        }
        const at = rows.findIndex(r => r.id === selected)
        if (same && at < 0 && selectedAt >= 0 && selected !== "" && !isWifi && rows.length) {
            // the selected entry left this list (deleted, restored, moved): its neighbour takes its place
            const id = rows[Math.min(selectedAt, rows.length - 1)].id
            Qt.callLater(() => pane.picked(id))
        }
        view.currentIndex = at
        selectedAt = at
    }
    onSelectedChanged: { view.currentIndex = rows.findIndex(r => r.id === selected); selectedAt = view.currentIndex }
    Component.onCompleted: { if (isWifi) wifi.load(); fill() }
    onIsWifiChanged: if (isWifi) wifi.load()

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ---- above the rows: the review's summary, the trash, the sort order ----------------------------
        Rectangle {
            Layout.fillWidth: true
            Layout.margins: 12
            Layout.bottomMargin: 4
            visible: pane.isSecurity
            implicitHeight: summary.implicitHeight + 28
            radius: 10
            color: pane.review.serious ? (pane.review.breached && pane.review.breached.length ? c.dangerTint : c.saffronTint) : c.okTint
            ColumnLayout {
                id: summary
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                anchors.margins: 14
                spacing: 6
                RowLayout {
                    spacing: 10
                    Icon {
                        name: pane.review.serious ? "warning" : "shieldCheck"; size: 22
                        color: pane.review.serious ? (pane.review.breached && pane.review.breached.length ? c.danger : c.saffronInk) : c.okInk
                    }
                    Text {
                        Layout.fillWidth: true
                        text: pane.review.serious ? app.plural("review_count", pane.review.serious) : app.t.review_clean
                        wrapMode: Text.WordWrap
                        font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.weight: Font.DemiBold
                        color: c.text
                    }
                }
                Text {
                    Layout.fillWidth: true
                    text: pane.review.serious ? app.t.review_lead : app.t.review_clean_lead.replace("%1", pane.review.total || 0)
                    wrapMode: Text.WordWrap
                    lineHeight: 1.25
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                    color: c.muted
                }
                OButton {
                    visible: pane.review.serious > 0 || (pane.review.twofa || []).length > 0
                    Layout.topMargin: 4
                    kind: "accent"; iconName: "ornis"
                    text: app.t.ornis_plan
                    onClicked: pane.ornisPlan()
                }
                Text {
                    visible: (pane.review.ignored || 0) > 0
                    Layout.fillWidth: true
                    text: app.plural("review_ignored", pane.review.ignored)
                    font.family: "Schibsted Grotesk"; font.pixelSize: 12
                    color: c.faint
                }
            }
        }

        // several entries chosen: what can be done to all of them
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
                color: c.text
            }
            OButton {
                visible: pane.category === "trash"
                kind: "quiet"; height_: 28; iconName: "restore"; iconSize: 16
                text: app.t.restore
                onClicked: { vault.restoreMany(pane.chosen); pane.chosen = [] }
            }
            OButton {
                kind: "quiet"; height_: 28; iconName: "trash"; iconSize: 16; danger: true
                text: pane.category === "trash" ? app.t.delete_forever : app.t.delete_entry
                onClicked: pane.removeChosen()
            }
            OButton {
                kind: "quiet"; height_: 28; implicitWidth: 28; iconName: "close"; iconSize: 14
                tip: app.t.select_clear
                onClicked: pane.chosen = []
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 16; Layout.rightMargin: 10
            Layout.topMargin: 8; Layout.bottomMargin: 4
            visible: !pane.isSecurity && !pane.isWifi && pane.rows.length > 0 && pane.chosen.length === 0
            Text {
                Layout.fillWidth: true
                text: app.plural(vault.query !== "" ? "results_count" : "items_count", pane.rows.length)
                font.family: "JetBrains Mono"; font.pixelSize: 12
                color: c.muted
            }
            OButton {
                visible: pane.category === "trash"
                kind: "quiet"; height_: 28
                text: app.t.trash_empty
                onClicked: emptyTrash.ask(app.t.trash_empty_title, app.t.trash_empty_text,
                                          [{ id: "cancel", text: app.t.cancel }, { id: "yes", text: app.t.trash_empty, kind: "danger" }],
                                          () => vault.emptyTrash())
            }
            OButton {
                visible: pane.category !== "trash"
                kind: "quiet"; height_: 28; iconName: "sort"; iconSize: 16
                text: app.prefs.sort === "recent" ? app.t.sort_recent : app.t.sort_name
                tip: app.t.sort
                onClicked: app.setPref("sort", app.prefs.sort === "recent" ? "name" : "recent")
            }
        }

        // ---- the rows ------------------------------------------------------------------------------------
        ListView {
            id: view
            Layout.fillWidth: true
            Layout.fillHeight: true
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
                height: section === "" ? 0 : (pane.isSecurity ? 40 : 28)
                visible: section !== ""
                Text {
                    x: 18; anchors.bottom: parent.bottom; anchors.bottomMargin: 6
                    text: pane.isSecurity ? (app.t["issue_" + parent.section + "_title"] || "") : parent.section
                    font.family: "Schibsted Grotesk"; font.pixelSize: pane.isSecurity ? 13 : 12; font.weight: Font.DemiBold
                    font.capitalization: pane.isSecurity ? Font.MixedCase : Font.AllUppercase
                    color: pane.isSecurity && parent.section === "breached" ? c.danger : c.muted
                }
            }
            onCurrentIndexChanged: {
                if (activeFocus && currentIndex >= 0 && currentIndex < pane.rows.length && pane.rows[currentIndex].id !== pane.selected)
                    pane.picked(pane.rows[currentIndex].id)
            }
            Keys.onReturnPressed: if (currentIndex >= 0) pane.picked(pane.rows[currentIndex].id)
            Keys.onDeletePressed: pane.removeChosen()
            Keys.onEscapePressed: event => { event.accepted = pane.chosen.length > 0; pane.chosen = [] }
            Keys.onPressed: event => {
                if (event.key === Qt.Key_A && (event.modifiers & Qt.ControlModifier)) {
                    pane.chooseAll()
                    event.accepted = true
                }
            }

            delegate: AbstractButton {
                id: row
                required property int index
                readonly property var modelData: pane.rows[index] || ({})
                readonly property bool chosen: pane.chosen.length > 0 && pane.isChosen(modelData.id)
                // with a selection, only its lines stand out
                readonly property bool current: pane.chosen.length > 0 ? chosen : modelData.id === pane.selected
                width: ListView.view.width
                height: 58
                hoverEnabled: true
                focusPolicy: Qt.NoFocus
                Accessible.name: modelData.label || ""
                onClicked: { view.forceActiveFocus(); pane.clickRow(index, app.modifier()) }
                background: Rectangle {
                    anchors.fill: parent
                    anchors.leftMargin: 8; anchors.rightMargin: 8; anchors.topMargin: 1; anchors.bottomMargin: 1
                    radius: 8
                    color: row.current ? (view.activeFocus ? c.card : Qt.tint(c.card, Qt.alpha(c.famTools, theme.dark ? 0.14 : 0.05)))
                         : (row.hovered ? c.hover : "transparent")
                    border.width: row.current && view.activeFocus ? 1.5 : 0
                    border.color: Qt.alpha(c.famTools, theme.dark ? 0.6 : 0.4)
                    Band {
                        visible: row.current
                        anchors { left: parent.left; top: parent.top; bottom: parent.bottom; topMargin: 10; bottomMargin: 10 }
                        radius: 1.5
                        color: c.famTools
                    }
                }
                contentItem: RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 18; anchors.rightMargin: 18
                    spacing: 12
                    SiteIcon {
                        size: 34
                        source: row.modelData.icon || ""
                        initial: row.modelData.initial || ""
                        tile: row.modelData.tile || "#002FA7"
                        glyph: row.modelData.wifi ? "wifi" : ""
                        opacity: row.modelData.trashed ? 0.6 : 1
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 1
                        Text {
                            Layout.fillWidth: true
                            text: row.modelData.label || ""
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.weight: Font.DemiBold
                            color: c.text
                        }
                        Text {
                            Layout.fillWidth: true
                            visible: text !== ""
                            text: row.modelData.username || ""
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13
                            color: c.muted
                            opacity: row.current && view.activeFocus ? 0.85 : 1
                        }
                    }
                    Rectangle {               // waiting to reach the cloud
                        visible: !!row.modelData.pending
                        implicitWidth: 7; implicitHeight: 7; radius: 3.5
                        color: c.saffron
                        ToolTip.text: app.t.pending_one
                        ToolTip.visible: pendingHover.hovered
                        HoverHandler { id: pendingHover }
                    }
                    Icon {
                        visible: !!row.modelData.sharedIn || !!row.modelData.shared
                        name: "people"; size: 16
                        color: c.muted
                    }
                    Icon {
                        visible: !pane.isSecurity && row.modelData.issue !== ""
                        name: "warning"; size: 16
                        color: row.modelData.issue === "breached" ? c.danger : c.saffronInk
                    }
                    Icon {
                        visible: !!row.modelData.favorite && pane.category !== "favorites"
                        name: "star"; size: 15
                        color: c.saffron
                    }
                }
                TapHandler {
                    acceptedButtons: Qt.RightButton
                    enabled: !row.modelData.wifi
                    onTapped: rowMenu.openFor(row.modelData, row)
                }
            }
        }

        // ---- nothing here --------------------------------------------------------------------------------
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: pane.rows.length === 0 && !pane.isSecurity
            ColumnLayout {
                anchors.centerIn: parent
                width: parent.width - 48
                spacing: 8
                Icon {
                    Layout.alignment: Qt.AlignHCenter
                    name: vault.query !== "" ? "search" : pane.isWifi ? "wifi" : pane.category === "trash" ? "trash"
                        : pane.category === "codes" ? "clock" : pane.category === "favorites" ? "star" : "key"
                    size: 30; color: c.faint
                }
                Text {
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                    text: vault.query !== "" ? app.t.empty_search
                        : app.t["empty_" + (pane.category.indexOf("folder:") === 0 ? "folder" : pane.category)] || app.t.empty_all
                    font.family: "Schibsted Grotesk"; font.pixelSize: 14
                    color: c.muted
                    lineHeight: 1.25
                }
            }
        }
    }

    ChoiceDialog { id: emptyTrash }

    OMenu {
        id: rowMenu
        property var row: ({})
        // the right click on a line of the selection acts on the whole selection
        property bool many: false
        function openFor(r, item) {
            row = r
            many = pane.chosen.length > 1 && pane.isChosen(r.id)
            const p = item.mapToItem(pane, Math.min(item.width - 280, 120), item.height - 6)
            x = p.x; y = p.y
            open()
        }
        OMenuItem { visible: rowMenu.many && !rowMenu.row.trashed; text: app.t.delete_entry + " (" + pane.chosen.length + ")"; iconName: "trash"; onTriggered: pane.removeChosen() }
        OMenuItem { visible: rowMenu.many && !!rowMenu.row.trashed; text: app.t.restore + " (" + pane.chosen.length + ")"; iconName: "restore"; onTriggered: { vault.restoreMany(pane.chosen); pane.chosen = [] } }
        OMenuItem { visible: rowMenu.many && !!rowMenu.row.trashed; text: app.t.delete_forever + " (" + pane.chosen.length + ")"; iconName: "trash"; onTriggered: pane.removeChosen() }
        OMenuItem { visible: !rowMenu.many && !rowMenu.row.trashed; text: app.t.copy_username; iconName: "user"; onTriggered: app.copy(vault.detail(rowMenu.row.id).username, "username") }
        OMenuItem { visible: !rowMenu.many && !rowMenu.row.trashed; text: app.t.copy_password; iconName: "key"; onTriggered: app.copy(vault.detail(rowMenu.row.id).password, "password") }
        OMenuItem { visible: !rowMenu.many && !rowMenu.row.trashed && !!rowMenu.row.code; text: app.t.copy_code; iconName: "clock"; onTriggered: app.copy(vault.code(rowMenu.row.id).code, "code") }
        OMenuItem { visible: !rowMenu.many && !rowMenu.row.trashed && rowMenu.row.host !== ""; text: app.t.open_site; iconName: "globe"; onTriggered: app.openUrl(vault.detail(rowMenu.row.id).link) }
        OMenuItem { visible: !rowMenu.many && !rowMenu.row.trashed; text: rowMenu.row.favorite ? app.t.favorite_remove : app.t.favorite_add; iconName: "star"; onTriggered: vault.toggleFavorite(rowMenu.row.id) }
        OMenuItem { visible: !rowMenu.many && !rowMenu.row.trashed; text: app.t.delete_entry; iconName: "trash"; onTriggered: vault.trash(rowMenu.row.id) }
        OMenuItem { visible: !rowMenu.many && !!rowMenu.row.trashed; text: app.t.restore; iconName: "restore"; onTriggered: vault.restore(rowMenu.row.id) }
    }
}
