// A picture of the chat over the window: the cloud's preview at once, then the original once here. Échap or a
// click beside closes it; copy it, save it, open it with this computer's app (buttons, or a right click on it).
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "components"

Popup {
    id: viewer
    property var file: ({})
    property string original: ""
    property var album: []          // the pictures sent together: ← → go through them
    readonly property int at: album.findIndex(f => String(f.id) === String(file.id))
    function show(f, list) { album = list || []; go(f) }
    function go(f) { file = f; original = ""; if (!opened) open(); meet.fetchForView(f) }
    function step(d) { if (album.length > 1 && at >= 0) go(album[(at + d + album.length) % album.length]) }
    parent: Overlay.overlay
    x: 0; y: 0
    width: parent ? parent.width : 800
    height: parent ? parent.height : 600
    modal: true
    padding: 0
    closePolicy: Popup.CloseOnEscape
    Overlay.modal: Rectangle { color: Qt.alpha("#0A192F", 0.86) }
    background: Item {}
    Connections {
        target: meet
        enabled: viewer.opened
        function onFileReady(id, url) { if (id === String(viewer.file.id)) viewer.original = url }
    }

    contentItem: Item {
        MouseArea { anchors.fill: parent; onClicked: viewer.close() }
        Image {
            id: picture
            anchors.fill: parent
            anchors.margins: 64
            anchors.topMargin: 72
            source: viewer.original || (viewer.file.local ? viewer.file.local : viewer.file.id ? "image://meet/preview/" + viewer.file.id : "")
            sourceSize: viewer.original ? undefined : Qt.size(1024, 1024)
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            smooth: true; mipmap: true
            // the picture itself: a click keeps it open, a right click gives its actions where the pointer is
            MouseArea {
                anchors.centerIn: parent; width: parent.paintedWidth; height: parent.paintedHeight
                acceptedButtons: Qt.LeftButton | Qt.RightButton
                onClicked: mouse => {
                    if (mouse.button !== Qt.RightButton) return
                    const p = mapToItem(actions.parent, mouse.x, mouse.y)
                    actions.x = Math.min(p.x, actions.parent.width - actions.implicitWidth - 8)
                    actions.y = Math.min(p.y, actions.parent.height - actions.implicitHeight - 8)
                    actions.open()
                }
            }
        }
        BusyIndicator { anchors.centerIn: parent; running: picture.status === Image.Loading }
        // an album: previous and next on the sides, ← → too, and where we are under the name
        Item {
            anchors.fill: parent
            visible: viewer.album.length > 1
            focus: viewer.opened
            Keys.onLeftPressed: viewer.step(-1)
            Keys.onRightPressed: viewer.step(1)
            OButton { anchors.left: parent.left; anchors.leftMargin: 12; anchors.verticalCenter: parent.verticalCenter
                      kind: "secondary"; iconName: "arrow"; rotation: 180; onClicked: viewer.step(-1) }
            OButton { anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter
                      kind: "secondary"; iconName: "arrow"; onClicked: viewer.step(1) }
        }
        MeetMenu {
            id: actions
            objectName: "imageActions"
            z: 1
            OMenuItem { text: app.t.copy_image; iconName: "copy"; onTriggered: meet.copyImage(viewer.file) }
            OMenuItem { text: app.t.save_as; iconName: "download"; visible: !!viewer.file.id; onTriggered: saver.open() }
            OMenuItem { text: app.t.open_with_app; iconName: "openExternal"; visible: !!viewer.file.id
                        onTriggered: { meet.openFile(viewer.file); viewer.close() } }
        }
        RowLayout {
            anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right
            anchors.margins: 16
            spacing: 8
            Text {
                Layout.fillWidth: true
                textFormat: Text.PlainText
                text: (viewer.file.name || "") + (viewer.album.length > 1 && viewer.at >= 0 ? "  ·  " + (viewer.at + 1) + " / " + viewer.album.length : "")
                elide: Text.ElideMiddle
                font.pixelSize: 15; font.weight: Font.DemiBold; color: "white"
            }
            OButton { kind: "secondary"; iconName: "copy"; text: app.t.copy_image; onClicked: meet.copyImage(viewer.file) }
            OButton { kind: "secondary"; iconName: "download"; text: app.t.save_as; visible: !!viewer.file.id; onClicked: saver.open() }
            OButton { kind: "secondary"; iconName: "openExternal"; text: app.t.open_with_app; visible: !!viewer.file.id; onClicked: { meet.openFile(viewer.file); viewer.close() } }
            OButton { kind: "secondary"; iconName: "close"; tip: app.t.close; onClicked: viewer.close() }
        }
    }
    FileDialog {
        id: saver
        fileMode: FileDialog.SaveFile
        title: app.t.save_as
        currentFile: "file:///" + (viewer.file.name || "")
        onAccepted: meet.saveFile(viewer.file, String(selectedFile))
    }
}
