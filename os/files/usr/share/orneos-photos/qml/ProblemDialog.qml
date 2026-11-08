// What the cloud refused (the change is already undone in the window): said in a window, once.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    property string message
    width: Math.min(440, parent ? parent.width - 48 : 440)
    title: app.t.problem_title
    function tell(text) { message = text; open() }
    Text {
        Layout.fillWidth: true
        text: dialog.message
        wrapMode: Text.WordWrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: theme.c.text
    }
    footer: [
        Item { Layout.fillWidth: true },
        OButton { kind: "primary"; text: app.t.ok; onClicked: dialog.close() }
    ]
}
