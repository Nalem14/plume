// Breakout rooms (Talk's « sous-salles »). Moderators make them (Talk shares the people out, or each one
// chooses), open and close them, write to all of them at once. Everyone sees them; in « free » mode one goes
// from one to another, and in a breakout room one can call a moderator for help. Talk moves the call itself
// when they open or close (Calls follows the « switchto » of the signaling).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    readonly property var c: theme.c
    readonly property var room: meet.room
    readonly property bool inBreakout: !!room.breakout
    readonly property bool configured: (room.breakoutMode || 0) > 0
    readonly property bool running: (room.breakoutStatus || 0) === 1
    title: app.t.breakout_rooms
    tint: c.famCommunicate

    Text {
        Layout.fillWidth: true
        visible: !dialog.configured && !dialog.inBreakout
        text: app.t.breakout_lead
        wrapMode: Text.WordWrap; font.pixelSize: 13; color: dialog.c.muted
    }

    // making them (moderators)
    ColumnLayout {
        visible: !dialog.configured && !dialog.inBreakout && !!dialog.room.moderator
        Layout.fillWidth: true
        spacing: 10
        RowLayout {
            Layout.fillWidth: true
            spacing: 12
            Text { Layout.fillWidth: true; text: app.t.breakout_amount; font.pixelSize: 14; color: dialog.c.text }
            OComboBox {
                id: amount
                Layout.preferredWidth: 110
                model: [2, 3, 4, 5, 6, 8, 10].map(n => ({ text: String(n), value: n }))
                currentIndex: 0
            }
        }
        OComboBox {
            id: mode
            Layout.fillWidth: true
            model: [{ text: app.t.breakout_auto, value: 1 }, { text: app.t.breakout_free, value: 3 }]
        }
    }

    // the rooms
    Repeater {
        model: meet.extras.breakout || []
        Surface {
            id: br
            required property var modelData
            Layout.fillWidth: true
            implicitHeight: 54
            radius: 10
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 14; anchors.rightMargin: 10
                spacing: 10
                Rectangle { implicitWidth: 8; implicitHeight: 8; radius: 4; color: br.modelData.hasCall ? dialog.c.ok : dialog.c.line }
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: br.modelData.name; elide: Text.ElideRight; font.pixelSize: 14; color: dialog.c.text }
                Rectangle {
                    visible: br.modelData.assistance
                    implicitWidth: help.implicitWidth + 14; implicitHeight: 22; radius: 11
                    color: dialog.c.saffronTint
                    Text { id: help; anchors.centerIn: parent; text: app.t.needs_help; font.pixelSize: 11; font.weight: Font.DemiBold; color: dialog.c.saffronInk }
                }
                OButton {
                    visible: dialog.running && (!!dialog.room.moderator || dialog.room.breakoutMode === 3)
                    kind: "secondary"; height_: 30; text: app.t.go_there
                    onClicked: { meet.switchBreakout(br.modelData.token); dialog.close() }
                }
            }
        }
    }

    // writing to all of them, help
    RowLayout {
        visible: dialog.configured && dialog.running && !!dialog.room.moderator && !dialog.inBreakout
        Layout.fillWidth: true
        spacing: 6
        OTextField { id: message; Layout.fillWidth: true; placeholderText: app.t.broadcast_placeholder; onAccepted: sendAll.clicked() }
        OButton { id: sendAll; kind: "primary"; iconName: "send"; tip: app.t.broadcast; enabled: message.text.trim() !== ""
                  onClicked: { meet.broadcast(message.text); message.text = "" } }
    }
    OButton {
        visible: dialog.inBreakout
        Layout.fillWidth: true
        kind: (dialog.room.breakoutStatus || 0) === 2 ? "secondary" : "primary"
        iconName: "hand"
        text: (dialog.room.breakoutStatus || 0) === 2 ? app.t.cancel_help : app.t.ask_help
        onClicked: meet.askAssistance((dialog.room.breakoutStatus || 0) !== 2)
    }

    footer: [
        OButton {
            visible: dialog.configured && !!dialog.room.moderator && !dialog.inBreakout && !dialog.running
            kind: "quiet"; text: app.t.breakout_remove; danger: true
            onClicked: { meet.removeBreakout(); dialog.close() }
        },
        OButton { text: app.t.close; onClicked: dialog.close() },
        OButton {
            visible: !!dialog.room.moderator && !dialog.inBreakout
            kind: "primary"
            text: !dialog.configured ? app.t.breakout_create : (dialog.running ? app.t.breakout_stop : app.t.breakout_start)
            onClicked: {
                if (!dialog.configured) meet.configureBreakout(mode.currentValue || 1, amount.currentValue || 2)
                else meet.startBreakout(!dialog.running)
            }
        }
    ]
}
