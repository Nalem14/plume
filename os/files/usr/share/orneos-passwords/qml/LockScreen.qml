// Locked: the session password (or a finger), and nothing of the passwords behind. The Klein field with the
// graticule of the rail on the left, the form on the right.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Rectangle {
    id: screen
    readonly property var c: theme.c
    property string message
    // Touch ID, Windows Hello: a dialog of the system, asked once each time the lock shows (and only in front,
    // not over another app); then from the button. fprintd listens to the reader all along.
    property bool asked
    readonly property bool dialogFinger: lock.fingerprintKind === "touchid" || lock.fingerprintKind === "hello"
    color: c.bg

    function finger(again) {
        if (!lock.fingerprint || !screen.visible)
            return
        if (!dialogFinger) {
            lock.startFingerprint("")
            return
        }
        if ((asked && !again) || Qt.application.state !== Qt.ApplicationActive)
            return
        asked = true
        lock.startFingerprint(app.t.unlock_reason)
    }

    onVisibleChanged: {
        if (visible) {
            message = ""
            field.text = ""
            asked = false
            Qt.callLater(() => field.forceActiveFocus())
            finger(false)
        } else {
            lock.stopFingerprint()
        }
    }
    Connections {
        target: lock
        function onFailed(why) {
            if (why === "fingercancel")
                return
            screen.message = why === "wait" ? app.t.unlock_wait : why === "finger" ? app.t.unlock_finger_failed : app.t.unlock_wrong
            if (why === "wrong") { field.selectAll(); shake.restart() }
            if (why === "finger" && !screen.dialogFinger) lock.startFingerprint("")
        }
        function onChanged() { screen.finger(false) }
    }
    Connections {
        target: Qt.application
        function onStateChanged() { screen.finger(false) }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.fillHeight: true
            Layout.preferredWidth: Math.round(parent.width * 0.38)
            color: screen.c.rail
            clip: true
            Row {
                anchors.fill: parent
                Repeater {
                    model: Math.ceil(parent.width / 40)
                    Item {
                        width: 40; height: screen.height
                        Rectangle { width: 1; height: parent.height; color: "white"; opacity: 0.07 }
                    }
                }
            }
            Column {
                anchors.centerIn: parent
                spacing: 18
                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: 84; height: 84; radius: 20
                    color: screen.c.railMark
                    Icon { anchors.centerIn: parent; name: "key"; size: 46; color: screen.c.railMarkText }
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: app.t.app_name
                    font.family: "Schibsted Grotesk"; font.pixelSize: 22; font.weight: Font.DemiBold
                    color: screen.c.railText
                }
                Rectangle { anchors.horizontalCenter: parent.horizontalCenter; width: 36; height: 3; color: screen.c.saffron }
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            ColumnLayout {
                id: form
                anchors.centerIn: parent
                width: Math.min(380, parent.width - 64)
                spacing: 0
                Icon { name: "lock"; size: 30; color: screen.c.accent }
                Text {
                    Layout.fillWidth: true
                    Layout.topMargin: 18
                    text: app.t.locked_title
                    wrapMode: Text.WordWrap
                    font.family: "Schibsted Grotesk"; font.pixelSize: 24; font.weight: Font.DemiBold
                    color: screen.c.text
                }
                Text {
                    Layout.fillWidth: true
                    Layout.topMargin: 8
                    text: lock.fingerprintKind === "touchid" ? app.t.locked_lead_touchid : lock.fingerprintKind === "hello" ? app.t.locked_lead_hello
                          : lock.fingerprint ? app.t.locked_lead_finger : app.t.locked_lead
                    wrapMode: Text.WordWrap
                    lineHeight: 1.3
                    font.family: "Schibsted Grotesk"; font.pixelSize: 15
                    color: screen.c.muted
                }
                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 24
                    spacing: 8
                    OTextField {
                        id: field
                        Layout.fillWidth: true
                        iconName: "key"
                        echoMode: TextInput.Password
                        placeholderText: app.t.session_password
                        enabled: !lock.checking
                        inputMethodHints: Qt.ImhSensitiveData | Qt.ImhNoPredictiveText
                        onAccepted: if (text || lock.blankAllowed) lock.unlock(text)
                        transform: Translate { id: nudge }
                        SequentialAnimation {
                            id: shake
                            NumberAnimation { target: nudge; property: "x"; to: -8; duration: 50 }
                            NumberAnimation { target: nudge; property: "x"; to: 8; duration: 70 }
                            NumberAnimation { target: nudge; property: "x"; to: -5; duration: 60 }
                            NumberAnimation { target: nudge; property: "x"; to: 0; duration: 50 }
                        }
                    }
                    OButton {
                        kind: "primary"; height_: 38
                        iconName: "unlock"; text: app.t.unlock
                        enabled: (field.text !== "" || lock.blankAllowed) && !lock.checking
                        onClicked: lock.unlock(field.text)
                    }
                }
                Text {
                    Layout.fillWidth: true
                    Layout.topMargin: 10
                    visible: screen.message !== ""
                    text: screen.message
                    wrapMode: Text.WordWrap
                    font.family: "Schibsted Grotesk"; font.pixelSize: 14
                    color: screen.c.danger
                }
                OButton {
                    Layout.topMargin: 22
                    visible: screen.dialogFinger
                    kind: "secondary"; height_: 38
                    iconName: "fingerprint"
                    text: lock.fingerprintKind === "hello" ? app.t.unlock_hello : app.t.unlock_touchid
                    onClicked: screen.finger(true)
                }
                RowLayout {
                    Layout.topMargin: 22
                    visible: lock.fingerprint && !screen.dialogFinger
                    spacing: 10
                    Icon {
                        name: "fingerprint"; size: 24; color: screen.c.accent
                        SequentialAnimation on opacity {
                            running: lock.fingerprint && !screen.dialogFinger && screen.visible
                            loops: Animation.Infinite
                            NumberAnimation { from: 1; to: 0.35; duration: 900; easing.type: Easing.InOutSine }
                            NumberAnimation { from: 0.35; to: 1; duration: 900; easing.type: Easing.InOutSine }
                        }
                    }
                    Text {
                        text: app.t.unlock_finger
                        font.family: "Schibsted Grotesk"; font.pixelSize: 14
                        color: screen.c.muted
                    }
                }
                Text {
                    Layout.fillWidth: true
                    Layout.topMargin: 30
                    text: app.t.locked_note
                    wrapMode: Text.WordWrap
                    lineHeight: 1.25
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                    color: screen.c.faint
                }
            }
        }
    }
}
