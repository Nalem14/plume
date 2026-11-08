// Our status message, as the others read it under our name (Talk, Plume, the cloud): an emoji, a few words,
// and when it goes away by itself.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    title: app.t.status_message_title
    tint: theme.c.famCommunicate
    property string icon: ""

    function start() {
        icon = meet.myStatus.icon || ""
        message.text = meet.myStatus.message || ""
        clear.currentIndex = 0
        open()
        message.forceActiveFocus()
    }

    RowLayout {
        Layout.fillWidth: true
        Layout.leftMargin: 22; Layout.rightMargin: 22
        spacing: 8
        AbstractButton {
            id: iconButton
            implicitWidth: 40; implicitHeight: 40
            hoverEnabled: true
            onClicked: picker.popupAt(iconButton, true)
            Accessible.name: app.t.emoji
            background: Rectangle { radius: 8; color: iconButton.hovered ? theme.c.hover : theme.c.card; border.width: 1; border.color: theme.c.line }
            contentItem: Item {
                Text { anchors.centerIn: parent; visible: dialog.icon !== ""; textFormat: Text.PlainText; text: dialog.icon; font.pixelSize: 20 }
                Icon { anchors.centerIn: parent; visible: dialog.icon === ""; name: "smile"; size: 20; color: theme.c.muted }
            }
        }
        OTextField {
            id: message
            Layout.fillWidth: true
            maximumLength: 80
            placeholderText: app.t.status_message_placeholder
            onAccepted: save.clicked()
        }
    }
    RowLayout {
        Layout.fillWidth: true
        Layout.leftMargin: 22; Layout.rightMargin: 22
        Text { text: app.t.status_clear_after; color: theme.c.text; font.pixelSize: 14; Layout.fillWidth: true }
        OComboBox {
            id: clear
            Layout.preferredWidth: 180
            // seconds; -1: the end of today
            model: [{ text: app.t.clear_never, value: 0 }, { text: app.t.clear_30m, value: 1800 }, { text: app.t.clear_1h, value: 3600 },
                    { text: app.t.clear_4h, value: 14400 }, { text: app.t.clear_today, value: -1 }]
        }
    }
    EmojiPicker { id: picker; onPicked: emoji => dialog.icon = emoji }

    footer: [
        OButton {
            visible: !!(meet.myStatus.message || meet.myStatus.icon)
            kind: "quiet"; text: app.t.status_message_clear
            onClicked: { meet.setMyStatusMessage("", "", 0); dialog.close() }
        },
        OButton { text: app.t.cancel; onClicked: dialog.close() },
        OButton {
            id: save
            kind: "primary"; text: app.t.save
            enabled: message.text.trim() !== "" || dialog.icon !== ""
            onClicked: { meet.setMyStatusMessage(dialog.icon, message.text, clear.currentValue || 0); dialog.close() }
        }
    ]
}
