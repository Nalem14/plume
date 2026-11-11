// A project of the Work mode, made or set, as in Claude and ChatGPT: its name, where its files are (a folder of the
// Drive, seen from every device, or a folder of this computer, or none), the instructions Ornis follows in each of its
// conversations, and whether Ornis remembers its other conversations (project memory).
import QtCore as Std               // StandardPaths only: its Settings would hide ours
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "components"

ODialog {
    id: dlg
    property string projectId: ""        // "" : a new project
    property string moveSession: ""      // a conversation to put in the new project (« Nouveau projet… » of a chat)
    property string kind: "drive"        // drive | local | none
    property string drivePath: ""
    property string localPath: ""
    property bool pathEdited: false
    readonly property bool editing: projectId !== ""
    readonly property bool localOk: app.prefs.local_tools !== false
    title: editing ? app.t.project_settings : app.t.project_new_title
    tint: c.famCommunicate
    width: Math.min(600, parent ? parent.width - 48 : 600)

    function create(session) {
        projectId = ""; moveSession = session || ""
        name.text = ""; instructions.text = ""; memory.checked = true
        kind = "drive"; drivePath = ""; localPath = ""; pathEdited = false
        open(); name.forceActiveFocus()
    }
    function edit(p) {
        projectId = p.id; moveSession = ""
        name.text = p.name; instructions.text = p.instructions || ""; memory.checked = p.memory !== false
        kind = p.folder && p.folder.kind ? p.folder.kind : "none"
        drivePath = kind === "drive" ? p.folder.path : ""; localPath = kind === "local" ? p.folder.path : ""
        pathEdited = true
        open(); instructions.forceActiveFocus()
    }
    function defaultDrive() { return "/" + app.t.project_drive_root + "/" + (name.text.trim() || app.t.project_untitled).replace(/\//g, "-") }
    function save() {
        const label = name.text.trim()
        if (!label) { name.forceActiveFocus(); return }
        const where = kind === "drive" ? (drivePath || defaultDrive()) : kind === "local" ? localPath : ""
        const k = kind === "none" || !where ? "" : kind
        if (editing) {
            projects.update(projectId, "name", label)
            projects.update(projectId, "instructions", instructions.text)
            projects.update(projectId, "memory", memory.checked)
            const p = projects.items.find(x => x.id === projectId)
            if (p && (p.folder.kind !== k || p.folder.path !== where)) projects.setFolder(projectId, k, where)
        } else {
            const pid = projects.create(label, k, where, instructions.text)
            if (!memory.checked) projects.update(pid, "memory", false)
            if (moveSession) projects.assign(moveSession, pid)
            win.openProject(pid)
        }
        close()
    }

    OTextField {
        id: name
        Layout.fillWidth: true
        placeholderText: app.t.project_name_hint
        maximumLength: 60
        onAccepted: dlg.save()
    }

    Text {
        Layout.topMargin: 8
        text: app.t.project_files_where
        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
        color: dlg.c.text
    }
    Rectangle {                              // Drive | Cet ordinateur | Aucun
        Layout.fillWidth: true
        implicitHeight: 34
        radius: 10
        color: dlg.c.hover
        RowLayout {
            anchors.fill: parent; anchors.margins: 3
            spacing: 3
            Repeater {
                model: [{ key: "drive", label: app.t.project_where_drive, icon: "cloud" },
                        { key: "local", label: app.t.project_where_local, icon: "devices" },
                        { key: "none", label: app.t.project_where_none, icon: "close" }].filter(o => o.key !== "local" || dlg.localOk)
                AbstractButton {
                    required property var modelData
                    readonly property bool on: dlg.kind === modelData.key
                    Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 1
                    onClicked: dlg.kind = modelData.key
                    Accessible.role: Accessible.RadioButton
                    Accessible.checked: on
                    Accessible.name: modelData.label
                    background: Rectangle { radius: 8; color: parent.on ? dlg.c.card : "transparent" }
                    contentItem: Item {
                        Row {
                            id: seg
                            readonly property bool on: dlg.kind === modelData.key
                            spacing: 6
                            anchors.centerIn: parent
                            Icon { anchors.verticalCenter: parent.verticalCenter; name: modelData.icon; size: 13; color: seg.on ? dlg.c.famCommunicate : dlg.c.muted }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: modelData.label
                                font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: seg.on ? Font.DemiBold : Font.Medium
                                color: seg.on ? dlg.c.text : dlg.c.muted
                            }
                        }
                    }
                }
            }
        }
    }
    RowLayout {
        visible: dlg.kind !== "none"
        Layout.fillWidth: true
        spacing: 8
        Icon { name: dlg.kind === "drive" ? "cloud" : "folder"; size: 16; color: dlg.c.muted }
        Text {
            Layout.fillWidth: true
            text: dlg.kind === "drive" ? (dlg.drivePath || dlg.defaultDrive()) : (dlg.localPath || app.t.project_local_none)
            elide: Text.ElideMiddle
            font.family: "JetBrains Mono"; font.pixelSize: 12
            color: dlg.kind === "local" && !dlg.localPath ? dlg.c.muted : dlg.c.text
        }
        OButton {
            text: app.t.project_choose
            onClicked: dlg.kind === "drive" ? drivePick.openAt(dlg.drivePath ? dlg.drivePath.replace(/\/[^\/]+\/?$/, "") || "/" : "/")
                                            : localPick.open()
        }
    }
    Text {
        Layout.fillWidth: true
        wrapMode: Text.Wrap
        text: dlg.kind === "drive" ? app.t.project_where_drive_lead : dlg.kind === "local" ? app.t.project_where_local_lead : app.t.project_where_none_lead
        font.family: "Schibsted Grotesk"; font.pixelSize: 12
        color: dlg.c.muted
    }

    Text {
        Layout.topMargin: 8
        text: app.t.project_instructions
        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
        color: dlg.c.text
    }
    ScrollView {
        Layout.fillWidth: true
        Layout.preferredHeight: 150
        OTextArea {
            id: instructions
            placeholderText: app.t.project_instructions_hint
            font.pixelSize: 14
            onTextChanged: if (length > 4000) remove(4000, length)
        }
    }
    Text {
        Layout.alignment: Qt.AlignRight
        text: instructions.length + " / 4000"
        font.family: "JetBrains Mono"; font.pixelSize: 11
        color: dlg.c.muted
    }
    OSwitch {
        id: memory
        Layout.fillWidth: true
        text: app.t.project_memory
    }
    Text {
        Layout.fillWidth: true
        Layout.leftMargin: 46
        wrapMode: Text.Wrap
        text: app.t.project_memory_lead
        font.family: "Schibsted Grotesk"; font.pixelSize: 12
        color: dlg.c.muted
    }

    footer: [
        Item { Layout.fillWidth: true },
        OButton { text: app.t.cancel; onClicked: dlg.close() },
        OButton { kind: "primary"; text: dlg.editing ? app.t.save : app.t.project_create; enabled: name.text.trim() !== "" && (dlg.kind !== "local" || dlg.localPath !== ""); onClicked: dlg.save() }
    ]

    DrivePicker {
        id: drivePick
        folderMode: true
        onFolderPicked: path => { dlg.drivePath = path === "/" ? "" : path }
    }
    FolderDialog {
        id: localPick
        currentFolder: Std.StandardPaths.writableLocation(Std.StandardPaths.HomeLocation)
        title: app.t.project_where_local
        onAccepted: dlg.localPath = app.localPath(selectedFolder)
    }
}
