// Written while Ornis works: the messages waiting above the box, sent one by one after the reply (as Claude Code's
// and Cursor's queue). Each can go now (the reply stops), go back into the box to be changed, or not go at all.
// The Chat mode (chat.later) and the Code mode (code.later) show the same.
import QtQuick
import QtQuick.Layouts
import "components"

Rectangle {
    id: dock
    property var items: []
    signal sendNow(int index)
    signal editRequested(int index)
    signal dropRequested(int index)
    readonly property var c: theme.c
    visible: items.length > 0
    implicitHeight: visible ? col.implicitHeight + 12 : 0
    radius: 14
    color: c.card
    border.width: 1; border.color: c.line
    Accessible.role: Accessible.List
    Accessible.name: app.t.later_label

    ColumnLayout {
        id: col
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 6 }
        spacing: 2
        Repeater {
            model: dock.items
            Rectangle {
                id: row
                required property string modelData
                required property int index
                Layout.fillWidth: true
                implicitHeight: Math.max(36, line.implicitHeight + 14)
                radius: 10
                color: hover.hovered ? dock.c.hover : "transparent"
                HoverHandler { id: hover }
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 4
                    spacing: 8
                    Rectangle {                  // a dashed-like ring: not sent yet
                        implicitWidth: 22; implicitHeight: 22; radius: 11
                        color: "transparent"
                        border.width: 1.5; border.color: dock.c.accentLine
                        Icon { anchors.centerIn: parent; name: "clock"; size: 12; color: dock.c.accent }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0
                        Text {
                            text: row.index === 0 ? app.t.later_next : app.t.later_label
                            font.family: "Schibsted Grotesk"; font.pixelSize: 11; font.weight: Font.DemiBold
                            color: dock.c.muted
                        }
                        Text {
                            id: line
                            Layout.fillWidth: true
                            text: row.modelData.replace(/\s+/g, " ")
                            elide: Text.ElideRight
                            maximumLineCount: 2
                            wrapMode: Text.Wrap
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13
                            color: dock.c.text
                        }
                    }
                    OButton {
                        kind: "quiet"; iconName: "send"; iconSize: 14; height_: 28
                        text: dock.width >= 460 ? app.t.later_send_now : ""
                        tip: app.t.later_send_now_tip
                        onClicked: dock.sendNow(row.index)
                    }
                    OButton {
                        kind: "quiet"; iconName: "edit"; iconSize: 14; height_: 28
                        tip: app.t.later_edit
                        onClicked: dock.editRequested(row.index)
                    }
                    OButton {
                        kind: "quiet"; iconName: "close"; iconSize: 13; height_: 28
                        tip: app.t.later_drop
                        onClicked: dock.dropRequested(row.index)
                    }
                }
            }
        }
    }
}
