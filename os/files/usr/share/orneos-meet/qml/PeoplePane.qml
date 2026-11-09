// The tab « Participants » of a group, in place of the chat: who is there, searched by name or address, filtered
// by presence (online, in the call, offline), by role in sections (owner and moderators, members, guests, groups
// and teams). Each person: their status and its message, their role, the call; write to them privately in a
// click, the rest (moderator, permissions, remove, ban) in their menu. Moderators add people and see the banned.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Rectangle {
    id: people
    readonly property var c: theme.c
    color: c.bg
    property string presence: ""        // "", online, call, offline
    function focusSearch() { search.forceActiveFocus(); search.selectAll() }

    function online(p) { return p.status === "online" || p.status === "away" || p.status === "dnd" || p.status === "busy" || p.inCall > 0 || p.self }
    function presenceText(p) {
        if (p.inCall > 0) return app.t.people_in_call
        if (p.self) return app.t.status_online
        return ({ online: app.t.status_online, away: app.t.status_away, dnd: app.t.status_dnd, busy: app.t.status_busy })[p.status] || (p.status ? app.t.offline : "")
    }
    readonly property var all: meet.participants || []
    readonly property var counts: ({
        "": all.length,
        online: all.filter(p => !p.group && online(p)).length,
        call: all.filter(p => p.inCall > 0).length,
        offline: all.filter(p => !p.group && !online(p)).length
    })
    readonly property var shown: {
        const q = search.text.trim().toLowerCase()
        return all.filter(p => (!q || (p.name + " " + (p.address || "") + " " + p.actorId).toLowerCase().indexOf(q) >= 0)
                           && (presence === "" || (presence === "call" ? p.inCall > 0 : presence === "online" ? !p.group && online(p) : !p.group && !online(p))))
    }
    // sections by role, each one in the order of the cloud's list (ourselves, the call, then by name)
    readonly property var rows: {
        const groups = [["people_mods", p => p.moderator], ["people_members", p => !p.moderator && !p.guest && !p.email && !p.group],
                        ["people_guests", p => !p.moderator && (p.guest || p.email)], ["people_groups", p => p.group]]
        const out = []
        for (const [key, test] of groups) {
            const part = shown.filter(test)
            if (!part.length) continue
            out.push({ heading: app.t[key], count: part.length })
            for (const p of part) out.push(p)
        }
        return out
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: 24; anchors.rightMargin: 24; anchors.topMargin: 16
        spacing: 12

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            OTextField {
                id: search
                Layout.fillWidth: true
                iconName: "search"
                placeholderText: app.t.rs_find_person
                Keys.onEscapePressed: text = ""
            }
            OButton {
                visible: !!(meet.room.moderator && meet.room.type !== 1)
                kind: "primary"; iconName: "plus"
                text: app.t.add_people
                onClicked: addPeople.start()
            }
        }

        Flow {
            Layout.fillWidth: true
            spacing: 6
            Repeater {
                model: [{ id: "", text: app.t.anyone }, { id: "online", text: app.t.people_online },
                        { id: "call", text: app.t.people_in_call }, { id: "offline", text: app.t.people_offline }]
                AbstractButton {
                    id: chip
                    required property var modelData
                    readonly property bool on: people.presence === modelData.id
                    visible: modelData.id !== "call" || people.counts.call > 0
                    implicitHeight: 30
                    implicitWidth: chipRow.implicitWidth + 24
                    hoverEnabled: true
                    onClicked: people.presence = modelData.id
                    background: Rectangle {
                        radius: 15
                        color: chip.on ? people.c.tint : chip.hovered ? people.c.hover : "transparent"
                        border.width: 1; border.color: chip.on ? people.c.accentLine : people.c.hairline
                    }
                    contentItem: Item {
                        Row {
                            id: chipRow
                            anchors.centerIn: parent
                            spacing: 6
                            Rectangle {
                                visible: chip.modelData.id === "online" || chip.modelData.id === "call"
                                anchors.verticalCenter: parent.verticalCenter
                                width: 8; height: 8; radius: 4; color: people.c.ok
                            }
                            Text {
                                textFormat: Text.PlainText
                                text: chip.modelData.text + "  " + (people.counts[chip.modelData.id] || 0)
                                font.pixelSize: 13; font.weight: chip.on ? Font.DemiBold : Font.Normal
                                color: chip.on ? people.c.tintText : people.c.text
                            }
                        }
                    }
                }
            }
        }

        EmptyState {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: people.shown.length === 0
            iconName: "people"
            title: app.t.people_no_match
            actionText: app.t.clear_filters
            onActivated: { search.text = ""; people.presence = "" }
        }

        ListView {
            id: list
            visible: people.shown.length > 0
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: people.rows
            spacing: 2
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            delegate: Loader {
                required property var modelData
                width: ListView.view.width
                property var it: modelData
                sourceComponent: modelData.heading ? heading : person
            }
            // the people banned (moderators)
            footer: ColumnLayout {
                width: ListView.view ? ListView.view.width : 0
                visible: !!meet.room.moderator && (meet.extras.bans || []).length > 0
                height: visible ? implicitHeight + 16 : 16
                spacing: 2
                Text {
                    Layout.topMargin: 16
                    textFormat: Text.PlainText
                    text: app.t.banned_people
                    font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.weight: Font.DemiBold
                    color: people.c.text
                }
                Repeater {
                    model: meet.room.moderator ? (meet.extras.bans || []) : []
                    RowLayout {
                        id: banned
                        required property var modelData
                        Layout.fillWidth: true
                        implicitHeight: 48
                        spacing: 12
                        Icon { Layout.leftMargin: 14; name: "lock"; size: 16; color: people.c.danger }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: banned.modelData.name; elide: Text.ElideRight; font.pixelSize: 14; color: people.c.text }
                            Text { textFormat: Text.PlainText; Layout.fillWidth: true; visible: text !== ""; text: banned.modelData.note; elide: Text.ElideRight; font.pixelSize: 12; color: people.c.muted }
                        }
                        OButton { height_: 30; kind: "quiet"; text: app.t.unban; onClicked: meet.unban(banned.modelData.id) }
                    }
                }
            }
        }
    }

    Component {
        id: heading
        Row {
            topPadding: 14; bottomPadding: 6; leftPadding: 4
            spacing: 8
            Text {
                textFormat: Text.PlainText
                text: parent && parent.parent ? parent.parent.it.heading : ""
                font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.weight: Font.DemiBold
                color: people.c.text
            }
            Text {
                topPadding: 3
                textFormat: Text.PlainText
                text: parent && parent.parent ? parent.parent.it.count : ""
                font.family: "JetBrains Mono"; font.pixelSize: 12
                color: people.c.faint
            }
        }
    }

    Component {
        id: person
        AbstractButton {
            id: row
            readonly property var p: parent ? parent.it : ({})
            readonly property bool canMenu: !p.self && (!!meet.room.moderator || p.actorType === "users")
            implicitHeight: 60
            hoverEnabled: true
            Accessible.name: p.name || ""
            onClicked: if (canMenu) menu.openFor(p, row)
            background: Rectangle { radius: 10; color: row.hovered ? people.c.hover : "transparent" }
            contentItem: RowLayout {
                spacing: 12
                RoomAvatar { Layout.leftMargin: 6; size: 40; source: row.p.avatar || ""; name: row.p.name || ""; status: row.p.self ? "online" : (row.p.status || "") }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Text {
                            textFormat: Text.PlainText
                            Layout.maximumWidth: implicitWidth
                            Layout.fillWidth: true
                            text: (row.p.name || "") + (row.p.self ? " (" + app.t.you + ")" : "")
                            elide: Text.ElideRight; font.pixelSize: 14; font.weight: Font.DemiBold; color: people.c.text
                        }
                        // the role, as a small label
                        Rectangle {
                            visible: !!(row.p.owner || row.p.moderator || row.p.guest || row.p.email)
                            implicitWidth: roleText.implicitWidth + 12; implicitHeight: 20; radius: 10
                            color: row.p.owner ? Qt.alpha(people.c.saffron, 0.16) : people.c.tint
                            Text {
                                id: roleText
                                anchors.centerIn: parent
                                textFormat: Text.PlainText
                                text: row.p.owner ? app.t.owner : row.p.moderator ? app.t.moderator : app.t.guest
                                font.pixelSize: 11; font.weight: Font.DemiBold
                                color: row.p.owner ? people.c.saffronInk : people.c.tintText
                            }
                        }
                        Icon { visible: !!meet.room.moderator && !!row.p.custom && !row.p.moderator; name: "lock"; size: 13; color: people.c.muted }
                        Item { Layout.fillWidth: true }
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: text !== ""
                        textFormat: Text.PlainText
                        text: [row.p.email ? (row.p.address || app.t.rs_email_guest) : "", row.p.statusMessage || ""].filter(x => x).join(" · ")
                        elide: Text.ElideRight; font.pixelSize: 12; color: people.c.muted
                    }
                }
                // presence
                Row {
                    spacing: 6
                    visible: !row.p.group
                    Icon { visible: row.p.inCall > 0; name: "video"; size: 14; color: people.c.ok; anchors.verticalCenter: parent.verticalCenter }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        textFormat: Text.PlainText
                        text: people.presenceText(row.p)
                        font.pixelSize: 12
                        color: row.p.inCall > 0 ? people.c.okInk : people.c.muted
                    }
                }
                Row {
                    Layout.rightMargin: 6
                    spacing: 2
                    opacity: row.hovered ? 1 : 0
                    OButton { kind: "quiet"; iconName: "chat"; height_: 30; tip: app.t.write_privately
                              visible: row.p.actorType === "users" && !row.p.self; onClicked: meet.openWith(row.p.actorId) }
                    OButton { kind: "quiet"; iconName: "more"; height_: 30; tip: app.t.more; visible: row.canMenu; onClicked: menu.openFor(row.p, row) }
                }
            }
        }
    }

    PersonMenu { id: menu; anchors.fill: parent }
    AddPeople { id: addPeople }
}
