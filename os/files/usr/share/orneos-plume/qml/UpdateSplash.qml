// While an update goes in (« Mettre à jour », updater.py): Plume's windows are gone, this small window stays in
// the middle of the screen, on the night sky of Orneos: the logo breathing in a turning ring, the version, then
// « Redémarrage… » until the new Plume opens. Nothing to click: it only says that something is happening.
import QtQuick
import QtQuick.Window
import "components"

Window {
    id: splash
    objectName: "updateSplash"             // updater.py hides every window but this one
    readonly property var c: theme.c
    readonly property bool restarting: updater.state === "restarting"
    visible: updater.state === "installing" || restarting
    flags: Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    color: "transparent"
    width: 320; height: 340
    x: Screen.virtualX + (Screen.width - width) / 2
    y: Screen.virtualY + (Screen.height - height) / 2
    title: plume.t.update_title

    Rectangle {
        id: card
        anchors.fill: parent
        radius: 24
        gradient: Gradient {
            GradientStop { position: 0; color: splash.c.night2 }
            GradientStop { position: 0.55; color: splash.c.night1 }
            GradientStop { position: 1; color: splash.c.night0 }
        }
        border.width: 1; border.color: Qt.alpha(splash.c.onNight, 0.08)
        clip: true

        // a few stars, slowly
        Repeater {
            model: 18
            Rectangle {
                required property int index
                readonly property real seed: Math.sin(index * 12.9898) * 43758.5453
                x: (seed - Math.floor(seed)) * card.width
                y: ((seed * 7) - Math.floor(seed * 7)) * card.height * 0.7
                width: index % 5 === 0 ? 2.5 : 1.5; height: width; radius: width / 2
                color: splash.c.onNight
                opacity: 0.25
                SequentialAnimation on opacity {
                    running: splash.visible; loops: Animation.Infinite
                    PauseAnimation { duration: (index * 137) % 1200 }
                    NumberAnimation { to: 0.8; duration: 1400; easing.type: Easing.InOutSine }
                    NumberAnimation { to: 0.2; duration: 1400; easing.type: Easing.InOutSine }
                }
            }
        }

        // the logo, breathing, inside a ring that turns
        Item {
            id: mark
            width: 132; height: 132
            anchors.horizontalCenter: parent.horizontalCenter
            y: 58
            // the glow under it
            Rectangle {
                anchors.centerIn: parent
                width: 120; height: 120; radius: 60
                color: Qt.alpha(splash.c.famCommunicate, 0.22)
                SequentialAnimation on scale {
                    running: splash.visible; loops: Animation.Infinite
                    NumberAnimation { from: 0.9; to: 1.15; duration: 1100; easing.type: Easing.InOutSine }
                    NumberAnimation { from: 1.15; to: 0.9; duration: 1100; easing.type: Easing.InOutSine }
                }
            }
            Canvas {
                id: ring
                anchors.fill: parent
                property color tone: splash.c.famCommunicate
                onPaint: {
                    const ctx = getContext("2d")
                    ctx.reset()
                    ctx.lineWidth = 4
                    ctx.lineCap = "round"
                    ctx.strokeStyle = Qt.alpha(splash.c.onNight, 0.1)
                    ctx.beginPath(); ctx.arc(width / 2, height / 2, width / 2 - 4, 0, 2 * Math.PI); ctx.stroke()
                    const grad = ctx.createLinearGradient(0, 0, width, height)
                    grad.addColorStop(0, Qt.alpha(tone, 0))
                    grad.addColorStop(1, tone)
                    ctx.strokeStyle = grad
                    ctx.beginPath(); ctx.arc(width / 2, height / 2, width / 2 - 4, -Math.PI / 2, Math.PI * 0.9); ctx.stroke()
                }
                RotationAnimator on rotation {
                    running: splash.visible; loops: Animation.Infinite
                    from: 0; to: 360; duration: 1100
                }
            }
            Rectangle {
                anchors.centerIn: parent
                width: 72; height: 72; radius: 20
                gradient: Gradient {
                    GradientStop { position: 0; color: Qt.lighter(splash.c.famCommunicate, 1.15) }
                    GradientStop { position: 1; color: splash.c.famCommunicate }
                }
                Icon { anchors.centerIn: parent; name: "plume"; size: 38; color: splash.c.onNight }
                SequentialAnimation on scale {
                    running: splash.visible; loops: Animation.Infinite
                    NumberAnimation { from: 1; to: 1.06; duration: 700; easing.type: Easing.InOutSine }
                    NumberAnimation { from: 1.06; to: 1; duration: 700; easing.type: Easing.InOutSine }
                }
            }
        }

        Column {
            anchors.top: mark.bottom; anchors.topMargin: 28
            anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width - 48
            spacing: 6
            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                textFormat: Text.PlainText
                text: splash.restarting ? plume.t.update_restarting : plume.t.update_title
                font.family: "Schibsted Grotesk"; font.pixelSize: 19; font.weight: Font.Bold
                color: splash.c.onNight
            }
            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                textFormat: Text.PlainText
                text: plume.t.update_installing_short.replace("%1", updater.version)
                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                color: splash.c.onNightMuted
                wrapMode: Text.Wrap
            }
        }

        // three dots, one after the other
        Row {
            anchors.bottom: parent.bottom; anchors.bottomMargin: 26
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 8
            Repeater {
                model: 3
                Rectangle {
                    required property int index
                    width: 7; height: 7; radius: 3.5
                    color: splash.c.onNight
                    opacity: 0.3
                    SequentialAnimation on opacity {
                        running: splash.visible; loops: Animation.Infinite
                        PauseAnimation { duration: index * 180 }
                        NumberAnimation { to: 1; duration: 320 }
                        NumberAnimation { to: 0.3; duration: 320 }
                        PauseAnimation { duration: (2 - index) * 180 }
                    }
                }
            }
        }
    }
}
