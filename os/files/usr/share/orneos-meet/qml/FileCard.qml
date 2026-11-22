// A file shared in a conversation: an image in preview (the cloud draws it), a video with an inline player,
// anything else as a line with its type, name and size. A click opens it; its button saves it.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtMultimedia
import "components"

AbstractButton {
    id: card
    readonly property var c: theme.c
    property var file: ({})
    property bool mine: false
    readonly property bool image: (file.preview || !!file.local) && String(file.mime).startsWith("image/")
    readonly property bool video: (!!file.local || !!file.id) && (String(file.mime || "").startsWith("video/") || /\.(mp4|mov|webm|mkv)$/i.test(file.name || ""))
    property string videoSource: file.local ? String(file.local) : ""
    property bool fetchingVideo: false
    readonly property bool playing: player.playbackState === MediaPlayer.PlayingState
    signal opened()
    signal saveWanted()
    hoverEnabled: true
    onClicked: if (!video) opened()
    Accessible.name: file.name
    implicitHeight: video ? 196 : image ? Math.min(320, Math.max(120, file.width && file.height ? width * file.height / file.width : 200)) : 52
    implicitWidth: video || image ? 320 : 260

    function toggleVideo() {
        if (playing) { player.pause(); return }
        if (videoSource) { player.play(); return }
        if (!fetchingVideo && file.id && file.path) {
            fetchingVideo = true
            voice.fetchVideo(String(file.id), String(file.path), String(file.name || "video.mp4"))
        }
    }
    Connections {
        target: voice
        function onVideoReady(fid, url) {
            if (String(card.file.id || "") !== fid) return
            card.fetchingVideo = false
            if (url) { card.videoSource = url; player.play() }
            else card.opened()
        }
    }

    background: Rectangle {
        radius: 10
        color: card.video ? "#0B111E" : card.image ? "transparent" : (card.mine ? Qt.alpha("white", 0.14) : (card.hovered ? card.c.hover : card.c.bg))
        border.width: card.image ? 0 : 1
        border.color: card.mine ? Qt.alpha("white", 0.25) : card.c.hairline
    }
    contentItem: Item {
        // Inline video player
        Item {
            visible: card.video
            anchors.fill: parent
            clip: true
            MediaPlayer {
                id: player
                source: card.videoSource
                audioOutput: AudioOutput {}
                videoOutput: videoOut
                onErrorOccurred: card.opened()
            }
            VideoOutput {
                id: videoOut
                anchors.fill: parent
                fillMode: VideoOutput.PreserveAspectFit
            }
            // Center Play/Pause overlay
            AbstractButton {
                anchors.centerIn: parent
                width: 48; height: 48
                visible: !card.playing || card.hovered
                onClicked: card.toggleVideo()
                background: Rectangle { radius: 24; color: Qt.alpha("#0A192F", 0.72) }
                contentItem: Icon {
                    anchors.centerIn: parent
                    name: card.fetchingVideo ? "refresh" : card.playing ? "pause" : "play"
                    size: 20; color: "white"
                }
            }
            // Bottom controls bar
            Rectangle {
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                height: 32
                color: Qt.alpha("#0A192F", 0.78)
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 6
                    spacing: 6
                    Text {
                        text: app.duration(Math.floor(player.position / 1000)) + (player.duration > 0 ? " / " + app.duration(Math.floor(player.duration / 1000)) : "")
                        font.family: "JetBrains Mono"; font.pixelSize: 11; color: "white"
                    }
                    Rectangle {
                        Layout.fillWidth: true; height: 4; radius: 2; color: Qt.alpha("white", 0.25)
                        Rectangle {
                            width: player.duration > 0 ? parent.width * (player.position / player.duration) : 0
                            height: parent.height; radius: 2; color: card.c.accent
                        }
                    }
                    OButton { visible: !!card.file.id; kind: "quiet"; iconName: "download"; height_: 24; tip: app.t.save_as; onClicked: card.saveWanted() }
                    OButton { kind: "quiet"; iconName: "openExternal"; height_: 24; tip: app.t.open; onClicked: card.opened() }
                }
            }
        }

        Image {
            visible: card.image && !card.video
            anchors.fill: parent
            source: !card.image ? "" : card.file.local ? card.file.local : "image://meet/preview/" + card.file.id
            sourceSize: Qt.size(720, 720)
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
            Rectangle { anchors.fill: parent; color: card.c.hover; visible: parent.status !== Image.Ready; radius: 10 }
        }
        RowLayout {
            visible: !card.image && !card.video
            anchors.fill: parent
            anchors.leftMargin: 10; anchors.rightMargin: 10
            spacing: 10
            Rectangle {
                implicitWidth: 32; implicitHeight: 32; radius: 8
                color: card.mine ? Qt.alpha("white", 0.2) : card.c.tint
                Icon { anchors.centerIn: parent; name: String(card.file.mime).indexOf("pdf") >= 0 ? "pdf" : "clip"; size: 16
                       color: card.mine ? card.c.actionText : card.c.tintText }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                Text { textFormat: Text.PlainText;
                    Layout.fillWidth: true
                    text: card.file.name || ""
                    elide: Text.ElideMiddle
                    font.pixelSize: 13; font.weight: Font.Medium
                    color: card.mine ? card.c.actionText : card.c.text
                }
                Text {
                    visible: card.file.size > 0
                    text: app.size(card.file.size)
                    font.pixelSize: 11
                    color: card.mine ? Qt.alpha(card.c.actionText, 0.8) : card.c.muted
                }
            }
            OButton {
                visible: card.hovered && !!card.file.id
                kind: "quiet"; iconName: "download"; height_: 28; tip: app.t.save_as
                onClicked: card.saveWanted()
            }
        }
    }
}
