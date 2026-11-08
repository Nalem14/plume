// « Envoyer vers Tâches »: the open items of the note's checklists (all chosen), or the note itself as one
// task. Each task keeps a link back to the note. Ornis can look for the tasks a text holds.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    readonly property var c: theme.c
    property string key
    property var items: []
    property var picked: []
    width: Math.min(520, parent ? parent.width - 48 : 520)
    title: app.t.tasks_title

    function openFor(k) {
        key = k
        const d = notes.detail(k)
        items = notes.openItems(k)
        if (!items.length)
            items = [d.title || app.t.untitled]
        picked = items.map(() => true)
        open()
    }

    Text {
        Layout.fillWidth: true
        text: app.t.tasks_lead
        wrapMode: Text.WordWrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: dialog.c.muted
    }
    Repeater {
        model: dialog.items
        AbstractButton {
            id: item
            required property string modelData
            required property int index
            Layout.fillWidth: true
            implicitHeight: 38
            hoverEnabled: true
            onClicked: { const p = dialog.picked.slice(); p[index] = !p[index]; dialog.picked = p }
            background: Rectangle { radius: 8; color: item.hovered ? dialog.c.hover : "transparent" }
            contentItem: RowLayout {
                spacing: 10
                Rectangle {
                    Layout.leftMargin: 6
                    implicitWidth: 18; implicitHeight: 18; radius: 9
                    color: dialog.picked[item.index] ? dialog.c.action : "transparent"
                    border.width: dialog.picked[item.index] ? 0 : 1.5; border.color: dialog.c.faint
                    Icon { anchors.centerIn: parent; visible: !!dialog.picked[item.index]; name: "check"; size: 12; color: dialog.c.actionText }
                }
                Text {
                    Layout.fillWidth: true
                    text: item.modelData
                    elide: Text.ElideRight
                    font.family: "Schibsted Grotesk"; font.pixelSize: 14
                    color: dialog.c.text
                }
            }
        }
    }
    footer: [
        OButton { kind: "quiet"; iconName: "ornis"; text: app.t.ornis_tasks; onClicked: { dialog.close(); win.askOrnis("tasks") } },
        Item { Layout.fillWidth: true },
        OButton { text: app.t.cancel; onClicked: dialog.close() },
        OButton {
            kind: "primary"; iconName: "bell"
            text: app.plural("tasks_add", dialog.picked.filter(x => x).length)
            enabled: dialog.picked.some(x => x)
            onClicked: { notes.sendToTasks(dialog.key, dialog.items.filter((_, i) => dialog.picked[i])); dialog.close() }
        }
    ]
}
