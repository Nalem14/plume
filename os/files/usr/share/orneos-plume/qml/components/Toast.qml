// One short line at the bottom of the window (sync problems, sending, imports), with an optional action
// ("Undo"). Gone after a few seconds.
import QtQuick
import QtQuick.Controls
import QtQuick.Effects

Item {
    id: toast
    readonly property var c: theme.c
    property string message
    property string actionText
    property var action: null
    property bool shown: false

    function show(text, label, fn, seconds) {
        message = text
        actionText = label || ""
        action = fn || null
        timer.interval = (seconds || 5) * 1000
        timer.restart()
        shown = true
    }
    function hide() { shown = false; timer.stop() }

    anchors.horizontalCenter: parent.horizontalCenter
    anchors.bottom: parent.bottom
    anchors.bottomMargin: shown ? 24 : -60
    width: Math.min(620, row.implicitWidth + 40)
    height: 46
    opacity: shown ? 1 : 0
    Behavior on anchors.bottomMargin { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
    Behavior on opacity { NumberAnimation { duration: 160 } }

    Timer { id: timer; interval: 5000; onTriggered: toast.shown = false }

    RectangularShadow { anchors.fill: card; radius: card.radius; blur: 24; offset.y: 8; color: toast.c.shadow }
    Rectangle {
        id: card
        anchors.fill: parent
        radius: 8
        color: theme.dark ? "#E8ECF3" : "#0F2440"
        MouseArea { anchors.fill: parent; onClicked: toast.hide() }
        Row {
            id: row
            anchors.centerIn: parent
            spacing: 16
            Text { textFormat: Text.PlainText;
                anchors.verticalCenter: parent.verticalCenter
                width: Math.min(implicitWidth, 480)
                text: toast.message
                elide: Text.ElideRight
                font.family: "Schibsted Grotesk"; font.pixelSize: 14
                color: theme.dark ? "#0A1424" : "#FFFFFF"
            }
            AbstractButton {
                id: act
                visible: toast.actionText !== ""
                anchors.verticalCenter: parent.verticalCenter
                implicitWidth: actLabel.implicitWidth + 16; implicitHeight: 30
                hoverEnabled: true
                onClicked: { const fn = toast.action; toast.hide(); if (fn) fn() }
                background: Rectangle { radius: 6; color: act.hovered ? (theme.dark ? "#C9D3EC" : "#1E3A66") : "transparent" }
                contentItem: Text {
                    id: actLabel
                    text: toast.actionText
                    horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                    font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
                    color: theme.dark ? "#002FA7" : "#F0A202"
                }
            }
        }
    }
}
