// Ornis on the opened message: a summary, three replies to start from, the appointment it mentions,
// or the answer to a question about it. A soft Klein card above the body; closing drops the request.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

Rectangle {
    id: panel
    readonly property var c: theme.c
    readonly property var loc: Qt.locale(plume.locale)
    property var message: ({})
    property string mode                 // "", summary, replies, mailEvent, question
    property int request: -1
    property bool loading
    property string error
    property var result: null
    signal replyWith(string text)

    visible: mode !== ""
    implicitHeight: visible ? content.implicitHeight + 28 : 0
    radius: 10
    color: c.tint

    function reset() {
        if (request >= 0)
            ornis.cancel(request)
        mode = ""; request = -1; loading = false; error = ""; result = null
    }
    // a list from Python reaches QML as an array-like object, not an Array
    function asList(value) {
        return value && typeof value === "object" && typeof value.length === "number" ? Array.from(value) : []
    }
    // What Ornis reads of the message. Answers are kept by its content, not by the line's number: the cache
    // reuses the number of a deleted message, whose summary would show on the new one.
    function messageText() {
        const m = message
        return (m.threadText || m.text || "") + (m.inviteText ? "\n\n" + m.inviteText : "")
    }
    function cacheKey(kind) {
        return kind + ":" + Qt.md5((message.subject || "") + "\n" + messageText())
    }
    // an answer already given this session (summary of a message opened again): shown, nothing is asked
    function showCached(kind) {
        const value = ornis.cached(cacheKey(kind))
        if (value === undefined || value === null)
            return false
        mode = kind; error = ""; loading = false; request = -1; result = value
        return true
    }
    function run(kind, extra) {
        if (request >= 0 && loading)
            ornis.cancel(request)
        mode = kind
        error = ""
        result = null
        if (kind === "question" && !extra) {
            loading = false
            question.text = ""
            question.forceActiveFocus()
            return
        }
        loading = true
        const m = message
        // a conversation: Ornis reads all of it (each message without the quotes of the previous ones)
        const data = { from: ((m.from || {}).name || "") + " <" + ((m.from || {}).email || "") + ">", date: m.date || "",
                       subject: m.subject || "", text: messageText() }
        if (m.threadText)
            data.thread = true
        if (kind !== "question")
            data.cacheKey = cacheKey(kind)
        else
            data.question = extra
        request = ornis.ask(kind, data)
    }
    function when(e) {
        const s = new Date(e.start)
        if (e.allDay)
            return loc.toString(s, "dddd d MMMM")
        return loc.toString(s, "dddd d MMMM · HH:mm") + (e.end && e.end !== e.start ? " – " + loc.toString(new Date(e.end), "HH:mm") : "")
    }

    Connections {
        target: ornis
        function onAnswered(id, kind, value) {
            if (id !== panel.request) return
            panel.loading = false
            panel.result = value
        }
        function onFailed(id, kind, text) {
            if (id !== panel.request) return
            panel.loading = false
            panel.error = text
        }
    }

    ColumnLayout {
        id: content
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        anchors.margins: 14; anchors.leftMargin: 16
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Icon { name: "ornis"; size: 18; color: panel.c.accent }
            Text {
                Layout.fillWidth: true
                text: panel.mode === "summary" ? plume.t.ornis_summary : panel.mode === "replies" ? plume.t.ornis_replies_title
                    : panel.mode === "mailEvent" ? plume.t.ornis_event_title : plume.t.ornis_answer
                font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
                color: panel.c.accent
            }
            Text {
                visible: (ornis.quota.percent || 0) >= 50
                text: plume.t.ornis_quota_use.replace("%1", ornis.quota.percent || 0)
                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                color: panel.c.muted
            }
            OButton {
                kind: "quiet"; height_: 26; implicitWidth: 26; iconName: "openExternal"; iconSize: 13
                ToolTip.text: "Ornis"
                onClicked: {
                    const subj = (panel.message.subject || "").trim()
                    const ref = subj ? "« " + subj + " » (mail) — " : ""
                    plume.open("ornis", "--draft=" + ref)
                    panel.reset()
                }
            }
            OButton { kind: "quiet"; height_: 26; implicitWidth: 26; iconName: "close"; iconSize: 12; Accessible.name: plume.t.close; onClicked: panel.reset() }
        }

        // the question about the message
        OTextField {
            id: question
            iconName: "ornis"
            visible: panel.mode === "question"
            Layout.fillWidth: true
            placeholderText: plume.t.ornis_ask_ph
            onAccepted: if (text.trim()) panel.run("question", text.trim())
        }

        OrnisThinking { visible: panel.loading }

        // something went wrong
        RowLayout {
            visible: panel.error !== ""
            Layout.fillWidth: true
            spacing: 10
            Text {
                Layout.fillWidth: true
                text: panel.error
                wrapMode: Text.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 14
                color: panel.c.text
            }
            OButton { height_: 30; text: plume.t.ornis_retry; onClicked: panel.run(panel.mode, panel.mode === "question" ? question.text : undefined) }
        }

        // summary, answer (the model writes light Markdown: bold, lists, links)
        OrnisAnswer {
            visible: !panel.loading && typeof panel.result === "string"
            TextEdit {
                visible: !panel.loading && typeof panel.result === "string"
                Layout.fillWidth: true
                text: typeof panel.result === "string" ? panel.result : ""
                textFormat: TextEdit.MarkdownText
                readOnly: true
                selectByMouse: true
                wrapMode: Text.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 15
                color: panel.c.text
                selectionColor: panel.c.accentLine
                onLinkActivated: link => plume.openUrl(link)
                HoverHandler { cursorShape: parent.hoveredLink ? Qt.PointingHandCursor : Qt.IBeamCursor }
            }
        }

        // replies to start from
        OrnisAnswer {
            visible: !panel.loading && panel.mode === "replies" && panel.asList(panel.result).length > 0
            Flow {
                visible: !panel.loading && panel.mode === "replies" && panel.asList(panel.result).length > 0
                Layout.fillWidth: true
                spacing: 8
                Repeater {
                    model: panel.asList(panel.result)
                    OButton {
                        required property var modelData
                        iconName: "reply"
                        text: modelData.label || modelData.text.slice(0, 30)
                        ToolTip.text: modelData.text
                        onClicked: panel.replyWith(modelData.text)
                    }
                }
            }
        }

        // the appointment of the message
        OrnisAnswer {
            visible: !panel.loading && panel.mode === "mailEvent" && !!panel.result && !!panel.result.none
            Text {
                visible: !panel.loading && panel.mode === "mailEvent" && !!panel.result && !!panel.result.none
                Layout.fillWidth: true
                text: plume.t.ornis_no_event
                wrapMode: Text.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 14
                color: panel.c.text
            }
        }
        OrnisAnswer {
            visible: !panel.loading && panel.mode === "mailEvent" && !!panel.result && !panel.result.none && !!panel.result.start
            RowLayout {
                visible: !panel.loading && panel.mode === "mailEvent" && !!panel.result && !panel.result.none && !!panel.result.start
                Layout.fillWidth: true
                spacing: 12
                Rectangle {
                    implicitWidth: 44; implicitHeight: 48; radius: 8
                    color: panel.c.card
                    border.width: 1; border.color: panel.c.line
                    Column {
                        anchors.centerIn: parent
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: panel.result && panel.result.start ? panel.loc.toString(new Date(panel.result.start), "MMM").toUpperCase().replace(".", "") : ""
                            font.family: "Schibsted Grotesk"; font.pixelSize: 10; font.weight: Font.Bold
                            color: panel.c.danger
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: panel.result && panel.result.start ? new Date(panel.result.start).getDate() : ""
                            font.family: "Schibsted Grotesk"; font.pixelSize: 19; font.weight: Font.DemiBold
                            color: panel.c.text
                        }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Text {
                        Layout.fillWidth: true
                        text: panel.result ? panel.result.title || "" : ""
                        elide: Text.ElideRight
                        font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.weight: Font.DemiBold
                        color: panel.c.text
                    }
                    Text {
                        Layout.fillWidth: true
                        text: panel.result && panel.result.start ? panel.when(panel.result) + (panel.result.location ? "  ·  " + panel.result.location : "") : ""
                        elide: Text.ElideRight
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13
                        color: panel.c.muted
                    }
                }
                OButton { kind: "primary"; height_: 32; iconName: "calendar"; text: plume.t.ornis_event_open; onClicked: plume.proposeEvent(panel.result) }
            }
        }
    }
}
