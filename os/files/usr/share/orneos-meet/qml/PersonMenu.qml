// What can be done for one person of the conversation (write privately, owner, moderator, permissions, invitation,
// remove, ban): from the Details panel and the tab « Participants ». openFor(person, item) opens it beside item.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Item {
    id: holder
    function openFor(p, item) { personMenu.openFor(p, item) }

    MeetMenu {
        id: personMenu
        property var person: ({})
        readonly property bool mod: !!meet.room.moderator
        function openFor(p, item) { person = p; popupAt(item) }
        OMenuItem { text: app.t.write_privately; iconName: "chat"; visible: personMenu.person.actorType === "users"
                    onTriggered: meet.openWith(personMenu.person.actorId) }
        OMenuItem { text: app.t.rs_make_owner; iconName: "star"
                    visible: !!(meet.room.owner && (meet.room.can || {}).owner && !personMenu.person.owner && personMenu.person.actorType === "users")
                    onTriggered: meet.makeOwner(personMenu.person.attendee) }
        OMenuItem { text: app.t.make_moderator; iconName: "shield"
                    visible: personMenu.mod && !personMenu.person.moderator && !personMenu.person.group && !personMenu.person.email
                    onTriggered: meet.setModerator(personMenu.person.attendee, true) }
        OMenuItem { text: personMenu.person.owner ? app.t.rs_remove_owner : app.t.remove_moderator; iconName: "shield"
                    visible: personMenu.mod && !!personMenu.person.moderator && (!personMenu.person.owner || !!meet.room.owner)
                    onTriggered: meet.setModerator(personMenu.person.attendee, false) }
        OMenuItem { text: app.t.rs_person_permissions; iconName: "lock"
                    visible: personMenu.mod && !!(meet.room.can || {}).permissions && !personMenu.person.moderator && !personMenu.person.group && meet.room.type !== 1
                    onTriggered: personPermissions.ask(personMenu.person) }
        OMenuItem { text: app.t.rs_resend_one; iconName: "mail"; visible: personMenu.mod && !!personMenu.person.email
                    onTriggered: meet.resendInvitations(personMenu.person.attendee) }
        OMenuItem { text: app.t.remove_from_conversation; iconName: "close"; danger: true; visible: personMenu.mod && !personMenu.person.owner && meet.room.type !== 1
                    onTriggered: meet.removeParticipant(personMenu.person.attendee) }
        OMenuItem { text: app.t.ban; iconName: "lock"; danger: true
                    visible: !!(personMenu.mod && meet.room.canBan && !personMenu.person.owner && !personMenu.person.moderator && !personMenu.person.group)
                    onTriggered: banDialog.ask(personMenu.person) }
    }

    // one person's permissions: their own, whatever the conversation's
    ODialog {
        id: personPermissions
        property var person: ({})
        property int value: 0
        function ask(p) { person = p; value = (p.permissions || 0) & ~1; open() }
        title: app.t.rs_person_permissions_title.replace("%1", person.name || "")
        tint: theme.c.famCommunicate
        Text { Layout.fillWidth: true; textFormat: Text.PlainText; text: app.t.rs_person_permissions_lead; wrapMode: Text.Wrap; font.pixelSize: 13; color: theme.c.muted }
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
        Text { Layout.fillWidth: true; text: app.t.ban_lead; wrapMode: Text.WordWrap; font.pixelSize: 13; color: theme.c.muted }
        OTextField { id: note; Layout.fillWidth: true; placeholderText: app.t.ban_note }
        footer: [
            OButton { text: app.t.cancel; onClicked: banDialog.close() },
            OButton { kind: "danger"; text: app.t.ban; onClicked: { meet.ban(banDialog.person.attendee, note.text); banDialog.close() } }
        ]
    }
}
