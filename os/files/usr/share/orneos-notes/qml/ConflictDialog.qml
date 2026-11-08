// A note changed here and elsewhere on the same lines: the sync kept both (the other one as « … (autre
// version) »). Here they show line by line, and one is chosen: this computer's, the other one, or both kept.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    readonly property var c: theme.c
    property string copy
    property var lines: []
    signal openRequested(string key)
    width: Math.min(820, parent ? parent.width - 48 : 820)
    title: app.t.conflict_title

    function openFor(k) {
        copy = k
        lines = notes.conflictDiff(k)
        open()
    }

    Text {
        Layout.fillWidth: true
        text: app.t.conflict_lead
        wrapMode: Text.WordWrap
        lineHeight: 1.2
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: dialog.c.muted
    }
    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: 380
        radius: 10
        color: dialog.c.bg
        border.width: 1; border.color: dialog.c.line
        ListView {
            anchors.fill: parent
            anchors.margins: 10
            clip: true
            model: dialog.lines
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            delegate: DiffLine { required property var modelData; width: ListView.view.width; line: modelData }
        }
    }
    Text {
        Layout.fillWidth: true
        text: app.t.conflict_legend
        wrapMode: Text.WordWrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 12
        color: dialog.c.faint
    }
    footer: [
        OButton { kind: "quiet"; text: app.t.conflict_both; onClicked: { notes.keepBoth(dialog.copy); dialog.close() } },
        Item { Layout.fillWidth: true },
        OButton {
            text: app.t.conflict_keep_other
            onClicked: { const k = notes.keepOther(dialog.copy); dialog.close(); if (k) dialog.openRequested(k) }
        },
        OButton {
            kind: "primary"; text: app.t.conflict_keep_here
            onClicked: { const k = notes.keepHere(dialog.copy); dialog.close(); if (k) dialog.openRequested(k) }
        }
    ]
}
