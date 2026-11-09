// Live status of the open bot, above the message box — never written into the conversation.
// « Orla réfléchit… », « Orla écrit un fichier… », « Orla appelle un outil… », …
import QtQuick
import QtQuick.Layouts
import "components"

Item {
    id: bubble
    property bool active: false
    property string text: ""
    property var face: null               // the bot's face (the mascot when none)
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

        BotFace {
            visible: !!bubble.face
            Layout.alignment: Qt.AlignVCenter
            face: bubble.face || ({})
            size: 30
            busy: bubble.active
        }
        Rectangle {
            visible: !bubble.face
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
            implicitWidth: Math.min(parent.width - 44, label.implicitWidth + 28 + dots.width + 8)
            implicitHeight: label.implicitHeight + 18
            radius: 16
            color: bubble.c.field
            border.width: 1
            border.color: bubble.c.line

            Row {                         // three dots that breathe: it is writing
                id: dots
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left; anchors.leftMargin: 14
                spacing: 4
                Repeater {
                    model: 3
                    Rectangle {
                        required property int index
                        width: 6; height: 6; radius: 3
                        color: bubble.c.muted
                        SequentialAnimation on opacity {
                            running: bubble.active && Qt.styleHints.reduceMotion !== true
                            loops: Animation.Infinite
                            PauseAnimation { duration: index * 160 }
                            NumberAnimation { from: 0.3; to: 1; duration: 320 }
                            NumberAnimation { from: 1; to: 0.3; duration: 320 }
                            PauseAnimation { duration: (2 - index) * 160 }
                        }
                    }
                }
            }
            Text {
                id: label
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: dots.right
                anchors.leftMargin: 8
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
