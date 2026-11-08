// « Demander à vos notes »: a question, answered by Ornis from the few notes that share its words (listed:
// only those leave the computer). [1], [2] in the answer open the notes they come from.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    readonly property var c: theme.c
    property var sources: []          // [{key, title}]
    property int request: -1
    property bool working: false
    property string answer: ""
    property string error: ""
    width: Math.min(620, parent ? parent.width - 48 : 620)
    title: app.t.ask_title

    function start(question) {
        field.text = question || ""
        answer = ""; error = ""; sources = []; working = false
        open()
        field.forceActiveFocus()
        if (question) go()
    }
    function go() {
        const q = field.text.trim()
        if (!q) return
        const keys = notes.relevant(q)
        sources = keys.map(k => { const d = notes.detail(k); return { key: k, title: d.title || app.t.untitled, content: d.content } })
        answer = ""; error = ""
        if (!sources.length) { error = app.t.ask_nothing; return }
        working = true
        request = ornis.ask("question", { question: q, notes: sources.map(s => ({ title: s.title, content: s.content })) })
    }
    Connections {
        target: ornis
        function onAnswered(id, kind, value) {
            if (id !== dialog.request) return
            dialog.working = false
            dialog.answer = String(value).replace(/\[(\d)\]/g, (m, n) => dialog.sources[n - 1] ? "[[" + n + "]](note:" + (n - 1) + ")" : m)
        }
        function onFailed(id, kind, message) { if (id === dialog.request) { dialog.working = false; dialog.error = message } }
    }

    Text {
        Layout.fillWidth: true
        text: app.t.ask_lead
        wrapMode: Text.WordWrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: dialog.c.muted
    }
    OTextField {
        id: field
        Layout.fillWidth: true
        iconName: "ornis"
        clearable: true
        placeholderText: app.t.ask_placeholder
        onAccepted: dialog.go()
    }
    OrnisThinking { visible: dialog.working }
    Text {
        Layout.fillWidth: true
        visible: dialog.error !== ""
        text: dialog.error
        wrapMode: Text.WordWrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: dialog.c.danger
    }
    OrnisAnswer {
        visible: dialog.answer !== ""
        Text {
            Layout.fillWidth: true
            visible: dialog.answer !== ""
            text: dialog.answer
            textFormat: Text.MarkdownText
            wrapMode: Text.WordWrap
            lineHeight: 1.3
            font.family: "Schibsted Grotesk"; font.pixelSize: 15
            color: dialog.c.body
            linkColor: dialog.c.accent
            onLinkActivated: link => {
                if (link.indexOf("note:") === 0) { win.openNote(dialog.sources[parseInt(link.slice(5))].key); dialog.close() }
                else app.openUrl(link)
            }
            HoverHandler { cursorShape: parent.hoveredLink ? Qt.PointingHandCursor : Qt.ArrowCursor }
        }
    }
    ColumnLayout {
        Layout.fillWidth: true
        visible: dialog.sources.length > 0
        spacing: 6
        Text {
            text: app.t.ask_read
            font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold
            font.capitalization: Font.AllUppercase; font.letterSpacing: 0.6
            color: dialog.c.muted
        }
        Flow {
            Layout.fillWidth: true
            spacing: 6
            Repeater {
                model: dialog.sources
                OButton {
                    required property var modelData
                    required property int index
                    height_: 28
                    iconName: "note"; iconSize: 14
                    text: (index + 1) + ". " + modelData.title
                    onClicked: { win.openNote(modelData.key); dialog.close() }
                }
            }
        }
    }
    footer: [
        Text {
            Layout.fillWidth: true
            text: ornis.quota.percent !== undefined ? app.t.ornis_quota_used.replace("%1", ornis.quota.percent) : ""
            font.family: "Schibsted Grotesk"; font.pixelSize: 12
            color: dialog.c.faint
        },
        OButton { text: app.t.close; onClicked: dialog.close() },
        OButton { kind: "primary"; iconName: "ornis"; text: app.t.ask_go; enabled: field.text.trim() !== "" && !dialog.working; onClicked: dialog.go() }
    ]
}
