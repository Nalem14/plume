// « Programmer une réunion »: a title, when, how long, the calendar it goes in. From the home it makes the
// conversation too (open by link) with the people chosen; from a conversation (forRoom) it plans that one.
// Talk writes the event with the link of the conversation and invites everyone; the calendars and the phones
// show it, and Meet's home lists it with « Rejoindre ».
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    readonly property var c: theme.c
    property bool forRoom: false
    property var invites: []
    title: forRoom ? app.t.plan_this_meeting : app.t.plan_meeting
    tint: c.famOrganize

    function start(room) {
        forRoom = !!room
        invites = []
        name.text = room ? (meet.room.name || "") : ""
        when.reset(0)
        length.currentIndex = 2
        people.text = ""
        meet.loadHome()
        open()
        name.forceActiveFocus()
    }

    Text { text: app.t.meeting_title; font.pixelSize: 13; font.weight: Font.DemiBold; color: dialog.c.text }
    OTextField {
        id: name
        Layout.fillWidth: true
        placeholderText: app.t.meeting_default
    }
    Text { text: app.t.meeting_when; font.pixelSize: 13; font.weight: Font.DemiBold; color: dialog.c.text }
    WhenPicker { id: when; Layout.fillWidth: true }
    RowLayout {
        Layout.fillWidth: true
        spacing: 12
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6
            Text { text: app.t.meeting_length; font.pixelSize: 13; font.weight: Font.DemiBold; color: dialog.c.text }
            OComboBox {
                id: length
                Layout.fillWidth: true
                model: [15, 30, 45, 60, 90, 120].map(m => ({ text: m < 60 ? m + " min" : (m / 60) + " h" + (m % 60 ? " 30" : ""), value: m }))
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6
            visible: (meet.home.calendars || []).length > 1
            Text { text: app.t.meeting_calendar; font.pixelSize: 13; font.weight: Font.DemiBold; color: dialog.c.text }
            OComboBox {
                id: calendar
                Layout.fillWidth: true
                model: (meet.home.calendars || []).map(cal => ({ text: cal.name, value: cal.uri }))
            }
        }
    }

    // from the home: who to invite (accounts, groups, teams, emails, Plume's contacts)
    Text { visible: !dialog.forRoom; text: app.t.meeting_people; font.pixelSize: 13; font.weight: Font.DemiBold; color: dialog.c.text }
    Flow {
        visible: !dialog.forRoom && dialog.invites.length > 0
        Layout.fillWidth: true
        spacing: 6
        Repeater {
            model: dialog.invites
            AbstractButton {
                id: chip
                required property var modelData
                required property int index
                implicitHeight: 30
                implicitWidth: chipRow.implicitWidth + 18
                onClicked: { const l = dialog.invites.slice(); l.splice(index, 1); dialog.invites = l }
                background: Rectangle { radius: 15; color: dialog.c.tint }
                contentItem: Row {
                    id: chipRow
                    leftPadding: 4
                    spacing: 6
                    RoomAvatar { size: 22; source: chip.modelData.avatar || ""; name: chip.modelData.name; anchors.verticalCenter: parent.verticalCenter }
                    Text { textFormat: Text.PlainText; text: chip.modelData.name; font.pixelSize: 13; color: dialog.c.tintText; anchors.verticalCenter: parent.verticalCenter }
                    Icon { name: "close"; size: 12; color: dialog.c.tintText; anchors.verticalCenter: parent.verticalCenter }
                }
            }
        }
    }
    OTextField {
        id: people
        visible: !dialog.forRoom
        Layout.fillWidth: true
        iconName: "search"
        placeholderText: app.t.search_people
        onTextChanged: searchTimer.restart()
        Timer { id: searchTimer; interval: 250; onTriggered: meet.searchPeople(people.text) }
    }
    Repeater {
        model: !dialog.forRoom && people.text.trim() !== "" ? meet.people.slice(0, 5) : []
        AbstractButton {
            id: person
            required property var modelData
            Layout.fillWidth: true
            implicitHeight: 42
            hoverEnabled: true
            onClicked: {
                if (!dialog.invites.some(p => p.id === modelData.id && p.source === modelData.source))
                    dialog.invites = dialog.invites.concat([modelData])
                people.text = ""
            }
            background: Rectangle { radius: 8; color: person.hovered ? dialog.c.hover : "transparent" }
            contentItem: RowLayout {
                spacing: 10
                RoomAvatar { Layout.leftMargin: 6; size: 28; source: person.modelData.avatar; name: person.modelData.name }
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: person.modelData.name + (person.modelData.sub ? "  ·  " + person.modelData.sub : "")
                       elide: Text.ElideRight; font.pixelSize: 14; color: dialog.c.text }
                Icon { name: "plus"; size: 16; color: dialog.c.action; Layout.rightMargin: 6 }
            }
        }
    }
    Text {
        Layout.fillWidth: true
        text: app.t.meeting_help
        wrapMode: Text.WordWrap
        font.pixelSize: 12; color: dialog.c.muted
    }

    footer: [
        OButton { text: app.t.cancel; onClicked: dialog.close() },
        OButton {
            kind: "primary"; iconName: "calendar"; text: app.t.plan
            onClicked: {
                const start = when.value
                const end = start + (length.currentValue || 60) * 60
                const cal = calendar.currentValue || ""
                if (dialog.forRoom) meet.scheduleMeeting(cal, start, end, name.text.trim(), "")
                else meet.planMeeting(name.text.trim(), start, end, cal, dialog.invites)
                dialog.close()
            }
        }
    ]
}
