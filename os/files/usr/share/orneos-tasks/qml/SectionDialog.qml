// « Section… »: the sections of the list of the tasks chosen, « Hors section », or a new one typed here.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    readonly property var c: theme.c
    property var keys: []
    property string list: ""
    property var names: []
    property string current: ""
    width: Math.min(420, parent ? parent.width - 48 : 420)
    title: app.t.section_move

    function openFor(taskKeys) {
        keys = taskKeys
        const d = tasks.detail(taskKeys[0])
        list = d.list || ""
        current = d.taskSection || ""
        names = tasks.sections(list)
        field.text = ""
        open()
    }
    function choose(name) {
        if (name && names.indexOf(name) < 0) tasks.addSection(list, name)
        tasks.setSection(keys, name)
        close()
    }

    Repeater {
        model: [""].concat(dialog.names)
        AbstractButton {
            id: row
            required property string modelData
            Layout.fillWidth: true
            implicitHeight: 38
            hoverEnabled: true
            Accessible.name: modelData || app.t.section_none
            onClicked: dialog.choose(modelData)
            background: Rectangle { radius: 8; color: row.hovered ? dialog.c.hover : "transparent" }
            contentItem: RowLayout {
                spacing: 10
                Icon { Layout.leftMargin: 8; name: row.modelData ? "listBullet" : "close"; size: 16; color: dialog.c.muted }
                Text {
                    Layout.fillWidth: true
                    text: row.modelData || app.t.section_none
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    font.family: "Schibsted Grotesk"; font.pixelSize: 14
                    font.weight: row.modelData === dialog.current ? Font.DemiBold : Font.Normal
                    color: dialog.c.text
                }
                Icon { Layout.rightMargin: 8; visible: row.modelData === dialog.current; name: "check"; size: 16; color: dialog.c.accent }
            }
        }
    }
    OTextField {
        id: field
        Layout.fillWidth: true
        Layout.topMargin: 4
        iconName: "plus"
        placeholderText: app.t.section_new
        onAccepted: if (text.trim()) dialog.choose(text.trim())
    }
    footer: [
        Item { Layout.fillWidth: true },
        OButton { text: app.t.cancel; onClicked: dialog.close() }
    ]
}
