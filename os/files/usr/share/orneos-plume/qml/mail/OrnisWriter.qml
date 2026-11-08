// Ornis writing tools in the composer: proofread, change the tone, shorten, translate, follow an instruction,
// or write the message from a few words. Works on the selection, or on the whole text; the proposal is shown
// first and only replaces the text when asked.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

Rectangle {
    id: writer
    readonly property var c: theme.c
    property var editor                  // the composer's RichEditor
    property string context              // the message answered, if any
    property string mailFrom             // « Name <address> » of who writes, for a draft in their name
    property string mailTo               // the addresses written to
    property string mailSubject
    property bool mailSigned             // a signature follows the text: the draft ends on the closing line
    property string mode                 // "", proofread, professional, …, translate:xx, custom, draft
    property string title
    property int request: -1
    property bool loading
    property bool asking                 // waiting for the instruction (custom, draft)
    property string error
    property string proposal
    property int start: -1               // the selection worked on (-1: the whole text)
    property int end: -1
    property string source

    visible: mode !== ""
    implicitHeight: visible ? box.implicitHeight + 24 : 0
    radius: 10
    color: c.tint

    function htmlOf(text) {
        return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\n/g, "<br>")
    }
    function begin(kind, label) {
        close()
        mode = kind
        title = label
        const area = editor.area
        // a draft continues the whole text written so far (« Salut Clément, »), never a selection
        if (kind !== "draft" && area.selectionEnd > area.selectionStart) {
            start = area.selectionStart
            end = area.selectionEnd
            source = area.selectedText.split(String.fromCharCode(0x2029)).join("\n").split(String.fromCharCode(0x2028)).join("\n")
        } else {
            start = -1; end = -1
            source = editor.exported().text
        }
        if (kind === "custom" || kind === "draft") {
            asking = true
            instruction.text = ""
            instruction.forceActiveFocus()
            return
        }
        send("")
    }
    function send(text) {
        asking = false
        loading = true
        error = ""
        proposal = ""
        if (mode === "draft")
            request = ornis.ask("draft", { instruction: text, context: context, beginning: source,
                                           from: mailFrom, to: mailTo, subject: mailSubject, signed: mailSigned })
        else
            request = ornis.ask("rewrite", { mode: mode, text: source, instruction: text, context: context })
        lastInstruction = text
    }
    property string lastInstruction
    function close() {
        if (request >= 0 && loading)
            ornis.cancel(request)
        mode = ""; request = -1; loading = false; asking = false; error = ""; proposal = ""
    }
    function apply(replace) {
        const area = editor.area
        const html = rich.markdownHtml(proposal) || htmlOf(proposal)
        if (mode === "draft") {                  // the proposal starts with what was already written
            editor.load(html)
        } else if (start >= 0) {
            if (replace) {
                area.remove(start, end)
                area.insert(start, html)
            } else {
                area.insert(end, "<br>" + html)
            }
        } else if (replace) {
            editor.load(html)
        } else {
            area.insert(area.cursorPosition, (area.cursorPosition > 0 ? "<br>" : "") + html)
        }
        close()
        area.forceActiveFocus()
    }

    Connections {
        target: ornis
        function onAnswered(id, kind, value) {
            if (id !== writer.request) return
            writer.loading = false
            writer.proposal = String(value)
        }
        function onFailed(id, kind, text) {
            if (id !== writer.request) return
            writer.loading = false
            writer.error = text
        }
    }

    ColumnLayout {
        id: box
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        anchors.margins: 12; anchors.leftMargin: 14
        spacing: 8

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Icon { name: "ornis"; size: 17; color: writer.c.accent }
            Text {
                text: writer.title
                font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
                color: writer.c.accent
            }
            Text {
                visible: writer.start >= 0 && writer.mode !== "draft"
                text: "·  " + plume.t.ornis_selection_note
                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                color: writer.c.muted
            }
            Item { Layout.fillWidth: true }
            Text {
                visible: (ornis.quota.percent || 0) >= 50
                text: plume.t.ornis_quota_use.replace("%1", ornis.quota.percent || 0)
                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                color: writer.c.muted
            }
            OButton { kind: "quiet"; height_: 26; implicitWidth: 26; iconName: "close"; iconSize: 12; Accessible.name: plume.t.close; onClicked: writer.close() }
        }

        OTextField {
            id: instruction
            iconName: "ornis"
            visible: writer.asking
            Layout.fillWidth: true
            placeholderText: writer.mode === "draft" ? plume.t.ornis_draft_ph : plume.t.ornis_custom_ph
            onAccepted: if (text.trim()) writer.send(text.trim())
        }

        OrnisThinking { visible: writer.loading }

        Text {
            visible: writer.error !== ""
            Layout.fillWidth: true
            text: writer.error
            wrapMode: Text.Wrap
            font.family: "Schibsted Grotesk"; font.pixelSize: 14
            color: writer.c.text
        }

        OrnisAnswer {
            visible: writer.proposal !== ""
            ScrollView {
                visible: writer.proposal !== ""
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(proposalText.implicitHeight, 200)
                contentWidth: availableWidth
                TextArea {
                    id: proposalText
                    text: writer.proposal
                    textFormat: TextEdit.MarkdownText
                    readOnly: true
                    selectByMouse: true
                    wrapMode: TextEdit.Wrap
                    padding: 0
                    background: null
                    font.family: "Schibsted Grotesk"; font.pixelSize: 15
                    color: writer.c.text
                }
            }
        }

        RowLayout {
            visible: writer.proposal !== "" || writer.error !== ""
            Layout.fillWidth: true
            spacing: 8
            OButton {
                visible: writer.proposal !== ""
                kind: "primary"; height_: 32
                text: writer.mode === "draft" ? plume.t.ornis_use : plume.t.ornis_replace
                onClicked: writer.apply(true)
            }
            OButton {
                visible: writer.proposal !== "" && writer.mode !== "draft"
                height_: 32; text: plume.t.ornis_insert
                onClicked: writer.apply(false)
            }
            OButton { height_: 32; kind: "quiet"; iconName: "refresh"; text: plume.t.ornis_retry; onClicked: writer.send(writer.lastInstruction) }
        }
    }
}
