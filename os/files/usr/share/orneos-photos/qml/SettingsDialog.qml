// Réglages (Ctrl+,): the folders the library shows (the cloud's own setting, the same on the web and the
// phone), with the phone's uploads offered when they sit outside; the thumbnails kept on the computer.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    property var folders: []
    property string suggest: ""
    property string cache: ""
    width: Math.min(560, parent ? parent.width - 48 : 560)
    tint: theme.c.famMedia
    title: app.t.settings

    onAboutToShow: {
        folders = photos.folders
        suggest = ""
        cache = photos.cacheSize()
        photos.loadFolders()
    }
    Connections {
        target: photos
        function onFoldersReady(data) { dialog.folders = data.folders; dialog.suggest = data.suggest }
    }

    component Heading: Text {
        Layout.topMargin: 6
        font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
        font.capitalization: Font.AllUppercase; font.letterSpacing: 0.8
        color: theme.c.muted
    }

    Heading { text: app.t.settings_folders }
    Text {
        Layout.fillWidth: true
        text: app.t.settings_folders_lead
        wrapMode: Text.WordWrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: theme.c.muted
    }
    Repeater {
        model: dialog.folders
        RowLayout {
            required property string modelData
            Layout.fillWidth: true
            spacing: 10
            Icon { name: "folder"; size: 18; color: theme.c.famMedia }
            Text { Layout.fillWidth: true; text: modelData; font.family: "JetBrains Mono"; font.pixelSize: 13; color: theme.c.text; elide: Text.ElideMiddle }
            OButton {
                visible: dialog.folders.length > 1
                kind: "quiet"; implicitWidth: 30; height_: 30; iconName: "close"; tip: app.t.settings_folder_remove
                onClicked: photos.setFolders(dialog.folders.filter(f => f !== modelData))
            }
        }
    }
    Surface {
        visible: dialog.suggest !== ""
        Layout.fillWidth: true
        implicitHeight: phoneRow.implicitHeight + 24
        radius: 10
        RowLayout {
            id: phoneRow
            anchors.fill: parent; anchors.margins: 12
            spacing: 12
            Icon { name: "phone"; size: 20; color: theme.c.famMedia }
            Text {
                Layout.fillWidth: true
                text: app.t.settings_phone.replace("%1", dialog.suggest)
                wrapMode: Text.WordWrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 14
                color: theme.c.text
            }
            OButton { kind: "primary"; text: app.t.settings_phone_add; onClicked: photos.setFolders(dialog.folders.concat([dialog.suggest])) }
        }
    }
    OButton {
        kind: "quiet"; iconName: "openExternal"; text: app.t.settings_folders_cloud
        onClicked: app.openCloud("/apps/memories/")
    }

    Heading { text: app.t.settings_cache }
    RowLayout {
        Layout.fillWidth: true
        spacing: 10
        Text {
            Layout.fillWidth: true
            text: app.t.settings_cache_lead.replace("%1", dialog.cache)
            wrapMode: Text.WordWrap
            font.family: "Schibsted Grotesk"; font.pixelSize: 14
            color: theme.c.muted
        }
        OButton { text: app.t.settings_cache_clear; onClicked: { photos.clearCache(); dialog.cache = photos.cacheSize() } }
    }

    footer: [
        Item { Layout.fillWidth: true },
        OButton { kind: "primary"; text: app.t.done; onClicked: dialog.close() }
    ]
}
