// A file shared in a conversation: an image in preview (the cloud draws it), anything else as a line with
// its type, name and size (one on its way: the picture on this computer). A click opens it (the viewer for a
// picture, this computer's app otherwise); its button saves it.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

AbstractButton {
    id: card
    readonly property var c: theme.c
    property var file: ({})
    property bool mine: false
    readonly property bool image: (file.preview || !!file.local) && String(file.mime).startsWith("image/")
    signal opened()
    signal saveWanted()
    hoverEnabled: true
    onClicked: opened()
    Accessible.name: file.name
    implicitHeight: image ? Math.min(320, Math.max(120, file.width && file.height ? width * file.height / file.width : 200)) : 52
    implicitWidth: image ? 320 : 260

    background: Rectangle {
        radius: 10
        color: card.image ? "transparent" : (card.mine ? Qt.alpha("white", 0.14) : (card.hovered ? card.c.hover : card.c.bg))
        border.width: card.image ? 0 : 1
        border.color: card.mine ? Qt.alpha("white", 0.25) : card.c.hairline
    }
    contentItem: Item {
        Image {
            visible: card.image
            anchors.fill: parent
            source: !card.image ? "" : card.file.local ? card.file.local : "image://meet/preview/" + card.file.id
            sourceSize: Qt.size(720, 720)
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
            Rectangle { anchors.fill: parent; color: card.c.hover; visible: parent.status !== Image.Ready; radius: 10 }
        }
        RowLayout {
            visible: !card.image
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
