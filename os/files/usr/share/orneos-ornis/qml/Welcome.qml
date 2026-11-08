// A new conversation, as the chosen mode (chat.uiMode: agent, plan, goal, research) wants it: what the mode is for,
// for a goal and research how it goes (three steps, what to know before starting), and examples of that mode only.
// An Agent example asks; a Plan, goal or research example fills the box (files are often to attach first).
// The examples are hidden in the settings. The mode itself is chosen in the message box only (no second switch here).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Flickable {
    id: welcome
    contentWidth: width
    contentHeight: Math.max(height, body.implicitHeight + 32)
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    ScrollBar.vertical: ScrollBar {}
    // Plume's side panel: smaller, and its own suggestions (about what is open beside) when it gives some
    property bool compact: false
    property var custom: []
    signal suggestion(string text)
    signal workSuggestion(string text, string kind)
    readonly property var c: theme.c
    readonly property string kind: ({ agent: "chat", plan: "plan", goal: "work", research: "research" })[chat.uiMode] || "chat"
    readonly property bool work: kind !== "chat"
    readonly property bool job: kind === "work" || kind === "research"
    readonly property var ideas: kind === "chat" && custom && custom.length ? custom : kind === "plan" ? [
        { text: app.t.plan_idea_1, icon: "code" }, { text: app.t.plan_idea_2, icon: "today" }, { text: app.t.plan_idea_3, icon: "folder" },
    ] : kind === "research" ? [
        { text: app.t.research_idea_1, icon: "search" }, { text: app.t.research_idea_2, icon: "search" },
    ] : kind === "work" ? [
        { text: app.t.work_idea_1, icon: "note" }, { text: app.t.work_idea_2, icon: "table" }, { text: app.t.work_idea_3, icon: "today" },
    ] : [
        { text: app.t.suggest_1, icon: "calendar" }, { text: app.t.suggest_2, icon: "mail" },
        { text: app.t.suggest_4, icon: "clock" }, { text: app.t.suggest_6, icon: "repeat" },
    ]

    ColumnLayout {
        id: body
        x: (welcome.width - width) / 2
        y: Math.max(16, (welcome.height - implicitHeight) / 2)
        width: Math.min(640, welcome.width - (welcome.compact ? 32 : 64))
        spacing: 0

        Image {
            Layout.alignment: Qt.AlignHCenter
            visible: !welcome.work
            source: "../../orneos/mascot/welcome-v1.png"
            sourceSize.width: 256; sourceSize.height: 256
            Layout.preferredWidth: welcome.compact ? 56 : 80; Layout.preferredHeight: welcome.compact ? 56 : 80
            fillMode: Image.PreserveAspectFit
        }
        Rectangle {                          // the mode, as a label: Work / Recherche approfondie
            Layout.alignment: Qt.AlignHCenter
            visible: welcome.work
            implicitWidth: eyebrow.implicitWidth + 20; implicitHeight: 24
            radius: 12
            color: welcome.kind === "plan" ? welcome.c.saffronTint : welcome.c.tint
            Text {
                id: eyebrow
                anchors.centerIn: parent
                text: welcome.kind === "research" ? app.t.research_mode : welcome.kind === "plan" ? app.t.mode_plan + " · " + app.t.plan_readonly : app.t.mode_goal
                font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                font.capitalization: Font.AllUppercase; font.letterSpacing: 0.8
                color: welcome.kind === "plan" ? welcome.c.saffronInk : welcome.c.tintText
            }
        }
        Text {
            Layout.fillWidth: true
            Layout.topMargin: welcome.work ? 14 : 20
            horizontalAlignment: Text.AlignHCenter
            text: welcome.work ? app.t["mode_" + welcome.kind + "Title"] : app.t.hello.replace("%1", app.profile.first || "")
            wrapMode: Text.WordWrap
            font.family: "Schibsted Grotesk"; font.pixelSize: welcome.compact ? 18 : 24; font.weight: Font.DemiBold
            color: welcome.c.text
            Accessible.role: Accessible.Heading
        }
        Text {
            Layout.fillWidth: true
            Layout.topMargin: 10
            horizontalAlignment: Text.AlignHCenter
            visible: !welcome.compact || welcome.work
            text: welcome.work ? app.t["mode_" + welcome.kind + "Lead"] : app.t.hello_lead
            wrapMode: Text.WordWrap
            lineHeight: 1.3
            font.family: "Schibsted Grotesk"; font.pixelSize: 15
            color: welcome.c.muted
        }

        GridLayout {                         // a goal and research: how it goes
            visible: welcome.job
            Layout.fillWidth: true
            Layout.topMargin: 20
            columns: welcome.width > 560 && !welcome.compact ? 3 : 1
            columnSpacing: 8; rowSpacing: 8
            Repeater {
                model: [app.t.mode_step_1, app.t.mode_step_2, app.t.mode_step_3]
                Rectangle {
                    id: step
                    required property string modelData
                    required property int index
                    Layout.fillWidth: true
                    implicitHeight: stepRow.implicitHeight + 20
                    radius: 10
                    color: welcome.c.card
                    border.width: 1; border.color: welcome.c.line
                    RowLayout {
                        id: stepRow
                        anchors.fill: parent; anchors.margins: 10
                        spacing: 8
                        Rectangle {
                            implicitWidth: 24; implicitHeight: 24; radius: 12
                            color: welcome.c.action
                            Text {
                                anchors.centerIn: parent
                                text: step.index + 1
                                font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold
                                color: welcome.c.actionText
                            }
                        }
                        Text {
                            Layout.fillWidth: true
                            text: step.modelData
                            wrapMode: Text.WordWrap
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                            color: welcome.c.text
                        }
                    }
                }
            }
        }

        Text {
            visible: app.prefs.suggestions !== false
            Layout.topMargin: 22
            Layout.bottomMargin: 8
            text: app.t.mode_examples
            font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold
            color: welcome.work ? welcome.c.famCommunicate : welcome.c.muted
        }
        GridLayout {
            visible: app.prefs.suggestions !== false
            Layout.fillWidth: true
            columns: welcome.width > 560 && !welcome.work && !welcome.compact ? 2 : 1
            columnSpacing: 10; rowSpacing: 10
            Repeater {
                model: welcome.ideas
                AbstractButton {
                    id: idea
                    required property var modelData
                    Layout.fillWidth: true
                    implicitHeight: welcome.work ? 46 : 54
                    hoverEnabled: true
                    focusPolicy: Qt.StrongFocus
                    Accessible.name: modelData.text
                    onClicked: welcome.work ? welcome.workSuggestion(modelData.text, welcome.kind) : welcome.suggestion(modelData.text)
                    background: Rectangle {
                        radius: 10
                        color: idea.hovered ? welcome.c.hover : welcome.c.card
                        border.width: idea.visualFocus ? 2 : 1
                        border.color: idea.visualFocus ? welcome.c.saffron : welcome.c.line
                    }
                    contentItem: RowLayout {
                        spacing: 10
                        Item { implicitWidth: 4 }
                        Icon { name: idea.modelData.icon; size: 18; color: welcome.work ? welcome.c.famCommunicate : welcome.c.accent }
                        Text {
                            Layout.fillWidth: true
                            text: idea.modelData.text
                            wrapMode: Text.Wrap
                            maximumLineCount: welcome.work ? 3 : 2
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 14
                            color: welcome.c.text
                        }
                        Item { implicitWidth: 4 }
                    }
                }
            }
        }

        // Work and research: what to know before starting, folded like the cloud's « Avant de commencer »
        AbstractButton {
            id: more
            visible: welcome.job
            Layout.fillWidth: true
            Layout.topMargin: 18
            checkable: true
            hoverEnabled: true
            focusPolicy: Qt.StrongFocus
            Accessible.name: app.t.mode_details
            Accessible.role: Accessible.Button
            Accessible.checkable: true
            Accessible.checked: checked
            implicitHeight: detail.implicitHeight + 24
            background: Rectangle {
                radius: 10
                color: more.hovered ? welcome.c.hover : "transparent"
                border.width: more.visualFocus ? 2 : 1
                border.color: more.visualFocus ? welcome.c.saffron : welcome.c.line
            }
            contentItem: ColumnLayout {
                id: detail
                spacing: 8
                RowLayout {
                    Layout.leftMargin: 14; Layout.rightMargin: 14
                    Text {
                        Layout.fillWidth: true
                        text: app.t.mode_details
                        font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
                        color: welcome.c.text
                    }
                    Text { text: more.checked ? "−" : "+"; font.pixelSize: 16; color: welcome.c.muted }
                }
                Repeater {
                    model: more.checked ? [app.t.mode_explain].concat(welcome.kind === "work" ? [app.t.mode_researchExplain] : [])
                                                              .concat(chat.workEstimate.allowed === false ? [app.t.mode_paid] : []) : []
                    Text {
                        required property string modelData
                        Layout.fillWidth: true
                        Layout.leftMargin: 14; Layout.rightMargin: 14
                        text: modelData
                        wrapMode: Text.WordWrap
                        lineHeight: 1.3
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13
                        color: welcome.c.muted
                    }
                }
            }
        }
    }
}
