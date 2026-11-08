// What Ornis did for an answer, as the other agents show it, above the answer: one line, « 4 étapes · Agenda, Notes », that unfolds
// into each tool call with what it looked at (« Le web · tarifs électricité 2026 »). While Ornis works, the calls
// come in as they happen, unfolded. An older answer reads its steps once from its task (chat.loadSteps); without
// them (an older agent, a task gone), the families only.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ColumnLayout {
    id: block
    property var message: ({})
    property bool streaming: false
    property bool open: false
    property bool headless: false          // its line is the reasoning's (« Réflexion · 2 étapes · Agenda »)
    // « 4 étapes · Agenda, Notes »: its own line, or the end of the reasoning's
    readonly property string summary: (steps.length ? app.plural("steps_count", steps.length) : app.t.steps_title)
                                      + " · " + families.map(f => f.label.charAt(0).toUpperCase() + f.label.slice(1)).join(", ")
    function toggle(on) {
        open = on
        if (open && !message.stepsKnown && message.task) chat.loadSteps(message.id)
    }
    readonly property var c: theme.c
    readonly property var families: message.tools || []
    readonly property var steps: streaming ? chat.liveSteps : (message.steps || [])
    // the rows shown: the steps when known, else one row per family
    readonly property var rows: steps.length ? steps : families.map(f => ({ icon: f.icon, label: f.label.charAt(0).toUpperCase() + f.label.slice(1), detail: "" }))
    readonly property bool unfolded: streaming || open
    spacing: 2
    visible: families.length > 0 || steps.length > 0

    AbstractButton {
        id: head
        visible: !block.streaming && !block.headless
        Layout.fillWidth: true
        implicitHeight: 26
        hoverEnabled: true
        focusPolicy: Qt.StrongFocus
        Accessible.role: Accessible.Button
        Accessible.name: headText.text
        Accessible.checkable: true
        Accessible.checked: block.open
        onClicked: block.toggle(!block.open)
        contentItem: RowLayout {
            spacing: 6
            Icon { name: block.open ? "chevronDown" : "chevronRight"; size: 12; color: block.c.muted }
            Text {
                id: headText
                Layout.fillWidth: true
                text: block.summary
                elide: Text.ElideRight
                font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.Medium
                color: head.hovered ? block.c.text : block.c.muted
            }
        }
        background: Rectangle { radius: 6; color: "transparent"; border.width: head.visualFocus ? 2 : 0; border.color: block.c.saffron }
    }

    Rectangle {
        visible: block.unfolded && block.rows.length > 0
        Layout.fillWidth: true
        implicitHeight: rowsCol.implicitHeight + 12
        radius: 10
        color: block.c.card
        border.width: 1; border.color: block.c.line
        Column {
            id: rowsCol
            x: 10; y: 6
            width: parent.width - 20
            spacing: 0
            Repeater {
                model: block.rows
                RowLayout {
                    required property var modelData
                    required property int index
                    width: rowsCol.width
                    height: 26
                    spacing: 8
                    Icon { name: modelData.icon || "search"; size: 13; color: block.c.muted }
                    Text {
                        text: modelData.label
                        font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold
                        color: block.c.text
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: (modelData.detail || "") !== ""
                        text: String(modelData.detail || "").split("\n").map(l => l.trim()).filter(l => l && !/^export PATH=/.test(l)).join("  ⏎  ")
                        textFormat: Text.PlainText
                        maximumLineCount: 1            // a multi-line command would spill over the next rows
                        elide: Text.ElideMiddle
                        font.family: "Schibsted Grotesk"; font.pixelSize: 12
                        color: block.c.muted
                    }
                    Item { Layout.fillWidth: (modelData.detail || "") === "" }
                    // the call running now: the last one while Ornis works
                    BusyIndicator {
                        visible: block.streaming && index === block.rows.length - 1 && block.steps.length > 0
                        running: visible
                        implicitWidth: 14; implicitHeight: 14
                    }
                }
            }
        }
    }
}
