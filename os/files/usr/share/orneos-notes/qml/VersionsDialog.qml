// « Versions précédentes »: the versions the cloud keeps of the note (90 days), the one picked shown beside the
// note as it is now (what it adds, what it takes out), and « Restaurer » puts it back: one more change of the
// note, so Ctrl+Z undoes it and the version before stays in the list.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    readonly property var c: theme.c
    property var editor
    property string key
    property var rows: []
    property bool loading: false
    property string picked: ""
    property string versionText: ""
    property bool showChanges: true
    width: Math.min(900, parent ? parent.width - 48 : 900)
    title: app.t.versions

    function openFor(k) {
        key = k
        rows = []
        picked = ""
        versionText = ""
        loading = true
        open()
        notes.loadVersions(k)
    }
    Connections {
        target: notes
        function onVersionsReady(k, list) {
            if (k !== dialog.key) return
            dialog.loading = false
            dialog.rows = list
            if (list.length) dialog.pick(list[0].href)
        }
        function onVersionReady(k, href, text) {
            if (k === dialog.key && href === dialog.picked) dialog.versionText = text
        }
    }
    function pick(href) {
        picked = href
        versionText = ""
        notes.loadVersion(key, href)
    }
    readonly property var changes: versionText && showChanges ? notes.compare(editor ? editor.currentText() : "", versionText) : []

    RowLayout {
        Layout.fillWidth: true
        Layout.preferredHeight: 460
        spacing: 14

        // the versions, newest first
        Rectangle {
            Layout.preferredWidth: 250
            Layout.fillHeight: true
            radius: 10
            color: dialog.c.card
            border.width: 1; border.color: dialog.c.line
            ListView {
                anchors.fill: parent
                anchors.margins: 6
                clip: true
                model: dialog.rows
                spacing: 2
                delegate: AbstractButton {
                    id: version
                    required property var modelData
                    required property int index
                    width: ListView.view.width
                    implicitHeight: 48
                    hoverEnabled: true
                    onClicked: dialog.pick(modelData.href)
                    background: Rectangle {
                        radius: 8
                        color: dialog.picked === version.modelData.href ? dialog.c.tint : (version.hovered ? dialog.c.hover : "transparent")
                    }
                    contentItem: ColumnLayout {
                        spacing: 1
                        Text {
                            Layout.fillWidth: true
                            leftPadding: 10
                            text: version.modelData.when
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
                            color: dialog.picked === version.modelData.href ? dialog.c.tintText : dialog.c.text
                        }
                        Text {
                            leftPadding: 10
                            text: app.t.version_size.replace("%1", Math.max(1, Math.round(version.modelData.size / 1024 * 10) / 10))
                            font.family: "JetBrains Mono"; font.pixelSize: 11
                            color: dialog.c.muted
                        }
                    }
                }
            }
            Column {
                anchors.centerIn: parent
                width: parent.width - 32
                spacing: 8
                visible: !dialog.rows.length
                OrnisThinking { visible: dialog.loading; anchors.horizontalCenter: parent.horizontalCenter }
                Text {
                    width: parent.width
                    visible: !dialog.loading
                    horizontalAlignment: Text.AlignHCenter
                    text: app.t.versions_none
                    wrapMode: Text.WordWrap
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                    color: dialog.c.muted
                }
            }
        }

        // the version picked: its text, or what changed from it to now
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 8
            RowLayout {
                Layout.fillWidth: true
                visible: dialog.picked !== ""
                OSwitch { text: app.t.version_changes; checked: dialog.showChanges; onToggled: dialog.showChanges = checked }
                Item { Layout.fillWidth: true }
            }
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: 10
                color: dialog.c.bg
                border.width: 1; border.color: dialog.c.line
                ScrollView {
                    anchors.fill: parent
                    anchors.margins: 10
                    clip: true
                    visible: dialog.versionText !== "" && !dialog.showChanges
                    TextArea {
                        readOnly: true
                        text: dialog.versionText
                        wrapMode: TextEdit.Wrap
                        textFormat: TextEdit.PlainText
                        selectByMouse: true
                        color: dialog.c.body
                        font.family: "Schibsted Grotesk"; font.pixelSize: 14
                        background: null
                    }
                }
                ListView {
                    anchors.fill: parent
                    anchors.margins: 10
                    clip: true
                    visible: dialog.versionText !== "" && dialog.showChanges
                    model: dialog.changes
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                    delegate: DiffLine { required property var modelData; width: ListView.view.width; line: modelData }
                }
                OrnisThinking { anchors.centerIn: parent; visible: dialog.picked !== "" && dialog.versionText === "" }
            }
            Text {
                Layout.fillWidth: true
                visible: dialog.versionText !== "" && dialog.showChanges
                text: app.t.version_legend
                wrapMode: Text.WordWrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                color: dialog.c.faint
            }
        }
    }
    footer: [
        Item { Layout.fillWidth: true },
        OButton { text: app.t.close; onClicked: dialog.close() },
        OButton {
            kind: "primary"; iconName: "restore"; text: app.t.version_restore
            enabled: dialog.versionText !== "" && !!dialog.editor && dialog.editor.editable
            onClicked: {
                dialog.editor.replaceText(dialog.versionText)
                win.toast.show(app.t.version_restored, app.t.undo, () => dialog.editor.undo())
                dialog.close()
            }
        }
    ]
}
