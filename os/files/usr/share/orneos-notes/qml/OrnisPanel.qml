// Ornis beside the note: what was asked (summary, tidy up, correct, shorter, checklist, tasks, translation,
// continue writing), Ornis at work, then the answer and what to do with it. With a passage selected, it works
// on that passage alone, and « Remplacer » puts the answer in its place. Nothing changes in the note before,
// and Ctrl+Z undoes it. The tasks found go to Tâches, each linked back to the note.
import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Layouts
import "components"

Item {
    id: panel
    readonly property var c: theme.c
    property var editor
    property string kind: ""
    property string noteKey: ""
    property int request: -1
    property bool working: false
    property string error: ""
    property var result: null
    property var picked: []
    property string lang: ""
    property var part: null              // {start, end, text}: the passage chosen, else null (the whole note)
    property int at: 0                   // « Continuer »: where the new text goes
    readonly property bool opened: kind !== ""
    readonly property var partKinds: ["summary", "tidy", "proofread", "concise", "checklist", "translate"]
    visible: opened
    width: 380

    function start(k) {
        kind = k
        noteKey = editor.key
        error = ""
        result = null
        lang = ""
        const sel = editor.selection()
        part = sel.text.trim() !== "" && partKinds.indexOf(k) >= 0 ? sel : null
        at = editor.cursor()
        if (k === "translate") {
            working = false
            return
        }
        ask()
    }
    function ask() {
        working = true
        error = ""
        result = null
        const full = editor.currentText()
        request = ornis.ask(kind, kind === "continue" ? { text: full, before: full.slice(0, at) }
                                                     : { text: part ? part.text : full, lang: lang, part: !!part })
    }
    function close() { kind = ""; working = false; request = -1 }

    Connections {
        target: ornis
        function onAnswered(id, k, value) {
            if (id !== panel.request) return
            panel.working = false
            panel.result = value
            if (k === "tasks") panel.picked = (value || []).map(() => true)
        }
        function onFailed(id, k, message) {
            if (id !== panel.request) return
            panel.working = false
            panel.error = message
        }
    }
    Component.onCompleted: ornis.loadQuota()

    RectangularShadow { anchors.fill: card; radius: card.radius; blur: 30; offset.y: 10; color: panel.c.shadow }
    Rectangle {
        id: card
        anchors.fill: parent
        anchors.margins: 12
        radius: 12
        color: panel.c.overlay
        border.width: 1; border.color: panel.c.overlayLine

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 12

            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                Rectangle {
                    implicitWidth: 30; implicitHeight: 30; radius: 15
                    color: panel.c.tint
                    Icon { anchors.centerIn: parent; name: "ornis"; size: 18; color: panel.c.accent }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Text {
                        Layout.fillWidth: true
                        text: app.t["ornis_" + panel.kind] || "Ornis"
                        elide: Text.ElideRight
                        font.family: "Schibsted Grotesk"; font.pixelSize: 16; font.weight: Font.DemiBold
                        color: panel.c.text
                    }
                    Text {
                        visible: !!panel.part
                        text: app.t.ornis_on_part
                        font.family: "Schibsted Grotesk"; font.pixelSize: 12
                        color: panel.c.muted
                    }
                }
                OButton {
                    kind: "quiet"; implicitWidth: 30; height_: 30; iconName: "openExternal"; iconSize: 14
                    tip: "Ornis"
                    onClicked: {
                        const txt = (panel.editor ? panel.editor.currentText() : "").slice(0, 1200)
                        app.openInOrnis(txt ? "À propos de cette note :\n\n" + txt + "\n\n" : "")
                        panel.close()
                    }
                }
                OButton { kind: "quiet"; implicitWidth: 30; height_: 30; iconName: "close"; iconSize: 14; tip: app.t.close; onClicked: panel.close() }
            }

            // translation: the language first
            Flow {
                Layout.fillWidth: true
                visible: panel.kind === "translate" && !panel.working && panel.result === null && panel.error === ""
                spacing: 8
                Repeater {
                    model: ["fr", "en", "de", "es", "it"]
                    OButton {
                        required property string modelData
                        text: app.t["lang_" + modelData]
                        onClicked: { panel.lang = modelData; panel.ask() }
                    }
                }
            }

            OrnisThinking { visible: panel.working; Layout.topMargin: 6 }

            Text {
                Layout.fillWidth: true
                visible: panel.error !== ""
                text: panel.error
                wrapMode: Text.WordWrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 14
                color: panel.c.danger
            }
            OButton { visible: panel.error !== ""; text: app.t.retry; iconName: "refresh"; onClicked: panel.ask() }

            // the answer
            OrnisAnswer {
                visible: panel.result !== null && panel.kind !== "tasks"
                Layout.fillHeight: true
                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: panel.result !== null && panel.kind !== "tasks"
                    contentWidth: availableWidth
                    clip: true
                    Text {
                        width: parent.width
                        text: typeof panel.result === "string" ? panel.result : ""
                        textFormat: Text.MarkdownText
                        wrapMode: Text.WordWrap
                        lineHeight: 1.3
                        font.family: "Schibsted Grotesk"; font.pixelSize: 14
                        color: panel.c.body
                        onLinkActivated: link => app.openUrl(link)
                    }
                }
            }

            // the tasks found: chosen ones go to Tâches
            OrnisAnswer {
                visible: panel.kind === "tasks" && panel.result !== null
                Layout.fillHeight: true
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: panel.kind === "tasks" && panel.result !== null
                    spacing: 6
                    Text {
                        Layout.fillWidth: true
                        text: (panel.result || []).length ? app.t.tasks_found_lead : app.t.tasks_none
                        wrapMode: Text.WordWrap
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13
                        color: panel.c.muted
                    }
                    ListView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: 2
                        model: panel.kind === "tasks" ? (panel.result || []) : []
                        delegate: AbstractButton {
                            id: item
                            required property var modelData
                            required property int index
                            width: ListView.view.width
                            implicitHeight: Math.max(40, lines.implicitHeight + 14)
                            hoverEnabled: true
                            onClicked: { const p = panel.picked.slice(); p[index] = !p[index]; panel.picked = p }
                            background: Rectangle { radius: 8; color: item.hovered ? panel.c.hover : "transparent" }
                            contentItem: RowLayout {
                                spacing: 10
                                Rectangle {
                                    Layout.leftMargin: 6
                                    implicitWidth: 18; implicitHeight: 18; radius: 9
                                    color: panel.picked[item.index] ? panel.c.action : "transparent"
                                    border.width: panel.picked[item.index] ? 0 : 1.5
                                    border.color: panel.c.faint
                                    Icon { anchors.centerIn: parent; visible: !!panel.picked[item.index]; name: "check"; size: 12; color: panel.c.actionText }
                                }
                                ColumnLayout {
                                    id: lines
                                    Layout.fillWidth: true
                                    spacing: 1
                                    Text {
                                        Layout.fillWidth: true
                                        text: item.modelData.title
                                        wrapMode: Text.WordWrap
                                        font.family: "Schibsted Grotesk"; font.pixelSize: 14
                                        color: panel.c.text
                                    }
                                    Text {
                                        visible: !!item.modelData.due
                                        text: app.t.due_on.replace("%1", item.modelData.due || "")
                                        font.family: "Schibsted Grotesk"; font.pixelSize: 12
                                        color: panel.c.muted
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // what to do with it
            Flow {
                Layout.fillWidth: true
                spacing: 8
                visible: panel.result !== null && !panel.working
                OButton {
                    visible: ["tidy", "proofread", "concise", "checklist", "translate"].indexOf(panel.kind) >= 0
                    kind: "primary"; text: app.t.ornis_replace
                    onClicked: {
                        if (panel.part) {
                            if (!panel.editor.replacePart(panel.part.start, panel.part.end, panel.part.text, String(panel.result))) {
                                win.toast.show(app.t.ornis_part_moved)
                                return
                            }
                        } else panel.editor.replaceText(panel.result)
                        win.toast.show(app.t.ornis_replaced, app.t.undo, () => panel.editor.undo())
                        panel.close()
                    }
                }
                OButton {
                    visible: panel.kind === "continue"
                    kind: "primary"; iconName: "edit"; text: app.t.ornis_insert
                    onClicked: { panel.editor.insertAt(panel.at, String(panel.result)); win.toast.show(app.t.ornis_inserted, app.t.undo, () => panel.editor.undo()); panel.close() }
                }
                OButton {
                    visible: panel.kind === "translate"
                    text: app.t.ornis_new_note
                    onClicked: { win.openNote(notes.createQuick(panel.result)); panel.close() }
                }
                OButton {
                    visible: panel.kind === "summary" && !panel.part
                    kind: "primary"; text: app.t.ornis_insert_summary
                    onClicked: { panel.editor.insertBelowTitle("> **" + app.t.summary + "**\n" + String(panel.result).split("\n").map(l => "> " + l).join("\n")); panel.close() }
                }
                OButton {
                    visible: panel.kind === "tasks" && (panel.result || []).length > 0
                    kind: "primary"; iconName: "bell"
                    text: app.plural("tasks_add", panel.picked.filter(x => x).length)
                    enabled: panel.picked.some(x => x)
                    onClicked: { notes.sendToTasks(panel.noteKey, (panel.result || []).filter((_, i) => panel.picked[i])); panel.close() }
                }
                OButton {
                    visible: panel.kind !== "tasks"
                    iconName: "copy"; text: app.t.copy
                    onClicked: { clip.text = String(panel.result); clip.selectAll(); clip.copy(); win.toast.show(app.t.copied) }
                }
                OButton { kind: "quiet"; iconName: "refresh"; text: app.t.ornis_again; onClicked: panel.ask() }
            }
            TextEdit { id: clip; visible: false }

            Text {
                Layout.fillWidth: true
                text: app.t.ornis_privacy + (ornis.quota.percent !== undefined ? "  ·  " + app.t.ornis_quota_used.replace("%1", ornis.quota.percent) : "")
                wrapMode: Text.WordWrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                color: panel.c.faint
            }
        }
    }
}
