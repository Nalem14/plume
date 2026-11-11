// The pictures of this computer a reply names (`img/plan.png`, ![](…), a full path), shown under it at once, as the
// pictures of a Meet chat: one in large, several as vignettes. A click opens it in the file panel on the right; on
// hover, « Enregistrer sous… » (the system's picker) and « Ouvrir le dossier » (its folder in the panel).
// app.localImages finds them (ornis_core/app.py); Message.qml (Chat, Code, Bots) and GroupView.qml use it.
import QtCore as Std               // StandardPaths only: its Settings would hide ours
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "components"

Flow {
    id: pics
    property var pictures: []               // [{path, name, url}]
    property real maxWidth: 520
    readonly property var c: theme.c
    readonly property bool single: pictures.length === 1
    objectName: "localPictures"
    visible: pictures.length > 0
    spacing: 8

    Repeater {
        model: pics.pictures
        AbstractButton {
            id: pic
            required property var modelData
            readonly property real boxW: pics.single ? Math.min(pics.maxWidth, 380) : 168
            readonly property real boxH: pics.single ? (img.status === Image.Ready && img.implicitWidth > 0
                                                        ? Math.max(90, Math.min(300, boxW * img.implicitHeight / img.implicitWidth)) : 220) : 124
            width: boxW; height: boxH
            hoverEnabled: true
            onClicked: app.openLocal(modelData.path)
            Accessible.name: modelData.name
            ToolTip.visible: hovered && !saveBtn.hovered && !folderBtn.hovered
            ToolTip.delay: 600
            ToolTip.text: modelData.path
            background: Rectangle {
                radius: 12
                color: pics.c.field
                border.width: 1; border.color: pic.hovered ? pics.c.accentLine : pics.c.line
            }
            contentItem: Item {
                Image {
                    id: img
                    anchors.fill: parent; anchors.margins: 1
                    source: pic.modelData.url
                    sourceSize: Qt.size(pics.single ? 760 : 336, pics.single ? 600 : 248)
                    fillMode: pics.single ? Image.PreserveAspectFit : Image.PreserveAspectCrop
                    asynchronous: true
                    smooth: true; mipmap: true
                    clip: true
                }
                BusyIndicator { anchors.centerIn: parent; running: img.status === Image.Loading; width: 28; height: 28 }
                Rectangle {                      // its name, on a soft band at the bottom
                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 1 }
                    height: 26
                    radius: 11
                    visible: pic.hovered || !pics.single
                    color: Qt.alpha(pics.c.card, 0.92)
                    Text {
                        anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10
                        verticalAlignment: Text.AlignVCenter
                        text: pic.modelData.name
                        elide: Text.ElideMiddle
                        textFormat: Text.PlainText
                        font.family: "Schibsted Grotesk"; font.pixelSize: 11; font.weight: Font.Medium
                        color: pics.c.text
                    }
                }
                Row {                            // on hover: save it elsewhere, its folder
                    anchors { top: parent.top; right: parent.right; margins: 6 }
                    spacing: 4
                    visible: pic.hovered
                    OButton { id: saveBtn; kind: "secondary"; iconName: "download"; iconSize: 14; height_: 28; tip: app.t.lp_save
                              onClicked: pics.saveAs(pic.modelData.path, pic.modelData.name) }
                    OButton { id: folderBtn; kind: "secondary"; iconName: "folder"; iconSize: 14; height_: 28; tip: app.t.lp_folder
                              onClicked: app.openLocal(pic.modelData.path.replace(/[\/\\][^\/\\]*$/, "") || "/") }
                }
            }
        }
    }

    // « Enregistrer sous… »: the system's picker, made when asked, in Téléchargements with the picture's name
    function saveAs(path, name) {
        const dl = Std.StandardPaths.writableLocation(Std.StandardPaths.DownloadLocation)
        const dialog = saverComponent.createObject(pics, { path: path, currentFolder: dl, selectedFile: dl + "/" + encodeURIComponent(name) })
        dialog.open()
    }
    Component {
        id: saverComponent
        FileDialog {
            property string path: ""
            title: app.t.lp_save
            fileMode: FileDialog.SaveFile
            onAccepted: { app.saveLocalCopy(path, String(selectedFile)); destroy() }
            onRejected: destroy()
        }
    }
}
