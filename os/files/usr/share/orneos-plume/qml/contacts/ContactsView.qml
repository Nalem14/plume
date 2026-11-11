// Contacts module: address books and groups on the side, the list (letters, instant filter, several selected),
// the card — or what several selected cards share, or the duplicates to merge.
import QtCore
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "../components"

Rectangle {
    id: view
    readonly property var c: theme.c
    readonly property var loc: Qt.locale(plume.locale)
    property int currentId: 0
    property var selected: []               // several cards (Ctrl+clic, Maj+clic, Ctrl+A); one: the card is shown
    property int anchorRow: -1              // where Maj+clic starts
    property bool showDuplicates: false
    property int ornisRequest: 0
    property var card: { people.revision; return currentId ? people.details(currentId) : ({}) }
    readonly property bool many: selected.length > 1
    color: c.bg

    function newContact() { editor.openNew(null) }
    function editCurrent() { if (currentId) editor.openEdit(card) }
    function select(id) {
        currentId = id
        selected = id ? [id] : []
        showDuplicates = false
        const row = people.rowOf(id)
        if (row >= 0) {
            list.currentIndex = row
            list.positionViewAtIndex(row, ListView.Contain)
        }
    }
    function bday(value) {
        if (!value)
            return ""
        if (value.startsWith("--"))
            return loc.toString(new Date(2000, parseInt(value.slice(2, 4)) - 1, parseInt(value.slice(5, 7))), "d MMMM")
        return loc.toString(new Date(value + "T12:00"), "d MMMM yyyy")
    }
    // deleted now, gone from the cloud after a few seconds unless « Annuler »
    function removeIds(ids) {
        const names = ids.length === 1 ? (people.details(ids[0]).fn || "") : ""
        const row = Math.max(0, people.rowOf(ids[0]))
        const token = people.removeLater(ids)
        if (!token)
            return
        selected = []
        currentId = people.idAt(Math.min(row, people.count - 1))
        if (currentId) selected = [currentId]
        undoToast.show(ids.length === 1 ? plume.t.deleted_contact.replace("%1", names) : plume.t.deleted_contacts.replace("%1", ids.length),
                       plume.t.undo, () => { people.undoRemove(token); view.select(ids[0]) }, 6)
    }
    function remove() { if (currentId) removeIds([currentId]) }
    function itemLabel(prefix, item) {
        return (item.label || plume.t[prefix + item.type] || plume.t[prefix + "other"]) + (item.pref ? " · " + plume.t.pref_mark : "")
    }
    // write or call: straight away with one address or number, a small menu to choose with several
    function writeTo(anchor) {
        const emails = card.emails || []
        if (emails.length === 1) plume.compose(emails[0].value)
        else if (emails.length > 1) pick.openFor(anchor, emails.map(e => ({ text: e.value, detail: itemLabel("email_", e), act: () => plume.compose(e.value) })))
    }
    function callTo(anchor) {
        const phones = card.phones || []
        const call = v => Qt.openUrlExternally("tel:" + v.replace(/[\s.]/g, ""))
        if (phones.length === 1) call(phones[0].value)
        else if (phones.length > 1) pick.openFor(anchor, phones.map(p => ({ text: p.value, detail: itemLabel("phone_", p), act: () => call(p.value) })))
    }
    function completeWithOrnis() {
        const emails = (card.emails || []).map(e => e.value)
        const text = people.lastMailText(emails)
        if (!text) {
            plume.toast(plume.t.ornis_complete_nomail)
            return
        }
        plume.toast(plume.t.ornis_reading)
        ornisRequest = ornis.ask("contact", { text: text, name: card.fn || "", email: emails[0] || "", contactId: currentId })
    }
    // a click on a line: alone, added (Ctrl), or a range (Maj)
    function clickRow(row, id, modifiers) {
        showDuplicates = false
        if (modifiers & Qt.ControlModifier) {
            const s = selected.slice()
            const i = s.indexOf(id)
            if (i >= 0) s.splice(i, 1); else s.push(id)
            selected = s
            currentId = s.length ? s[s.length - 1] : 0
            anchorRow = row
        } else if ((modifiers & Qt.ShiftModifier) && anchorRow >= 0) {
            selected = Array.from(people.idsBetween(anchorRow, row))
            currentId = id
        } else {
            selected = [id]
            currentId = id
            anchorRow = row
        }
        list.currentIndex = row
    }
    function isSelected(id) { return selected.indexOf(id) >= 0 }
    function popAt(menu, anchor, px, py) { menu.parent = anchor; menu.x = px; menu.y = py; menu.open() }

    Shortcut { enabled: plume.module === "contacts"; sequence: "Ctrl+N"; onActivated: editor.openNew(null) }
    Shortcut { enabled: plume.module === "contacts"; sequence: "Ctrl+F"; onActivated: filter.forceActiveFocus() }
    Shortcut { enabled: plume.module === "contacts" && view.currentId > 0 && !view.many; sequence: "Ctrl+E"; onActivated: view.editCurrent() }
    Shortcut {
        enabled: plume.module === "contacts" && list.activeFocus; sequence: "Ctrl+A"
        onActivated: { view.selected = Array.from(people.allIds()); view.showDuplicates = false }
    }
    Shortcut { enabled: plume.module === "contacts" && view.many; sequence: "Escape"; onActivated: view.select(view.currentId) }

    Component.onCompleted: if (!currentId) select(people.idAt(0))
    Connections {
        target: people
        function onChanged() {
            if (!view.currentId || people.rowOf(view.currentId) < 0) {
                view.currentId = people.idAt(0)
                view.selected = view.currentId ? [view.currentId] : []
            } else {
                view.selected = view.selected.filter(id => people.rowOf(id) >= 0)
            }
            if (view.showDuplicates && people.duplicates.length === 0)
                view.showDuplicates = false
        }
        function onBooksDone(what, ok) {
            if (!ok) plume.toast(plume.t.book_failed)
            else if (what === "create") plume.toast(plume.t.book_created)
        }
    }
    Connections {
        target: ornis
        function onAnswered(id, kind, value) {
            if (id !== view.ornisRequest || kind !== "contact")
                return
            view.ornisRequest = 0
            if (!value || value.none) {
                plume.toast(plume.t.ornis_complete_none)
                return
            }
            plume.toast(plume.t.ornis_completed)
            editor.openEdit(view.card, value)
        }
        function onFailed(id, kind, message) {
            if (id === view.ornisRequest) {
                view.ornisRequest = 0
                plume.toast(message)
            }
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        // ---- side: new, all, duplicates, books, groups, import / export ----
        Rectangle {
            Layout.preferredWidth: 240
            Layout.fillHeight: true
            color: view.c.chrome
            Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: view.c.hairline }

            component SideItem: AbstractButton {
                id: item
                property string iconName
                property string dot
                property string detail
                property int count: -1
                property bool active: false
                property bool dropTarget: false
                Layout.fillWidth: true
                implicitHeight: detail !== "" ? 44 : 36
                hoverEnabled: true
                Accessible.name: text
                background: Rectangle {
                    radius: 7
                    color: item.dropTarget ? Qt.alpha(view.c.famCommunicate, 0.14) : item.active ? view.c.card : item.hovered ? view.c.hover : "transparent"
                    border.width: item.dropTarget ? 1 : 0
                    border.color: view.c.famCommunicate
                    Band {
                        visible: item.active
                        anchors { left: parent.left; top: parent.top; bottom: parent.bottom; topMargin: 8; bottomMargin: 8 }
                        radius: 1.5
                        color: view.c.famCommunicate
                    }
                }
                contentItem: RowLayout {
                    spacing: 12
                    Item {
                        Layout.leftMargin: 10
                        implicitWidth: 20; implicitHeight: 20
                        Icon { anchors.centerIn: parent; visible: item.iconName !== ""; name: item.iconName; size: 20; color: item.active ? view.c.famCommunicate : view.c.muted }
                        Rectangle { anchors.centerIn: parent; visible: item.dot !== ""; width: 8; height: 8; radius: 4; color: item.dot || "transparent" }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0
                        Text {
                            Layout.fillWidth: true
                            text: item.text
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: item.active ? Font.DemiBold : Font.Medium
                            color: view.c.text
                        }
                        Text {
                            visible: item.detail !== ""
                            Layout.fillWidth: true
                            text: item.detail
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 12
                            color: view.c.muted
                        }
                    }
                    Text {
                        visible: item.count >= 0
                        Layout.rightMargin: 10
                        text: item.count
                        font.family: "JetBrains Mono"; font.pixelSize: 12
                        color: item.active ? view.c.famCommunicate : view.c.muted
                    }
                }
            }
            // a section title with its « + » (new book, new group)
            component SideLabel: RowLayout {
                id: label
                property string text
                property string addTip
                signal add()
                Layout.fillWidth: true
                Layout.leftMargin: 12; Layout.topMargin: 16; Layout.bottomMargin: 2
                Text {
                    Layout.fillWidth: true
                    text: label.text
                    font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium; font.letterSpacing: 0.8
                    font.capitalization: Font.AllUppercase
                    color: view.c.muted
                }
                OButton {
                    visible: label.addTip !== ""
                    kind: "quiet"; iconName: "plus"; iconSize: 14; height_: 24; implicitWidth: 24
                    tip: label.addTip
                    onClicked: label.add()
                }
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 12; anchors.topMargin: 14
                spacing: 2
                Text {
                    Layout.leftMargin: 4; Layout.bottomMargin: 10
                    text: plume.t.contacts
                    font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                    font.capitalization: Font.AllUppercase; font.letterSpacing: 0.9
                    color: view.c.famCommunicate
                }
                // the new-item line: opens a new card
                Capture {
                    Layout.fillWidth: true
                    Layout.bottomMargin: 12
                    enabled: people.defaultBook > 0
                    tint: view.c.famCommunicate
                    iconName: "plus"
                    text: plume.t.new_contact_hint
                    shortcut: "Ctrl N"
                    onClicked: editor.openNew(null)
                }
                SideItem {
                    iconName: "people"; text: plume.t.all_contacts; count: people.total
                    active: people.book === 0 && people.group === "" && !view.showDuplicates
                    onClicked: { view.showDuplicates = false; people.setFilter(filter.text, 0, "") }
                }
                SideItem {
                    visible: people.duplicates.length > 0
                    iconName: "duplicate"; text: plume.t.duplicates; count: people.duplicates.length
                    active: view.showDuplicates
                    onClicked: view.showDuplicates = true
                }
                Flickable {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    contentHeight: sideCol.implicitHeight
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    ColumnLayout {
                        id: sideCol
                        width: parent.width
                        spacing: 2
                        SideLabel {
                            text: plume.t.books; addTip: plume.t.book_new
                            onAdd: prompt.ask(plume.t.book_new_title, "", plume.t.book_name_ph, "", plume.t.book_create, name => people.createBook(name))
                        }
                        Repeater {
                            model: people.books
                            SideItem {
                                required property var modelData
                                iconName: modelData.shared ? "share" : "book"; text: modelData.name; count: modelData.count
                                detail: modelData.shared && modelData.ownerName ? plume.t.book_owner.replace("%1", modelData.ownerName) : ""
                                active: people.book === modelData.id && !view.showDuplicates
                                onClicked: { view.showDuplicates = false; people.setFilter(filter.text, modelData.id, "") }
                                TapHandler { acceptedButtons: Qt.RightButton; onTapped: point => bookMenu.openFor(modelData, parent, point.position.x, point.position.y) }
                            }
                        }
                        SideLabel {
                            text: plume.t.groups; addTip: plume.t.group_new_side
                            onAdd: prompt.ask(plume.t.group_new_title, "", plume.t.group_name_ph, "", plume.t.group_add, name => {
                                if (people.createGroup(name)) {
                                    view.showDuplicates = false
                                    people.setFilter(filter.text, 0, name)
                                }
                            })
                        }
                        Repeater {
                            model: people.groups
                            SideItem {
                                id: groupItem
                                required property var modelData
                                required property int index
                                dot: [view.c.saffron, view.c.ok, view.c.action, view.c.faint][index % 4]
                                text: modelData.name; count: modelData.count
                                active: people.group === modelData.name && !view.showDuplicates
                                dropTarget: drop.containsDrag
                                onClicked: { view.showDuplicates = false; people.setFilter(filter.text, 0, modelData.name) }
                                TapHandler { acceptedButtons: Qt.RightButton; onTapped: point => groupMenu.openFor(modelData.name, parent, point.position.x, point.position.y) }
                                // contacts dragged from the list go into the group
                                DropArea {
                                    id: drop
                                    anchors.fill: parent
                                    keys: ["plume-contacts"]
                                    onDropped: d => {
                                        const ids = d.source && d.source.ids ? d.source.ids : []
                                        const n = people.setGroupMany(ids, groupItem.modelData.name, true)
                                        plume.toast(plume.t.added_to_group.replace("%1", n).replace("%2", groupItem.modelData.name))
                                    }
                                }
                            }
                        }
                    }
                }
                SideItem { iconName: "import"; text: plume.t.import_contacts; onClicked: importDialog.open() }
                SideItem { iconName: "export"; text: plume.t.export_contacts; enabled: people.total > 0; onClicked: exportDialog.exportSome("", 0, "") }
                AccountBar {
                    Layout.fillWidth: true
                    Layout.topMargin: 6
                    Layout.leftMargin: -4; Layout.rightMargin: -4; Layout.bottomMargin: -6
                    name: plume.profile.name || ""
                    email: plume.profile.email || ""
                    initials: plume.profile.initials || ""
                    onSettingsRequested: plume.openSettings("")
                    OMenuItem { text: plume.t.account_manage; iconName: "user"; onTriggered: plume.openAccount() }
                    OMenuItem { visible: !signin.canSignOut; height: visible ? implicitHeight : 0; text: plume.t.reconnect; iconName: "refresh"; onTriggered: plume.openConnect() }
                    OMenuItem { visible: signin.canSignOut; height: visible ? implicitHeight : 0; text: plume.t.sign_out; iconName: "lock"; onTriggered: plume.openSettings("") }
                }
            }
        }

        // ---- the list ----
        Rectangle {
            Layout.preferredWidth: 340
            Layout.fillHeight: true
            color: view.c.card
            z: 1
            Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: view.c.hairline; z: 2 }
            ColumnLayout {
                anchors.fill: parent
                spacing: 0
                RowLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 18; Layout.rightMargin: 10; Layout.topMargin: 16
                    spacing: 6
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 1
                        Text {
                            Layout.fillWidth: true
                            text: people.group || (people.book ? (people.books.find(b => b.id === people.book) || {}).name || "" : plume.t.all_contacts)
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 24; font.weight: Font.Bold; font.letterSpacing: -0.4
                            color: view.c.text
                            Accessible.role: Accessible.Heading
                        }
                        Text {
                            text: plume.t.contacts_count.replace("%1", list.count)
                            font.family: "JetBrains Mono"; font.pixelSize: 12
                            color: view.c.muted
                        }
                    }
                    OButton {
                        id: sortButton
                        kind: "quiet"; iconName: "sort"; implicitWidth: 34
                        tip: plume.t.sort_label
                        onClicked: view.popAt(sortMenu, sortButton, 0, sortButton.height + 4)
                    }
                }
                OTextField {
                    id: filter
                    Layout.fillWidth: true
                    Layout.margins: 12; Layout.leftMargin: 14; Layout.rightMargin: 14
                    iconName: "search"
                    placeholderText: plume.t.filter_ph
                    onTextChanged: people.setFilter(text, people.book, people.group)
                    Keys.onDownPressed: { list.forceActiveFocus(); view.select(people.idAt(0)) }
                    Keys.onReturnPressed: view.select(people.idAt(0))
                }
                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    ListView {
                        id: list
                        property bool dragging: false
                        anchors.fill: parent
                        anchors.rightMargin: letterIndex.visible ? 18 : 0
                        clip: !dragging
                        model: people.model
                        boundsBehavior: Flickable.StopAtBounds
                        keyNavigationEnabled: true
                        reuseItems: true
                        ScrollBar.vertical: ScrollBar {}
                        onCurrentIndexChanged: if (activeFocus && currentIndex >= 0 && !view.many) { view.currentId = people.idAt(currentIndex); view.selected = [view.currentId]; view.anchorRow = currentIndex }
                        Keys.onMenuPressed: if (view.currentId) contactMenu.openFor(view.currentId, list, 40, 40)
                        Keys.onDeletePressed: view.removeIds(view.many ? view.selected : [view.currentId])
                        Keys.onReturnPressed: if (!view.many) view.editCurrent()
                        // a letter typed in the list goes to the first name at that letter
                        Keys.onPressed: event => {
                            if (event.text.length === 1 && event.text.toLowerCase() !== event.text.toUpperCase() && !(event.modifiers & (Qt.ControlModifier | Qt.AltModifier))) {
                                const row = people.rowForLetter(event.text)
                                if (row >= 0) { view.select(people.idAt(row)); list.positionViewAtIndex(row, ListView.Beginning) }
                                event.accepted = true
                            }
                        }
                        section.property: "section"
                        section.criteria: ViewSection.FullString
                        section.delegate: Item {
                            required property string section
                            width: ListView.view.width; height: 30
                            Rectangle { width: parent.width; height: 1; color: view.c.hairline; visible: y > 0 }
                            Text {
                                x: 18; anchors.bottom: parent.bottom; anchors.bottomMargin: 4
                                text: parent.section
                                font.family: "JetBrains Mono"; font.pixelSize: 12
                                color: view.c.muted
                            }
                        }
                        delegate: Item {
                            id: row
                            required property int contactId
                            required property string name
                            required property string initials
                            required property string subtitle
                            required property string photo
                            required property int tint
                            required property int index
                            readonly property bool chosen: view.isSelected(contactId) || (!view.many && view.currentId === contactId)
                            width: ListView.view.width
                            height: 56
                            Accessible.role: Accessible.ListItem
                            Accessible.name: name
                            Accessible.selected: chosen
                            Rectangle {
                                anchors.fill: parent
                                color: row.chosen ? Qt.tint(view.c.card, Qt.alpha(view.c.famCommunicate, view.many ? 0.12 : 0.07))
                                     : area.containsMouse ? view.c.hover : "transparent"
                                Band { visible: row.chosen; height: parent.height; color: view.c.famCommunicate }
                            }
                            RowLayout {
                                anchors.fill: parent
                                spacing: 12
                                Avatar { Layout.leftMargin: 18; initials: row.initials; tint: row.tint; photo: row.photo; size: 36; selected: row.chosen }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Layout.rightMargin: 14
                                    spacing: 1
                                    Text {
                                        Layout.fillWidth: true
                                        text: row.name
                                        elide: Text.ElideRight
                                        font.family: "Schibsted Grotesk"; font.pixelSize: 15
                                        font.weight: row.chosen ? Font.DemiBold : Font.Medium
                                        color: view.c.text
                                    }
                                    Text {
                                        visible: text !== ""
                                        Layout.fillWidth: true
                                        text: row.subtitle
                                        elide: Text.ElideRight
                                        font.family: "Schibsted Grotesk"; font.pixelSize: 13
                                        color: view.c.muted
                                    }
                                }
                            }
                            // what is dragged onto a group: this card, or all the selected ones with it
                            Rectangle {
                                id: proxy
                                property var ids: []
                                visible: Drag.active
                                width: proxyText.implicitWidth + 24; height: 30; radius: 15
                                color: view.c.famCommunicate
                                Drag.active: area.drag.active
                                Drag.keys: ["plume-contacts"]
                                Drag.hotSpot.x: 12; Drag.hotSpot.y: 15
                                Text {
                                    id: proxyText
                                    anchors.centerIn: parent
                                    text: proxy.ids.length > 1 ? plume.t.selected_count.replace("%1", proxy.ids.length) : row.name
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                                    color: "white"
                                }
                            }
                            MouseArea {
                                id: area
                                anchors.fill: parent
                                hoverEnabled: true
                                acceptedButtons: Qt.LeftButton | Qt.RightButton
                                drag.target: proxy
                                drag.threshold: 8
                                onPressed: mouse => {
                                    proxy.ids = row.chosen && view.many ? view.selected.slice() : [row.contactId]
                                    proxy.x = mouse.x - 12; proxy.y = mouse.y - 15
                                }
                                drag.onActiveChanged: list.dragging = drag.active
                                onReleased: { if (drag.active) proxy.Drag.drop(); proxy.x = 0; proxy.y = 0 }
                                onClicked: mouse => {
                                    list.forceActiveFocus()
                                    if (mouse.button === Qt.RightButton) {
                                        if (view.many && row.chosen) view.popAt(selectionMenu, row, mouse.x, mouse.y)
                                        else { view.select(row.contactId); contactMenu.openFor(row.contactId, row, mouse.x, mouse.y) }
                                    } else {
                                        view.clickRow(row.index, row.contactId, mouse.modifiers)
                                    }
                                }
                                onDoubleClicked: mouse => { if (mouse.button === Qt.LeftButton && !view.many) view.editCurrent() }
                            }
                        }
                        Skeleton { anchors.fill: parent; anchors.margins: 20; visible: people.waiting; tone: view.c.line; rows: 8; Accessible.name: plume.t.loading }
                        Text {
                            anchors.centerIn: parent
                            width: parent.width - 40
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.Wrap
                            visible: list.count === 0 && !people.waiting
                            text: people.group && !filter.text ? plume.t.group_empty_hint : people.total === 0 ? plume.t.no_contacts : plume.t.no_match
                            font.family: "Schibsted Grotesk"; font.pixelSize: 15
                            color: view.c.muted
                        }
                    }
                    // the letters of the list, to jump (a long list only)
                    Column {
                        id: letterIndex
                        visible: list.count > 30 && people.letters.length > 3
                        anchors.right: parent.right; anchors.rightMargin: 2
                        anchors.verticalCenter: parent.verticalCenter
                        width: 16
                        Repeater {
                            model: letterIndex.visible ? people.letters : []
                            Text {
                                required property var modelData
                                width: 16
                                height: Math.min(18, (list.height - 8) / Math.max(1, people.letters.length))
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                text: modelData.letter
                                font.family: "JetBrains Mono"; font.pixelSize: 10; font.weight: Font.Medium
                                color: letterArea.containsMouse ? view.c.famCommunicate : view.c.muted
                                Accessible.role: Accessible.Button
                                Accessible.name: plume.t.letter_index.replace("%1", modelData.letter)
                                MouseArea {
                                    id: letterArea
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: list.positionViewAtIndex(modelData.row, ListView.Beginning)
                                }
                            }
                        }
                    }
                }
            }
        }

        // ---- the right side: the card, the selection, or the duplicates ----
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: view.c.bg
            Surface {
                id: sheet
                anchors.fill: parent
                anchors.margins: 16
                visible: !!view.card.contactId || view.many || view.showDuplicates
                Rectangle {
                    width: parent.width; height: 150
                    radius: sheet.radius
                    gradient: Gradient {
                        GradientStop { position: 0; color: Qt.alpha(view.c.famCommunicate, theme.dark ? 0.18 : 0.09) }
                        GradientStop { position: 1; color: Qt.alpha(view.c.famCommunicate, 0) }
                    }
                }
            }

            Text {
                anchors.centerIn: parent
                visible: !sheet.visible
                text: plume.t.pick_contact
                font.family: "Schibsted Grotesk"; font.pixelSize: 16
                color: view.c.muted
            }

            // several cards selected: what can be done to all of them
            ColumnLayout {
                visible: view.many && !view.showDuplicates
                anchors.centerIn: sheet
                width: Math.min(sheet.width - 80, 460)
                spacing: 14
                Row {
                    Layout.alignment: Qt.AlignHCenter
                    spacing: 6
                    Repeater {
                        model: view.selected.slice(0, 5)
                        Avatar {
                            required property int modelData
                            readonly property var info: people.details(modelData)
                            initials: info.initials || ""; tint: info.tint || 0; photo: info.photoView || ""; size: 56
                        }
                    }
                }
                Text {
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    text: plume.t.selected_count.replace("%1", view.selected.length)
                    font.family: "Schibsted Grotesk"; font.pixelSize: 24; font.weight: Font.Bold
                    color: view.c.text
                }
                Text {
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    text: plume.t.sel_hint
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                    color: view.c.muted
                }
                Flow {
                    Layout.fillWidth: true
                    Layout.topMargin: 6
                    spacing: 8
                    OButton {
                        iconName: "mail"; text: plume.t.sel_write
                        enabled: people.emailsOf(view.selected).length > 0
                        onClicked: plume.compose("mailto:" + people.emailsOf(view.selected).join(","))
                    }
                    OButton { id: selGroup; iconName: "tag"; text: plume.t.sel_group; onClicked: view.popAt(selectionGroups, selGroup, 0, selGroup.height + 4) }
                    OButton { iconName: "export"; text: plume.t.sel_export; onClicked: exportDialog.exportIds(view.selected) }
                    OButton {
                        iconName: "duplicate"; text: plume.t.sel_merge
                        enabled: people.countWritable(view.selected) > 1 && view.selected.length <= 10
                        onClicked: view.merge(view.selected)
                    }
                    OButton {
                        iconName: "trash"; text: plume.t.sel_delete; danger: true
                        enabled: people.countWritable(view.selected) > 0
                        onClicked: view.removeIds(view.selected)
                    }
                    OButton { kind: "quiet"; text: plume.t.sel_clear; onClicked: view.select(view.currentId) }
                }
            }

            // duplicates: each group of cards that are one person, merged in one click
            Flickable {
                anchors.fill: sheet
                visible: view.showDuplicates
                contentHeight: dupCol.implicitHeight + 56
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {}
                ColumnLayout {
                    id: dupCol
                    x: 40; y: 28
                    width: parent.width - 80
                    spacing: 12
                    Text {
                        text: plume.t.dup_title
                        font.family: "Schibsted Grotesk"; font.pixelSize: 28; font.weight: Font.Bold; font.letterSpacing: -0.4
                        color: view.c.text
                        Accessible.role: Accessible.Heading
                    }
                    Text {
                        Layout.fillWidth: true
                        text: plume.t.dup_hint
                        wrapMode: Text.Wrap
                        font.family: "Schibsted Grotesk"; font.pixelSize: 14
                        color: view.c.muted
                    }
                    Repeater {
                        model: view.showDuplicates ? people.duplicates : []
                        Rectangle {
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: dupRow.implicitHeight + 24
                            radius: 10
                            color: view.c.card
                            border.width: 1; border.color: view.c.line
                            RowLayout {
                                id: dupRow
                                anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: 14 }
                                spacing: 12
                                Icon { name: "duplicate"; size: 20; color: view.c.famCommunicate }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Layout.preferredWidth: 1          // gives way to the buttons
                                    spacing: 2
                                    Text {
                                        Layout.fillWidth: true
                                        text: modelData.names.filter((n, i, all) => all.indexOf(n) === i).join(" · ")
                                        elide: Text.ElideRight
                                        textFormat: Text.PlainText
                                        font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.weight: Font.DemiBold
                                        color: view.c.text
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        elide: Text.ElideRight
                                        text: plume.t["dup_reason_" + modelData.reason] + " · " + plume.t.group_members.replace("%1", modelData.ids.length)
                                        font.family: "Schibsted Grotesk"; font.pixelSize: 13
                                        color: view.c.muted
                                    }
                                }
                                OButton { kind: "quiet"; text: plume.t.dup_keep; onClicked: people.notDuplicates(modelData.key) }
                                OButton { kind: "quiet"; iconName: "eye"; implicitWidth: 34; tip: plume.t.open_card; onClicked: { view.showDuplicates = false; view.selected = modelData.ids.slice(); view.currentId = modelData.ids[0] } }
                                OButton { kind: "primary"; text: plume.t.dup_merge; onClicked: view.merge(modelData.ids) }
                            }
                        }
                    }
                }
            }

            Flickable {
                anchors.fill: sheet
                visible: !!view.card.contactId && !view.many && !view.showDuplicates
                contentHeight: page.implicitHeight + 56
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {}

                ColumnLayout {
                    id: page
                    x: 40; y: 28
                    width: parent.width - 80
                    spacing: 0

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 20
                        Avatar { initials: view.card.initials || ""; tint: view.card.tint || 0; photo: view.card.photoView || ""; size: 76 }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Text {
                                Layout.fillWidth: true
                                text: view.card.fn || ""
                                wrapMode: Text.Wrap
                                font.family: "Schibsted Grotesk"; font.pixelSize: 28; font.weight: Font.Bold; font.letterSpacing: -0.4
                                color: view.c.text
                            }
                            Text {
                                visible: !!view.card.nickname
                                text: "« " + (view.card.nickname || "") + " »"
                                textFormat: Text.PlainText
                                font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.italic: true
                                color: view.c.muted
                            }
                            // an account of the cloud: Meet reaches them inside Orneos
                            Rectangle {
                                visible: !!view.card.cloudUser
                                Layout.topMargin: 2; Layout.bottomMargin: 2
                                implicitWidth: cloudRow.implicitWidth + 16; implicitHeight: 22
                                radius: 11
                                color: view.c.tint
                                Row {
                                    id: cloudRow
                                    anchors.centerIn: parent
                                    spacing: 5
                                    Icon { anchors.verticalCenter: parent.verticalCenter; name: "people"; size: 13; color: view.c.tintText }
                                    Text { anchors.verticalCenter: parent.verticalCenter; text: plume.t.orneos_account; font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold; color: view.c.tintText }
                                }
                            }
                            Text {
                                visible: text !== ""
                                Layout.fillWidth: true
                                text: [view.card.title, view.card.org].filter(x => x).join(" · ")
                                wrapMode: Text.Wrap
                                font.family: "Schibsted Grotesk"; font.pixelSize: 15
                                color: view.c.muted
                            }
                        }
                        OButton { kind: "primary"; iconName: "edit"; text: plume.t.edit; onClicked: editor.openEdit(view.card) }
                        OButton { visible: !view.card.readonly; kind: "quiet"; iconName: "trash"; implicitWidth: 34; danger: true; tip: plume.t.delete; onClicked: view.remove() }
                        OButton {
                            id: cardMore
                            kind: "quiet"; iconName: "more"; implicitWidth: 34
                            tip: plume.t.more_actions
                            onClicked: contactMenu.openFor(view.currentId, cardMore, 0, cardMore.height + 6)
                        }
                    }

                    // a birthday (or wedding anniversary) coming within a month
                    Rectangle {
                        readonly property int days: view.card.birthdayIn === undefined ? -1 : view.card.birthdayIn
                        readonly property int anniv: view.card.anniversaryIn === undefined ? -1 : view.card.anniversaryIn
                        visible: (days >= 0 && days <= 30) || (anniv >= 0 && anniv <= 14)
                        Layout.topMargin: 16
                        implicitWidth: soonRow.implicitWidth + 24; implicitHeight: 32
                        radius: 16
                        color: view.c.saffronTint
                        Row {
                            id: soonRow
                            anchors.centerIn: parent
                            spacing: 8
                            Icon { anchors.verticalCenter: parent.verticalCenter; name: "gift"; size: 16; color: view.c.saffronInk }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                readonly property int d: parent.parent.days
                                readonly property int a: parent.parent.anniv
                                text: d >= 0 && d <= 30
                                      ? (d === 0 ? plume.t.birthday_today : d === 1 ? plume.t.birthday_tomorrow : plume.t.birthday_in.replace("%1", d))
                                        + (view.card.age > 0 ? " · " + plume.t.age_next.replace("%1", view.card.age) : "")
                                      : plume.t.anniversary_soon.replace("%1", a)
                                font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                                color: view.c.saffronInk
                            }
                        }
                    }

                    // quick actions
                    RowLayout {
                        Layout.topMargin: 22
                        spacing: 10
                        component Action: AbstractButton {
                            id: act
                            property string iconName
                            implicitWidth: 92; implicitHeight: 64
                            hoverEnabled: true
                            opacity: enabled ? 1 : 0.4
                            Accessible.name: text
                            background: Rectangle {
                                radius: 8
                                color: act.hovered ? view.c.tint : view.c.card
                                border.width: 1; border.color: act.hovered ? view.c.tint : view.c.line
                            }
                            contentItem: Column {
                                topPadding: 10
                                spacing: 6
                                Icon { anchors.horizontalCenter: parent.horizontalCenter; name: act.iconName; size: 20; color: view.c.accent }
                                Text {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: act.text
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.Medium
                                    color: view.c.accent
                                }
                            }
                        }
                        Action {
                            id: writeAction
                            iconName: "mail"; text: plume.t.write
                            enabled: (view.card.emails || []).length > 0
                            onClicked: view.writeTo(writeAction)
                        }
                        Action {
                            id: callAction
                            iconName: "phone"; text: plume.t.call
                            enabled: (view.card.phones || []).length > 0
                            onClicked: view.callTo(callAction)
                        }
                        // Meet finds the account of the cloud by its address (else invites it); a teammate without one, by account
                        Action {
                            iconName: "chat"; text: plume.t.chat_with
                            enabled: !!view.card.cloudUser || (view.card.emails || []).length > 0
                            onClicked: plume.meetWith(view.card.primaryEmail || view.card.cloudUser, view.card.fn || "", false)
                        }
                        Action {
                            iconName: "video"; text: plume.t.visio
                            enabled: !!view.card.cloudUser || (view.card.emails || []).length > 0
                            onClicked: plume.meetWith(view.card.primaryEmail || view.card.cloudUser, view.card.fn || "", true)
                        }
                        Action {
                            iconName: "calendar"; text: plume.t.plan
                            enabled: (view.card.emails || []).length > 0
                            onClicked: plume.planWith(view.card.primaryEmail)
                        }
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: 14
                        columns: page.width > 760 ? 2 : 1
                        columnSpacing: 40
                        rowSpacing: 12

                        // relevés: label on the left, value on the right
                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignTop
                            spacing: 0
                            component Reading: RowLayout {
                                id: reading
                                property string label
                                property string value
                                property bool mono: false
                                property string link
                                property string tip
                                Layout.fillWidth: true
                                spacing: 16
                                Text {
                                    Layout.preferredWidth: 110
                                    Layout.alignment: Qt.AlignTop
                                    Layout.topMargin: 13
                                    text: reading.label
                                    elide: Text.ElideRight
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 14
                                    color: view.c.muted
                                }
                                Text {
                                    Layout.fillWidth: true
                                    Layout.topMargin: 12; Layout.bottomMargin: 12
                                    text: reading.value
                                    wrapMode: Text.Wrap
                                    font.family: reading.mono ? "JetBrains Mono" : "Schibsted Grotesk"
                                    font.pixelSize: reading.mono ? 14 : 15
                                    color: reading.link ? view.c.accent : view.c.text
                                    textFormat: Text.PlainText
                                    MouseArea {
                                        id: readingArea
                                        anchors.fill: parent
                                        enabled: reading.link !== ""
                                        hoverEnabled: reading.tip !== ""
                                        cursorShape: Qt.PointingHandCursor
                                        ToolTip.visible: reading.tip !== "" && containsMouse
                                        ToolTip.text: reading.tip
                                        ToolTip.delay: 600
                                        onClicked: reading.link.startsWith("mailto:") ? plume.compose(reading.link) : Qt.openUrlExternally(reading.link)
                                    }
                                }
                            }
                            component Line: Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: view.c.hairline }
                            Repeater {
                                model: view.card.emails || []
                                ColumnLayout {
                                    required property var modelData
                                    Layout.fillWidth: true; spacing: 0
                                    Reading { label: view.itemLabel("email_", modelData); value: modelData.value; link: "mailto:" + modelData.value }
                                    Line {}
                                }
                            }
                            Repeater {
                                model: view.card.phones || []
                                ColumnLayout {
                                    required property var modelData
                                    Layout.fillWidth: true; spacing: 0
                                    Reading { label: view.itemLabel("phone_", modelData); value: modelData.value; mono: true; link: "tel:" + modelData.value.replace(/[\s.]/g, "") }
                                    Line {}
                                }
                            }
                            Repeater {
                                model: view.card.addresses || []
                                ColumnLayout {
                                    required property var modelData
                                    Layout.fillWidth: true; spacing: 0
                                    Reading {
                                        label: view.itemLabel("address_", modelData)
                                        value: [modelData.street, [modelData.code, modelData.city].filter(x => x).join(" "), modelData.region, modelData.country].filter(x => x).join("\n")
                                        link: "https://www.openstreetmap.org/search?query=" + encodeURIComponent(value.replace(/\n/g, ", "))
                                        tip: plume.t.open_map
                                    }
                                    Line {}
                                }
                            }
                            Repeater {
                                model: view.card.related || []
                                ColumnLayout {
                                    required property var modelData
                                    Layout.fillWidth: true; spacing: 0
                                    Reading { label: modelData.label || plume.t["rel_" + modelData.type] || plume.t.rel_other; value: modelData.value }
                                    Line {}
                                }
                            }
                            ColumnLayout {
                                visible: !!view.card.bday
                                Layout.fillWidth: true; spacing: 0
                                Reading { label: plume.t.birthday; value: view.bday(view.card.bday || "") }
                                Line {}
                            }
                            ColumnLayout {
                                visible: !!view.card.anniversary
                                Layout.fillWidth: true; spacing: 0
                                Reading { label: plume.t.anniversary; value: view.bday(view.card.anniversary || "") }
                                Line {}
                            }
                            Repeater {
                                model: view.card.urls || []
                                ColumnLayout {
                                    required property string modelData
                                    Layout.fillWidth: true; spacing: 0
                                    Reading { label: plume.t.website; value: modelData; link: /^[a-z][a-z0-9+.-]*:/i.test(modelData) ? modelData : "https://" + modelData }
                                    Line {}
                                }
                            }
                            RowLayout {
                                visible: (view.card.categories || []).length > 0
                                Layout.fillWidth: true
                                spacing: 16
                                Text {
                                    Layout.preferredWidth: 110
                                    text: plume.t.groups_label
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 14
                                    color: view.c.muted
                                }
                                Flow {
                                    Layout.fillWidth: true
                                    Layout.topMargin: 10; Layout.bottomMargin: 10
                                    spacing: 6
                                    Repeater {
                                        model: view.card.categories || []
                                        Rectangle {
                                            required property string modelData
                                            height: 24; radius: 12
                                            width: chipText.implicitWidth + 20
                                            color: view.c.okTint
                                            Text { id: chipText; anchors.centerIn: parent; text: modelData; font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.Medium; color: view.c.okInk }
                                        }
                                    }
                                }
                            }
                            Line { visible: (view.card.categories || []).length > 0 }
                            Reading { label: plume.t.book_label; value: view.card.bookName || "" }
                            Text {
                                visible: !!view.card.note
                                Layout.fillWidth: true
                                Layout.topMargin: 14
                                text: view.card.note || ""
                                textFormat: Text.PlainText
                                wrapMode: Text.Wrap
                                lineHeight: 1.3
                                font.family: "Schibsted Grotesk"; font.pixelSize: 14
                                color: view.c.muted
                            }
                        }

                        // coming up with this person, and the latest messages
                        ColumnLayout {
                            readonly property var mails: { people.revision; return view.card.contactId ? people.recentMails((view.card.emails || []).map(e => e.value)) : [] }
                            id: sideInfo
                            visible: (view.card.upcoming || []).length > 0 || mails.length > 0
                            Layout.preferredWidth: page.width > 760 ? 280 : -1
                            Layout.fillWidth: page.width <= 760
                            Layout.alignment: Qt.AlignTop
                            Layout.topMargin: 14
                            spacing: 8
                            component SideTitle: Text {
                                font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold; font.letterSpacing: 0.8
                                color: view.c.muted
                            }
                            SideTitle { visible: (view.card.upcoming || []).length > 0; text: plume.t.upcoming }
                            Repeater {
                                model: view.card.upcoming || []
                                AbstractButton {
                                    id: up
                                    required property var modelData
                                    readonly property date when: new Date(modelData.start)
                                    Layout.fillWidth: true
                                    implicitHeight: 58
                                    hoverEnabled: true
                                    onClicked: plume.setModule("calendar")
                                    background: Rectangle { radius: 8; color: up.hovered ? view.c.hover : "transparent"; border.width: 1; border.color: view.c.line }
                                    contentItem: RowLayout {
                                        spacing: 12
                                        Column {
                                            Layout.leftMargin: 12
                                            Layout.preferredWidth: 36
                                            Text {
                                                anchors.horizontalCenter: parent.horizontalCenter
                                                text: view.loc.dayName(up.when.getDay(), Locale.ShortFormat).toUpperCase().replace(".", "") + "."
                                                font.family: "Schibsted Grotesk"; font.pixelSize: 11; font.weight: Font.DemiBold
                                                color: view.c.accent
                                            }
                                            Text {
                                                anchors.horizontalCenter: parent.horizontalCenter
                                                text: up.when.getDate()
                                                font.family: "JetBrains Mono"; font.pixelSize: 18
                                                color: view.c.text
                                            }
                                        }
                                        Column {
                                            Layout.fillWidth: true
                                            Text {
                                                width: parent.width
                                                text: up.modelData.title
                                                elide: Text.ElideRight
                                                font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
                                                color: view.c.text
                                            }
                                            Text {
                                                width: parent.width
                                                text: (up.modelData.allDay ? plume.t.all_day : Qt.formatTime(up.when, "HH:mm")) + (up.modelData.location ? " · " + up.modelData.location : "")
                                                elide: Text.ElideRight
                                                font.family: "JetBrains Mono"; font.pixelSize: 12
                                                color: view.c.muted
                                            }
                                        }
                                    }
                                }
                            }
                            SideTitle { visible: sideInfo.mails.length > 0; text: plume.t.recent_mails; Layout.topMargin: (view.card.upcoming || []).length ? 10 : 0 }
                            Repeater {
                                model: sideInfo.mails
                                AbstractButton {
                                    id: mailRow
                                    required property var modelData
                                    Layout.fillWidth: true
                                    implicitHeight: mailCol.implicitHeight + 16
                                    hoverEnabled: true
                                    Accessible.name: modelData.subject
                                    onClicked: people.openMail(modelData.messageId)
                                    background: Rectangle { radius: 8; color: mailRow.hovered ? view.c.hover : "transparent"; border.width: 1; border.color: view.c.line }
                                    contentItem: ColumnLayout {
                                        id: mailCol
                                        spacing: 2
                                        RowLayout {
                                            Layout.leftMargin: 12; Layout.rightMargin: 12; Layout.topMargin: 8
                                            spacing: 6
                                            Icon { name: mailRow.modelData.incoming ? "inbox" : "send"; size: 13; color: view.c.muted }
                                            Text {
                                                Layout.fillWidth: true
                                                text: (mailRow.modelData.incoming ? plume.t.mail_received : plume.t.mail_sent) + " · "
                                                      + view.loc.toString(new Date(mailRow.modelData.date), "d MMM")
                                                font.family: "JetBrains Mono"; font.pixelSize: 11
                                                color: view.c.muted
                                            }
                                        }
                                        Text {
                                            Layout.fillWidth: true
                                            Layout.leftMargin: 12; Layout.rightMargin: 12; Layout.bottomMargin: 8
                                            text: mailRow.modelData.subject || plume.t.untitled
                                            textFormat: Text.PlainText
                                            elide: Text.ElideRight
                                            font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.Medium
                                            color: view.c.text
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            Toast { id: undoToast }
        }
    }

    function merge(ids) {
        const result = people.mergeIds(ids)
        if (!result.id)
            return
        view.showDuplicates = people.duplicates.length > 0 && view.showDuplicates
        if (!view.showDuplicates) view.select(result.id)
        const name = people.details(result.id).fn || ""
        undoToast.show(plume.t.merged.replace("%1", name), plume.t.undo, () => people.undoRemove(result.token), 6)
    }

    ContactEditor { id: editor; onSaved: id => { if (id) view.select(id) }; onOpenOther: id => view.select(id) }
    ChoiceDialog { id: choice }
    FileDialog {
        id: importDialog
        currentFolder: StandardPaths.writableLocation(StandardPaths.HomeLocation)
        nameFilters: ["vCard, CSV (*.vcf *.vcard *.csv)", "vCard (*.vcf *.vcard)", "CSV (*.csv)"]
        function into(file, book) {
            const r = people.importFile(file, book)
            plume.toast(r.error ? plume.t.import_failed
                        : plume.t.imported_result.replace("%1", r.added).replace("%2", r.updated).replace("%3", r.same))
        }
        onAccepted: {
            const file = selectedFile.toString()
            const books = people.books.filter(b => !b.readonly)
            if (books.length < 2) { into(file, 0); return }
            // several address books I can write to: which one
            choice.ask(plume.t.import_into_title, plume.t.import_contacts_hint,
                       books.map(b => ({ id: String(b.id), text: b.name, kind: b.id === people.defaultBook ? "primary" : "secondary" })),
                       id => into(file, parseInt(id)))
        }
    }
    FileDialog {
        id: exportDialog
        currentFolder: StandardPaths.writableLocation(StandardPaths.DocumentsLocation)
        property string group
        property int contactId
        property var ids: []
        function exportSome(groupName, id, label) {
            group = groupName; contactId = id; ids = []
            selectedFile = StandardPaths.writableLocation(StandardPaths.DocumentsLocation) + "/" + encodeURIComponent(label ? people.exportNameFor(label) : people.exportName())
            open()
        }
        function exportIds(list) {
            group = ""; contactId = 0; ids = list.slice()
            selectedFile = StandardPaths.writableLocation(StandardPaths.DocumentsLocation) + "/" + encodeURIComponent(people.exportName())
            open()
        }
        fileMode: FileDialog.SaveFile
        defaultSuffix: "vcf"
        nameFilters: ["vCard (*.vcf)"]
        onAccepted: plume.toast(plume.t.exported_contacts.replace("%1", ids.length
            ? people.exportIds(selectedFile.toString(), ids) : people.exportFile(selectedFile.toString(), group, contactId)))
    }
    PromptDialog { id: prompt }
    BookShare { id: bookShare }

    // a few addresses or numbers to choose from (« Écrire », « Appeler »)
    OMenu {
        id: pick
        property var options: []
        function openFor(anchor, list) {
            options = list
            heading = view.card.fn || ""
            subheading = ""
            parent = anchor; x = 0; y = anchor.height + 6
            open()
        }
        Repeater {
            model: pick.options
            OMenuItem {
                required property var modelData
                text: modelData.text + "  ·  " + modelData.detail
                onTriggered: modelData.act()
            }
        }
    }

    OMenu {
        id: sortMenu
        OMenuItem { text: plume.t.sort_given; switchable: true; on: people.sortBy === "given"; onTriggered: people.setSortBy("given") }
        OMenuItem { text: plume.t.sort_family; switchable: true; on: people.sortBy === "family"; onTriggered: people.setSortBy("family") }
    }

    // several selected (right click on one of them)
    OMenu {
        id: selectionMenu
        heading: plume.t.selected_count.replace("%1", view.selected.length)
        OMenuItem { text: plume.t.sel_write; iconName: "mail"; onTriggered: plume.compose("mailto:" + people.emailsOf(view.selected).join(",")) }
        OMenuItem { text: plume.t.sel_group; iconName: "tag"; onTriggered: view.popAt(selectionGroups, selectionMenu.parent, selectionMenu.x, selectionMenu.y) }
        OMenuItem { text: plume.t.sel_export; iconName: "export"; onTriggered: exportDialog.exportIds(view.selected) }
        OMenuItem { text: plume.t.sel_merge; iconName: "duplicate"; enabled: people.countWritable(view.selected) > 1; onTriggered: view.merge(view.selected) }
        Rectangle { width: parent ? parent.width : 0; height: 1; color: view.c.hairline }
        OMenuItem { text: plume.t.sel_delete; iconName: "trash"; danger: true; onTriggered: view.removeIds(view.selected) }
    }
    OMenu {
        id: selectionGroups
        heading: plume.t.sel_group
        Repeater {
            model: people.groups
            OMenuItem {
                required property var modelData
                required property int index
                text: modelData.name
                dot: [view.c.saffron, view.c.ok, view.c.action, view.c.faint][index % 4]
                onTriggered: plume.toast(plume.t.added_to_group.replace("%1", people.setGroupMany(view.selected, modelData.name, true)).replace("%2", modelData.name))
            }
        }
        OMenuItem {
            text: plume.t.group_new; iconName: "plus"
            onTriggered: {
                const ids = view.selected.slice()
                prompt.ask(plume.t.group_new_title, "", plume.t.group_name_ph, "", plume.t.group_add,
                           name => plume.toast(plume.t.added_to_group.replace("%1", people.setGroupMany(ids, name, true)).replace("%2", name)))
            }
        }
    }

    // an address book (right click): rename, share, delete (mine), make a new one
    OMenu {
        id: bookMenu
        property var book: ({})
        function openFor(b, anchor, px, py) {
            book = b
            heading = b.name
            subheading = b.shared && b.ownerName ? plume.t.book_owner.replace("%1", b.ownerName) : ""
            parent = anchor; x = px; y = py
            open()
        }
        OMenuItem {
            visible: !!bookMenu.book.mine
            text: plume.t.book_rename; iconName: "edit"
            onTriggered: {
                const b = bookMenu.book
                prompt.ask(plume.t.book_rename_title.replace("%1", b.name), "", plume.t.book_name_ph, b.name, plume.t.group_rename_go,
                           name => people.renameBook(b.id, name))
            }
        }
        OMenuItem { visible: !!bookMenu.book.mine; text: plume.t.book_share; iconName: "share"; onTriggered: bookShare.openFor(bookMenu.book) }
        OMenuItem { visible: !bookMenu.book.readonly; text: plume.t.import_contacts; iconName: "import"; onTriggered: { importDialog.open() } }
        OMenuItem { text: plume.t.book_new; iconName: "plus"; onTriggered: prompt.ask(plume.t.book_new_title, "", plume.t.book_name_ph, "", plume.t.book_create, name => people.createBook(name)) }
        Rectangle { visible: !!bookMenu.book.mine; width: parent ? parent.width : 0; height: 1; color: view.c.hairline }
        OMenuItem {
            visible: !!bookMenu.book.mine && people.books.filter(b => b.mine).length > 1
            text: plume.t.book_delete; iconName: "trash"; danger: true
            onTriggered: {
                const b = bookMenu.book
                choice.ask(plume.t.book_delete_title.replace("%1", b.name), plume.t.book_delete_text.replace("%1", b.count),
                           [{ id: "cancel", text: plume.t.cancel }, { id: "delete", text: plume.t.book_delete, kind: "danger" }],
                           id => { if (id === "delete") people.deleteBook(b.id) })
            }
        }
    }

    // a contact (right click on its line, « ⋯ » of its card): write, call, plan, its groups, export, delete
    OMenu {
        id: contactMenu
        property var card: ({})
        property var groups: []
        function openFor(id, anchor, px, py) {
            card = people.details(id)
            if (!card.contactId)
                return
            groups = Array.from(card.categories || [])
            heading = card.fn || ""
            subheading = card.primaryEmail || ""
            parent = anchor; x = px; y = py
            open()
        }
        readonly property string email: card.primaryEmail || ""
        readonly property string phone: card.phones && card.phones.length ? card.phones[0].value : ""
        OMenuItem { visible: contactMenu.email !== ""; text: plume.t.write; iconName: "mail"; onTriggered: plume.compose(contactMenu.email) }
        OMenuItem { visible: contactMenu.email !== ""; text: plume.t.contact_copy_email; iconName: "draft"; onTriggered: plume.copyText(contactMenu.email) }
        OMenuItem { visible: contactMenu.phone !== ""; text: plume.t.call; iconName: "phone"; onTriggered: Qt.openUrlExternally("tel:" + contactMenu.phone.replace(/[\s.]/g, "")) }
        OMenuItem { visible: contactMenu.email !== ""; text: plume.t.plan; iconName: "calendar"; onTriggered: plume.planWith(contactMenu.email) }
        Rectangle { width: parent ? parent.width : 0; height: 1; color: view.c.hairline }
        OMenuItem {
            text: plume.t.edit; iconName: "draft"
            onTriggered: { view.select(contactMenu.card.contactId); editor.openEdit(contactMenu.card) }
        }
        OMenuItem {
            visible: contactMenu.email !== "" && view.ornisRequest === 0
            text: plume.t.ornis_complete; iconName: "ornis"
            onTriggered: { view.select(contactMenu.card.contactId); view.completeWithOrnis() }
        }
        Text {
            visible: !contactMenu.card.readonly
            leftPadding: 10; topPadding: 10; bottomPadding: 4
            text: plume.t.groups_label
            font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold; font.letterSpacing: 0.6
            color: view.c.muted
        }
        Repeater {
            model: contactMenu.card.readonly ? [] : people.groups
            OMenuItem {
                required property var modelData
                required property int index
                text: modelData.name
                dot: [view.c.saffron, view.c.ok, view.c.action, view.c.faint][index % 4]
                switchable: true
                on: contactMenu.groups.indexOf(modelData.name) >= 0
                onTriggered: {
                    const add = !on
                    people.setGroup(contactMenu.card.contactId, modelData.name, add)
                    contactMenu.groups = add ? contactMenu.groups.concat([modelData.name]) : contactMenu.groups.filter(g => g !== modelData.name)
                }
            }
        }
        OMenuItem {
            visible: !contactMenu.card.readonly
            text: plume.t.group_new; iconName: "plus"
            onTriggered: {
                const id = contactMenu.card.contactId
                prompt.ask(plume.t.group_new_title, "", plume.t.group_name_ph, "", plume.t.group_add,
                           name => people.setGroup(id, name, true))
            }
        }
        Rectangle { width: parent ? parent.width : 0; height: 1; color: view.c.hairline }
        OMenuItem { text: plume.t.contact_export; iconName: "export"; onTriggered: exportDialog.exportSome("", contactMenu.card.contactId, contactMenu.card.fn || "") }
        OMenuItem {
            visible: !contactMenu.card.readonly
            text: plume.t.delete; iconName: "trash"; danger: true
            onTriggered: view.removeIds([contactMenu.card.contactId])
        }
    }

    // a group (right click on it): write to everyone in it, rename, export, delete
    OMenu {
        id: groupMenu
        property string group
        property var info: ({ emails: [], without: 0 })
        function openFor(name, anchor, px, py) {
            group = name
            info = people.groupInfo(name)
            heading = name
            const count = (people.groups.find(g => g.name === name) || { count: 0 }).count
            subheading = plume.t.group_members.replace("%1", count)
                         + (info.without > 0 ? " · " + plume.t.group_without.replace("%1", info.without) : "")
            parent = anchor; x = px; y = py
            open()
        }
        OMenuItem {
            visible: (groupMenu.info.emails || []).length > 0
            text: plume.t.group_write_count.replace("%1", (groupMenu.info.emails || []).length); iconName: "mail"
            onTriggered: plume.compose("mailto:" + groupMenu.info.emails.join(","))
        }
        OMenuItem {
            text: plume.t.group_rename; iconName: "draft"
            onTriggered: {
                const old = groupMenu.group
                prompt.ask(plume.t.group_rename_title.replace("%1", old), "", plume.t.group_name_ph, old, plume.t.group_rename_go,
                           name => people.renameGroup(old, name))
            }
        }
        OMenuItem { text: plume.t.group_export; iconName: "export"; onTriggered: exportDialog.exportSome(groupMenu.group, 0, groupMenu.group) }
        Rectangle { width: parent ? parent.width : 0; height: 1; color: view.c.hairline }
        OMenuItem {
            text: plume.t.group_delete; iconName: "trash"; danger: true
            onTriggered: {
                const name = groupMenu.group
                choice.ask(plume.t.group_delete_title.replace("%1", name), plume.t.group_delete_text,
                           [{ id: "cancel", text: plume.t.cancel }, { id: "delete", text: plume.t.group_delete, kind: "danger" }],
                           id => { if (id === "delete") people.deleteGroup(name) })
            }
        }
    }
}
