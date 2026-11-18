// A file of the project in Fichiers (BenchPanel), as an editor shows it: numbered lines in the colours of its language
// (bench.highlight, ornis_core/highlight.py), Markdown drawn (« Aperçu ») or as text, and « Modifier » to change it
// here: Ctrl+S saves (bench.write, refused when the file changed on disk since, often Ornis's doing), Échap leaves.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Item {
    id: ed
    objectName: "codeEditor"
    property string path: ""                 // relative to the project
    property var preview: ({})               // bench.read(path)
    property bool editing: false
    property string mdMode: "render"         // render | source (Markdown only)
    property string problem: ""              // changed | error, after a refused save
    property string original: ""
    property string baseMtime: ""            // the file as it was when « Modifier » was pressed: saved over only that
    readonly property var c: theme.c
    readonly property bool isMarkdown: preview.family === "md"
    readonly property bool dirty: editing && area.text !== original
    readonly property bool rendered: isMarkdown && mdMode === "render" && !editing
    signal savedFile()

    function colors() {
        return { keyword: String(c.accent), string: String(c.famDocs), comment: String(c.faint), number: String(c.saffronInk),
                 "function": String(c.famMedia), type: String(c.famSpace), tag: String(c.accent), attr: String(c.saffronInk),
                 heading: String(c.accent), added: String(c.okInk), removed: String(c.danger) }
    }
    function paint() { code.bench.highlight(area.textDocument, ed.path, ed.colors()) }
    function load() {
        if (editing) return                  // what the person types is never replaced under them
        area.text = preview.text || ""
        problem = ""
    }
    function startEdit() {
        if (!preview.editable) return
        original = preview.text || ""
        baseMtime = preview.mtime || ""
        area.text = original
        problem = ""
        editing = true
        area.forceActiveFocus()
    }
    function cancel() {
        editing = false
        problem = ""
        load()
    }
    function save() {
        if (!editing) return
        if (!dirty) { editing = false; return }
        const why = code.bench.write(path, area.text, baseMtime)
        if (why === "") {
            editing = false
            problem = ""
            if (typeof win !== "undefined" && win.toast) win.toast.show(app.t.bench_saved)
            savedFile()
        } else {
            problem = why
        }
    }
    // the file again from the disk (after « changed »): what was typed is lost, on purpose
    function reloadFromDisk() { editing = false; problem = ""; savedFile() }

    onPreviewChanged: load()
    onPathChanged: { editing = false; mdMode = "render"; problem = ""; paint() }
    Component.onCompleted: { paint(); load() }
    Connections {
        target: theme
        function onChanged() { ed.paint() }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Markdown: Aperçu | Texte; and Modifier / Enregistrer — Annuler
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 12; Layout.rightMargin: 10; Layout.topMargin: 6; Layout.bottomMargin: 6
            spacing: 6
            visible: ed.isMarkdown || !!ed.preview.editable || ed.editing
            Row {                                    // Aperçu | Texte
                visible: ed.isMarkdown && !ed.editing
                spacing: 2
                Repeater {
                    model: [{ key: "render", label: app.t.lp_render, icon: "eye" }, { key: "source", label: app.t.lp_source, icon: "code" }]
                    AbstractButton {
                        id: mdBtn
                        required property var modelData
                        readonly property bool on: ed.mdMode === modelData.key
                        implicitHeight: 28; implicitWidth: mdRow.implicitWidth + 16
                        hoverEnabled: true
                        onClicked: ed.mdMode = modelData.key
                        Accessible.role: Accessible.PageTab
                        Accessible.name: modelData.label
                        background: Rectangle { radius: 8; color: mdBtn.on ? ed.c.card : mdBtn.hovered ? ed.c.hover : "transparent"
                                                border.width: mdBtn.on ? 1 : 0; border.color: ed.c.line }
                        contentItem: Item {
                            Row {
                                id: mdRow
                                anchors.centerIn: parent
                                spacing: 5
                                Icon { anchors.verticalCenter: parent.verticalCenter; name: mdBtn.modelData.icon; size: 13
                                       color: mdBtn.on ? ed.c.famCommunicate : ed.c.muted }
                                Text { anchors.verticalCenter: parent.verticalCenter; text: mdBtn.modelData.label
                                       font.family: "Schibsted Grotesk"; font.pixelSize: 12
                                       font.weight: mdBtn.on ? Font.DemiBold : Font.Medium
                                       color: mdBtn.on ? ed.c.text : ed.c.muted }
                            }
                        }
                    }
                }
            }
            Text {
                visible: ed.editing
                Layout.fillWidth: true
                text: ed.dirty ? "● " + app.t.bench_unsaved : app.t.bench_editing
                elide: Text.ElideRight
                font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.Medium
                color: ed.dirty ? ed.c.saffronInk : ed.c.muted
            }
            Item { visible: !ed.editing; Layout.fillWidth: true }
            OButton {
                visible: !ed.editing && !!ed.preview.editable
                kind: "quiet"; iconName: "edit"; iconSize: 14; height_: 28
                text: app.t.bench_edit; tip: app.t.bench_edit_tip
                onClicked: ed.startEdit()
            }
            OButton { visible: ed.editing; kind: "quiet"; height_: 28; text: app.t.cancel; onClicked: ed.cancel() }
            OButton { visible: ed.editing; kind: "primary"; iconName: "check"; iconSize: 14; height_: 28
                      text: app.t.bench_save; tip: app.t.bench_save + "  (Ctrl+S)"; enabled: ed.dirty; onClicked: ed.save() }
        }

        // a save refused: the file changed on disk since it was opened (Ornis wrote it), or could not be written
        Rectangle {
            visible: ed.problem !== ""
            Layout.fillWidth: true
            Layout.leftMargin: 10; Layout.rightMargin: 10; Layout.bottomMargin: 6
            implicitHeight: probRow.implicitHeight + 16
            radius: 10
            color: ed.c.saffronTint
            RowLayout {
                id: probRow
                anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: 10 }
                spacing: 8
                Icon { name: "warning"; size: 14; color: ed.c.saffronInk }
                Text {
                    Layout.fillWidth: true
                    text: ed.problem === "changed" ? app.t.bench_save_changed : app.t.bench_save_error
                    wrapMode: Text.Wrap
                    font.family: "Schibsted Grotesk"; font.pixelSize: 12
                    color: ed.c.text
                }
                OButton { visible: ed.problem === "changed"; kind: "secondary"; height_: 26; text: app.t.bench_reload
                          onClicked: ed.reloadFromDisk() }
            }
        }

        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: ed.c.hairline }

        // Markdown drawn
        Flickable {
            id: mdView
            visible: ed.rendered
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentHeight: mdText.implicitHeight + 32
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            TextEdit {
                id: mdText
                x: 18; y: 14
                width: mdView.width - 36
                readOnly: true
                selectByMouse: true
                text: ed.rendered ? (ed.preview.text || "") : ""
                textFormat: TextEdit.MarkdownText
                wrapMode: TextEdit.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 14
                color: ed.c.text
                selectionColor: ed.c.tint; selectedTextColor: ed.c.text
                onLinkActivated: link => app.openLink(link)
                HoverHandler { cursorShape: mdText.hoveredLink ? Qt.PointingHandCursor : Qt.IBeamCursor }
            }
        }

        // the text: numbered, coloured; editable after « Modifier »
        Flickable {
            id: flick
            visible: !ed.rendered
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: Math.max(width, gutter.width + area.contentWidth + 24)
            contentHeight: Math.max(height, area.contentHeight + 24)
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded }
            function follow(r) {                     // the caret stays in view while typing
                const x0 = gutter.width + r.x, y0 = area.y + r.y
                if (y0 < contentY) contentY = y0
                else if (y0 + r.height > contentY + height - 12) contentY = y0 + r.height - height + 12
                if (x0 < contentX + gutter.width) contentX = Math.max(0, x0 - gutter.width - 20)
                else if (x0 > contentX + width - 20) contentX = x0 - width + 40
            }
            Rectangle {                              // the gutter's band
                width: gutter.width; height: flick.contentHeight
                color: ed.editing ? ed.c.field : "transparent"
            }
            Text {
                id: gutter
                y: area.y
                width: Math.max(34, String(area.lineCount).length * 8 + 18)
                rightPadding: 10
                horizontalAlignment: Text.AlignRight
                text: {
                    const n = Math.max(1, area.lineCount)
                    let out = "1"
                    for (let i = 2; i <= n; i++) out += "\n" + i
                    return out
                }
                font: area.font
                color: ed.c.faint
            }
            TextEdit {
                id: area
                x: gutter.width + 6; y: 8
                width: Math.max(implicitWidth, flick.width - gutter.width - 12)
                readOnly: !ed.editing
                selectByMouse: true
                persistentSelection: true
                textFormat: TextEdit.PlainText
                wrapMode: TextEdit.NoWrap
                font.family: "JetBrains Mono"; font.pixelSize: 12
                color: ed.c.text
                selectionColor: ed.c.tint; selectedTextColor: ed.c.text
                tabStopDistance: 4 * metrics.advanceWidth(" ")
                cursorVisible: ed.editing && activeFocus
                onCursorRectangleChanged: if (ed.editing) flick.follow(cursorRectangle)
                Keys.onPressed: event => {
                    if (event.matches(StandardKey.Save)) { ed.save(); event.accepted = true }
                    else if (event.key === Qt.Key_Escape && ed.editing && !ed.dirty) { ed.cancel(); event.accepted = true }
                }
                FontMetrics { id: metrics; font: area.font }
            }
        }
        Text {                                       // a long file: its start only, and not editable here
            visible: !!ed.preview.truncated && !ed.rendered
            Layout.fillWidth: true
            Layout.preferredHeight: 28
            leftPadding: 14; verticalAlignment: Text.AlignVCenter
            text: app.t.bench_truncated
            font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.italic: true
            color: ed.c.muted
        }
    }
}
