// Add people to the open conversation: accounts, groups, teams, email addresses (Plume's contacts too).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    title: app.t.add_people
    tint: theme.c.famCommunicate
    readonly property var c: theme.c

    function start() {
        search.text = ""
        meet.searchPeople("")
        open()
        search.forceActiveFocus()
    }

    OTextField {
        id: search
        Layout.fillWidth: true
        Layout.leftMargin: 22; Layout.rightMargin: 22
        iconName: "search"
        placeholderText: app.t.search_people
        onTextChanged: timer.restart()
        Timer { id: timer; interval: 250; onTriggered: meet.searchPeople(search.text) }
    }
    ListView {
        Layout.fillWidth: true
        Layout.preferredHeight: Math.min(300, contentHeight)
        Layout.leftMargin: 14; Layout.rightMargin: 14
        clip: true
        model: meet.people
        delegate: AbstractButton {
            id: person
            required property var modelData
            width: ListView.view.width
            implicitHeight: 48
            hoverEnabled: true
            onClicked: { meet.addParticipant(modelData.id, modelData.source); app.toast(app.t.added.replace("%1", modelData.name)) }
            background: Rectangle { radius: 8; color: person.hovered ? dialog.c.hover : "transparent" }
            contentItem: RowLayout {
                spacing: 10
                RoomAvatar { Layout.leftMargin: 8; size: 32; source: person.modelData.avatar; name: person.modelData.name }
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: person.modelData.name + (person.modelData.sub ? "  ·  " + person.modelData.sub : "")
                       elide: Text.ElideRight; font.pixelSize: 14; color: dialog.c.text }
                Icon { name: "plus"; size: 16; color: dialog.c.action; Layout.rightMargin: 8 }
            }
        }
    }
    footer: [OButton { kind: "primary"; text: app.t.done; onClicked: dialog.close() }]
}
