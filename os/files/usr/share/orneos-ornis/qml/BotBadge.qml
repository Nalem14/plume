// A bot's title (« Secrétaire », « Service client »…), as a small badge next to its name: in the list, the
// header of its thread and the room of a group. Nothing when the bot has none.
import QtQuick

Rectangle {
    id: badge
    property string text: ""
    property color tint: theme.c.accent
    property int size: 11
    visible: text !== ""
    implicitWidth: visible ? label.implicitWidth + 12 : 0
    implicitHeight: visible ? label.implicitHeight + 4 : 0
    radius: height / 2
    color: Qt.rgba(tint.r, tint.g, tint.b, theme.dark ? 0.22 : 0.12)
    Text {
        id: label
        anchors.centerIn: parent
        text: badge.text
        font.family: "Schibsted Grotesk"; font.pixelSize: badge.size; font.weight: Font.DemiBold
        color: theme.dark ? Qt.lighter(badge.tint, 1.5) : Qt.darker(badge.tint, 1.25)
    }
}
