// « Nouvelle tâche », the capture line under the hero: typed in plain words, understood as one types (chips for
// the date, the repeat, the priority, the tags, the list). A chip removed keeps its words in the title.
// Under it, Date, Flag and Priority set the same without words (they win over the words). Return adds the task
// and keeps the field ready for the next one. Same look as Capture.qml (shared kit).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Rectangle {
    id: quick
    readonly property var c: theme.c
    property color tone: c.action
    property var understood: ({ chips: [] })
    property var keep: []
    property var extras: ({})                // chosen with the buttons: {due, flagged, priority}
    readonly property bool open_: field.activeFocus || field.text !== "" || Object.keys(extras).length > 0
                                  || datePick.opened || prioPick.opened
    signal added(string key)
    Connections { target: tasks; function onViewChanged() { quick.extras = ({}) } }
    implicitHeight: column.implicitHeight + 18
    radius: 10
    color: c.field
    border.width: 1
    border.color: field.activeFocus ? tone : c.line

    function focusField() { field.forceActiveFocus() }
    function setText(text) { field.text = text; field.forceActiveFocus() }
    function update() { understood = field.text.trim() ? tasks.preview(field.text) : ({ chips: [] }); filterChips() }
    function filterChips() { understood = Object.assign({}, understood, { chips: (understood.chips || []).filter(ch => keep.indexOf(ch.kind) < 0) }) }
    function add() {
        const key = tasks.quickAddWith(field.text, keep, extras)
        if (key) {
            field.text = ""
            keep = []
            extras = ({})
            added(key)
        }
    }
    function setExtra(name, value) {
        const out = Object.assign({}, extras)
        if (value === undefined || value === "" || value === false || value === 0) delete out[name]
        else out[name] = value
        extras = out
        field.forceActiveFocus()
    }
    readonly property var extraChips: {
        const out = []
        if (extras.due) out.push({ kind: "due", text: app.dateLabel(extras.due), icon: "calendar" })
        if (extras.flagged) out.push({ kind: "flagged", text: app.t.flag, icon: "flag" })
        if (extras.priority) out.push({ kind: "priority", text: app.t["priority_" + extras.priority], icon: "priority" })
        if (extras.section) out.push({ kind: "section", text: extras.section, icon: "listBullet" })
        return out
    }

    Rectangle {
        anchors.fill: parent; anchors.margins: -3
        radius: quick.radius + 3
        color: "transparent"
        border.width: 3; border.color: Qt.alpha(quick.tone, 0.18)
        visible: field.activeFocus
    }

    ColumnLayout {
        id: column
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        anchors.leftMargin: 12; anchors.rightMargin: 12; anchors.topMargin: 9
        spacing: 6

        RowLayout {
            Layout.fillWidth: true
            spacing: 12
            Rectangle {
                implicitWidth: 22; implicitHeight: 22; radius: 11
                color: field.activeFocus ? quick.tone : "transparent"
                border.width: field.activeFocus ? 0 : 1.5
                border.color: Qt.alpha(quick.tone, 0.6)
                Icon { anchors.centerIn: parent; name: "plus"; size: 14; color: field.activeFocus ? "#FFFFFF" : quick.tone }
            }
            TextField {
                id: field
                Layout.fillWidth: true
                placeholderText: app.t.new_task_placeholder
                placeholderTextColor: quick.c.faint
                font.family: "Schibsted Grotesk"; font.pixelSize: 15
                color: quick.c.text
                selectionColor: quick.c.tint
                background: null
                leftPadding: 0
                onTextChanged: { if (!text) quick.keep = []; quick.update() }
                onAccepted: quick.add()
                Keys.onEscapePressed: { text = ""; quick.extras = ({}); quick.parent.forceActiveFocus() }
            }
            Text {
                visible: field.activeFocus && field.text === ""
                text: app.t.new_task_hint
                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                color: quick.c.faint
            }
        }
        Flow {
            Layout.fillWidth: true
            Layout.leftMargin: 34
            spacing: 6
            visible: (quick.understood.chips || []).length > 0 || quick.extraChips.length > 0
            // chosen with the buttons: × takes it away
            Repeater {
                model: quick.extraChips
                AbstractButton {
                    id: extraChip
                    required property var modelData
                    implicitHeight: 26
                    implicitWidth: extraRow.implicitWidth + 16
                    hoverEnabled: true
                    focusPolicy: Qt.NoFocus
                    Accessible.name: modelData.text
                    onClicked: quick.setExtra(modelData.kind, undefined)
                    background: Rectangle { radius: 13; color: extraChip.hovered ? quick.c.hover : quick.c.tint }
                    contentItem: Item { Row {
                        id: extraRow
                        anchors.centerIn: parent
                        spacing: 5
                        Icon { anchors.verticalCenter: parent.verticalCenter; name: extraChip.modelData.icon; size: 13; color: quick.c.tintText }
                        Text { anchors.verticalCenter: parent.verticalCenter; text: extraChip.modelData.text; font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: quick.c.tintText }
                        Icon { anchors.verticalCenter: parent.verticalCenter; name: "close"; size: 10; color: quick.c.tintText; opacity: extraChip.hovered ? 1 : 0.5 }
                    } }
                }
            }
            Repeater {
                model: quick.understood.chips || []
                AbstractButton {
                    id: chip
                    required property var modelData
                    implicitHeight: 26
                    implicitWidth: chipRow.implicitWidth + 16
                    hoverEnabled: true
                    Accessible.name: modelData.text
                    ToolTip.text: app.t.chip_remove; ToolTip.visible: hovered; ToolTip.delay: 600
                    onClicked: { quick.keep = quick.keep.concat([modelData.kind]); quick.update() }
                    background: Rectangle { radius: 13; color: chip.hovered ? quick.c.hover : quick.c.tint }
                    contentItem: Item { Row {
                        id: chipRow
                        anchors.centerIn: parent
                        spacing: 5
                        Rectangle { visible: !!chip.modelData.color; anchors.verticalCenter: parent.verticalCenter; width: 8; height: 8; radius: 4; color: chip.modelData.color || "transparent" }
                        Icon { visible: !chip.modelData.color; anchors.verticalCenter: parent.verticalCenter; name: chip.modelData.icon; size: 13; color: quick.c.tintText }
                        Text { anchors.verticalCenter: parent.verticalCenter; text: chip.modelData.text; font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: quick.c.tintText }
                        Icon { anchors.verticalCenter: parent.verticalCenter; name: "close"; size: 10; color: quick.c.tintText; opacity: chip.hovered ? 1 : 0.5 }
                    } }
                }
            }
        }
        // the same without words
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 30
            Layout.bottomMargin: 2
            visible: quick.open_
            spacing: 2
            OButton {
                id: dateBtn
                kind: "quiet"; height_: 26; iconName: "calendar"; iconSize: 14; text: app.t.quick_date
                focusPolicy: Qt.NoFocus
                onClicked: datePick.open()
                DatePicker {
                    id: datePick
                    y: dateBtn.height + 4
                    value: quick.extras.due || ""
                    onPicked: iso => quick.setExtra("due", iso)
                }
            }
            OButton {
                kind: "quiet"; height_: 26; iconName: "flag"; iconSize: 14; text: app.t.quick_flag
                focusPolicy: Qt.NoFocus
                onClicked: quick.setExtra("flagged", !quick.extras.flagged)
            }
            OButton {
                id: prioQuick
                kind: "quiet"; height_: 26; iconName: "priority"; iconSize: 14; text: app.t.quick_priority
                focusPolicy: Qt.NoFocus
                onClicked: prioPick.open()
                OMenu {
                    id: prioPick
                    y: prioQuick.height + 4
                    implicitWidth: 200
                    OMenuItem { text: app.t.priority_1; onTriggered: quick.setExtra("priority", 1) }
                    OMenuItem { text: app.t.priority_5; onTriggered: quick.setExtra("priority", 5) }
                    OMenuItem { text: app.t.priority_9; onTriggered: quick.setExtra("priority", 9) }
                    OMenuItem { text: app.t.priority_0; onTriggered: quick.setExtra("priority", 0) }
                }
            }
            Item { Layout.fillWidth: true }
        }
    }
}
