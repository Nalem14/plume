// Centered message for a module with nothing to show yet: icon tile, title, a line, one action (and a quiet second).
import QtQuick
import QtQuick.Layouts

Rectangle {
    id: empty
    property string iconName
    property string title
    property string lead
    property string actionText
    property string actionIcon: "arrow"
    property string secondaryText
    signal activated()
    signal secondary()
    readonly property var c: theme.c

    color: c.bg

    ColumnLayout {
        anchors.centerIn: parent
        width: Math.min(440, parent.width - 64)
        spacing: 0

        Rectangle {
            Layout.alignment: Qt.AlignHCenter
            implicitWidth: 64; implicitHeight: 64; radius: 14
            color: empty.c.tint
            Icon { anchors.centerIn: parent; name: empty.iconName; size: 30; color: empty.c.accent }
        }
        Text { textFormat: Text.PlainText;
            Layout.fillWidth: true
            Layout.topMargin: 22
            text: empty.title
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            font.family: "Schibsted Grotesk"; font.pixelSize: 22; font.weight: Font.DemiBold
            color: empty.c.text
        }
        Text { textFormat: Text.PlainText;
            Layout.fillWidth: true
            Layout.topMargin: 10
            visible: text !== ""
            text: empty.lead
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            lineHeight: 1.3
            font.family: "Schibsted Grotesk"; font.pixelSize: 15
            color: empty.c.muted
        }
        OButton {
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: 24
            visible: empty.actionText !== ""
            kind: "primary"
            height_: 40
            text: empty.actionText
            iconName: empty.actionIcon
            onClicked: empty.activated()
        }
        OButton {
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: 8
            visible: empty.secondaryText !== ""
            kind: "quiet"
            text: empty.secondaryText
            onClicked: empty.secondary()
        }
    }
}
