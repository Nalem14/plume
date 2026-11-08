// The new-item line at the top of a column (« Nouveau message », « Nouvel événement… », « Nouveau contact… »):
// a quiet card-shaped button with the app's glyph and the shortcut, so the main action reads as a line of the
// column rather than a big filled button. A click (or the shortcut) opens the editor at once; nothing is typed here.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

AbstractButton {
    id: cap
    readonly property var c: theme.c
    property color tint: c.famCommunicate
    property string iconName: "plus"
    property string shortcut              // the key hint ("Ctrl N")

    implicitHeight: 40
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    Accessible.name: text + (shortcut ? " (" + shortcut + ")" : "")

    background: Rectangle {
        radius: 8
        color: cap.down ? cap.c.hover : cap.c.field
        border.width: 1
        border.color: cap.hovered || cap.visualFocus ? cap.tint : cap.c.line
        Behavior on border.color { ColorAnimation { duration: 120 } }
        Rectangle {
            anchors.fill: parent; anchors.margins: -3
            radius: parent.radius + 3
            color: "transparent"
            border.width: 3; border.color: Qt.alpha(cap.tint, 0.18)
            visible: cap.visualFocus
        }
    }
    contentItem: RowLayout {
        spacing: 8
        Item { implicitWidth: 2 }
        Icon { name: cap.iconName; size: 18; color: cap.tint }
        Text {
            Layout.fillWidth: true
            text: cap.text
            elide: Text.ElideRight
            font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.Medium
            color: cap.hovered ? cap.c.text : cap.c.muted
        }
        TextMetrics { id: room; font.family: "Schibsted Grotesk"; font.pixelSize: 14; text: cap.text }
        Rectangle {
            // the key hint gives way to the label in a narrow column
            visible: cap.shortcut !== "" && room.advanceWidth + implicitWidth + 52 < cap.width
            implicitWidth: key.implicitWidth + 10; implicitHeight: 20
            radius: 4; color: cap.c.card
            border.width: 1; border.color: cap.c.line
            Text {
                id: key
                anchors.centerIn: parent
                text: cap.shortcut
                font.family: "JetBrains Mono"; font.pixelSize: 11
                color: cap.c.muted
            }
        }
        Item { implicitWidth: 0 }
    }
}
