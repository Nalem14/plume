// Live status of the open bot, above the message box — never written into the conversation.
// « Orla réfléchit… », « Orla écrit un fichier… », « Orla appelle un outil… », …
import QtQuick
import QtQuick.Layouts
import "components"

Item {
    id: bubble
    property bool active: false
    property string text: ""
    readonly property var c: theme.c
    implicitHeight: active ? card.implicitHeight : 0
    visible: active || opacity > 0
    opacity: active ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: 160 } }
    Behavior on implicitHeight { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
    Accessible.role: Accessible.StatusBar
    Accessible.name: label.text

    RowLayout {
        id: card
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: 14

        Rectangle {
            Layout.alignment: Qt.AlignTop
            implicitWidth: 30; implicitHeight: 30; radius: 15
            color: "transparent"
            Icon { anchors.centerIn: parent; name: "ornis-mascot"; thinking: bubble.active; size: 30 }
            SequentialAnimation on opacity {
                running: bubble.active && Qt.styleHints.reduceMotion !== true
                loops: Animation.Infinite
                NumberAnimation { from: 1; to: 0.55; duration: 700; easing.type: Easing.InOutSine }
                NumberAnimation { from: 0.55; to: 1; duration: 700; easing.type: Easing.InOutSine }
                onRunningChanged: if (!running) parent.opacity = 1
            }
        }

        Rectangle {
            Layout.alignment: Qt.AlignVCenter
            Layout.maximumWidth: parent.width - 44
            implicitWidth: Math.min(parent.width - 44, label.implicitWidth + 28)
            implicitHeight: label.implicitHeight + 18
            radius: 16
            color: bubble.c.field
            border.width: 1
            border.color: bubble.c.line

            Text {
                id: label
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.leftMargin: 14
                anchors.right: parent.right
                anchors.rightMargin: 14
                text: bubble.text
                wrapMode: Text.NoWrap
                elide: Text.ElideRight
                font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.Medium
                font.italic: true
                color: bubble.c.muted
                onTextChanged: if (bubble.active && Qt.styleHints.reduceMotion !== true) pulse.restart()
                SequentialAnimation {
                    id: pulse
                    NumberAnimation { target: label; property: "opacity"; to: 0.4; duration: 80 }
                    NumberAnimation { target: label; property: "opacity"; to: 1; duration: 160 }
                }
            }
        }
    }
}
