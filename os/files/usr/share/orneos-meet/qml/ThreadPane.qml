// A thread of the conversation (Talk 25), beside the chat: its title, its messages, a field to answer in it.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Rectangle {
    id: pane
    readonly property var c: theme.c
    signal closeWanted()
    color: c.chrome

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 64
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: Qt.tint(pane.c.chrome, Qt.alpha(pane.c.famCommunicate, theme.dark ? 0.16 : 0.08)) }
                GradientStop { position: 1; color: pane.c.chrome }
            }
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: pane.c.hairline }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16; anchors.rightMargin: 8
                spacing: 10
                Icon { name: "chat"; size: 18; color: pane.c.famCommunicate }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Text {
                        text: app.t.thread
                        font.family: "JetBrains Mono"; font.pixelSize: 11; font.capitalization: Font.AllUppercase; font.letterSpacing: 0.8
                        color: pane.c.famCommunicate
                    }
                    Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: meet.thread.title || ""; elide: Text.ElideRight; font.pixelSize: 15; font.weight: Font.DemiBold; color: pane.c.text }
                }
                OButton { kind: "quiet"; iconName: "close"; tip: app.t.close; onClicked: pane.closeWanted() }
            }
        }

        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: meet.threadMessages
            topMargin: 8; bottomMargin: 8
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            delegate: MessageRow { compact: true; inThread: true; onImageWanted: (file, album) => threadViewer.show(file, album) }
            onCountChanged: Qt.callLater(positionViewAtEnd)
            BusyIndicator { anchors.centerIn: parent; running: list.count === 0 && !!meet.thread.id; visible: running; implicitWidth: 28; implicitHeight: 28 }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 60
            color: pane.c.chrome
            Rectangle { width: parent.width; height: 1; color: pane.c.hairline }
            RowLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 6
                OTextField {
                    id: field
                    Layout.fillWidth: true
                    placeholderText: app.t.reply_in_thread
                    onAccepted: send.clicked()
                }
                OButton {
                    id: send
                    kind: "primary"; iconName: "send"; tip: app.t.send
                    enabled: field.text.trim() !== ""
                    onClicked: { meet.sendInThread(field.text); field.text = "" }
                }
            }
        }
    }
    ImageViewer { id: threadViewer }
}
