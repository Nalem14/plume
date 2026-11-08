// What Ornis thought before answering (the model reasons: ornis/relay RELAY_REASONING), above its answer.
// Folded by default, like the assistants of the market: while it thinks, the header says so and the last
// lines of the thought go by underneath in grey; once answered, one quiet line « Réflexion » to unfold.
// The model reasons in English: the text is shown as it is, never as a part of the answer.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ColumnLayout {
    id: block
    property string text: ""
    property bool autoLive: false
    property double started: 0
    property int seconds: 0
    property bool live: false
    onLiveChanged: {
        if (!autoLive) return
        if (live) { started = Date.now(); open = true }
        else { seconds = Math.max(1, Math.round((Date.now() - started) / 1000)); open = false }
    }
    Component.onCompleted: if (autoLive && live) { started = Date.now(); open = true }
    property bool open: app.prefs.reasoning_open === true      // a click changes it for this reply only
    property var steps: null            // the steps of the same answer: one line for both, « Réflexion · 2 étapes · Agenda »
    readonly property bool joined: !live && steps !== null && steps.visible && !steps.streaming
    onOpenChanged: if (joined && steps.open !== open) steps.toggle(open)
    readonly property var c: theme.c
    spacing: 6
    visible: text !== ""

    AbstractButton {
        id: header
        Layout.fillWidth: true
        implicitHeight: 26
        hoverEnabled: true
        Accessible.name: app.t.reasoning_toggle
        Accessible.role: Accessible.Button
        onClicked: block.open = !block.open
        contentItem: Row {
            spacing: 6
            Icon {
                anchors.verticalCenter: parent.verticalCenter
                name: "ornis"; size: 14
                color: header.hovered ? block.c.text : block.c.muted
            }
            Text {
                id: label
                anchors.verticalCenter: parent.verticalCenter
                text: block.live ? app.t.reasoning_live : (block.autoLive && block.seconds > 0 ? app.t.code_reasoning_duration.replace("%1", block.seconds) : app.t.reasoning_done) + (block.joined ? " · " + block.steps.summary : "")
                font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                color: header.hovered ? block.c.text : block.c.muted
                SequentialAnimation on opacity {
                    running: block.live && Qt.styleHints.reduceMotion !== true
                    loops: Animation.Infinite
                    NumberAnimation { from: 1; to: 0.5; duration: 800; easing.type: Easing.InOutSine }
                    NumberAnimation { from: 0.5; to: 1; duration: 800; easing.type: Easing.InOutSine }
                    onRunningChanged: if (!running) label.opacity = 1
                }
            }
            Icon {
                anchors.verticalCenter: parent.verticalCenter
                name: block.open ? "chevronDown" : "chevronRight"; size: 13
                color: header.hovered ? block.c.text : block.c.muted
            }
        }
    }

    // folded and thinking: the last two lines go by, so one sees it work without reading it all
    Text {
        visible: block.live && !block.open
        Layout.fillWidth: true
        Layout.leftMargin: 20
        text: block.text.split("\n").filter(l => l.trim() !== "").slice(-2).join(" ").slice(-240)
        wrapMode: Text.Wrap
        maximumLineCount: 2
        elide: Text.ElideLeft
        font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.italic: true
        color: block.c.muted
        opacity: 0.85
    }

    // unfolded: the whole thought, bounded in height (it can be long), following the end while it is written
    Rectangle {
        visible: block.open
        Layout.fillWidth: true
        Layout.leftMargin: 6
        implicitHeight: Math.min(thought.implicitHeight + 16, 280)
        color: "transparent"
        Rectangle { width: 2; height: parent.height; radius: 1; color: block.c.line }
        Flickable {
            id: flick
            anchors { fill: parent; leftMargin: 14; topMargin: 8; bottomMargin: 8 }
            contentHeight: thought.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            TextEdit {
                id: thought
                width: flick.width - 12
                text: block.text
                readOnly: true
                selectByMouse: true
                wrapMode: Text.Wrap
                textFormat: TextEdit.PlainText
                font.family: "Schibsted Grotesk"; font.pixelSize: Math.max(12, app.textSize - 2)
                color: block.c.muted
                onImplicitHeightChanged: if (block.live) flick.contentY = Math.max(0, thought.implicitHeight - flick.height)
            }
        }
    }
}
