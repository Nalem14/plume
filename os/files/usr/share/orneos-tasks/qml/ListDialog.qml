// A list made or changed: its name and its colour (the round boxes and the title take it).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"
import "components/colors.js" as Colors

ODialog {
    id: dialog
    readonly property var c: theme.c
    property string href: ""
    property string color: tasks.colors[0]
    width: Math.min(440, parent ? parent.width - 48 : 440)
    title: href ? app.t.list_edit : app.t.list_new

    function ask(list) {
        href = list ? list.href : ""
        name.text = list ? list.name : ""
        color = list ? list.color : tasks.colors[tasks.lists.length % tasks.colors.length]
        open()
        name.forceActiveFocus()
        name.selectAll()
    }
    function accept() {
        if (!name.text.trim()) return
        if (href) tasks.editList(href, name.text.trim(), color)
        else tasks.createList(name.text.trim(), color)
        close()
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 12
        Rectangle {
            implicitWidth: 44; implicitHeight: 44; radius: 22
            color: Colors.display(dialog.color, theme.dark)
            Icon { anchors.centerIn: parent; name: "list"; size: 22; color: "#FFFFFF" }
        }
        OTextField {
            id: name
            Layout.fillWidth: true
            placeholderText: app.t.list_name
            onAccepted: dialog.accept()
        }
    }
    Flow {
        Layout.fillWidth: true
        spacing: 10
        Repeater {
            model: tasks.colors
            AbstractButton {
                id: swatch
                required property string modelData
                implicitWidth: 30; implicitHeight: 30
                hoverEnabled: true
                Accessible.name: modelData
                onClicked: dialog.color = modelData
                background: Rectangle {
                    radius: 15
                    color: Colors.display(swatch.modelData, theme.dark)
                    border.width: dialog.color === swatch.modelData ? 3 : 0
                    border.color: dialog.c.overlay
                    Rectangle {
                        anchors.fill: parent; anchors.margins: -3; radius: 18; color: "transparent"
                        border.width: 2; border.color: Colors.display(swatch.modelData, theme.dark)
                        visible: dialog.color === swatch.modelData
                    }
                }
            }
        }
    }
    footer: [
        Item { Layout.fillWidth: true },
        OButton { text: app.t.cancel; onClicked: dialog.close() },
        OButton { kind: "primary"; text: dialog.href ? app.t.save : app.t.create; onClicked: dialog.accept() }
    ]
}
