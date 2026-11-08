// The keyboard shortcuts (Ctrl+/), the same list as the settings (shortcuts.js).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"
import "shortcuts.js" as Keys

ODialog {
    id: dialog
    title: app.t.shortcuts
    width: Math.min(520, parent ? parent.width - 48 : 520)
    readonly property bool mac: Qt.platform.os === "osx" || Qt.platform.os === "macos"

    ColumnLayout {
        Layout.fillWidth: true
        Layout.margins: 22; Layout.topMargin: 10
        spacing: 8
        Repeater {
            model: dialog.opened ? Keys.rows(app.t, chat.voice) : []
            delegate: RowLayout {
                id: row
                required property var modelData
                readonly property string keys: Keys.keyName(modelData[0], app.lang, dialog.mac)
                Layout.fillWidth: true
                spacing: 12
                Accessible.role: Accessible.StaticText
                Accessible.name: modelData[1] + ", " + keys
                Text {
                    Layout.fillWidth: true
                    textFormat: Text.PlainText
                    text: row.modelData[1]
                    wrapMode: Text.Wrap
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                    color: dialog.c.text
                    Accessible.ignored: true
                }
                Rectangle {
                    implicitWidth: keyText.implicitWidth + 14; implicitHeight: 24; radius: 5
                    color: dialog.c.field
                    border.width: 1; border.color: dialog.c.line
                    Accessible.ignored: true
                    Text {
                        id: keyText
                        anchors.centerIn: parent
                        textFormat: Text.PlainText
                        text: row.keys
                        font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.Medium
                        color: dialog.c.muted
                    }
                }
            }
        }
    }
    footer: [
        Item { Layout.fillWidth: true },
        OButton { kind: "primary"; text: app.t.close; onClicked: dialog.close() }
    ]
}
