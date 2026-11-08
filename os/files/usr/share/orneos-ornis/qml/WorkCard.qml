// A Work job, docked above the composer: what it is, where it stands (in progress, needs you, done, stopped), its
// plan with the steps done and the one in progress (live while Ornis works), its folder in the Drive, and « Resume »
// for a job stopped by the daily limit (what is done is not done again). Steps start folded and scroll within
// the card when expanded, keeping room for the conversation. A deep research
// also counts the pages it read and shows them by their site, numbered as in its report.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Rectangle {
    id: card
    property var job: ({})               // chat.currentJob
    signal resumeRequested()
    readonly property var c: theme.c
    readonly property string status: job.status || "running"
    property var folded: ({})            // session → folded by the user
    readonly property bool open: (job.session in folded) ? !folded[job.session] : false
    readonly property int stepCount: (job.steps || []).length
    readonly property int sourceCount: (job.sources || []).length
    readonly property color tone: status === "done" ? c.okInk : status === "stopped" ? c.saffronInk
                                  : status === "waiting" ? c.saffronInk : c.famCommunicate
    implicitHeight: body.implicitHeight + (open ? 24 : 20)
    radius: 12
    color: c.card
    border.width: 1; border.color: c.line

    Flickable {
        anchors.fill: parent; anchors.margins: card.open ? 12 : 10
        contentWidth: width
        contentHeight: body.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}
        ColumnLayout {
            id: body
            width: parent.width
            spacing: 8

            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                Rectangle {
                    implicitWidth: 28; implicitHeight: 28; radius: 8
                    color: card.c.tint
                    Icon { anchors.centerIn: parent; name: card.job.research ? "search" : "sparkle"; size: 15; color: card.c.tintText }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 1
                    Flow {
                        Layout.fillWidth: true
                        spacing: 8
                        Text {
                            text: card.job.research ? app.t.research_card : app.t.work_card
                            font.family: "JetBrains Mono"; font.pixelSize: 10; font.weight: Font.Medium
                            font.capitalization: Font.AllUppercase; font.letterSpacing: 0.8
                            color: card.c.famCommunicate
                        }
                        Rectangle {                  // where it stands
                            width: statusText.implicitWidth + 12; height: 18; radius: 9
                            color: Qt.alpha(card.tone, 0.12)
                            Text {
                                id: statusText
                                anchors.centerIn: parent
                                text: card.job.label || ""
                                font.family: "Schibsted Grotesk"; font.pixelSize: 11; font.weight: Font.DemiBold
                                color: card.tone
                            }
                        }
                        Text {                       // a deep research: how many pages it read
                            visible: card.sourceCount > 0
                            text: card.sourceCount === 1 ? app.t.research_one_source : app.t.research_sources.replace("%1", card.sourceCount)
                            font.family: "Schibsted Grotesk"; font.pixelSize: 12
                            color: card.c.muted
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: card.job.title || ""
                        elide: Text.ElideRight
                        font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.Medium
                        color: card.c.text
                    }
                }
                OButton {
                    visible: !!card.job.folder
                    kind: "quiet"; iconName: "folder"; text: card.width > 620 ? app.t.work_folder : ""; tip: app.t.work_folder
                    onClicked: app.openCloud("/apps/files/?dir=" + encodeURIComponent(card.job.folder))
                }
                OButton {                            // « 2 of 3 steps » and the chevron: fold or unfold the plan
                    visible: card.stepCount > 0
                    kind: "quiet"; iconName: card.open ? "collapse" : "expand"
                    text: card.width > 520 ? app.t.work_steps.replace("%1", Math.min(card.job.done || 0, card.stepCount)).replace("%2", card.stepCount) : ""
                    tip: card.open ? app.t.work_hide_steps : app.t.work_show_steps
                    Accessible.name: tip
                    onClicked: { const f = Object.assign({}, card.folded); f[card.job.session] = card.open; card.folded = f }
                }
                OButton {
                    visible: card.status === "stopped" && !chat.busy
                    kind: "accent"; iconName: "refresh"; text: app.t.work_resume
                    onClicked: card.resumeRequested()
                }
            }

            Repeater {                           // the plan: done, in progress, to come
                model: card.open ? (card.job.steps || []) : []
                RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: 10
                    Item {
                        implicitWidth: 18; implicitHeight: 18
                        Layout.alignment: Qt.AlignTop
                        Layout.topMargin: 1
                        Rectangle {
                            anchors.fill: parent; radius: 9
                            color: modelData.done ? card.c.ok : "transparent"
                            border.width: modelData.done ? 0 : 1.5
                            border.color: modelData.current ? card.c.famCommunicate : card.c.line
                            Icon { anchors.centerIn: parent; visible: modelData.done; name: "check"; size: 11; color: card.c.card }
                        }
                        Rectangle {                  // the step in progress breathes
                            anchors.centerIn: parent
                            visible: modelData.current
                            width: 8; height: 8; radius: 4
                            color: card.c.famCommunicate
                            SequentialAnimation on opacity {
                                running: modelData.current && Qt.styleHints.reduceMotion !== true
                                loops: Animation.Infinite
                                NumberAnimation { to: 0.3; duration: 700; easing.type: Easing.InOutSine }
                                NumberAnimation { to: 1; duration: 700; easing.type: Easing.InOutSine }
                            }
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: modelData.text
                        wrapMode: Text.Wrap
                        font.family: "Schibsted Grotesk"; font.pixelSize: 14
                        font.weight: modelData.current ? Font.DemiBold : Font.Normal
                        color: modelData.done ? card.c.muted : card.c.text
                    }
                }
            }

            Flow {                               // the pages read, by their site, numbered as in the report
                Layout.fillWidth: true
                visible: card.open && card.sourceCount > 0
                spacing: 6
                Repeater {
                    model: card.open ? (card.job.sources || []) : []
                    AbstractButton {
                        id: source
                        required property var modelData
                        required property int index
                        implicitWidth: sourceRow.implicitWidth + 16; implicitHeight: 24
                        hoverEnabled: true
                        onClicked: app.openLink(modelData.url)
                        Accessible.role: Accessible.Link
                        Accessible.name: (index + 1) + ", " + (modelData.title || modelData.host)
                        ToolTip.text: modelData.title || modelData.url
                        ToolTip.delay: 450
                        ToolTip.visible: hovered
                        background: Rectangle {
                            radius: 12
                            color: source.hovered ? card.c.hover : card.c.field
                            border.width: source.visualFocus ? 2 : 0; border.color: card.c.saffron
                        }
                        contentItem: Item {
                            Row {
                                id: sourceRow
                                anchors.centerIn: parent
                                spacing: 6
                                Text {
                                    text: source.index + 1
                                    font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                                    color: card.c.muted
                                }
                                Text {
                                    text: source.modelData.host
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 12
                                    color: card.c.text
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
