// « Déplacer vers… »: every folder, the current one ticked.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    readonly property var c: theme.c
    property var keys: []
    property string current: ""
    width: Math.min(440, parent ? parent.width - 48 : 440)
    title: keys.length > 1 ? app.plural("move_many", keys.length) : app.t.move_to

    function openFor(list) {
        keys = list
        current = list.length === 1 ? (notes.detail(list[0]).folder || "") : "\u0000"
        open()
    }
    ListView {
        Layout.fillWidth: true
        Layout.preferredHeight: Math.min(contentHeight, 360)
        clip: true
        model: notes.allFolders
        delegate: AbstractButton {
            id: row
            required property var modelData
            width: ListView.view.width
            implicitHeight: 36
            hoverEnabled: true
            onClicked: { notes.moveTo(dialog.keys, modelData.path); dialog.close() }
            background: Rectangle { radius: 7; color: row.hovered ? dialog.c.hover : "transparent" }
            contentItem: RowLayout {
                spacing: 10
                Icon { Layout.leftMargin: 8; name: "folder"; size: 18; color: dialog.c.saffronInk }
                Text {
                    Layout.fillWidth: true
                    text: row.modelData.name
                    elide: Text.ElideMiddle
                    font.family: "Schibsted Grotesk"; font.pixelSize: 14
                    color: dialog.c.text
                }
                Icon { Layout.rightMargin: 8; visible: row.modelData.path === dialog.current; name: "check"; size: 16; color: dialog.c.accent }
            }
        }
    }
    footer: [
        Item { Layout.fillWidth: true },
        OButton { text: app.t.cancel; onClicked: dialog.close() }
    ]
}
