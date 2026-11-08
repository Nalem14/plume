// Sharing one of my lists with an account or a group of the cloud (as the cloud's Tasks and Calendar apps do):
// who has it, read only or able to edit, and a field to find someone. The cloud does the sharing.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    readonly property var c: theme.c
    property var list: ({})
    property var shares: []
    property var found: []
    property bool loading: false
    width: Math.min(520, parent ? parent.width - 48 : 520)
    title: app.t.list_share_title.replace("%1", list.name || "")

    function openFor(l) {
        list = l
        shares = []
        found = []
        field.text = ""
        loading = true
        tasks.loadShares(l.href)
        open()
        field.forceActiveFocus()
    }

    Connections {
        target: tasks
        function onSharesRead(href, list) {
            if (href === dialog.list.href) {
                dialog.shares = list
                dialog.loading = false
            }
        }
        function onSharees(text, list) {
            if (text === field.text.trim())
                dialog.found = list.filter(p => !dialog.shares.some(s => s.principal === p.principal))
        }
    }
    Timer { id: typing; interval: 300; onTriggered: tasks.findSharees(field.text) }

    OTextField {
        id: field
        Layout.fillWidth: true
        iconName: "search"
        placeholderText: app.t.list_share_ph
        onTextChanged: { dialog.found = []; typing.restart() }
    }
    Repeater {
        model: dialog.found
        AbstractButton {
            id: candidate
            required property var modelData
            Layout.fillWidth: true
            implicitHeight: 44
            hoverEnabled: true
            Accessible.name: modelData.name
            onClicked: {
                tasks.shareList(dialog.list.href, modelData.principal, false)
                field.text = ""
                dialog.loading = true
            }
            background: Rectangle { radius: 7; color: candidate.hovered ? dialog.c.hover : "transparent" }
            contentItem: RowLayout {
                spacing: 10
                Icon { Layout.leftMargin: 8; name: candidate.modelData.group ? "people" : "user"; size: 18; color: dialog.c.muted }
                Text {
                    Layout.fillWidth: true
                    text: candidate.modelData.name + (candidate.modelData.group ? " · " + app.t.list_share_group : "")
                          + (candidate.modelData.detail ? " · " + candidate.modelData.detail : "")
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    font.family: "Schibsted Grotesk"; font.pixelSize: 14
                    color: dialog.c.text
                }
                Icon { Layout.rightMargin: 8; name: "plus"; size: 16; color: dialog.c.accent }
            }
        }
    }

    Text {
        Layout.topMargin: 8
        text: app.t.list_shared_with
        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
        color: dialog.c.muted
    }
    Text {
        visible: !dialog.loading && dialog.shares.length === 0
        text: app.t.list_share_none
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: dialog.c.muted
    }
    Skeleton { visible: dialog.loading; Layout.fillWidth: true; Layout.preferredHeight: 40; rows: 1; tone: dialog.c.line }
    Repeater {
        model: dialog.loading ? [] : dialog.shares
        RowLayout {
            required property var modelData
            Layout.fillWidth: true
            spacing: 10
            Icon { name: modelData.group ? "people" : "user"; size: 18; color: dialog.c.muted }
            Text {
                Layout.fillWidth: true
                text: modelData.name
                textFormat: Text.PlainText
                elide: Text.ElideRight
                font.family: "Schibsted Grotesk"; font.pixelSize: 14
                color: dialog.c.text
            }
            OComboBox {
                Layout.preferredWidth: 160
                model: [{ text: app.t.list_share_ro, value: "ro" }, { text: app.t.list_share_rw, value: "rw" }]
                Component.onCompleted: select(modelData.readOnly ? "ro" : "rw")
                onActivated: { dialog.loading = true; tasks.shareList(dialog.list.href, modelData.principal, currentValue === "ro") }
            }
            OButton {
                kind: "quiet"; iconName: "close"; implicitWidth: 34; tip: app.t.list_share_remove
                onClicked: { dialog.loading = true; tasks.unshareList(dialog.list.href, modelData.principal) }
            }
        }
    }

    footer: [
        Item { Layout.fillWidth: true },
        OButton { kind: "primary"; text: app.t.done; onClicked: dialog.close() }
    ]
}
