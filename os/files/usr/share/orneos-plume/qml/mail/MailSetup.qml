// The one time mail asks for the password: the address is already there, the password is checked on the
// server and kept in the KDE wallet.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

Rectangle {
    id: setup
    readonly property var c: theme.c
    property bool checking: false
    property string error
    color: c.bg

    Connections {
        target: mail
        function onSetupResult(ok, kind) {
            setup.checking = false
            if (!ok) {
                setup.error = kind === "auth" ? plume.t.mail_wrong : plume.t.mail_offline
                password.selectAll()
                password.forceActiveFocus()
            }
        }
    }

    function connect() {
        if (!password.text || checking)
            return
        error = ""
        checking = true
        mail.setup(password.text)
    }

    Rectangle {
        anchors.centerIn: parent
        width: Math.min(560, parent.width - 64)
        height: column.implicitHeight + 64
        radius: 10
        color: setup.c.card
        border.width: 1; border.color: setup.c.line

        ColumnLayout {
            id: column
            anchors.fill: parent
            anchors.margins: 32
            spacing: 14

            RowLayout {
                spacing: 14
                Rectangle {
                    implicitWidth: 48; implicitHeight: 48; radius: 12
                    color: setup.c.tint
                    Icon { anchors.centerIn: parent; name: "mail"; size: 26; color: setup.c.accent }
                }
                Text {
                    Layout.fillWidth: true
                    text: plume.t.mail_setup_title
                    wrapMode: Text.Wrap
                    font.family: "Schibsted Grotesk"; font.pixelSize: 22; font.weight: Font.DemiBold
                    color: setup.c.text
                }
            }
            Text {
                Layout.fillWidth: true
                text: plume.t.mail_setup_lead
                wrapMode: Text.Wrap
                lineHeight: 1.3
                font.family: "Schibsted Grotesk"; font.pixelSize: 15
                color: setup.c.muted
            }
            Rectangle {
                Layout.fillWidth: true
                Layout.topMargin: 6
                implicitHeight: 42
                radius: 6
                color: setup.c.bg
                border.width: 1; border.color: setup.c.line
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12
                    spacing: 10
                    Icon { name: "user"; size: 18; color: setup.c.muted }
                    Text {
                        Layout.fillWidth: true
                        text: mail.account.address || ""
                        font.family: "Schibsted Grotesk"; font.pixelSize: 15
                        color: setup.c.text
                    }
                }
            }
            OTextField {
                id: password
                Layout.fillWidth: true
                iconName: "lock"
                echoMode: TextInput.Password
                placeholderText: plume.t.mail_password
                enabled: !setup.checking
                onAccepted: setup.connect()
                Component.onCompleted: forceActiveFocus()
            }
            Text {
                visible: setup.error !== ""
                Layout.fillWidth: true
                text: setup.error
                wrapMode: Text.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
                color: setup.c.danger
            }
            Text {
                Layout.fillWidth: true
                text: plume.t.mail_separate
                wrapMode: Text.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                color: setup.c.muted
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: 8
                Item { Layout.fillWidth: true }
                OButton {
                    kind: "primary"; height_: 40
                    text: setup.checking ? "…" : plume.t.mail_connect
                    enabled: password.text.length > 0 && !setup.checking
                    onClicked: setup.connect()
                }
            }
        }
    }
}
