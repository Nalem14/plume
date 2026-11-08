// Side-by-side artifact & code preview pane (Canvas style): inspect code with line numbers, render Markdown/HTML,
// copy, send to Notes, or save to a local file. The code can be changed here (the drawing follows; « Rétablir » goes
// back to Ornis's), and « Demander une modification » asks Ornis for a new version, with the code as it is now.
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "components"

Rectangle {
    id: pane
    property bool open: false
    property string title: ""
    property string lang: "code"
    property string code: ""
    property string tab: "code"          // "render" | "code"
    property string original: ""         // the code as Ornis wrote it (« Rétablir »)
    readonly property bool edited: code !== original
    signal changeRequested(string text)  // a message for Ornis: change this artifact
    readonly property var c: theme.c
    // a page, a drawing, a diagram: drawn by Chromium in its sandbox (ArtifactWeb.qml), when QtWebEngine is there
    readonly property string artifact: {
        const l = (lang || "").toLowerCase()
        return l === "html" || l === "htm" ? "html" : l === "svg" ? "svg" : l === "mermaid" ? "mermaid" : ""
    }
    readonly property bool web: artifact !== "" && webLoader.status !== Loader.Error
    readonly property bool canRender: {
        const l = (lang || "").toLowerCase()
        return l === "markdown" || l === "md" || l === "html" || l === "txt" || web
    }
    color: c.chrome
    visible: open

    function show(newTitle, newLang, newCode) {
        title = newTitle || app.t.preview_title
        lang = newLang || "code"
        code = newCode || ""
        original = code
        const l = (lang || "").toLowerCase()
        tab = (l === "markdown" || l === "md" || l === "html" || l === "htm" || l === "svg" || l === "mermaid") ? "render" : "code"
        open = true
    }
    function close() { open = false }

    RowLayout {
        anchors.fill: parent
        anchors.bottomMargin: askRow.implicitHeight + 20
        spacing: 0

        Rectangle { Layout.fillHeight: true; Layout.preferredWidth: 1; color: pane.c.line }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // Header bar (52px, aligned with Conversation header)
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 52
                color: pane.c.chrome
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 14; anchors.rightMargin: 10
                    spacing: 6
                    Icon { name: "code"; size: 16; color: pane.c.famCommunicate }
                    Text {
                        Layout.fillWidth: true
                        text: pane.title || app.t.preview_title
                        elide: Text.ElideRight
                        font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
                        color: pane.c.text
                    }
                    Rectangle {
                        visible: (pane.lang || "") !== "" && pane.width >= 520
                        implicitWidth: langText.implicitWidth + 14
                        implicitHeight: 22
                        radius: 6
                        color: pane.c.field
                        border.width: 1; border.color: pane.c.line
                        Text {
                            id: langText
                            anchors.centerIn: parent
                            text: pane.lang
                            font.family: "JetBrains Mono"; font.pixelSize: 11
                            color: pane.c.muted
                        }
                    }
                    Rectangle {
                        visible: pane.canRender
                        implicitWidth: tabRow.implicitWidth + 6
                        implicitHeight: 28
                        radius: 7
                        color: pane.c.hover
                        Row {
                            id: tabRow
                            anchors.centerIn: parent
                            spacing: 2
                            Repeater {
                                model: [
                                    { key: "render", label: app.t.preview_tab_render },
                                    { key: "code", label: app.t.preview_tab_code }
                                ]
                                AbstractButton {
                                    id: tBtn
                                    required property var modelData
                                    readonly property bool active: pane.tab === modelData.key
                                    implicitWidth: tLbl.implicitWidth + 16
                                    implicitHeight: 22
                                    hoverEnabled: true
                                    onClicked: pane.tab = modelData.key
                                    background: Rectangle {
                                        radius: 5
                                        color: tBtn.active ? pane.c.card : "transparent"
                                    }
                                    contentItem: Item {
                                        Text {
                                            id: tLbl
                                            anchors.centerIn: parent
                                            text: tBtn.modelData.label
                                            font.family: "Schibsted Grotesk"; font.pixelSize: 12
                                            font.weight: tBtn.active ? Font.DemiBold : Font.Medium
                                            color: tBtn.active ? pane.c.text : pane.c.muted
                                        }
                                    }
                                }
                            }
                        }
                    }
                    OButton {                // changed here: back to Ornis's version
                        visible: pane.edited
                        kind: "quiet"; iconName: "restore"; iconSize: 15; height_: 30; text: app.t.preview_restore
                        onClicked: pane.code = pane.original
                    }
                    OButton {
                        kind: "quiet"; iconName: "copy"; iconSize: 15; height_: 30; tip: app.t.copy_code
                        onClicked: app.copy(pane.code)
                    }
                    OButton {
                        kind: "quiet"; iconName: "note"; iconSize: 15; height_: 30; tip: app.t.send_notes
                        onClicked: app.savePreviewToNotes(pane.title || "Ornis", pane.code)
                    }
                    OButton {
                        kind: "quiet"; iconName: "export"; iconSize: 15; height_: 30; tip: app.t.preview_save_file
                        onClicked: saveDialog.open()
                    }
                    OButton {
                        kind: "quiet"; iconName: "close"; iconSize: 15; height_: 30; tip: app.t.close
                        onClicked: pane.close()
                    }
                }
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: pane.c.line }
            }

            // Body: the artifact drawn, or the text
            Loader {
                id: webLoader
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: active && pane.tab === "render" && status === Loader.Ready
                active: pane.open && pane.artifact !== ""
                source: "ArtifactWeb.qml"
                onLoaded: item.page = Qt.binding(() => app.artifactUrl(pane.lang, pane.code, theme.dark))
            }
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: !webLoader.visible
                clip: true
                ScrollBar.vertical.policy: ScrollBar.AsNeeded

                Item {
                    width: parent.width
                    implicitHeight: pane.tab === "render" && pane.canRender && !pane.web ? renderedText.implicitHeight + 36 : codeRow.implicitHeight + 32

                    TextEdit {
                        id: renderedText
                        visible: pane.tab === "render" && pane.canRender && !pane.web
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 18 }
                        readOnly: true
                        selectByMouse: true
                        textFormat: TextEdit.RichText
                        wrapMode: Text.Wrap
                        text: pane.visible && visible ? (
                            pane.lang.toLowerCase() === "html" ? pane.code
                            : app.markdown(pane.code, pane.c.accent, app.textSize, pane.c.line, pane.c.field)
                        ) : ""
                        font.family: "Schibsted Grotesk"; font.pixelSize: app.textSize
                        color: pane.c.body
                        selectionColor: pane.c.accentLine
                        onLinkActivated: link => app.openLink(link)
                    }

                    RowLayout {
                        id: codeRow
                        visible: !(pane.tab === "render" && pane.canRender) || (pane.tab === "render" && pane.web && !webLoader.visible)
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 16 }
                        spacing: 12
                        Text {
                            Layout.alignment: Qt.AlignTop
                            text: {
                                const n = Math.max(1, (pane.code || "").split("\n").length)
                                const out = []
                                for (let i = 1; i <= n; i++) out.push(i)
                                return out.join("\n")
                            }
                            horizontalAlignment: Text.AlignRight
                            font.family: "JetBrains Mono"; font.pixelSize: 13
                            color: pane.c.faint
                            lineHeight: 1.35
                        }
                        Rectangle { Layout.fillHeight: true; Layout.preferredWidth: 1; color: pane.c.hairline }
                        TextEdit {               // the code, changed in place (the drawing follows after a pause)
                            id: codeEdit
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignTop
                            selectByMouse: true
                            persistentSelection: true
                            text: pane.code
                            onTextChanged: if (activeFocus) codeTimer.restart()
                            Timer { id: codeTimer; interval: 450; onTriggered: pane.code = codeEdit.text }
                            Accessible.name: app.t.preview_tab_code
                            wrapMode: Text.WrapAnywhere
                            font.family: "JetBrains Mono"; font.pixelSize: 13
                            color: pane.c.text
                            selectionColor: pane.c.accentLine
                        }
                    }
                }
            }
        }
    }

    // « Demander une modification »: the next message of the conversation, about this artifact
    Rectangle {
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom; leftMargin: 1 }
        height: askRow.implicitHeight + 20
        color: pane.c.chrome
        Rectangle { width: parent.width; height: 1; color: pane.c.line }
        RowLayout {
            id: askRow
            anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; leftMargin: 12; rightMargin: 10 }
            spacing: 8
            OTextField {
                id: askField
                Layout.fillWidth: true
                iconName: "ornis"
                placeholderText: app.t.preview_ask_ph
                onAccepted: askSend.clicked()
            }
            OButton {
                id: askSend
                kind: "primary"; iconName: "send"; height_: 34
                tip: app.t.preview_ask
                enabled: askField.text.trim() !== "" && !chat.busy
                onClicked: {
                    if (!enabled) return
                    const fence = "```" + (pane.lang || "") + "\n" + pane.code + "\n```"
                    pane.changeRequested(app.t.preview_ask_message.replace("%1", pane.title || pane.lang).replace("%2", askField.text.trim())
                                         + (pane.edited ? "\n\n" + app.t.preview_ask_current + "\n\n" + fence : ""))
                    askField.text = ""
                }
            }
        }
    }

    FileDialog {
        id: saveDialog
        title: app.t.preview_save_file
        fileMode: FileDialog.SaveFile
        currentFile: app.exportUrl(pane.title || "code")
        onAccepted: app.savePreviewToFile(selectedFile, pane.code)
    }
}

