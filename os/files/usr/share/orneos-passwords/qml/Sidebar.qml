// The side column: the app's kicker, the search, the categories as cards (SmartCard: a line glyph in the
// category's colour, the count in the data face), the folders, and at the foot the account and the settings
// (AccountBar, the same place in every app).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Rectangle {
    id: side
    readonly property var c: theme.c
    readonly property var counts: vault.counts
    signal toList()
    signal settingsRequested()
    color: c.chrome

    function focusSearch() { search.forceActiveFocus(); search.selectAll() }

    component Tile: SmartCard {
        property string category
        Layout.fillWidth: true
        selected: vault.category === category && vault.query === ""
        onClicked: { vault.setQuery(""); search.text = ""; vault.setCategory(category) }
    }
    component Row_: AbstractButton {
        id: row
        property string category
        property string iconName
        property int count: 0
        property var folder: null
        readonly property bool active: vault.category === category && vault.query === ""
        Layout.fillWidth: true
        implicitHeight: 34
        hoverEnabled: true
        Accessible.name: text
        onClicked: { vault.setQuery(""); search.text = ""; vault.setCategory(category) }
        background: Rectangle {
            radius: 7
            color: row.active ? side.c.card : (row.hovered ? side.c.hover : "transparent")
            Band {
                visible: row.active
                anchors { left: parent.left; top: parent.top; bottom: parent.bottom; topMargin: 8; bottomMargin: 8 }
                radius: 1.5
                color: side.c.famTools
            }
        }
        contentItem: RowLayout {
            spacing: 10
            Icon { Layout.leftMargin: 10; name: row.iconName; size: 18; color: row.active ? side.c.text : side.c.muted }
            Text {
                Layout.fillWidth: true
                text: row.text
                elide: Text.ElideRight
                font.family: "Schibsted Grotesk"; font.pixelSize: 14
                font.weight: row.active ? Font.DemiBold : Font.Normal
                color: side.c.text
            }
            Rectangle {                      // made or renamed here, on its way to the cloud
                visible: !!(row.folder && row.folder.pending)
                implicitWidth: 6; implicitHeight: 6; radius: 3
                color: side.c.saffron
            }
            Text {
                Layout.rightMargin: 10
                text: row.count || ""
                font.family: "JetBrains Mono"; font.pixelSize: 12
                color: side.c.muted
            }
        }
        TapHandler {
            acceptedButtons: Qt.RightButton
            enabled: row.folder !== null
            onTapped: folderMenu.openFor(row.folder, row)
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 14
        anchors.topMargin: 12
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.bottomMargin: 14
            spacing: 10
            Text {
                Layout.fillWidth: true
                Layout.leftMargin: 4; Layout.topMargin: 4
                text: app.t.app_name
                elide: Text.ElideRight
                font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                font.capitalization: Font.AllUppercase; font.letterSpacing: 0.9
                color: theme.dark ? side.c.famTools : side.c.muted
            }
        }

        OTextField {
            id: search
            Layout.fillWidth: true
            Layout.bottomMargin: 14
            iconName: "search"
            placeholderText: app.t.search
            onTextChanged: vault.setQuery(text)
            Keys.onDownPressed: side.toList()
            Keys.onReturnPressed: side.toList()
        }

        GridLayout {
            Layout.fillWidth: true
            columns: 2
            rowSpacing: 8; columnSpacing: 8
            Tile { category: "all"; iconName: "key"; tint: side.c.famCommunicate; text: app.t.cat_all; count: side.counts.all || 0 }
            Tile { category: "codes"; iconName: "clock"; tint: side.c.ok; text: app.t.cat_codes; count: side.counts.codes || 0 }
            Tile {
                category: "security"; iconName: (side.counts.security || 0) ? "warning" : "shieldCheck"
                tint: (side.counts.breached || 0) ? side.c.danger : (side.counts.security || 0) ? side.c.saffronInk : side.c.ok
                text: app.t.cat_security; count: side.counts.security || 0
            }
            Tile {
                visible: app.prefs.show_wifi && wifi.available
                category: "wifi"; iconName: "wifi"; tint: side.c.famMedia; text: app.t.cat_wifi; count: wifi.networks.length
            }
            Tile { category: "favorites"; iconName: "star"; tint: side.c.saffron; text: app.t.cat_favorites; count: side.counts.favorites || 0 }
            Tile { category: "trash"; iconName: "trash"; tint: side.c.muted; text: app.t.cat_trash; count: side.counts.trash || 0 }
        }

        Flickable {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.topMargin: 18
            contentHeight: lower.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            ColumnLayout {
                id: lower
                width: parent.width
                spacing: 2

                Row_ {
                    visible: (side.counts.shared || 0) > 0
                    category: "shared"; iconName: "people"; text: app.t.cat_shared; count: side.counts.shared || 0
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: (side.counts.shared || 0) > 0 ? 14 : 0
                    Layout.bottomMargin: 4
                    Text {
                        Layout.fillWidth: true
                        Layout.leftMargin: 10
                        text: app.t.folders
                        font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                        font.capitalization: Font.AllUppercase; font.letterSpacing: 0.8
                        color: side.c.muted
                    }
                    OButton {
                        kind: "quiet"; implicitWidth: 28; height_: 28; iconSize: 16
                        iconName: "folderPlus"; tip: app.t.folder_new
                        enabled: vault.online
                        onClicked: folderDialog.ask("", "")
                    }
                }
                Repeater {
                    model: vault.folders
                    Row_ {
                        required property var modelData
                        category: "folder:" + modelData.id
                        iconName: "folder"
                        text: modelData.label
                        folder: modelData
                        count: side.counts["folder:" + modelData.id] || 0
                    }
                }
                Text {
                    visible: vault.folders.length === 0
                    Layout.fillWidth: true
                    Layout.leftMargin: 10; Layout.rightMargin: 10
                    text: app.t.folders_none
                    wrapMode: Text.WordWrap
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                    color: side.c.faint
                }
            }
        }

        AccountBar {
            Layout.fillWidth: true
            Layout.topMargin: 6
            Layout.leftMargin: -4; Layout.rightMargin: -4; Layout.bottomMargin: -6
            name: app.profile.name || ""
            email: app.profile.email || ""
            initials: app.profile.initials || ""
            onSettingsRequested: side.settingsRequested()
            OMenuItem { text: app.t.open_cloud; iconName: "cloud"; onTriggered: app.openCloud("/apps/passwords/") }
            OMenuItem { text: app.t.account_security; iconName: "shield"; onTriggered: app.openAccount() }
            OMenuItem { text: app.t.reconnect; iconName: "refresh"; onTriggered: app.openConnect() }
        }
    }
    OMenu {
        id: folderMenu
        property var folder: null
        function openFor(f, item) {
            folder = f
            const p = item.mapToItem(side, item.width - 40, item.height)
            x = p.x; y = p.y
            open()
        }
        OMenuItem { text: app.t.folder_rename; iconName: "edit"; enabled: vault.online && !folderMenu.folder.pending; onTriggered: folderDialog.ask(folderMenu.folder.id, folderMenu.folder.label) }
        OMenuItem { text: app.t.folder_delete; iconName: "trash"; enabled: vault.online && !folderMenu.folder.pending; onTriggered: deleteFolder.ask(app.t.folder_delete_title.replace("%1", folderMenu.folder.label), app.t.folder_delete_text, [{ id: "cancel", text: app.t.cancel }, { id: "yes", text: app.t.folder_delete, kind: "danger" }], () => vault.deleteFolder(folderMenu.folder.id)) }
    }
    ChoiceDialog { id: deleteFolder }

    ODialog {
        id: folderDialog
        property string folderId
        width: Math.min(420, parent ? parent.width - 48 : 420)
        title: folderId ? app.t.folder_rename : app.t.folder_new
        function ask(id, label) {
            folderId = id
            name.text = label
            open()
            name.forceActiveFocus()
            name.selectAll()
        }
        function accept() {
            if (!name.text.trim())
                return
            if (folderId) vault.renameFolder(folderId, name.text)
            else vault.createFolder(name.text)
            close()
        }
        OTextField {
            id: name
            Layout.fillWidth: true
            placeholderText: app.t.folder_name
            onAccepted: folderDialog.accept()
        }
        footer: [
            Item { Layout.fillWidth: true },
            OButton { text: app.t.cancel; onClicked: folderDialog.close() },
            OButton { kind: "primary"; text: folderDialog.folderId ? app.t.save : app.t.create; onClicked: folderDialog.accept() }
        ]
    }
}
