// A video of the library, from its copy on the computer (QtMultimedia). Loaded only for a video: without the
// module, the viewer hands the file to the computer's own player.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtMultimedia
import "components"

Item {
    id: player
    function play(uri) { media.source = uri; media.play() }
    function toggle() { media.playbackState === MediaPlayer.PlayingState ? media.pause() : media.play() }

    MediaPlayer {
        id: media
        videoOutput: output
        audioOutput: AudioOutput {}
    }
    VideoOutput { id: output; anchors.fill: parent }
    TapHandler { onTapped: player.toggle() }

    Rectangle {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom; anchors.bottomMargin: 18
        width: Math.min(parent.width - 40, 560); height: 44; radius: 22
        color: Qt.rgba(0, 0, 0, 0.6)
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 16
            spacing: 12
            AbstractButton {
                implicitWidth: 28; implicitHeight: 28
                Accessible.name: media.playbackState === MediaPlayer.PlayingState ? app.t.pause : app.t.play
                onClicked: player.toggle()
                contentItem: Item {
                    Icon { anchors.centerIn: parent; visible: media.playbackState !== MediaPlayer.PlayingState; name: "play"; size: 18; color: "white" }
                    Row {
                        anchors.centerIn: parent; spacing: 4
                        visible: media.playbackState === MediaPlayer.PlayingState
                        Rectangle { width: 4; height: 16; color: "white" }
                        Rectangle { width: 4; height: 16; color: "white" }
                    }
                }
                background: Item {}
            }
            Slider {
                id: seek
                Layout.fillWidth: true
                from: 0; to: Math.max(1, media.duration)
                value: media.position
                onMoved: media.setPosition(value)
            }
            Text {
                text: app.duration(media.position / 1000) + " / " + app.duration(media.duration / 1000)
                font.family: "JetBrains Mono"; font.pixelSize: 12; color: "white"
            }
        }
    }
}
