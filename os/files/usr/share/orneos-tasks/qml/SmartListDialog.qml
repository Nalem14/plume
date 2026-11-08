// A smart list of one's own: a name and a colour, then the conditions (tags, date, priority, flag, lists), all
// of them or at least one. The count of what it holds now shows as one chooses.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"
import "components/colors.js" as Colors

ODialog {
    id: dialog
    readonly property var c: theme.c
    property string sid: ""
    property string color: tasks.colors[0]
    property var tags: []
    property var lists: []
    width: Math.min(520, parent ? parent.width - 48 : 520)
    title: sid ? app.t.smart_edit : app.t.smart_new

    function ask(rule) {
        rule = rule || {}
        sid = rule.id || ""
        name.text = rule.name || ""
        color = rule.color || tasks.colors[(tasks.smartLists.length + 3) % tasks.colors.length]
        tags = (rule.tags || []).slice()
        lists = (rule.lists || []).slice()
        match.select(rule.match || "all")
        due.select(rule.due || "")
        priority.select(rule.priority || 0)
        flagged.checked = !!rule.flagged
        open()
        name.forceActiveFocus()
    }
    function rule() {
        return { id: sid, name: name.text.trim(), color: color, tags: tags, lists: lists, match: match.currentValue,
                 due: due.currentValue, priority: priority.currentValue, flagged: flagged.checked }
    }
    function accept() {
        if (!name.text.trim()) { name.forceActiveFocus(); return }
        tasks.saveSmartList(rule())
        close()
    }
    function toggleList(href) {
        const out = lists.slice()
        const at = out.indexOf(href)
        if (at >= 0) out.splice(at, 1)
        else out.push(href)
        lists = out
    }

    component Label_: Text {
        Layout.fillWidth: true
        Layout.topMargin: 4
        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
        color: dialog.c.muted
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 12
        Rectangle {
            implicitWidth: 40; implicitHeight: 40; radius: 20
            color: Colors.display(dialog.color, theme.dark)
            Icon { anchors.centerIn: parent; name: "sort"; size: 20; color: "#FFFFFF" }
        }
        OTextField {
            id: name
            Layout.fillWidth: true
            placeholderText: app.t.smart_name
            onAccepted: dialog.accept()
        }
    }
    Flow {
        Layout.fillWidth: true
        spacing: 8
        Repeater {
            model: tasks.colors
            AbstractButton {
                id: swatch
                required property string modelData
                implicitWidth: 26; implicitHeight: 26
                Accessible.name: modelData
                onClicked: dialog.color = modelData
                background: Rectangle {
                    radius: 13
                    color: Colors.display(swatch.modelData, theme.dark)
                    border.width: dialog.color === swatch.modelData ? 3 : 0
                    border.color: dialog.c.overlay
                }
            }
        }
    }

    RowLayout {
        Layout.fillWidth: true
        Layout.topMargin: 6
        spacing: 10
        Text { text: app.t.smart_match; font.family: "Schibsted Grotesk"; font.pixelSize: 14; color: dialog.c.text }
        OComboBox {
            id: match
            Layout.fillWidth: true
            model: [{ text: app.t.smart_match_all, value: "all" }, { text: app.t.smart_match_any, value: "any" }]
        }
    }

    Label_ { text: app.t.smart_tags }
    Flow {
        Layout.fillWidth: true
        spacing: 6
        Repeater {
            model: dialog.tags
            AbstractButton {
                id: tagChip
                required property string modelData
                implicitHeight: 26; implicitWidth: tagRow.implicitWidth + 16
                hoverEnabled: true
                onClicked: dialog.tags = dialog.tags.filter(x => x !== modelData)
                ToolTip.text: app.t.tag_remove; ToolTip.visible: hovered; ToolTip.delay: 600
                background: Rectangle { radius: 13; color: tagChip.hovered ? dialog.c.hover : dialog.c.tint }
                contentItem: Item { Row {
                    id: tagRow
                    anchors.centerIn: parent
                    spacing: 5
                    Text { text: "#" + tagChip.modelData; textFormat: Text.PlainText; font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: dialog.c.tintText }
                    Icon { anchors.verticalCenter: parent.verticalCenter; name: "close"; size: 10; color: dialog.c.tintText }
                } }
            }
        }
        // the tags in use, one click to add
        Repeater {
            model: tasks.tags.filter(t => dialog.tags.indexOf(t.tag) < 0).slice(0, 8)
            AbstractButton {
                id: known
                required property var modelData
                implicitHeight: 26; implicitWidth: knownText.implicitWidth + 16
                hoverEnabled: true
                onClicked: dialog.tags = dialog.tags.concat([modelData.tag])
                background: Rectangle { radius: 13; color: known.hovered ? dialog.c.hover : "transparent"; border.width: 1; border.color: dialog.c.line }
                contentItem: Text {
                    id: knownText
                    text: "+ #" + known.modelData.tag
                    textFormat: Text.PlainText
                    horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: dialog.c.muted
                }
            }
        }
        TextField {
            id: newTag
            implicitWidth: 170; implicitHeight: 26
            placeholderText: app.t.smart_tags_ph
            placeholderTextColor: dialog.c.faint
            font.family: "Schibsted Grotesk"; font.pixelSize: 13
            color: dialog.c.text
            leftPadding: 10
            background: Rectangle { radius: 13; color: "transparent"; border.width: 1; border.color: newTag.activeFocus ? dialog.c.action : dialog.c.line }
            onAccepted: {
                const t = text.replace(/^#/, "").trim().toLowerCase()
                if (t && dialog.tags.indexOf(t) < 0) dialog.tags = dialog.tags.concat([t])
                text = ""
            }
        }
    }

    GridLayout {
        Layout.fillWidth: true
        columns: 2
        columnSpacing: 12; rowSpacing: 6
        Label_ { text: app.t.smart_due }
        Label_ { text: app.t.smart_priority }
        OComboBox {
            id: due
            Layout.fillWidth: true
            model: [{ text: app.t.smart_due_none_set, value: "" }, { text: app.t.smart_due_today, value: "today" },
                    { text: app.t.smart_due_week, value: "week" }, { text: app.t.smart_due_overdue, value: "overdue" },
                    { text: app.t.smart_due_any, value: "any" }, { text: app.t.smart_due_none, value: "none" }]
        }
        OComboBox {
            id: priority
            Layout.fillWidth: true
            model: [{ text: app.t.smart_priority_0, value: 0 }, { text: app.t.smart_priority_9, value: 9 },
                    { text: app.t.smart_priority_5, value: 5 }, { text: app.t.smart_priority_1, value: 1 }]
        }
    }
    OSwitch { id: flagged; Layout.topMargin: 4; text: app.t.smart_flagged }

    Label_ { text: app.t.smart_lists }
    Flow {
        Layout.fillWidth: true
        spacing: 6
        Repeater {
            model: tasks.lists
            AbstractButton {
                id: listChip
                required property var modelData
                readonly property bool on: dialog.lists.indexOf(modelData.href) >= 0
                implicitHeight: 28; implicitWidth: listRow.implicitWidth + 18
                hoverEnabled: true
                Accessible.role: Accessible.CheckBox
                Accessible.checked: on
                Accessible.name: modelData.name
                onClicked: dialog.toggleList(modelData.href)
                background: Rectangle {
                    radius: 14
                    color: listChip.on ? dialog.c.tint : listChip.hovered ? dialog.c.hover : "transparent"
                    border.width: listChip.on ? 0 : 1; border.color: dialog.c.line
                }
                contentItem: Item { Row {
                    id: listRow
                    anchors.centerIn: parent
                    spacing: 6
                    Rectangle { anchors.verticalCenter: parent.verticalCenter; width: 9; height: 9; radius: 3; color: Colors.display(listChip.modelData.color, theme.dark) }
                    Text { text: listChip.modelData.name; textFormat: Text.PlainText; font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: dialog.c.text }
                    Icon { anchors.verticalCenter: parent.verticalCenter; visible: listChip.on; name: "check"; size: 12; color: dialog.c.tintText }
                } }
            }
        }
    }
    Text {
        Layout.fillWidth: true
        text: app.t.smart_lists_hint
        wrapMode: Text.WordWrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 12
        color: dialog.c.faint
    }

    footer: [
        OButton {
            visible: dialog.sid !== ""
            kind: "quiet"; danger: true; iconName: "trash"; text: app.t.smart_delete
            onClicked: { const id = dialog.sid; dialog.close(); tasks.deleteSmartList(id) }
        },
        Item { Layout.fillWidth: true },
        OButton { text: app.t.cancel; onClicked: dialog.close() },
        OButton { kind: "primary"; text: dialog.sid ? app.t.save : app.t.create; onClicked: dialog.accept() }
    ]
}
