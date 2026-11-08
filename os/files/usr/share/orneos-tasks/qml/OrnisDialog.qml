// Ornis in Tâches: the plan of the day (from the titles of today's tasks), subtasks for a task, or the tasks
// a pasted text holds. What Ornis proposes is chosen, then added.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    readonly property var c: theme.c
    property string kind: ""             // plan | breakdown | extract
    property string key: ""
    property int request: -1
    property bool working: false
    property string error: ""
    property var result: null
    property var picked: []
    // a list from Python is not an Array for Array.isArray: a list is what has a length and is not text
    readonly property bool isList: result !== null && typeof result === "object" && result.length !== undefined
    width: Math.min(560, parent ? parent.width - 48 : 560)
    title: app.t["ornis_" + kind] || "Ornis"

    function start(k, taskKey) {
        kind = k
        key = taskKey || ""
        result = null; error = ""; working = false
        open()
        if (k !== "extract") ask()
        else Qt.callLater(() => pasted.forceActiveFocus())
    }
    function ask() {
        working = true
        error = ""
        result = null
        let data = {}
        if (kind === "breakdown") { const d = tasks.detail(key); data = { title: d.title, notes: d.notesFull } }
        else if (kind === "plan") data = { tasks: tasks.rows.filter(r => !r.done).map(r => ({ title: r.title, due: r.due, priority: r.priority, flagged: r.flagged, list: r.listName })) }
        else data = { text: pasted.text }
        request = ornis.ask(kind, data)
    }
    Connections {
        target: ornis
        function onAnswered(id, k, value) {
            if (id !== dialog.request) return
            dialog.working = false
            dialog.result = value
            if (value && typeof value === "object" && value.length !== undefined) dialog.picked = Array.from(value).map(() => true)
        }
        function onFailed(id, k, message) { if (id === dialog.request) { dialog.working = false; dialog.error = message } }
    }

    Text {
        Layout.fillWidth: true
        text: app.t["ornis_" + dialog.kind + "_lead"] || ""
        wrapMode: Text.WordWrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: dialog.c.muted
    }
    OTextArea {
        id: pasted
        leftPadding: 48
        Icon { x: 10; y: 10; name: "ornis"; size: 28 }
        Layout.fillWidth: true
        Layout.preferredHeight: 140
        visible: dialog.kind === "extract" && dialog.result === null
        placeholderText: app.t.ornis_extract_placeholder
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
        visible: typeof dialog.result === "string"
        Text {
            Layout.fillWidth: true
            visible: typeof dialog.result === "string"
            text: typeof dialog.result === "string" ? dialog.result : ""
            textFormat: Text.MarkdownText
            wrapMode: Text.WordWrap
            lineHeight: 1.3
            font.family: "Schibsted Grotesk"; font.pixelSize: 15
            color: dialog.c.body
        }
    }
    OrnisAnswer {
        visible: dialog.isList
        Repeater {
            model: dialog.isList ? dialog.result : []
            AbstractButton {
                id: item
                required property var modelData
                required property int index
                Layout.fillWidth: true
                implicitHeight: 38
                hoverEnabled: true
                onClicked: { const p = dialog.picked.slice(); p[index] = !p[index]; dialog.picked = p }
                background: Rectangle { radius: 8; color: item.hovered ? dialog.c.hover : "transparent" }
                contentItem: RowLayout {
                    spacing: 10
                    Rectangle {
                        Layout.leftMargin: 6
                        implicitWidth: 18; implicitHeight: 18; radius: 9
                        color: dialog.picked[item.index] ? dialog.c.action : "transparent"
                        border.width: dialog.picked[item.index] ? 0 : 1.5; border.color: dialog.c.faint
                        Icon { anchors.centerIn: parent; visible: !!dialog.picked[item.index]; name: "check"; size: 12; color: dialog.c.actionText }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: typeof item.modelData === "string" ? item.modelData : item.modelData.title + (item.modelData.due ? "  ·  " + app.dateLabel(item.modelData.due) : "")
                        elide: Text.ElideRight
                        font.family: "Schibsted Grotesk"; font.pixelSize: 14
                        color: dialog.c.text
                    }
                }
            }
        }
    }
    Text {
        Layout.fillWidth: true
        text: app.t["ornis_privacy_" + dialog.kind] + (ornis.quota.percent !== undefined ? "  ·  " + app.t.ornis_quota_used.replace("%1", ornis.quota.percent) : "")
        wrapMode: Text.WordWrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 12
        color: dialog.c.faint
    }
    footer: [
        Item { Layout.fillWidth: true },
        OButton { text: app.t.close; onClicked: dialog.close() },
        OButton {
            visible: dialog.kind === "extract" && dialog.result === null
            kind: "primary"; iconName: "ornis"; text: app.t.ornis_find
            enabled: pasted.text.trim() !== "" && !dialog.working
            onClicked: dialog.ask()
        },
        OButton {
            visible: dialog.isList && dialog.result.length > 0
            kind: "primary"; iconName: "plus"
            text: app.plural(dialog.kind === "breakdown" ? "subtasks_add" : "tasks_add", dialog.picked.filter(x => x).length)
            enabled: dialog.picked.some(x => x)
            onClicked: {
                const items = Array.from(dialog.result).filter((_, i) => dialog.picked[i])
                for (const it of items) {
                    if (dialog.kind === "breakdown") tasks.add({ title: it, parentKey: dialog.key })
                    else tasks.add({ title: it.title, due: it.due || "" })
                }
                dialog.close()
            }
        }
    ]
}
