// Create or edit a Code-mode bot: face, title, description, folder, SOUL, skills.
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "components"

ODialog {
    id: dlg
    property string botId: ""
    property bool creating: botId === ""
    title: creating ? app.t.bots_new : app.t.bots_edit
    width: Math.min(560, Overlay.overlay ? Overlay.overlay.width - 48 : 560)
    height: Math.min(640, Overlay.overlay ? Overlay.overlay.height - 48 : 640)

    property string shape: "hexagon"
    property string color: "#7C5CFF"
    property bool lockFace: false
    property bool advanced: false

    function randomizeFace() {
        const f = bots.randomFace()
        shape = f.shape; color = f.color
        lockFace = true   // keep this look until the person picks another
    }
    function openNew() {
        botId = ""; titleField.text = ""; badgeField.text = ""; descField.text = ""; folderField.text = ""
        soulField.text = ""
        idField.text = Qt.binding(() => dlg.slug(titleField.text))
        // the face follows the name as it is typed, until a shape, a colour or a model is chosen
        const f = bots.faceFor("bot"); shape = f.shape; color = f.color; lockFace = false
        advanced = false
        skillList.model = bots.skills("")
        open()
        titleField.forceActiveFocus()
    }
    // « Équipe Rédac » → equipe-redac (accents kept as letters, as the groups)
    function slug(text) {
        return String(text || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase()
               .replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40)
    }
    function useTemplate(t) {
        titleField.text = t.title; descField.text = t.description; soulField.text = t.soul
        shape = t.face.shape; color = t.face.color; lockFace = true
        advanced = true
    }
    function openEdit(id) {
        botId = id
        const row = bots.list.concat(bots.hidden).find(b => b.id === id) || bots.current
        titleField.text = (row && row.title) || id
        descField.text = (row && row.description) || ""
        badgeField.text = (row && row.badge) || ""
        folderField.text = (row && row.folder) || ""
        soulField.text = bots.soul(id)
        const f = (row && row.face) || {}
        shape = f.shape || "hexagon"; color = f.color || "#7C5CFF"; lockFace = !!f.locked
        advanced = false
        skillList.model = bots.skills(id)
        open()
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 14
        BotFace { face: ({ shape: dlg.shape, color: dlg.color }); size: 52 }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 4
            Text {
                text: creating ? app.t.bots_new_sub : app.t.bots_edit_sub.replace("%1", titleField.text || botId)
                wrapMode: Text.Wrap; Layout.fillWidth: true
                font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: theme.c.muted
            }
        }
    }

    Flow {                               // starting points: a role, a face and a SOUL, all editable
        visible: dlg.creating
        Layout.fillWidth: true
        spacing: 6
        Repeater {
            model: dlg.creating ? bots.templates() : []
            AbstractButton {
                id: tpl
                required property var modelData
                implicitHeight: 30
                implicitWidth: tplRow.implicitWidth + 18
                hoverEnabled: true
                onClicked: dlg.useTemplate(modelData)
                Accessible.name: modelData.title + ", " + modelData.description
                ToolTip.text: modelData.description; ToolTip.delay: 400; ToolTip.visible: hovered
                background: Rectangle { radius: 15; color: tpl.hovered ? theme.c.hover : "transparent"
                                        border.width: 1; border.color: titleField.text === tpl.modelData.title ? theme.c.accentLine : theme.c.line }
                contentItem: Item {
                    Row {
                        id: tplRow
                        anchors.centerIn: parent
                        spacing: 6
                        BotFace { anchors.verticalCenter: parent.verticalCenter; face: tpl.modelData.face; size: 16 }
                        Text { anchors.verticalCenter: parent.verticalCenter; text: tpl.modelData.title
                               font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.Medium; color: theme.c.text }
                    }
                }
            }
        }
    }

    RowLayout {
        Layout.fillWidth: true
        Text {
            Layout.fillWidth: true
            text: app.t.bots_face
            font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold; color: theme.c.muted
        }
        OButton {
            kind: "quiet"; iconName: "dice"; iconSize: 15; height_: 26
            tip: app.t.bots_face_random
            onClicked: dlg.randomizeFace()
        }
    }
    Flow {
        Layout.fillWidth: true
        spacing: 6
        Repeater {
            model: bots.shapes()
            Rectangle {
                required property string modelData
                width: 34; height: 34; radius: 8
                color: "transparent"
                border.width: dlg.shape === modelData ? 2 : 1
                border.color: dlg.shape === modelData ? theme.c.saffron : theme.c.line
                BotFace {
                    anchors.centerIn: parent
                    face: ({ shape: modelData, color: dlg.color }); size: 26
                }
                MouseArea { anchors.fill: parent; onClicked: { dlg.shape = modelData; dlg.lockFace = true } }
            }
        }
    }
    Flow {
        Layout.fillWidth: true
        spacing: 6
        Repeater {
            model: bots.colors()
            Rectangle {
                required property string modelData
                width: 22; height: 22; radius: 11
                color: modelData
                border.width: dlg.color === modelData ? 3 : 0
                border.color: theme.c.text            // the chosen one: a ring that shows on both themes
                MouseArea { anchors.fill: parent; onClicked: { dlg.color = modelData; dlg.lockFace = true } }
            }
        }
    }

    OTextField {
        id: titleField
        Layout.fillWidth: true
        placeholderText: app.t.bots_title_ph
        onTextChanged: if (!dlg.lockFace && creating) {
            const f = bots.faceFor(text || "bot"); dlg.shape = f.shape; dlg.color = f.color
        }
    }
    OTextField {                               // « Secrétaire »: shown as a badge next to the name
        id: badgeField
        Layout.fillWidth: true
        maximumLength: 30
        placeholderText: app.t.bots_badge_ph
    }
    OTextField {
        id: idField
        visible: creating
        Layout.fillWidth: true
        placeholderText: app.t.bots_id_ph
        text: dlg.slug(titleField.text)
    }
    OTextArea {
        id: descField
        Layout.fillWidth: true
        Layout.preferredHeight: Math.max(72, implicitHeight)     // grows with the role: the dialog scrolls, never the text cut
        placeholderText: app.t.bots_desc_ph
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: 8
        OTextField {
            id: folderField
            Layout.fillWidth: true
            placeholderText: app.t.bots_folder_ph
        }
        OButton {
            kind: "quiet"; iconName: "folder"; iconSize: 15; height_: 34
            tip: app.t.bots_folder_pick
            onClicked: folderPick.open()
        }
        OButton {
            visible: folderField.text !== ""
            kind: "quiet"; iconName: "close"; iconSize: 14; height_: 34
            tip: app.t.bots_folder_clear
            onClicked: folderField.text = ""
        }
    }
    FolderDialog {
        id: folderPick
        title: app.t.bots_folder_pick
        currentFolder: folderField.text ? "file://" + folderField.text : ""
        onAccepted: folderField.text = app.localPath(selectedFolder)
    }

    AbstractButton {
        Layout.fillWidth: true
        implicitHeight: 36
        onClicked: dlg.advanced = !dlg.advanced
        contentItem: Text {
            text: (dlg.advanced ? "▾ " : "▸ ") + app.t.bots_advanced
            font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.Medium
            color: theme.c.accent; verticalAlignment: Text.AlignVCenter
        }
    }
    ColumnLayout {
        visible: dlg.advanced
        Layout.fillWidth: true
        spacing: 8
        Text {
            text: "SOUL.md"
            font.family: "JetBrains Mono"; font.pixelSize: 11; color: theme.c.muted
        }
        OTextArea {
            id: soulField
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(140, implicitHeight)
            font.family: "JetBrains Mono"; font.pixelSize: 12
        }
        Text {
            text: app.t.bots_skills
            font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold; color: theme.c.muted
        }
        ListView {
            id: skillList
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(140, contentHeight)
            clip: true
            model: []
            delegate: RowLayout {
                required property var modelData
                width: skillList.width
                spacing: 8
                OSwitch {
                    visible: !modelData.owned
                    checked: modelData.on
                    onToggled: {
                        skillList.model = skillList.model.map(s => Object.assign({}, s,
                            s.name === modelData.name ? { on: checked } : {}))
                    }
                }
                Text {
                    Layout.fillWidth: true
                    text: modelData.name + (modelData.owned ? " · " + app.t.bots_skill_owned : "")
                    elide: Text.ElideRight
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: theme.c.text
                }
            }
        }
        OButton {
            visible: !creating
            kind: "quiet"
            text: app.t.bots_open_memory
            onClicked: {
                const path = bots.memoryPath(botId)
                if (path) app.openFolder(path)
            }
        }
    }

    footer: [
        Item { Layout.fillWidth: true },
        OButton { kind: "quiet"; text: app.t.cancel; onClicked: dlg.close() },
        OButton {
            kind: "primary"
            text: creating ? app.t.bots_create : app.t.save
            onClicked: {
                if (creating) {
                    const id = dlg.slug(idField.text || titleField.text)
                    const created = bots.create(id, titleField.text, descField.text, folderField.text)
                    if (created && created.id) {
                        if (soulField.text.trim()) bots.setSoul(created.id, soulField.text)
                        // a face chosen (or a model's) is kept; one from the name follows a later rename
                        const fields = { enabled_skills: skillList.model.filter(s => !s.owned && s.on).map(s => s.name),
                                         badge: badgeField.text }
                        if (dlg.lockFace) Object.assign(fields, { shape: dlg.shape, color: dlg.color, lock_face: true })
                        bots.update(created.id, fields)
                        dlg.close()
                    }
                } else {
                    const saved = bots.update(botId, {
                        title: titleField.text, badge: badgeField.text, description: descField.text, folder: folderField.text,
                        shape: dlg.shape, color: dlg.color, lock_face: dlg.lockFace,
                        enabled_skills: skillList.model.filter(s => !s.owned && s.on).map(s => s.name)
                    })
                    if (!saved || !saved.id) return
                    bots.setSoul(botId, soulField.text)
                    dlg.close()
                }
            }
        }
    ]
}
