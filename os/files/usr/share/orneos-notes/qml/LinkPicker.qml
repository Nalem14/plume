// « Lier à… »: a note, a task or a recent mail of the account, found by its title, becomes a link (a chip in a
// note, a link of a task). The same in Notes and Tâches; `search` gives the candidates (links.search).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    readonly property var c: theme.c
    property var search: q => []
    property var exclude: []                 // addresses not to offer (the note or task itself)
    property var found: []
    property int current: 0
    signal picked(var item)
    width: Math.min(520, parent ? parent.width - 48 : 520)
    title: app.t.link_to

    function start() {
        field.text = ""
        refresh()
        open()
        field.forceActiveFocus()
    }
    function refresh() {
        found = search(field.text).filter(i => exclude.indexOf(i.url) < 0)
        current = 0
    }
    function choose(item) {
        if (!item) return
        close()
        picked(item)
    }

    OTextField {
        id: field
        Layout.fillWidth: true
        iconName: "search"
        placeholderText: app.t.link_search
        onTextChanged: dialog.refresh()
        Keys.onDownPressed: dialog.current = Math.min(dialog.current + 1, dialog.found.length - 1)
        Keys.onUpPressed: dialog.current = Math.max(dialog.current - 1, 0)
        onAccepted: dialog.choose(dialog.found[dialog.current])
    }
    ListView {
        Layout.fillWidth: true
        Layout.preferredHeight: Math.min(Math.max(contentHeight, 44), 360)
        Layout.topMargin: 6
        clip: true
        model: dialog.found
        currentIndex: dialog.current
        delegate: AbstractButton {
            id: row
            required property var modelData
            required property int index
            width: ListView.view.width
            implicitHeight: 44
            hoverEnabled: true
            onClicked: dialog.choose(modelData)
            background: Rectangle { radius: 7; color: row.index === dialog.current ? dialog.c.tint : row.hovered ? dialog.c.hover : "transparent" }
            contentItem: RowLayout {
                spacing: 10
                Icon {
                    Layout.leftMargin: 10
                    name: ({ mail: "mail", note: "note", task: "done", photo: "image", meet: "video" })[row.modelData.kind] || "link"
                    size: 18; color: dialog.c.accent
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Text {
                        Layout.fillWidth: true
                        text: row.modelData.title || "…"
                        elide: Text.ElideRight
                        font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.Medium
                        color: dialog.c.text
                    }
                    Text {
                        Layout.fillWidth: true
                        text: app.t["link_kind_" + row.modelData.kind] + (row.modelData.sub ? " · " + row.modelData.sub : "")
                        elide: Text.ElideRight
                        font.family: "Schibsted Grotesk"; font.pixelSize: 12
                        color: dialog.c.muted
                    }
                }
            }
        }
        Text {
            anchors.centerIn: parent
            visible: dialog.found.length === 0
            text: app.t.link_none
            font.family: "Schibsted Grotesk"; font.pixelSize: 13
            color: dialog.c.muted
        }
    }
    footer: [
        Item { Layout.fillWidth: true },
        OButton { text: app.t.cancel; onClicked: dialog.close() }
    ]
}
