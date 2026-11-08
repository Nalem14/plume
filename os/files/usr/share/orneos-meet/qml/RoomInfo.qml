// The details of the open conversation, beside the chat: who it is (picture, name, description), four shortcuts
// (copy the link, the notifications, plan a meeting, every setting), then two tabs: the people (add, write to,
// roles, permissions of one person, invitation again, remove, ban) and what was shared (pictures, files, voice
// messages, polls, places). The settings themselves are in ConversationSettings.qml.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Rectangle {
    id: info
    readonly property var c: theme.c
    readonly property var room: meet.room
    readonly property var can: room.can || ({})
    property string tab: "people"
    property bool longDescription: false
    signal closeWanted()
    signal planWanted()
    signal settingsWanted(string page)
    color: c.chrome
    // what was shared is read when its tab shows (a note to self has only this one)
    function readShared() { if (visible && (tab === "shared" || room.type === 6) && !meet.shared.loaded && meet.current !== "") meet.loadShared() }
    onTabChanged: readShared()
    onVisibleChanged: readShared()
    Connections {
        target: meet
        function onSharedChanged() { info.readShared() }
        function onRoomChanged() { info.readShared() }
    }

    component Kicker: Text {
        Layout.fillWidth: true
        Layout.topMargin: 14; Layout.bottomMargin: 4
        textFormat: Text.PlainText
        font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
        font.capitalization: Font.AllUppercase; font.letterSpacing: 0.8
        color: info.c.muted
    }
    // a shortcut under the name: its icon in a round, its word below
    component Shortcut: AbstractButton {
        id: shortcut
        property string iconName
        property bool active
        Layout.fillWidth: true
        implicitHeight: 62
        hoverEnabled: true
        Accessible.name: text
        background: Rectangle { radius: 10; color: shortcut.hovered || shortcut.visualFocus ? info.c.hover : "transparent" }
        contentItem: ColumnLayout {
            spacing: 5
            Rectangle {
                Layout.alignment: Qt.AlignHCenter
                implicitWidth: 34; implicitHeight: 34; radius: 17
                color: shortcut.active ? info.c.action : info.c.tint
                Icon { anchors.centerIn: parent; name: shortcut.iconName; size: 17; color: shortcut.active ? info.c.actionText : info.c.tintText }
            }
            Text {
                Layout.fillWidth: true
                textFormat: Text.PlainText
                text: shortcut.text
                horizontalAlignment: Text.AlignHCenter
                font.pixelSize: 11; color: info.c.text; elide: Text.ElideRight
            }
        }
    }
    // a line of the shared things: an icon, a name, who and when
    component SharedLine: AbstractButton {
        id: line
        property string iconName
        property string detail
        Layout.fillWidth: true
        implicitHeight: 46
        hoverEnabled: true
        Accessible.name: text
        background: Rectangle { radius: 8; color: line.hovered || line.visualFocus ? info.c.hover : "transparent" }
        contentItem: RowLayout {
            spacing: 10
            Rectangle {
                Layout.leftMargin: 4
                implicitWidth: 32; implicitHeight: 32; radius: 8
                color: info.c.card
                border.width: 1; border.color: info.c.hairline
                Icon { anchors.centerIn: parent; name: line.iconName; size: 16; color: info.c.muted }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: line.text; font.pixelSize: 13; color: info.c.text; elide: Text.ElideMiddle }
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: line.detail; font.pixelSize: 11; color: info.c.muted; elide: Text.ElideRight }
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 18; Layout.rightMargin: 10; Layout.topMargin: 10
            Text {
                Layout.fillWidth: true
                text: app.t.details
                font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                font.capitalization: Font.AllUppercase; font.letterSpacing: 0.9
                color: info.c.famCommunicate
            }
            OButton { kind: "quiet"; iconName: "close"; tip: app.t.close; onClicked: info.closeWanted() }
        }

        Flickable {
            id: flick
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentHeight: column.implicitHeight + 32
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            ColumnLayout {
                id: column
                x: 16; y: 4
                width: flick.width - 32
                spacing: 6

                // who it is
                RoomAvatar { Layout.alignment: Qt.AlignHCenter; Layout.topMargin: 4; room: info.room; size: 72 }
                Text {
                    Layout.fillWidth: true
                    Layout.topMargin: 6
                    textFormat: Text.PlainText
                    text: info.room.name || ""
                    horizontalAlignment: Text.AlignHCenter
                    font.family: "Schibsted Grotesk"; font.pixelSize: 18; font.weight: Font.DemiBold
                    color: info.c.text; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight
                }
                Text {
                    Layout.fillWidth: true
                    textFormat: Text.PlainText
                    text: info.room.type === 1 ? (info.room.statusMessage || "")
                          : [app.t["rs_type_" + (info.room.type || 2)] || "", info.room.type === 6 ? "" : app.plural("participants", meet.participants.length)]
                            .filter(x => x).join(" · ")
                    visible: text !== ""
                    horizontalAlignment: Text.AlignHCenter
                    font.pixelSize: 12; color: info.c.muted; elide: Text.ElideRight
                }
                Text {
                    id: description
                    Layout.fillWidth: true
                    Layout.topMargin: 4
                    visible: (info.room.description || "") !== ""
                    textFormat: Text.PlainText
                    text: info.room.description || ""
                    horizontalAlignment: Text.AlignHCenter
                    font.pixelSize: 13; color: info.c.text; wrapMode: Text.Wrap
                    maximumLineCount: info.longDescription ? 200 : 3
                    elide: Text.ElideRight
                }
                AbstractButton {
                    visible: description.visible && (description.truncated || info.longDescription)
                    Layout.alignment: Qt.AlignHCenter
                    implicitHeight: 20; implicitWidth: moreText.implicitWidth
                    onClicked: info.longDescription = !info.longDescription
                    contentItem: Text { id: moreText; text: info.longDescription ? app.t.rs_less : app.t.rs_more; font.pixelSize: 12; color: info.c.action }
                }
                // a moderator without a description is invited to write one
                AbstractButton {
                    visible: !description.visible && !!info.room.moderator && info.room.type !== 1 && info.room.type !== 6
                    Layout.alignment: Qt.AlignHCenter
                    implicitHeight: 22; implicitWidth: addDescription.implicitWidth
                    onClicked: info.settingsWanted("general")
                    contentItem: Text { id: addDescription; text: app.t.add_description; font.pixelSize: 12; color: info.c.action }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 10
                    spacing: 2
                    Shortcut { visible: info.room.type !== 6; iconName: "link"; text: app.t.rs_short_link
                               onClicked: { app.copy(info.room.link); app.toast(app.t.link_copied) } }
                    Shortcut { id: bellShortcut; iconName: "bell"; text: app.t.rs_short_notify; active: (info.room.notify || 0) === 3
                               onClicked: notifyMenu.popupAt(bellShortcut, true) }
                    Shortcut { visible: info.room.type !== 6; iconName: "calendar"; text: app.t.rs_short_plan; onClicked: info.planWanted() }
                    Shortcut { iconName: "settings"; text: app.t.rs_short_settings; onClicked: info.settingsWanted("") }
                }

                // the two tabs
                Rectangle {
                    Layout.fillWidth: true
                    Layout.topMargin: 12
                    implicitHeight: 36
                    radius: 10
                    color: info.c.hover
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 3
                        spacing: 3
                        Repeater {
                            model: [{ id: "people", text: info.room.type === 6 ? app.t.rs_tab_people_short : app.t.rs_tab_people + " · " + meet.participants.length },
                                    { id: "shared", text: app.t.rs_tab_shared }]
                            AbstractButton {
                                id: tabButton
                                required property var modelData
                                readonly property bool current: info.tab === modelData.id
                                visible: modelData.id !== "people" || info.room.type !== 6
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                Accessible.role: Accessible.PageTab
                                Accessible.name: modelData.text
                                Accessible.selected: current
                                onClicked: info.tab = modelData.id
                                background: Rectangle { radius: 8; color: tabButton.current ? info.c.card : "transparent"
                                                        border.width: tabButton.current && theme.dark ? 1 : 0; border.color: info.c.hairline }
                                contentItem: Text {
                                    textFormat: Text.PlainText
                                    text: tabButton.modelData.text
                                    horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                                    font.pixelSize: 13; font.weight: tabButton.current ? Font.DemiBold : Font.Normal
                                    color: tabButton.current ? info.c.text : info.c.muted
                                }
                            }
                        }
                    }
                }

                // ---- the people ----------------------------------------------------------------------------
                ColumnLayout {
                    visible: info.tab === "people" && info.room.type !== 6
                    Layout.fillWidth: true
                    Layout.topMargin: 6
                    spacing: 2
                    OTextField {
                        id: peopleFilter
                        visible: meet.participants.length > 8
                        Layout.fillWidth: true
                        Layout.bottomMargin: 4
                        iconName: "search"
                        placeholderText: app.t.rs_find_person
                    }
                    AbstractButton {
                        visible: !!(info.room.moderator && info.room.type !== 1)
                        Layout.fillWidth: true
                        implicitHeight: 44
                        hoverEnabled: true
                        onClicked: addPeople.start()
                        background: Rectangle { radius: 8; color: parent.hovered ? info.c.hover : "transparent" }
                        contentItem: RowLayout {
                            spacing: 10
                            Rectangle { Layout.leftMargin: 4; implicitWidth: 32; implicitHeight: 32; radius: 16; color: info.c.tint
                                Icon { anchors.centerIn: parent; name: "plus"; size: 16; color: info.c.tintText } }
                            Text { text: app.t.add_people; font.pixelSize: 14; color: info.c.action }
                        }
                    }
                    Repeater {
                        model: {
                            const q = peopleFilter.text.trim().toLowerCase()
                            return q ? meet.participants.filter(p => (p.name + " " + p.address).toLowerCase().indexOf(q) >= 0) : meet.participants
                        }
                        AbstractButton {
                            id: person
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: 48
                            hoverEnabled: true
                            Accessible.name: modelData.name
                            onClicked: if (!modelData.self && (info.room.moderator || modelData.actorType === "users")) personMenu.openFor(modelData, person)
                            background: Rectangle { radius: 8; color: person.hovered ? info.c.hover : "transparent" }
                            contentItem: RowLayout {
                                spacing: 10
                                RoomAvatar { Layout.leftMargin: 4; size: 32; source: person.modelData.avatar; name: person.modelData.name; status: person.modelData.status }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 0
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 6
                                        Text { textFormat: Text.PlainText
                                            Layout.fillWidth: true
                                            text: person.modelData.name + (person.modelData.self ? " (" + app.t.you + ")" : "")
                                            elide: Text.ElideRight; font.pixelSize: 14; color: info.c.text
                                        }
                                        Icon { visible: person.modelData.owner || person.modelData.moderator; name: person.modelData.owner ? "star" : "shield"
                                               size: 13; color: person.modelData.owner ? info.c.saffronInk : info.c.muted }
                                        Icon { visible: !!info.room.moderator && person.modelData.custom && !person.modelData.moderator
                                               name: "lock"; size: 13; color: info.c.muted }
                                    }
                                    Text { textFormat: Text.PlainText
                                        Layout.fillWidth: true
                                        visible: text !== ""
                                        text: [person.modelData.owner ? app.t.owner : (person.modelData.moderator ? app.t.moderator : ""),
                                               person.modelData.email ? (person.modelData.address || app.t.rs_email_guest)
                                               : person.modelData.guest ? app.t.guest : "",
                                               person.modelData.statusMessage].filter(x => x).join(" · ")
                                        elide: Text.ElideRight; font.pixelSize: 12; color: info.c.muted
                                    }
                                }
                                Icon { visible: person.modelData.inCall > 0; name: "video"; size: 15; color: info.c.ok; Layout.rightMargin: 6 }
                            }
                        }
                    }

                    // the people banned (moderators)
                    Kicker { text: app.t.banned_people; visible: !!info.room.moderator && (meet.extras.bans || []).length > 0 }
                    Repeater {
                        model: info.room.moderator ? (meet.extras.bans || []) : []
                        RowLayout {
                            id: banned
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: 10
                            Icon { Layout.leftMargin: 10; name: "lock"; size: 16; color: info.c.danger }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0
                                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: banned.modelData.name; elide: Text.ElideRight; font.pixelSize: 14; color: info.c.text }
                                Text { textFormat: Text.PlainText; Layout.fillWidth: true; visible: text !== ""; text: banned.modelData.note; elide: Text.ElideRight; font.pixelSize: 12; color: info.c.muted }
                            }
                            OButton { height_: 30; kind: "quiet"; text: app.t.unban; onClicked: meet.unban(banned.modelData.id) }
                        }
                    }
                }

                // ---- what was shared -----------------------------------------------------------------------
                ColumnLayout {
                    visible: info.tab === "shared" || info.room.type === 6
                    Layout.fillWidth: true
                    Layout.topMargin: 4
                    spacing: 2
                    readonly property var shared: meet.shared
                    Column {
                        Layout.fillWidth: true
                        visible: !meet.shared.loaded
                        spacing: 8
                        Repeater { model: 3; Skeleton { width: parent.width; height: 44 } }
                    }
                    Text {
                        Layout.fillWidth: true
                        Layout.topMargin: 24
                        visible: !!meet.shared.loaded && (meet.shared.kinds || []).length === 0
                        textFormat: Text.PlainText
                        text: meet.shared.failed ? app.t.offline_action : app.t.rs_shared_none
                        horizontalAlignment: Text.AlignHCenter
                        font.pixelSize: 13; color: info.c.muted; wrapMode: Text.Wrap
                    }
                    Repeater {
                        model: meet.shared.kinds || []
                        ColumnLayout {
                            id: kind
                            required property string modelData
                            readonly property var items: meet.shared[modelData] || []
                            Layout.fillWidth: true
                            spacing: 2
                            RowLayout {
                                Layout.fillWidth: true
                                Kicker { text: app.t["rs_shared_" + kind.modelData] || app.t.rs_shared_other }
                                AbstractButton {
                                    visible: !meet.shared[kind.modelData + "_all"]
                                    Layout.topMargin: 10
                                    implicitHeight: 20; implicitWidth: allText.implicitWidth
                                    onClicked: meet.loadShared(kind.modelData)
                                    contentItem: Text { id: allText; text: app.t.show_all; font.pixelSize: 12; color: info.c.action }
                                }
                            }
                            // pictures and videos: a grid of squares
                            GridLayout {
                                visible: kind.modelData === "media"
                                Layout.fillWidth: true
                                columns: 3
                                rowSpacing: 4; columnSpacing: 4
                                Repeater {
                                    model: kind.modelData === "media" ? kind.items : []
                                    AbstractButton {
                                        id: thumb
                                        required property var modelData
                                        readonly property var file: modelData.files[0] || ({})
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: (column.width - 8) / 3
                                        hoverEnabled: true
                                        Accessible.name: file.name || ""
                                        onClicked: {
                                            if (file.preview && String(file.mime).startsWith("image/"))
                                                viewer.show(file, kind.items.map(i => i.files[0]).filter(f => f && f.preview && String(f.mime).startsWith("image/")))
                                            else meet.openFile(file)
                                        }
                                        background: Rectangle { radius: 6; color: info.c.hover; clip: true
                                            Image {
                                                anchors.fill: parent
                                                visible: !!thumb.file.preview
                                                source: thumb.file.preview ? "image://meet/preview/" + thumb.file.id : ""
                                                sourceSize: Qt.size(240, 240)
                                                fillMode: Image.PreserveAspectCrop
                                                asynchronous: true
                                            }
                                            Icon { anchors.centerIn: parent; visible: String(thumb.file.mime).startsWith("video/"); name: "play"; size: 22; color: "white" }
                                            Rectangle { anchors.fill: parent; radius: 6; color: "transparent"; border.width: thumb.hovered ? 2 : 0; border.color: info.c.action }
                                        }
                                    }
                                }
                            }
                            Repeater {
                                model: kind.modelData === "media" ? [] : kind.items
                                SharedLine {
                                    required property var modelData
                                    readonly property var file: modelData.files[0] || null
                                    iconName: file ? (String(file.mime).startsWith("audio/") ? "mic" : "clip")
                                              : modelData.poll ? "checklist" : modelData.location ? "location" : "chat"
                                    text: file ? file.name : modelData.poll ? modelData.poll.question
                                          : modelData.location ? modelData.location.name : modelData.plain
                                    detail: [modelData.name, app.short(modelData.time), file && file.size ? app.size(file.size) : ""].filter(x => x).join(" · ")
                                    onClicked: file ? meet.openFile(file) : meet.jumpTo(modelData.id)
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // the notifications, from the shortcut: the level, then the calls, important, sensitive
    MeetMenu {
        id: notifyMenu
        function level(n, text) { return text + ((info.room.notify || 0) === n ? "  ✓" : "") }
        OMenuItem { text: notifyMenu.level(1, app.t.notify_always); iconName: "bell"; onTriggered: meet.setNotify(1) }
        OMenuItem { text: notifyMenu.level(2, app.t.rs_notify_mentions); iconName: "people"; onTriggered: meet.setNotify(2) }
        OMenuItem { text: notifyMenu.level(3, app.t.rs_notify_never); iconName: "close"; onTriggered: meet.setNotify(3) }
        OMenuItem { text: notifyMenu.level(0, app.t.notify_default); iconName: "settings"; onTriggered: meet.setNotify(0) }
        OMenuItem { visible: !!info.can.calls && info.room.type !== 6; text: app.t.rs_notify_calls; iconName: "phone"; switchable: true; on: !!info.room.notifyCalls
                    onTriggered: meet.setNotifyCalls(!info.room.notifyCalls) }
        OMenuItem { visible: !!info.can.important; text: app.t.rs_important; iconName: "flag"; switchable: true; on: !!info.room.important
                    onTriggered: meet.setImportant(!info.room.important) }
        OMenuItem { visible: !!info.can.sensitive; text: app.t.rs_sensitive; iconName: "eye"; switchable: true; on: !!info.room.sensitive
                    onTriggered: meet.setSensitive(!info.room.sensitive) }
    }

    MeetMenu {
        id: personMenu
        property var person: ({})
        readonly property bool mod: !!info.room.moderator
        function openFor(p, item) { person = p; popupAt(item) }
        OMenuItem { text: app.t.write_privately; iconName: "chat"; visible: personMenu.person.actorType === "users"
                    onTriggered: meet.openWith(personMenu.person.actorId) }
        OMenuItem { text: app.t.rs_make_owner; iconName: "star"
                    visible: !!(info.room.owner && info.can.owner && !personMenu.person.owner && personMenu.person.actorType === "users")
                    onTriggered: meet.makeOwner(personMenu.person.attendee) }
        OMenuItem { text: app.t.make_moderator; iconName: "shield"
                    visible: personMenu.mod && !personMenu.person.moderator && !personMenu.person.group && !personMenu.person.email
                    onTriggered: meet.setModerator(personMenu.person.attendee, true) }
        OMenuItem { text: personMenu.person.owner ? app.t.rs_remove_owner : app.t.remove_moderator; iconName: "shield"
                    visible: personMenu.mod && !!personMenu.person.moderator && (!personMenu.person.owner || !!info.room.owner)
                    onTriggered: meet.setModerator(personMenu.person.attendee, false) }
        OMenuItem { text: app.t.rs_person_permissions; iconName: "lock"
                    visible: personMenu.mod && !!info.can.permissions && !personMenu.person.moderator && !personMenu.person.group && info.room.type !== 1
                    onTriggered: personPermissions.ask(personMenu.person) }
        OMenuItem { text: app.t.rs_resend_one; iconName: "mail"; visible: personMenu.mod && !!personMenu.person.email
                    onTriggered: meet.resendInvitations(personMenu.person.attendee) }
        OMenuItem { text: app.t.remove_from_conversation; iconName: "close"; danger: true; visible: personMenu.mod && !personMenu.person.owner && info.room.type !== 1
                    onTriggered: meet.removeParticipant(personMenu.person.attendee) }
        OMenuItem { text: app.t.ban; iconName: "lock"; danger: true
                    visible: !!(personMenu.mod && info.room.canBan && !personMenu.person.owner && !personMenu.person.moderator && !personMenu.person.group)
                    onTriggered: banDialog.ask(personMenu.person) }
    }

    AddPeople { id: addPeople }
    ImageViewer { id: viewer }

    // one person's permissions: their own, whatever the conversation's
    ODialog {
        id: personPermissions
        property var person: ({})
        property int value: 0
        function ask(p) { person = p; value = (p.permissions || 0) & ~1; open() }
        title: app.t.rs_person_permissions_title.replace("%1", person.name || "")
        tint: theme.c.famCommunicate
        Text { Layout.fillWidth: true; textFormat: Text.PlainText; text: app.t.rs_person_permissions_lead; wrapMode: Text.Wrap; font.pixelSize: 13; color: info.c.muted }
        RowLayout {
            spacing: 8
            OButton { height_: 30; text: app.t.rs_grant_all; onClicked: personPermissions.value = 510 }
            OButton { height_: 30; text: app.t.rs_revoke_all; onClicked: personPermissions.value = 0 }
        }
        PermissionsEditor {
            Layout.fillWidth: true
            value: personPermissions.value
            onEdited: v => personPermissions.value = v
        }
        footer: [
            OButton { visible: !!personPermissions.person.custom; kind: "quiet"; text: app.t.rs_permissions_reset
                      onClicked: { meet.setAttendeePermissions(personPermissions.person.attendee, "set", 0); personPermissions.close() } },
            Item { Layout.fillWidth: true },
            OButton { text: app.t.cancel; onClicked: personPermissions.close() },
            // nothing at all is « Custom » alone (0 would mean the conversation's)
            OButton { kind: "primary"; text: app.t.save
                      onClicked: { meet.setAttendeePermissions(personPermissions.person.attendee, "set", personPermissions.value || 1); personPermissions.close() } }
        ]
    }

    ODialog {
        id: banDialog
        property var person: ({})
        function ask(p) { person = p; note.text = ""; open() }
        title: app.t.ban_title.replace("%1", person.name || "")
        Text { Layout.fillWidth: true; text: app.t.ban_lead; wrapMode: Text.WordWrap; font.pixelSize: 13; color: info.c.muted }
        OTextField { id: note; Layout.fillWidth: true; placeholderText: app.t.ban_note }
        footer: [
            OButton { text: app.t.cancel; onClicked: banDialog.close() },
            OButton { kind: "danger"; text: app.t.ban; onClicked: { meet.ban(banDialog.person.attendee, note.text); banDialog.close() } }
        ]
    }
}
