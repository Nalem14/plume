// Something the cloud refused or could not do after the window had already shown it done: said plainly,
// with what happened to the change.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    property string message
    width: Math.min(460, parent ? parent.width - 48 : 460)
    title: app.t.problem_title
    function tell(text) {
        message = text
        open()
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: 12
        Rectangle {
            Layout.alignment: Qt.AlignTop
            implicitWidth: 36; implicitHeight: 36; radius: 18
            color: theme.c.dangerTint
            Icon { anchors.centerIn: parent; name: "warning"; size: 18; color: theme.c.danger }
        }
        Text {
            Layout.fillWidth: true
            text: dialog.message
            wrapMode: Text.WordWrap
            lineHeight: 1.3
            font.family: "Schibsted Grotesk"; font.pixelSize: 15
            color: theme.c.body
        }
    }
    footer: [
        Item { Layout.fillWidth: true },
        OButton { kind: "primary"; text: app.t.ok; onClicked: dialog.close() }
    ]
}
