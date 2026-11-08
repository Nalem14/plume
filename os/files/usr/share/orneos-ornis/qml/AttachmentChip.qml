// A file of a message: an image as a vignette, any other file as a pill with its name. In the message box it can be
// removed (a cross, also Delete when focused) and shows its upload (pulsing) or its failure (saffron, a warning).
import QtQuick
import QtQuick.Controls
import "components"

AbstractButton {
    id: chip
    property string name
    property string kind                 // image, document, text
    property string thumb                // file:// of a vignette, "" for none
    property string state_: "ready"      // uploading, failed, ready
    property bool removable
    property bool openable               // a sent file: a click opens it from the Drive
    signal removeRequested()
    signal openRequested()
    readonly property var c: theme.c
    readonly property bool picture: kind === "image" && thumb !== ""
    implicitWidth: picture ? 64 : Math.min(220, pill.implicitWidth + 20)
    implicitHeight: picture ? 64 : 36
    hoverEnabled: true
    focusPolicy: removable || openable ? Qt.StrongFocus : Qt.NoFocus
    HoverHandler { cursorShape: chip.openable ? Qt.PointingHandCursor : Qt.ArrowCursor }
    Accessible.name: removable ? app.t.attach_remove.replace("%1", name) : name
    ToolTip.text: state_ === "failed" ? app.t.attach_failed + " · " + name : state_ === "uploading" ? app.t.attach_uploading + " " + name : name
    ToolTip.delay: 450
    ToolTip.visible: hovered
    onClicked: removable ? removeRequested() : openable ? openRequested() : undefined
    Keys.onDeletePressed: if (removable) removeRequested()
    Keys.onBackPressed: if (removable) removeRequested()

    background: Rectangle {
        radius: chip.picture ? 12 : 10
        color: chip.picture ? "transparent" : chip.c.hover
        border.width: chip.state_ === "failed" || chip.visualFocus ? 2 : 1
        border.color: chip.state_ === "failed" || chip.visualFocus ? chip.c.saffron : chip.c.line
        z: chip.picture ? 2 : -1
    }

    contentItem: Item {
        opacity: chip.state_ === "uploading" ? pulse.value : 1
        QtObject {
            id: pulse
            property real value: 1
            SequentialAnimation on value {
                running: chip.state_ === "uploading" && Qt.styleHints.reduceMotion !== true
                loops: Animation.Infinite
                NumberAnimation { to: 0.45; duration: 650; easing.type: Easing.InOutSine }
                NumberAnimation { to: 1; duration: 650; easing.type: Easing.InOutSine }
            }
        }
        Rectangle {
            visible: chip.picture
            anchors.fill: parent
            radius: 12
            clip: true
            color: chip.c.hover
            Image {
                anchors.fill: parent
                source: chip.picture ? chip.thumb : ""
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                sourceSize.width: 128; sourceSize.height: 128
            }
        }
        Row {
            id: pill
            visible: !chip.picture
            anchors.verticalCenter: parent.verticalCenter
            x: 10
            spacing: 7
            Icon {
                anchors.verticalCenter: parent.verticalCenter
                name: chip.state_ === "failed" ? "warning" : chip.kind === "image" ? "image" : /\.pdf$/i.test(chip.name) ? "pdf" : chip.kind === "text" ? "note" : "clip"
                size: 16
                color: chip.state_ === "failed" ? chip.c.saffronInk : chip.c.muted
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                width: Math.min(implicitWidth, 150)
                text: chip.name
                elide: Text.ElideMiddle
                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                color: chip.c.text
            }
            Item { width: chip.removable ? 14 : 0; height: 1 }
        }
    }

    Rectangle {                          // the cross, always there on a pill, on hover over a vignette
        visible: chip.removable && (!chip.picture || chip.hovered || chip.visualFocus)
        width: 20; height: 20; radius: 10
        z: 3
        anchors.right: parent.right; anchors.top: parent.top
        anchors.rightMargin: chip.picture ? -6 : 8
        anchors.topMargin: chip.picture ? -6 : (parent.height - height) / 2
        color: chip.picture ? chip.c.text : "transparent"
        Icon {
            anchors.centerIn: parent
            name: "close"; size: 12
            color: chip.picture ? chip.c.bg : chip.c.muted
        }
    }
}
