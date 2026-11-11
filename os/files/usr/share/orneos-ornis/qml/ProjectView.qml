// A project's page, as in ChatGPT and Claude: its name and folder, a box to start a conversation in it, its
// instructions and files side by side (files dropped here go into its folder), and its conversations.
import QtCore as Std               // StandardPaths only: its Settings would hide ours
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "components"

Rectangle {
    id: page
    readonly property var c: theme.c
    readonly property var p: projects.current
    readonly property var tones: [c.famCommunicate, c.famDocs, c.famOrganize, c.famMedia, c.famSpace, c.famTools]
    readonly property var chats: p.id ? chat.allSessions.filter(s => s.project === p.id) : []
    readonly property int column: Math.min(780, width - 48)
    signal settingsRequested(var project)
    signal menuRequested(var session, Item item, real x, real y)
    color: c.bg

    function focusInput() { ask.forceActiveFocus() }
    function start() {
        const text = ask.text.trim()
        projects.newChat(p.id)
        win.view = "chat"
        if (text) { chat.send(text); ask.text = "" }
        else conversation.focusInput()
    }

    // the page's header, as the conversation's: the sidebar's buttons when it is hidden
    RowLayout {
        id: top
        anchors { left: parent.left; right: parent.right; top: parent.top; leftMargin: win.sidebarShown ? 20 : 10; rightMargin: 12 }
        height: 52
        spacing: 6
        OButton { visible: !win.sidebarShown; kind: "quiet"; iconName: "sidebar"; tip: app.t.show_sidebar + "  (Ctrl+B)"; onClicked: win.toggleSidebar() }
        OButton { visible: !win.sidebarShown; kind: "quiet"; iconName: "compose"; tip: app.t.new_discussion + "  (Ctrl+N)"; onClicked: win.newChat() }
        Item { Layout.fillWidth: true }
        OButton {
            visible: !!page.p.folder && page.p.folder.kind !== "" && (page.p.folder.kind === "drive" || page.p.folderHere)
            kind: "quiet"; iconName: "folder"; text: win.wide ? app.t.project_open_folder : ""; tip: app.t.project_open_folder
            onClicked: projects.openFolder(page.p.id)
        }
        OButton { kind: "quiet"; iconName: "settings"; tip: app.t.project_settings; onClicked: page.settingsRequested(page.p) }
        OButton {
            id: more
            kind: "quiet"; iconName: "more"; tip: app.t.more
            onClicked: { const at = more.mapToItem(page, 0, more.height + 4); menu.x = Math.min(at.x, page.width - menu.implicitWidth - 8); menu.y = at.y; menu.open() }
        }
    }

    ScrollView {
        id: scroll
        anchors { left: parent.left; right: parent.right; top: top.bottom; bottom: parent.bottom }
        contentWidth: availableWidth
        clip: true
        ColumnLayout {
            x: (scroll.availableWidth - page.column) / 2
            width: page.column
            spacing: 18

            RowLayout {                      // the project itself
                Layout.topMargin: 18
                spacing: 14
                Rectangle {
                    implicitWidth: 48; implicitHeight: 48; radius: 13
                    color: page.tones[page.p.tone || 0]
                    Text { anchors.centerIn: parent; text: page.p.initial || "?"; font.family: "Schibsted Grotesk"; font.pixelSize: 22; font.weight: Font.Bold; color: "white" }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Text {
                        Layout.fillWidth: true
                        text: page.p.name || ""
                        elide: Text.ElideRight
                        font.family: "Schibsted Grotesk"; font.pixelSize: 26; font.weight: Font.DemiBold
                        color: page.c.text
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: text !== ""
                        text: page.p.folderSub || ""
                        elide: Text.ElideMiddle
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13
                        color: page.p.folderMissing ? page.c.saffronInk : page.c.muted
                    }
                }
            }

            Surface {                        // a new conversation in the project
                Layout.fillWidth: true
                implicitHeight: askRow.implicitHeight + 20
                radius: 18
                RowLayout {
                    id: askRow
                    anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; leftMargin: 14; rightMargin: 10 }
                    spacing: 8
                    TextArea {
                        id: ask
                        Layout.fillWidth: true
                        placeholderText: app.t.project_ask.replace("%1", page.p.name || "")
                        placeholderTextColor: page.c.muted
                        color: page.c.text
                        wrapMode: TextEdit.Wrap
                        font.family: "Schibsted Grotesk"; font.pixelSize: 15
                        background: null
                        Keys.onReturnPressed: event => {
                            if (event.modifiers & Qt.ShiftModifier) event.accepted = false
                            else page.start()
                        }
                    }
                    OButton {
                        kind: "primary"; iconName: ask.text.trim() ? "send" : "compose"
                        tip: ask.text.trim() ? app.t.send : app.t.project_new_chat
                        onClicked: page.start()
                    }
                }
            }

            GridLayout {                     // instructions | files
                Layout.fillWidth: true
                columns: page.column > 620 ? 2 : 1
                columnSpacing: 14; rowSpacing: 14

                Surface {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    Layout.alignment: Qt.AlignTop
                    implicitHeight: instr.implicitHeight + 28
                    ColumnLayout {
                        id: instr
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 14 }
                        spacing: 8
                        RowLayout {
                            Layout.fillWidth: true
                            Icon { name: "note"; size: 15; color: page.c.famCommunicate }
                            Text { Layout.fillWidth: true; text: app.t.project_instructions; font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold; color: page.c.text }
                            OButton { kind: "quiet"; text: page.p.instructions ? app.t.edit : app.t.add; height_: 26; onClicked: page.settingsRequested(page.p) }
                        }
                        Text {
                            Layout.fillWidth: true
                            text: page.p.instructions || app.t.project_instructions_empty
                            wrapMode: Text.Wrap
                            maximumLineCount: 6
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13
                            color: page.p.instructions ? page.c.text : page.c.muted
                        }
                        Text {
                            Layout.fillWidth: true
                            text: page.p.memory !== false ? app.t.project_memory_on : app.t.project_memory_off
                            wrapMode: Text.Wrap
                            font.family: "Schibsted Grotesk"; font.pixelSize: 12
                            color: page.c.muted
                        }
                    }
                }

                Surface {
                    id: filesCard
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    Layout.alignment: Qt.AlignTop
                    implicitHeight: filesCol.implicitHeight + 28
                    color: drop.containsDrag ? page.c.tint : page.c.card
                    ColumnLayout {
                        id: filesCol
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 14 }
                        spacing: 6
                        RowLayout {
                            Layout.fillWidth: true
                            Icon { name: "folder"; size: 15; color: page.c.famCommunicate }
                            Text { Layout.fillWidth: true; text: app.t.project_files; font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold; color: page.c.text }
                            OButton {
                                visible: !!page.p.folder && page.p.folder.kind !== "" && projects.filesState !== "elsewhere"
                                kind: "quiet"; iconName: "plus"; height_: 26; tip: app.t.project_add_files
                                onClicked: filePick.open()
                            }
                        }
                        Repeater {
                            model: projects.files.slice(0, 8)
                            AbstractButton {
                                required property var modelData
                                Layout.fillWidth: true
                                implicitHeight: 28
                                hoverEnabled: true
                                onClicked: modelData.folder ? projects.openFolder(page.p.id) : projects.openFile(modelData)
                                Accessible.name: modelData.name
                                background: Rectangle { radius: 6; color: parent.hovered ? page.c.hover : "transparent" }
                                contentItem: RowLayout {
                                    spacing: 8
                                    Icon { Layout.leftMargin: 4; name: modelData.folder ? "folder" : /\.pdf$/i.test(modelData.name) ? "pdf" : "note"; size: 14; color: page.c.muted }
                                    Text { Layout.fillWidth: true; text: modelData.name; elide: Text.ElideMiddle; font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: page.c.text }
                                }
                            }
                        }
                        Text {
                            visible: projects.files.length > 8
                            text: app.t.project_files_more.replace("%1", projects.files.length - 8)
                            font.family: "Schibsted Grotesk"; font.pixelSize: 12
                            color: page.c.muted
                        }
                        Text {
                            Layout.fillWidth: true
                            visible: projects.files.length === 0
                            wrapMode: Text.Wrap
                            text: !page.p.folder || page.p.folder.kind === "" ? app.t.project_files_none
                                : projects.filesState === "loading" ? app.t.loading
                                : projects.filesState === "elsewhere" ? page.p.folderSub
                                : projects.filesState === "missing" ? app.t.project_folder_missing
                                : projects.filesState === "offline" ? app.t.offline
                                : projects.filesState ? app.t.attach_failed : app.t.project_files_empty
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13
                            color: page.c.muted
                        }
                        OButton {
                            visible: !page.p.folder || page.p.folder.kind === ""
                            text: app.t.project_choose_folder
                            onClicked: page.settingsRequested(page.p)
                        }
                    }
                    DropArea {
                        id: drop
                        anchors.fill: parent
                        keys: ["text/uri-list"]
                        onDropped: d => { if (d.hasUrls) projects.addFiles(d.urls) }
                    }
                }
            }

            Text {
                Layout.topMargin: 6
                text: app.t.project_chats_title
                font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold
                color: page.c.muted
            }
            Text {
                visible: page.chats.length === 0
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                text: app.t.project_chats_empty
                font.family: "Schibsted Grotesk"; font.pixelSize: 14
                color: page.c.muted
            }
            ColumnLayout {
                Layout.fillWidth: true
                Layout.bottomMargin: 32
                spacing: 0
                Repeater {
                    model: page.chats
                    AbstractButton {
                        id: chatRow
                        required property var modelData
                        Layout.fillWidth: true
                        implicitHeight: 52
                        hoverEnabled: true
                        onClicked: win.openChat(modelData.id)
                        Accessible.name: modelData.label
                        TapHandler { acceptedButtons: Qt.RightButton; onTapped: e => page.menuRequested(chatRow.modelData, chatRow, e.position.x, e.position.y) }
                        background: Rectangle {
                            radius: 8
                            color: chatRow.hovered ? page.c.hover : "transparent"
                            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: page.c.hairline }
                        }
                        contentItem: RowLayout {
                            spacing: 10
                            Text {
                                Layout.leftMargin: 10
                                Layout.fillWidth: true
                                text: chatRow.modelData.label
                                elide: Text.ElideRight
                                font.family: "Schibsted Grotesk"; font.pixelSize: 15
                                font.weight: chatRow.modelData.unread ? Font.DemiBold : Font.Normal
                                color: page.c.text
                            }
                            Rectangle { visible: (chatRow.modelData.unread || 0) > 0; implicitWidth: 8; implicitHeight: 8; radius: 4; color: page.c.action }
                            Text {
                                text: chatRow.modelData.when || ""
                                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                                color: page.c.muted
                            }
                            OButton {
                                visible: chatRow.hovered
                                kind: "quiet"; iconName: "more"; iconSize: 16; height_: 26; tip: app.t.more
                                onClicked: page.menuRequested(chatRow.modelData, this, 0, height + 4)
                            }
                        }
                    }
                }
            }
        }
    }

    OMenu {
        id: menu
        OMenuItem { text: app.t.project_new_chat; iconName: "compose"; onTriggered: page.start() }
        OMenuItem { text: app.t.project_settings; iconName: "settings"; onTriggered: page.settingsRequested(page.p) }
        OMenuItem {
            visible: !!page.p.folder && (page.p.folder.kind === "drive" || page.p.folderHere)
            text: app.t.project_open_folder; iconName: "folder"; onTriggered: projects.openFolder(page.p.id)
        }
        Rectangle { width: parent ? parent.width : 0; height: 1; color: page.c.hairline }
        OMenuItem { text: app.t.project_delete; iconName: "trash"; onTriggered: win.deleteProject(page.p) }
    }
    FileDialog {
        id: filePick
        currentFolder: Std.StandardPaths.writableLocation(Std.StandardPaths.HomeLocation)
        title: app.t.project_add_files
        fileMode: FileDialog.OpenFiles
        onAccepted: projects.addFiles(selectedFiles)
    }
}
