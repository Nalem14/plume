// Waiting shapes: rows of bars where the content will be, never a "Loading…" text or the mascot (which only
// signs Ornis's answers). One file for the widgets and the apps: tools/design-tokens.py copies it into each
// app's components. The colour comes from the caller's palette (a hairline tone).
import QtQuick

Column {
    id: skeleton
    property color tone: "transparent"
    property int rows: 5
    // A round or square mark at the start of each row (a checkbox, an avatar).
    property bool lead: true
    property real rowHeight: 44
    spacing: 0
    Repeater {
        model: skeleton.rows
        delegate: Item {
            required property int index
            width: skeleton.width
            height: skeleton.rowHeight
            Rectangle {
                id: mark
                visible: skeleton.lead
                anchors.verticalCenter: parent.verticalCenter
                width: 18; height: 18; radius: 9
                color: skeleton.tone
            }
            Column {
                anchors.left: skeleton.lead ? mark.right : parent.left
                anchors.leftMargin: skeleton.lead ? 12 : 0
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                spacing: 7
                Rectangle { width: parent.width * [0.62, 0.44, 0.71, 0.53, 0.38][index % 5]; height: 10; radius: 5; color: skeleton.tone }
                Rectangle { width: parent.width * [0.28, 0.35, 0.22, 0.31, 0.26][index % 5]; height: 8; radius: 4; color: skeleton.tone; opacity: 0.7 }
            }
        }
    }
}
