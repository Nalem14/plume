// A new conversation: someone (one-to-one, the conversation with them opens if it exists), or several people,
// groups, teams and email addresses together (a group, named), possibly open to anyone with the link. The
// people come from the cloud and from Plume's contacts.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    title: app.t.new_conversation
    tint: theme.c.famCommunicate
    readonly property var c: theme.c
    property var chosen: []

    function start() {
        chosen = []
        search.text = ""
        name.text = ""
        publicLink.checked = false
        meet.searchPeople("")
        open()
        search.forceActiveFocus()
    }
    function toggle(p) {
        const i = chosen.findIndex(x => x.id === p.id && x.source === p.source)
        const list = chosen.slice()
        if (i >= 0) list.splice(i, 1); else list.push(p)
        chosen = list
        search.text = ""
        search.forceActiveFocus()
    }
    function create() {
        if (chosen.length === 1 && chosen[0].source === "users" && !name.text.trim() && !publicLink.checked)
            meet.openWith(chosen[0].id)
        else
            meet.create("group", name.text.trim() || chosen.map(p => p.name).join(", ") || app.t.untitled_conversation,
                        chosen, publicLink.checked)
        close()
    }

    Flow {
        visible: dialog.chosen.length > 0
        Layout.fillWidth: true
        Layout.leftMargin: 22; Layout.rightMargin: 22
        spacing: 6
        Repeater {
            model: dialog.chosen
            AbstractButton {
                required property var modelData
                implicitHeight: 30
                implicitWidth: chipText.implicitWidth + 36
                onClicked: dialog.toggle(modelData)
                background: Rectangle { radius: 15; color: dialog.c.tint }
                contentItem: RowLayout {
                    spacing: 4
                    Text { textFormat: Text.PlainText; id: chipText; Layout.leftMargin: 12; text: parent.parent.modelData.name; font.pixelSize: 13; color: dialog.c.tintText }
                    Icon { name: "close"; size: 12; color: dialog.c.tintText }
                }
            }
        }
    }
    OTextField {
        id: search
        Layout.fillWidth: true
        Layout.leftMargin: 22; Layout.rightMargin: 22
        iconName: "search"
        placeholderText: app.t.search_people
        onTextChanged: searchTimer.restart()
        Keys.onReturnPressed: if (meet.people.length) dialog.toggle(meet.people[0])
        Timer { id: searchTimer; interval: 250; onTriggered: meet.searchPeople(search.text) }
    }
    ListView {
        Layout.fillWidth: true
        Layout.preferredHeight: Math.min(260, contentHeight)
        Layout.leftMargin: 14; Layout.rightMargin: 14
        clip: true
        model: meet.people
        delegate: AbstractButton {
            id: person
            required property var modelData
            readonly property bool picked: dialog.chosen.some(x => x.id === modelData.id && x.source === modelData.source)
            width: ListView.view.width
            implicitHeight: 48
            hoverEnabled: true
            onClicked: dialog.toggle(modelData)
            background: Rectangle { radius: 8; color: person.hovered ? dialog.c.hover : "transparent" }
            contentItem: RowLayout {
                spacing: 10
                RoomAvatar { Layout.leftMargin: 8; size: 32; source: person.modelData.avatar; name: person.modelData.name; status: person.modelData.status }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: person.modelData.name; elide: Text.ElideRight; font.pixelSize: 14; color: dialog.c.text }
                    Text { textFormat: Text.PlainText;
                        Layout.fillWidth: true
                        text: person.modelData.source === "groups" ? app.t.source_group : (person.modelData.source === "circles" ? app.t.source_team
                              : (person.modelData.source === "emails" ? app.t.source_email + " · " + person.modelData.sub : person.modelData.sub))
                        visible: text !== ""
                        elide: Text.ElideRight; font.pixelSize: 12; color: dialog.c.muted
                    }
                }
                Icon { visible: person.picked; name: "check"; size: 18; color: dialog.c.action; Layout.rightMargin: 8 }
            }
        }
    }
    Text {
        visible: search.text.length > 1 && meet.people.length === 0
        Layout.leftMargin: 22
        text: app.t.no_people
        font.pixelSize: 13; color: dialog.c.muted
    }
    OTextField {
        id: name
        visible: dialog.chosen.length > 1 || publicLink.checked || dialog.chosen.some(p => p.source !== "users")
        Layout.fillWidth: true
        Layout.leftMargin: 22; Layout.rightMargin: 22
        placeholderText: app.t.conversation_name
    }
    RowLayout {
        Layout.leftMargin: 22; Layout.rightMargin: 22
        OSwitch { id: publicLink }
        ColumnLayout {
            spacing: 0
            Layout.fillWidth: true
            Text { text: app.t.public_link; color: dialog.c.text; font.pixelSize: 14 }
            Text { text: app.t.public_link_lead; color: dialog.c.muted; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
        }
    }
    footer: [
        OButton { text: app.t.note_to_self; kind: "quiet"; onClicked: { meet.create("note", app.t.note_to_self, [], false); dialog.close() } },
        OButton { text: app.t.cancel; onClicked: dialog.close() },
        OButton {
            kind: "primary"
            text: dialog.chosen.length === 1 && dialog.chosen[0].source === "users" && !publicLink.checked ? app.t.start_chat : app.t.create
            enabled: dialog.chosen.length > 0 || (publicLink.checked && name.text.trim() !== "")
            onClicked: dialog.create()
        }
    ]
}
