// Ctrl+K: one field for everything. Actions first; mail, events and contacts join as the modules arrive.
// The last line always offers to ask Ornis. Arrows move, Enter runs, Escape closes.
import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Layouts

Popup {
    id: cmd
    readonly property var c: theme.c
    signal action(string id)

    property var actions: [
        { id: "new_message", icon: "mail", text: plume.t.new_message, keys: "Ctrl N" },
        { id: "new_event", icon: "calendar", text: plume.t.new_event, keys: "" },
        { id: "new_contact", icon: "contacts", text: plume.t.new_contact, keys: "" },
        { id: "go_mail", icon: "inbox", text: plume.t.go_mail, keys: "Ctrl 1" },
        { id: "go_calendar", icon: "calendar", text: plume.t.go_calendar, keys: "Ctrl 2" },
        { id: "go_contacts", icon: "contacts", text: plume.t.go_contacts, keys: "Ctrl 3" },
        { id: "go_notes", icon: "note", text: plume.t.go_notes, keys: "Ctrl 4", module: "notes" },
        { id: "go_tasks", icon: "checklist", text: plume.t.go_tasks, keys: "Ctrl 5", module: "tasks" },
        { id: "go_passwords", icon: "key", text: plume.t.go_passwords, keys: "Ctrl 6", module: "passwords" },
        { id: "go_ornis", icon: "ornis", text: plume.t.go_ornis, keys: "Ctrl 7", module: "ornis" },
        { id: "go_photos", icon: "image", text: plume.t.go_photos, keys: "Ctrl 9", module: "photos" },
        { id: "apps", icon: "apps", text: plume.t.apps, keys: "" },
        { id: "settings", icon: "settings", text: plume.t.settings, keys: "Ctrl ," },
        { id: "add_box", icon: "plus", text: plume.t.box_add, keys: "", module: "mail" },
        // Ornis: a new conversation (in a mode), Code, Activité (its own conversations come with what is typed)
        { id: "orn:--new", icon: "ornis", text: plume.t.pal_ornis_new, keys: "", module: "ornis", typed: true },
        { id: "orn:--mode=plan", icon: "list", text: plume.t.pal_ornis_plan, keys: "", module: "ornis", typed: true },
        { id: "orn:--mode=goal", icon: "flag", text: plume.t.pal_ornis_goal, keys: "", module: "ornis", typed: true },
        { id: "orn:--mode=research", icon: "search", text: plume.t.pal_ornis_research, keys: "", module: "ornis", typed: true },
        { id: "orn:--code", icon: "code", text: plume.t.pal_ornis_code, keys: "", module: "ornis", typed: true },
        { id: "orn:--scheduled", icon: "repeat", text: plume.t.pal_ornis_activity, keys: "", module: "ornis", typed: true }
    ].filter(a => !a.module || plume.modules.indexOf(a.module) >= 0)
     // Courrier, Agenda, Contacts (Orneos OS): the other two are other apps, no Ctrl+1… there
     .map(a => plume.edition && a.id.indexOf("go_") === 0 ? Object.assign({}, a, { keys: "" }) : a).concat(plume.module === "mail" && mail.current.messageId ? [
        { id: "ornis_summary", icon: "ornis", text: plume.t.ornis + " · " + plume.t.ornis_summarize, keys: "" },
        { id: "ornis_replies", icon: "ornis", text: plume.t.ornis + " · " + plume.t.ornis_replies, keys: "" },
        { id: "ornis_mailEvent", icon: "ornis", text: plume.t.ornis + " · " + plume.t.ornis_find_event, keys: "" }
    ] : [])
    readonly property var results: {
        const q = field.text.trim().toLowerCase()
        // Ornis's own lines: in its module, or once something is typed (the list stays short otherwise)
        const found = actions.filter(a => q ? a.text.toLowerCase().indexOf(q) !== -1 : !a.typed || plume.module === "ornis")
            .concat(suite.ornisPanel ? suite.ornisFind(q).map(r => ({ id: "orn:--session=" + r.id, icon: "chat", text: r.label,
                                                                      sub: plume.t.pal_ornis_chat + " · " + r.when, keys: "" })) : [])
        if (q)
            found.push({ id: "ornis", icon: "ornis", text: plume.t.ask_ornis + " « " + field.text.trim() + " »", keys: "" })
        return found
    }
    property int current: 0

    function run(index) {
        const item = results[index]
        if (!item)
            return
        if (item.id === "ornis")
            plume.askOrnis(field.text)
        else
            cmd.action(item.id)
        close()
    }

    parent: Overlay.overlay
    x: Math.round((parent.width - width) / 2)
    y: 72
    width: Math.min(620, parent.width - 48)
    padding: 0
    modal: true
    focus: true
    onOpened: { field.text = ""; current = 0; field.forceActiveFocus() }
    onResultsChanged: current = 0

    Overlay.modal: Rectangle { color: cmd.c.scrim }
    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 140; easing.type: Easing.OutCubic }
            NumberAnimation { property: "y"; from: 64; to: 72; duration: 140; easing.type: Easing.OutCubic }
        }
    }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 100 } }

    background: Item {
        RectangularShadow {
            anchors.fill: card; radius: card.radius
            blur: 36; offset.y: 14; color: cmd.c.shadow
        }
        Rectangle {
            id: card
            anchors.fill: parent
            radius: 10
            color: cmd.c.overlay
            border.width: 1; border.color: cmd.c.overlayLine
        }
    }

    contentItem: ColumnLayout {
        spacing: 0
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 54
            Layout.leftMargin: 18; Layout.rightMargin: 18
            spacing: 12
            Icon { name: "search"; size: 20; color: cmd.c.muted }
            TextField {
                id: field
                Layout.fillWidth: true
                placeholderText: plume.t.search
                placeholderTextColor: cmd.c.muted
                color: cmd.c.text
                font.family: "Schibsted Grotesk"; font.pixelSize: 17
                background: null
                selectByMouse: true
                Keys.onDownPressed: cmd.current = Math.min(cmd.current + 1, cmd.results.length - 1)
                Keys.onUpPressed: cmd.current = Math.max(cmd.current - 1, 0)
                Keys.onReturnPressed: cmd.run(cmd.current)
                Keys.onEnterPressed: cmd.run(cmd.current)
            }
        }
        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: cmd.c.hairline }
        Text {
            Layout.leftMargin: 18; Layout.topMargin: 12; Layout.bottomMargin: 4
            text: plume.t.palette_actions
            font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold; font.letterSpacing: 0.8
            color: cmd.c.muted
        }
        Repeater {
            model: cmd.results
            delegate: AbstractButton {
                id: row
                required property var modelData
                required property int index
                Layout.fillWidth: true
                Layout.leftMargin: 8; Layout.rightMargin: 8
                implicitHeight: 40
                hoverEnabled: true
                onHoveredChanged: if (hovered) cmd.current = index
                onClicked: cmd.run(index)
                background: Rectangle {
                    radius: 6
                    color: cmd.current === row.index ? cmd.c.tint : "transparent"
                }
                contentItem: RowLayout {
                    spacing: 12
                    Icon {
                        Layout.leftMargin: 10
                        name: row.modelData.icon; size: 18; hovered: cmd.current === row.index
                        color: row.modelData.id === "ornis" || cmd.current === row.index ? cmd.c.accent : cmd.c.muted
                    }
                    Text {
                        Layout.fillWidth: true
                        text: row.modelData.text
                        font.family: "Schibsted Grotesk"; font.pixelSize: 15
                        color: cmd.current === row.index ? cmd.c.tintText : cmd.c.text
                        elide: Text.ElideRight
                    }
                    Text {                  // its keys, or what it is (« Conversation avec Ornis · hier »)
                        Layout.rightMargin: 10
                        visible: text !== ""
                        text: row.modelData.keys || row.modelData.sub || ""
                        font.family: row.modelData.keys ? "JetBrains Mono" : "Schibsted Grotesk"; font.pixelSize: 12
                        color: cmd.c.muted
                    }
                }
            }
        }
        Text {
            visible: cmd.results.length === 0
            Layout.leftMargin: 18; Layout.topMargin: 6
            text: plume.t.palette_none
            font.family: "Schibsted Grotesk"; font.pixelSize: 14
            color: cmd.c.muted
        }
        Item { Layout.preferredHeight: 8 }
    }
}
