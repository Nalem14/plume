import QtQuick
import QtQuick.Controls

Switch {
    id: sw
    readonly property var c: theme.c
    spacing: 10
    font.family: "Schibsted Grotesk"
    font.pixelSize: 14
    indicator: Rectangle {
        x: sw.leftPadding; anchors.verticalCenter: parent.verticalCenter
        implicitWidth: 36; implicitHeight: 20; radius: 10
        color: sw.checked ? sw.c.action : sw.c.line
        Behavior on color { ColorAnimation { duration: 120 } }
        Rectangle {
            x: sw.checked ? parent.width - width - 3 : 3; anchors.verticalCenter: parent.verticalCenter
            width: 14; height: 14; radius: 7
            color: sw.checked ? sw.c.actionText : sw.c.card
            Behavior on x { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
        }
        Rectangle {
            anchors.fill: parent; anchors.margins: -3; radius: 13; color: "transparent"
            border.width: 2; border.color: sw.c.saffron; visible: sw.visualFocus
        }
    }
    contentItem: Text {
        leftPadding: sw.indicator.width + sw.spacing
        text: sw.text; font: sw.font; color: sw.c.text
        verticalAlignment: Text.AlignVCenter
    }
}
