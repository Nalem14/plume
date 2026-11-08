// A scheduled task, as its conversation's head (or alone, before it has run): its instruction, how often, the last
// run, and what can be done with it (open it in the cloud, delete it). Each run's answer is in the conversation.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Rectangle {
    id: card
    property var task: ({})              // a row of chat.scheduled
    property bool compact: true
    signal deleteRequested(string id)
    readonly property var c: theme.c
    readonly property string taskId: task.id || ""
    onTaskIdChanged: folded = compact
    property bool folded: compact        // compact header bar in a conversation; unfolded when shown alone
    implicitHeight: body.implicitHeight + (folded ? 20 : 24)
    radius: 12
    color: c.card
    border.width: 1; border.color: c.line

    ColumnLayout {
        id: body
        anchors.fill: parent; anchors.margins: card.folded ? 10 : 12
        spacing: 8

        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            Rectangle {
                implicitWidth: 28; implicitHeight: 28; radius: 8
                color: card.c.tint
                Icon { anchors.centerIn: parent; name: "repeat"; size: 15; color: card.c.tintText }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    Text {
                        text: app.t.task_card
                        font.family: "JetBrains Mono"; font.pixelSize: 10; font.weight: Font.Medium
                        font.capitalization: Font.AllUppercase; font.letterSpacing: 0.8
                        color: card.c.famCommunicate
                    }
                    Text {
                        Layout.fillWidth: true
                        text: (card.task.repeat || "") + (card.task.last ? "  ·  " + card.task.last : "")
                        elide: Text.ElideRight
                        font.family: "Schibsted Grotesk"; font.pixelSize: 12
                        color: card.c.muted
                    }
                }
                Text {
                    Layout.fillWidth: true
                    visible: card.folded && (card.task.prompt || "") !== ""
                    text: (card.task.prompt || "").replace(/\s+/g, " ")
                    elide: Text.ElideRight
                    maximumLineCount: 1
                    textFormat: Text.PlainText
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.Medium
                    color: card.c.text
                }
            }
            OButton {
                kind: "quiet"; iconName: card.folded ? "expand" : "collapse"; tip: card.folded ? app.t.more : app.t.close
                onClicked: card.folded = !card.folded
            }
            OButton {
                kind: "quiet"; iconName: "openExternal"; tip: app.t.open_cloud
                onClicked: app.openCloud(card.task.session ? "/apps/assistant/?sessionId=" + card.task.session : "/apps/assistant/")
            }
            OButton {
                kind: "quiet"; iconName: "trash"; danger: true; tip: app.t.task_delete
                onClicked: card.deleteRequested(card.task.id)
            }
        }

        Text {
            visible: !card.folded
            text: app.t.task_prompt
            font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold
            color: card.c.muted
        }
        Text {
            id: prompt
            visible: !card.folded
            Layout.fillWidth: true
            text: card.task.prompt || ""
            wrapMode: Text.Wrap
            maximumLineCount: card.compact ? 5 : 12
            elide: Text.ElideRight
            textFormat: Text.PlainText
            font.family: "Schibsted Grotesk"; font.pixelSize: 14
            color: card.c.text
        }
    }
}
