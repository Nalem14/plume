// A sent image, seen again in large over the window, as in every assistant: the vignette at once, then the image
// itself (the file of this computer, or the cloud's preview). ← → go through the images of the message, Esc or a
// click outside closes, "Open in Drive" leaves for the cloud.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Popup {
    id: viewer
    property var images: []              // [{file_id, name, thumb}] of one message
    property int index: 0
    property string large: ""            // file:// of the current image in large, once there
    readonly property var current: images[index] || ({})
    readonly property var c: theme.c
    parent: Overlay.overlay
    x: 0; y: 0
    width: parent ? parent.width : 0
    height: parent ? parent.height : 0
    modal: true
    focus: true
    padding: 0
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    Overlay.modal: Rectangle {           // the conversation fades away behind the image
        color: viewer.c.scrim
        Rectangle { anchors.fill: parent; color: viewer.c.bg; opacity: 0.88 }
    }
    background: null

    function show(list, at) {
        images = list
        index = Math.max(0, Math.min(at, list.length - 1))
        load()
        open()
        forceActiveFocus()
    }
    function load() {
        large = ""
        if (current.file_id) chat.viewImage(current.file_id)
    }
    function go(step) {
        if (images.length < 2) return
        index = (index + step + images.length) % images.length
        load()
    }

    Connections {
        target: chat
        function onImageReady(fileId, url) { if (fileId === viewer.current.file_id) viewer.large = url }
    }

    contentItem: Item {
        focus: true
        Keys.onLeftPressed: viewer.go(-1)
        Keys.onRightPressed: viewer.go(1)
        MouseArea { anchors.fill: parent; onClicked: viewer.close() }      // around the image: closes

        Image {                          // the vignette while the large one comes, then the large one
            id: picture
            anchors.centerIn: parent
            width: Math.min(parent.width - 160, implicitWidth > 0 ? Math.max(implicitWidth, 480) : parent.width - 160)
            height: Math.min(parent.height - 140, implicitHeight > 0 ? Math.max(implicitHeight, 360) : parent.height - 140)
            fillMode: Image.PreserveAspectFit
            source: viewer.large || viewer.current.thumb || ""
            asynchronous: true
            smooth: true; mipmap: true
            MouseArea { anchors.fill: parent }                              // on the image: stays open
        }

        Rectangle {                      // its name (and which one of the message)
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom; anchors.bottomMargin: 22
            width: caption.width + 28; height: 32; radius: 16
            color: viewer.c.card
            Text {
                id: caption
                anchors.centerIn: parent
                width: Math.min(viewer.width - 240, implicitWidth)
                elide: Text.ElideMiddle
                text: viewer.current.name + (viewer.images.length > 1 ? "  ·  " + (viewer.index + 1) + " / " + viewer.images.length : "")
                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                color: viewer.c.text
            }
        }

        RowLayout {                      // open in the Drive, close
            anchors.top: parent.top; anchors.right: parent.right
            anchors.margins: 18
            spacing: 8
            OButton {
                visible: !!viewer.current.file_id
                text: app.t.open_drive; iconName: "openExternal"
                onClicked: { app.openCloud("/f/" + viewer.current.file_id); viewer.close() }
            }
            OButton { iconName: "close"; tip: app.t.close; onClicked: viewer.close() }
        }

        Repeater {                       // previous, next
            model: viewer.images.length > 1 ? [-1, 1] : []
            OButton {
                required property int modelData
                anchors.verticalCenter: parent.verticalCenter
                x: modelData < 0 ? 18 : parent.width - width - 18
                iconName: modelData < 0 ? "chevronLeft" : "chevronRight"; iconSize: 22; height_: 44
                tip: modelData < 0 ? app.t.image_prev : app.t.image_next
                onClicked: viewer.go(modelData)
            }
        }
    }
}
