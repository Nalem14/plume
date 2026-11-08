// « Déplacer vers… »: the lists one can write to.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"
import "components/colors.js" as Colors

ODialog {
    id: dialog
    readonly property var c: theme.c
    property var keys: []
    width: Math.min(420, parent ? parent.width - 48 : 420)
    title: keys.length > 1 ? app.plural("move_many", keys.length) : app.t.move_to

    function openFor(list) { keys = list; open() }
    Repeater {
        model: tasks.writableLists
        AbstractButton {
            id: row
            required property var modelData
            Layout.fillWidth: true
            implicitHeight: 38
            hoverEnabled: true
            onClicked: { tasks.move(dialog.keys, modelData.href); dialog.close() }
            background: Rectangle { radius: 8; color: row.hovered ? dialog.c.hover : "transparent" }
            contentItem: RowLayout {
                spacing: 10
                Rectangle {
                    Layout.leftMargin: 6
                    implicitWidth: 24; implicitHeight: 24; radius: 12
                    color: Colors.display(row.modelData.color, theme.dark)
                    Icon { anchors.centerIn: parent; name: "list"; size: 14; color: "#FFFFFF" }
                }
                Text { Layout.fillWidth: true; text: row.modelData.name; elide: Text.ElideRight; font.family: "Schibsted Grotesk"; font.pixelSize: 14; color: dialog.c.text }
            }
        }
    }
    footer: [
        Item { Layout.fillWidth: true },
        OButton { text: app.t.cancel; onClicked: dialog.close() }
    ]
}
