// What Ornis reads again with each question in this conversation (measured by the agent after each turn,
// chat.context): the Ornis ring (it measures something: docs/ROADMAP.md › Anneau), one arc per part, against the
// size past which the agent summarises the start by itself. Hover (or focus): the parts, as in other harnesses.
// A click compacts the conversation now (« /compact »). Hidden before the first answer.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

AbstractButton {
    id: gauge
    readonly property var c: theme.c
    // the conversation measured (chat.context by default; Code gives its own) and how to compact it
    property var info: chat.context
    property bool busy: chat.busy
    signal compactRequested()
    signal tipRequested(string prompt)
    signal tipDismissed(string key)
    readonly property int tokens: info.tokens || 0
    readonly property int percent: info.percent || 0
    readonly property color level: percent >= 85 ? c.danger : percent >= 60 ? c.saffron : c.famCommunicate
    function openDetails() { pop.open() }
    function k(n) { return n >= 1000 ? (Math.round(n / 100) / 10).toLocaleString(Qt.locale(app.lang), "f", 1).replace(/[.,]0$/, "") + " k" : String(n) }
    function tone(key) {
        return ({ conversation: c.famCommunicate, tool_results: c.famMedia, files: c.saffron, tools: c.famTools,
                  instructions: c.faint, memories: c.famDocs, skills: c.famOrganize, user_rules: c.famSpace })[key] || c.muted
    }
    // the parts side by side along the arc, scaled to the automatic summary's threshold
    readonly property var segments: {
        const out = []
        let at = 0
        const scale = Math.max(info.limit || 1, tokens)
        for (const p of info.parts || []) {
            const to = Math.min(1, at + p.tokens / scale)
            if (to > at) out.push({ from: at, to: Math.max(to, at + 0.012), color: tone(p.key) })
            at = to
        }
        return out
    }

    // only once it matters (half of the threshold): before that, a ring by the send button reads as loading
    property int showFrom: 50
    visible: tokens > 0 && percent >= showFrom
    implicitWidth: 30; implicitHeight: 36
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    enabled: !gauge.busy
    onClicked: pop.open()
    Accessible.role: Accessible.Button
    Accessible.name: app.t.context_label + " " + percent + " %, " + k(tokens) + " / " + k(info.limit || 0) + ". " + app.t.context_click

    background: Rectangle {
        radius: 8
        color: gauge.hovered ? gauge.c.hover : "transparent"
        border.width: gauge.visualFocus ? 2 : 0
        border.color: gauge.c.saffron
    }
    contentItem: Item {
        Ring {
            anchors.centerIn: parent
            width: 20; height: 20
            lineWidth: 3.2
            trackColor: gauge.c.line
            segments: gauge.segments
            opacity: gauge.enabled ? 1 : 0.5
        }
    }

    // open while the pointer (or the keyboard focus) is on the ring, a little after, like a tooltip
    Timer { id: show; interval: 280; onTriggered: pop.open() }
    Timer { id: hide; interval: 160; onTriggered: if (!gauge.hovered && !gauge.activeFocus && !popHover.hovered) pop.close() }
    onHoveredChanged: hovered ? show.restart() : (show.stop(), hide.restart())
    onActiveFocusChanged: activeFocus ? pop.open() : hide.restart()

    Popup {
        id: pop
        parent: gauge
        width: 300
        x: Math.min(0, -(width - gauge.width) + 40)
        y: -implicitHeight - 10
        padding: 14
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle {
            radius: 12
            color: gauge.c.overlay
            border.width: 1; border.color: gauge.c.overlayLine
        }
        HoverHandler { id: popHover; onHoveredChanged: if (!hovered) hide.restart() }
        contentItem: ColumnLayout {
            spacing: 8
            RowLayout {
                Layout.fillWidth: true
                Text {
                    Layout.fillWidth: true
                    text: app.t.context_label + " · " + gauge.percent + " %"
                    font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
                    color: gauge.c.text
                }
                Text {
                    text: gauge.k(gauge.tokens) + " / " + gauge.k(gauge.info.limit || 0)
                    font.family: "JetBrains Mono"; font.pixelSize: 12
                    color: gauge.c.muted
                }
            }
            Text {
                Layout.fillWidth: true
                text: app.t.context_title
                wrapMode: Text.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                color: gauge.c.muted
            }
            Rectangle {                      // the parts on one bar, like the arc
                Layout.fillWidth: true
                implicitHeight: 6; radius: 3
                color: gauge.c.line
                clip: true
                Row {
                    anchors.fill: parent
                    Repeater {
                        model: gauge.info.parts || []
                        Rectangle {
                            required property var modelData
                            width: parent.width * Math.min(100, modelData.percent) / 100
                            height: parent.height
                            color: gauge.tone(modelData.key)
                        }
                    }
                }
            }
            Repeater {
                model: gauge.info.parts || []
                RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: 8
                    Rectangle { implicitWidth: 9; implicitHeight: 9; radius: 2; color: gauge.tone(modelData.key) }
                    Text {
                        Layout.fillWidth: true
                        text: modelData.label
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13
                        color: gauge.c.text
                    }
                    Text {
                        text: gauge.k(modelData.tokens)
                        font.family: "JetBrains Mono"; font.pixelSize: 12
                        color: gauge.c.text
                    }
                }
            }
            ScrollView {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(fileList.implicitHeight, 140)
                visible: (gauge.info.files || []).length > 0
                clip: true
                Column {
                    id: fileList
                    width: parent.width
                    spacing: 5
                    Repeater {
                        model: gauge.info.files || []
                        Text {
                            required property var modelData
                            width: fileList.width
                            text: modelData.name + "  ·  " + gauge.k(modelData.bytes) + " B"
                            textFormat: Text.PlainText
                            elide: Text.ElideMiddle
                            font.family: "JetBrains Mono"; font.pixelSize: 11
                            color: gauge.c.muted
                        }
                    }
                }
            }
            Repeater {
                model: gauge.info.tips || []
                RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    AbstractButton {
                        id: tipAction
                        Layout.fillWidth: true
                        implicitHeight: tipLabel.implicitHeight + 12
                        hoverEnabled: true
                        onClicked: { pop.close(); gauge.tipRequested(modelData.prompt) }
                        background: Rectangle { radius: 8; color: tipAction.hovered ? gauge.c.hover : "transparent" }
                        contentItem: RowLayout {
                            spacing: 6
                            Icon { name: "ornis"; size: 14; color: gauge.c.tintText }
                            Text {
                                id: tipLabel
                                Layout.fillWidth: true
                                text: modelData.label
                                textFormat: Text.PlainText
                                wrapMode: Text.Wrap
                                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                                color: gauge.c.text
                            }
                        }
                    }
                    OButton { iconName: "close"; kind: "quiet"; tip: app.t.close
                              onClicked: gauge.tipDismissed(modelData.key) }
                }
            }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: gauge.c.hairline }
            Text {
                Layout.fillWidth: true
                text: app.t.context_auto.replace("%1", gauge.k(gauge.info.limit || 0))
                      + (gauge.info.compactedAt ? " · " + app.t.context_compacted_at.replace("%1", gauge.info.compactedAt) : "")
                wrapMode: Text.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                color: gauge.c.muted
            }
            AbstractButton {
                id: compactNow
                Layout.fillWidth: true
                implicitHeight: 32
                hoverEnabled: true
                enabled: !gauge.busy
                onClicked: { pop.close(); gauge.compactRequested() }
                background: Rectangle { radius: 8; color: compactNow.hovered ? gauge.c.tint : gauge.c.hover }
                contentItem: RowLayout {
                    spacing: 6
                    Item { Layout.fillWidth: true }
                    Icon { name: "collapse"; size: 14; color: gauge.c.tintText }
                    Text {
                        text: app.t.context_click
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                        color: gauge.c.tintText
                    }
                    Item { Layout.fillWidth: true }
                }
            }
        }
    }
}
