// One message. Mine: a tinted bubble on the right, then on hover its time, copy and (the last one) edit. Ornis's:
// its mark, the Markdown text (links open in Plume, Notes, Tâches or the browser), what it used to answer (unless
// hidden in the settings), then its time, copy (and another answer for the last one).
// While it writes (streaming): what it is looking at, with the text so far.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Item {
    id: msg
    property var message: ({})
    property bool last
    property bool lastMine
    // « Modifier » on my last question (Work: once the cloud has it; Code sets it itself)
    // any of my questions (Ornis answers again from there; what followed it is replaced)
    property bool editable: mine && !chat.busy && !String(message.id || "").startsWith("local-")
    // the answers given before this one (« Régénérer », an edited question): read again with ‹ › (-1: this one)
    readonly property var versions: message.versions || []
    property int version: -1
    readonly property bool olderShown: version >= 0 && version < versions.length - 1
    readonly property string answer: olderShown ? String(versions[version].content || "") : String(message.content || "")
    onVersionsChanged: version = -1
    property bool streaming
    // Bot chat: only the « is typing » pose — no tools, thoughts or computer cards
    property bool chatOnly: false
    // a bot's chat: its face (not the mascot) beside a speech bubble, its name above, as a messaging app
    property var botFace: null
    property string botName: ""
    readonly property bool botBubble: chatOnly && !!botFace && !compactCard
    signal editRequested()
    signal imageRequested(var images, int index)
    property bool localFiles: false      // Code: the files are on this computer, a click asks for them (fileRequested)
    signal fileRequested(string path)
    readonly property var c: theme.c
    readonly property bool mine: message.role === "human"
    readonly property int size: app.textSize
    // « /compact »: my command is a divider, Ornis's answer a card (its first line, the summary folded under it)
    readonly property bool compactAsk: mine && !!message.compact
    readonly property bool compactCard: !mine && !!message.compactAnswer
    property bool summaryOpen: false
    readonly property string compactHead: compactCard ? String(message.content || "").split("\n\n")[0].replace(/\*\*/g, "") : ""
    readonly property string compactBody: compactCard ? String(message.content || "").split("\n\n").slice(1).join("\n\n") : ""
    implicitHeight: compactAsk ? compactDivider.implicitHeight : mine ? mineColumn.implicitHeight : ornisColumn.implicitHeight

    HoverHandler { id: hover }
    // a 👎 just given: « what was wrong? » under the answer. Kept by the conversation ({id, reason, comment, share}):
    // the list rebuilds its rows at every change of the conversation, a property of the row would close it at once
    property var why: ({})
    // who keeps the votes: the Chat (chat, its answers have cloud ids) or Code and Bots (CodeView: code, rows « votable »)
    property var voter: chat
    property var reasons: ["wrong", "not_asked", "didnt_act", "too_long", "other"]
    property string shareNote: app.t.vote_share_note
    readonly property bool votable: /^\d+$/.test(String(message.id)) || message.votable === true
    signal whyEdited(var state)
    readonly property bool whyOpen: !!why && why.id === String(message.id || "")
    function setWhy(key, value) { const s = Object.assign({}, why); s[key] = value; whyEdited(s) }

    // ---- « /compact » asked: a divider across the conversation -------------------------------------------------
    RowLayout {
        id: compactDivider
        visible: msg.compactAsk
        width: parent.width
        spacing: 10
        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: msg.c.line }
        Icon { name: "collapse"; size: 13; color: msg.c.muted }
        Text {
            text: app.t.context_compacted_card
            font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
            font.capitalization: Font.AllUppercase; font.letterSpacing: 0.8
            color: msg.c.muted
        }
        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: msg.c.line }
    }

    // ---- mine ----------------------------------------------------------------------------------------------
    Column {
        id: mineColumn
        visible: msg.mine && !msg.compactAsk
        anchors.right: parent.right
        width: parent.width
        spacing: 2
        Rectangle {                       // the question that started a goal (Work job), a deep research, or asked for a plan
            visible: !!msg.message.work || !!msg.message.plan || !!msg.message.askMode
            anchors.right: parent.right
            width: workChip.implicitWidth + 18; height: 22; radius: 11
            color: msg.message.plan ? msg.c.saffronTint : msg.c.tint
            Row {
                id: workChip
                anchors.centerIn: parent
                spacing: 5
                Icon { anchors.verticalCenter: parent.verticalCenter; name: msg.message.plan ? "list" : msg.message.askMode ? "chat" : msg.message.research ? "search" : "flag"; size: 12
                       color: msg.message.plan ? msg.c.saffronInk : msg.c.tintText }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: msg.message.plan ? app.t.mode_plan + " · " + app.t.plan_readonly : msg.message.askMode ? app.t.mode_ask + " · " + app.t.plan_readonly
                          : msg.message.research ? app.t.research_card : app.t.mode_goal
                    font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold
                    color: msg.message.plan ? msg.c.saffronInk : msg.c.tintText
                }
            }
        }
        Rectangle {                       // what Plume had open with the question (a message, an event, a contact)
            visible: !!msg.message.about
            anchors.right: parent.right
            width: aboutChip.implicitWidth + 18; height: 22; radius: 11
            color: msg.c.hover
            border.width: 1; border.color: msg.c.line
            Row {
                id: aboutChip
                anchors.centerIn: parent
                spacing: 5
                Icon { anchors.verticalCenter: parent.verticalCenter; name: "link"; size: 12; color: msg.c.muted }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    width: Math.min(implicitWidth, msg.width * 0.82 - 40)
                    text: msg.message.about || ""
                    elide: Text.ElideRight
                    font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.Medium
                    color: msg.c.muted
                }
            }
        }
        Flow {                            // the files sent with the question
            anchors.right: parent.right
            width: msg.width * 0.82
            layoutDirection: Qt.RightToLeft
            spacing: 6
            bottomPadding: (msg.message.content || "") !== "" ? 4 : 0
            visible: (msg.message.files || []).length > 0
            Repeater {
                model: (msg.message.files || []).slice().reverse()     // right to left: the first one ends up first
                AttachmentChip {
                    required property var modelData
                    name: modelData.name; kind: modelData.kind; thumb: modelData.thumb
                    openable: msg.localFiles || modelData.file_id !== "" || (modelData.kind === "image" && modelData.thumb !== "")
                    // an image opens in large here (the viewer); any other file where it is kept, in the Drive
                    onOpenRequested: {
                        if (msg.localFiles) {
                            msg.fileRequested(String(modelData.path || modelData.name || ""))
                        } else if (modelData.kind === "image") {
                            const images = (msg.message.files || []).filter(f => f.kind === "image")
                            msg.imageRequested(images, images.indexOf(modelData))
                        } else {
                            app.openCloud("/f/" + modelData.file_id)
                        }
                    }
                }
            }
        }
        Rectangle {
            id: bubble
            visible: (msg.message.content || "") !== ""
            anchors.right: parent.right
            // measured on the text without wrapping: the wrapped text's own width changes with the bubble's, and a short
            // message of two words (« bah go ») wrapped, shrank, unwrapped… for ever: the window froze (seen 02/11 in Code)
            width: Math.min(Math.ceil(mineMeasure.implicitWidth) + 34, msg.width * 0.82)
            height: mineText.implicitHeight + 22
            radius: 14
            color: msg.c.tint
            Text {
                id: mineMeasure
                visible: false
                text: mineText.text
                textFormat: Text.PlainText
                font: mineText.font
            }
            TextEdit {
                id: mineText
                anchors.fill: parent; anchors.margins: 11; anchors.leftMargin: 16; anchors.rightMargin: 16
                readOnly: true; selectByMouse: true
                Accessible.name: app.t.you          // a screen reader says who wrote it, then the text
                // only my messages (a hidden one is laid out all the same), and a long paste not drawn whole
                text: !msg.mine ? "" : String(msg.message.content || "").length > 16000
                      ? String(msg.message.content).slice(0, 16000) + "\n…" : (msg.message.content || "")
                wrapMode: Text.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: msg.size
                color: msg.c.text
                selectionColor: msg.c.accentLine
            }
        }
        Row {
            anchors.right: parent.right
            opacity: hover.hovered ? 1 : 0
            spacing: 2
            Behavior on opacity { NumberAnimation { duration: 120 } }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                rightPadding: 6
                text: msg.message.when || ""
                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                color: msg.c.faint
            }
            OButton {
                visible: msg.editable
                kind: "quiet"; iconName: "edit"; iconSize: 15; height_: 28; tip: app.t.edit
                onClicked: msg.editRequested()
            }
            OButton { kind: "quiet"; iconName: "copy"; iconSize: 15; height_: 28; tip: app.t.copy; onClicked: app.copy(msg.message.content) }
        }
    }

    // ---- Ornis ---------------------------------------------------------------------------------------------
    RowLayout {
        id: ornisColumn
        visible: !msg.mine && !msg.compactAsk
        width: parent.width
        spacing: 14

        BotFace {
            visible: msg.botBubble
            Layout.alignment: Qt.AlignTop
            Layout.topMargin: botNameText.visible ? botNameText.implicitHeight + 4 : 0
            face: msg.botFace || ({})
            size: 30
            busy: msg.streaming
        }
        Rectangle {
            visible: !msg.botBubble
            Layout.alignment: Qt.AlignTop
            implicitWidth: 30; implicitHeight: 30; radius: 15
            color: "transparent"
            Icon { anchors.centerIn: parent; name: "ornis-mascot"; thinking: msg.streaming; size: 30 }
            SequentialAnimation on opacity {
                running: msg.streaming && Qt.styleHints.reduceMotion !== true
                loops: Animation.Infinite
                NumberAnimation { from: 1; to: 0.55; duration: 700; easing.type: Easing.InOutSine }
                NumberAnimation { from: 0.55; to: 1; duration: 700; easing.type: Easing.InOutSine }
                onRunningChanged: if (!running) parent.opacity = 1
            }
        }

        ColumnLayout {
            id: ornisBody
            Layout.fillWidth: true
            spacing: 8

            Text {
                id: botNameText
                visible: msg.botBubble && msg.botName !== ""
                text: msg.botName
                font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold
                color: (msg.botFace && msg.botFace.color) || msg.c.muted
                Layout.bottomMargin: -4
            }
            // what Ornis is doing, while it writes (its live reasoning says « thinking » already, until a tool runs)
            // only what it does for real (« Consulte votre agenda… »): « Ornis réfléchit » is the line above the box
            OrnisThinking {
                Layout.alignment: Qt.AlignLeft
                // bot chat: its status bubble above the box says what it does, nothing here
                visible: !msg.chatOnly && msg.streaming && chat.working !== app.t.ornis_working
                         && !(reasoning.live && reasoning.visible && (chat.workingTools || []).length === 0 && !(chat.computer.phase || ""))
                text: chat.working
                showMascot: false
            }
            // what it thought before answering, folded
            ReasoningBlock {
                id: reasoning
                Layout.fillWidth: true
                visible: !msg.chatOnly
                text: msg.streaming ? chat.streamReasoning : String(msg.message.reasoning || "")
                live: msg.streaming && (msg.message.content || "") === ""
                steps: stepsBlock
            }
            // what it did: « 4 étapes · Agenda, Notes », unfolded into each tool call (live while it works); once
            // answered, on the reasoning's line when there is one (one line above the answer, as Claude shows it)
            StepsBlock {
                id: stepsBlock
                Layout.fillWidth: true
                message: msg.message
                streaming: msg.streaming
                headless: reasoning.joined
                visible: !msg.chatOnly
                         && ((msg.message.tools || []).length > 0 || (msg.streaming && chat.liveSteps.length > 0))
                         && (msg.streaming || app.prefs.show_tools !== false)
            }
            // a command or action Ornis runs, or asks to run, on this computer (with live output + Stop)
            Rectangle {
                visible: !msg.chatOnly && msg.streaming && ((chat.computer.command || "") !== "" || (chat.computer.summary || "") !== "")
                Layout.fillWidth: true
                implicitHeight: computerBox.implicitHeight + 20
                radius: 8
                color: chat.computer.phase === "asking" ? msg.c.saffronTint : msg.c.field
                border.width: 1
                border.color: chat.computer.phase === "asking" ? msg.c.saffron : msg.c.line
                ColumnLayout {
                    id: computerBox
                    anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: 10 }
                    spacing: 6
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Text {
                            id: commandText
                            Layout.fillWidth: true
                            text: (chat.computer.command || "") !== ""
                                  ? "$ " + chat.computer.command
                                  : (chat.computer.summary || "")
                            wrapMode: Text.WrapAnywhere
                            maximumLineCount: 4
                            elide: Text.ElideRight
                            font.family: (chat.computer.command || "") !== "" ? "JetBrains Mono" : "Schibsted Grotesk"
                            font.pixelSize: 12
                            font.weight: (chat.computer.command || "") !== "" ? Font.Normal : Font.DemiBold
                            color: chat.computer.phase === "asking" ? msg.c.saffronInk : msg.c.text
                        }
                        Text {
                            visible: (chat.computer.seconds || 0) > 0
                            text: chat.computer.seconds + " s"
                            font.family: "Schibsted Grotesk"; font.pixelSize: 11
                            font.features: { "tnum": 1 }
                            color: msg.c.muted
                        }
                        OButton {
                            visible: chat.computer.phase === "running" && (chat.computer.job || "") !== ""
                            kind: "quiet"
                            text: app.t.stop
                            height_: 24
                            onClicked: app.stopLocalCommand(chat.computer.job)
                        }
                    }
                    Text {
                        visible: (chat.computer.output || "") !== ""
                        Layout.fillWidth: true
                        text: String(chat.computer.output || "").split("\n").slice(-8).join("\n")
                        wrapMode: Text.WrapAnywhere
                        maximumLineCount: 8
                        elide: Text.ElideLeft
                        font.family: "JetBrains Mono"; font.pixelSize: 11
                        color: msg.c.muted
                    }
                }
            }

            // the answer to « /compact »: what was saved, the summary on demand
            AbstractButton {
                id: compactHeader
                visible: msg.compactCard
                Layout.fillWidth: true
                implicitHeight: compactRow.implicitHeight + 20
                hoverEnabled: true
                onClicked: msg.summaryOpen = !msg.summaryOpen
                Accessible.name: msg.compactHead
                Accessible.role: Accessible.Button
                background: Rectangle {
                    radius: 10
                    color: compactHeader.hovered ? msg.c.hover : msg.c.card
                    border.width: 1; border.color: msg.c.line
                }
                contentItem: Item {
                    RowLayout {
                        id: compactRow
                        anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; leftMargin: 12; rightMargin: 12 }
                        spacing: 10
                        Rectangle {
                            implicitWidth: 28; implicitHeight: 28; radius: 8
                            color: msg.c.tint
                            Icon { anchors.centerIn: parent; name: "collapse"; size: 15; color: msg.c.tintText }
                        }
                        Text {
                            Layout.fillWidth: true
                            text: msg.compactHead
                            wrapMode: Text.Wrap
                            font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
                            color: msg.c.text
                        }
                        Text {
                            visible: msg.compactBody !== ""
                            text: msg.summaryOpen ? app.t.context_summary_hide : app.t.context_summary_show
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.Medium
                            color: msg.c.accent
                        }
                        Icon {
                            visible: msg.compactBody !== ""
                            name: "chevronDown"; size: 14; color: msg.c.muted
                            rotation: msg.summaryOpen ? 180 : 0
                        }
                    }
                }
            }

            Text {                       // an earlier answer, read again (and the question as it was, if it was changed)
                visible: msg.olderShown
                Layout.fillWidth: true
                text: app.t.version_older + (msg.olderShown && msg.versions[msg.version].question
                                             ? " · « " + msg.versions[msg.version].question + " »" : "")
                elide: Text.ElideRight
                font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                color: msg.c.muted
            }
            TextMetrics {                // the answer on one line, to size the bot's bubble to a short message (bots only)
                id: bubbleMeasure
                text: msg.botBubble ? msg.answer.replace(/[*_`#>]/g, "") : ""
                font.family: "Schibsted Grotesk"; font.pixelSize: msg.size
            }
            ColumnLayout {
                id: bodyBlocks
                Layout.fillWidth: !msg.botBubble
                // a bot: a speech bubble (a card that fits the text, up to most of the column)
                Layout.preferredWidth: msg.botBubble ? Math.min(Math.ceil(bubbleMeasure.advanceWidth) + 4, msg.width * 0.78 - 44 - 28) : -1
                Layout.leftMargin: msg.botBubble ? 14 : 0
                Layout.topMargin: msg.botBubble ? 10 : 0
                Layout.bottomMargin: msg.botBubble ? 10 : 0
                spacing: 8
                Loader {                 // the bubble behind the text: made only in a bot's chat (every message of a
                                         // project paid for it, invisible: scrolling a long session lagged, 09/11)
                    active: msg.botBubble && !msg.mine && !msg.compactAsk
                    parent: msg               // a plain Item: no layout places it
                    z: -1
                    sourceComponent: Rectangle {
                        visible: bodyBlocks.visible
                        x: ornisColumn.x + ornisBody.x + bodyBlocks.x - 14; y: ornisColumn.y + ornisBody.y + bodyBlocks.y - 10
                        width: bodyBlocks.width + 28; height: bodyBlocks.height + 20
                        radius: 16
                        color: msg.c.card
                        border.width: 1; border.color: msg.c.line
                        Rectangle { width: 14; height: 14; radius: 4; color: parent.color; anchors.left: parent.left; anchors.top: parent.top
                                    border.width: 0; z: -1 }
                    }
                }
                readonly property var blocks: app.messageBlocks(msg.compactCard ? msg.compactBody : msg.answer)
                visible: blocks.length > 0 && (!msg.compactCard || msg.summaryOpen)
                // Kept block by block: while a reply is written, only its last block (the one growing) is laid out
                // again. A new array as the model rebuilt every block at each step of the text, and a long answer
                // froze the window (seen 02/11 while a plan ran).
                ListModel { id: blockModel }
                onBlocksChanged: sync()
                Component.onCompleted: sync()
                function sync() {
                    const b = blocks
                    for (let i = 0; i < b.length; i++) {
                        if (i >= blockModel.count) {
                            blockModel.append(b[i])
                            continue
                        }
                        const o = blockModel.get(i)
                        if (o.kind !== b[i].kind || o.text !== b[i].text || o.code !== b[i].code || o.lang !== b[i].lang
                                || o.previewable !== b[i].previewable || o.artifact !== b[i].artifact || o.title !== b[i].title
                                || o.shown !== b[i].shown || o.more !== b[i].more)
                            blockModel.set(i, b[i])
                    }
                    if (blockModel.count > b.length)
                        blockModel.remove(b.length, blockModel.count - b.length)
                }

                Repeater {
                    model: blockModel
                    Item {
                        id: blk
                        readonly property var modelData: ({ kind: model.kind, text: model.text, lang: model.lang, code: model.code,
                                                            lines: model.lines, previewable: model.previewable,
                                                            artifact: model.artifact, title: model.title,
                                                            shown: model.shown, more: model.more })
                        // a page, a drawing, a diagram: a card that opens it drawn beside the conversation
                        readonly property bool isArtifact: modelData.kind === "code" && !!modelData.artifact
                        Layout.fillWidth: true
                        implicitHeight: isArtifact ? artifactCard.implicitHeight : modelData.kind === "code" ? codeCard.implicitHeight
                                        : proseBody.implicitHeight + (proseMore.visible ? proseMore.implicitHeight + 6 : 0)

                        TextEdit {
                            id: proseBody
                            visible: blk.modelData.kind !== "code"
                            width: parent.width
                            readOnly: true
                            selectByMouse: true
                            Accessible.name: app.t.app_name
                            textFormat: TextEdit.RichText
                            text: visible && blk.modelData.text ? app.markdown(blk.modelData.text, msg.c.accent, msg.size, msg.c.line, msg.c.field) : ""
                            wrapMode: width > 80 ? Text.Wrap : Text.NoWrap     // as the code below: not at 0 px
                            font.family: "Schibsted Grotesk"; font.pixelSize: msg.size
                            color: msg.c.body
                            selectionColor: msg.c.accentLine
                            onLinkActivated: link => app.openLink(link)
                            // a web link (a numbered source): its site and page on hover
                            ToolTip.visible: /^https?:/.test(hoveredLink)
                            ToolTip.delay: 300
                            ToolTip.text: hoveredLink.replace(/^https?:\/\/(www\.)?/, "").replace(/[?#].*$/, "").slice(0, 70)
                            MouseArea {
                                anchors.fill: parent
                                acceptedButtons: Qt.NoButton
                                cursorShape: proseBody.hoveredLink ? Qt.PointingHandCursor : Qt.IBeamCursor
                            }
                        }
                        Text {                      // a very long reply: the rest is not drawn (« Copier » gives it)
                            id: proseMore
                            visible: blk.modelData.kind !== "code" && blk.modelData.more > 0
                            anchors.top: proseBody.bottom; anchors.topMargin: 6
                            width: parent.width
                            wrapMode: Text.Wrap
                            text: visible ? app.t.reply_more_hidden : ""
                            font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.italic: true
                            color: msg.c.muted
                        }

                        AbstractButton {
                            id: artifactCard
                            visible: blk.isArtifact
                            width: Math.min(parent.width, 460)
                            implicitHeight: 64
                            hoverEnabled: true
                            enabled: !msg.streaming
                            onClicked: app.openPreview(blk.modelData.title || app.t.preview_title, blk.modelData.lang, blk.modelData.code)
                            Accessible.name: (blk.modelData.title || "") + ", " + app.t.artifact_open
                            background: Rectangle {
                                radius: 12
                                color: artifactCard.hovered ? msg.c.hover : msg.c.card
                                border.width: 1; border.color: artifactCard.hovered ? msg.c.accentLine : msg.c.line
                            }
                            contentItem: RowLayout {
                                spacing: 12
                                Item { implicitWidth: 2 }
                                Rectangle {
                                    implicitWidth: 40; implicitHeight: 40; radius: 10
                                    color: msg.c.tint
                                    Icon { anchors.centerIn: parent; size: 20; color: msg.c.tintText
                                           name: blk.modelData.artifact === "mermaid" ? "listBullet" : blk.modelData.artifact === "svg" ? "image" : "globe" }
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 2
                                    Text {
                                        Layout.fillWidth: true
                                        text: blk.modelData.title || app.t.preview_title
                                        elide: Text.ElideRight
                                        font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
                                        color: msg.c.text
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: (msg.streaming ? app.t.code_running : app.t["artifact_" + (blk.modelData.artifact === "mermaid" ? "diagram" : blk.modelData.artifact)])
                                              + (blk.modelData.lines > 1 ? " · " + app.t.artifact_lines.replace("%1", blk.modelData.lines) : "")
                                        elide: Text.ElideRight
                                        font.family: "JetBrains Mono"; font.pixelSize: 11
                                        color: msg.c.muted
                                    }
                                }
                                Text {
                                    text: app.t.artifact_open
                                    visible: !msg.streaming
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.Medium
                                    color: msg.c.accent
                                }
                                Icon { visible: !msg.streaming; name: "chevronRight"; size: 14; color: msg.c.accent }
                                Item { implicitWidth: 6 }
                            }
                        }

                        Rectangle {
                            id: codeCard
                            visible: blk.modelData.kind === "code" && !blk.isArtifact
                            width: parent.width
                            implicitHeight: codeCol.implicitHeight
                            radius: 10
                            color: msg.c.field
                            border.width: 1; border.color: msg.c.line
                            property bool justCopied: false
                            Timer { id: copiedTimer; interval: 1800; onTriggered: codeCard.justCopied = false }

                            ColumnLayout {
                                id: codeCol
                                width: parent.width
                                spacing: 0

                                Rectangle {
                                    Layout.fillWidth: true
                                    implicitHeight: 34
                                    radius: 10
                                    color: msg.c.chrome
                                    Rectangle {
                                        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                                        height: 10; color: msg.c.chrome
                                    }
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 12; anchors.rightMargin: 8
                                        spacing: 6
                                        Icon { name: "code"; size: 14; color: msg.c.muted }
                                        Text {
                                            text: blk.modelData.lang || "code"
                                            font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                                            color: msg.c.muted
                                        }
                                        Item { Layout.fillWidth: true }
                                        OButton {
                                            visible: !!blk.modelData.previewable
                                            kind: "quiet"
                                            iconName: "eye"
                                            iconSize: 14
                                            height_: 26
                                            text: app.t.preview_open
                                            onClicked: app.openPreview(chat.title || app.t.preview_title, blk.modelData.lang || "code", blk.modelData.code || "")
                                        }
                                        OButton {
                                            kind: "quiet"
                                            iconName: codeCard.justCopied ? "check" : "copy"
                                            iconSize: 14
                                            height_: 26
                                            text: codeCard.justCopied ? app.t.copied : app.t.copy_code
                                            onClicked: {
                                                app.copy(blk.modelData.code || "")
                                                codeCard.justCopied = true
                                                copiedTimer.restart()
                                            }
                                        }
                                    }
                                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: msg.c.line }
                                }

                                TextEdit {
                                    Layout.fillWidth: true
                                    // its own width never feeds the layout: wrapped, it changes with the width it gets,
                                    // and with the list held at its end the two chased each other for ever (seen 02/11:
                                    // a conversation of Code froze the window once reopened)
                                    Layout.preferredWidth: 1
                                    Layout.margins: 12
                                    readOnly: true
                                    selectByMouse: true
                                    text: blk.modelData.shown || blk.modelData.code || ""
                                    // no wrapping before its width is known: at 0 px every character was a line, the
                                    // card thousands of pixels high, and the list held at its end chased it for ever
                                    wrapMode: width > 80 ? Text.WrapAnywhere : Text.NoWrap
                                    font.family: "JetBrains Mono"; font.pixelSize: Math.max(12, msg.size - 2)
                                    color: msg.c.text
                                    selectionColor: msg.c.accentLine
                                }
                                Text {              // a long block: its first lines only (« Copier le code » gives all)
                                    visible: blk.modelData.more > 0
                                    Layout.fillWidth: true
                                    Layout.leftMargin: 12; Layout.rightMargin: 12; Layout.bottomMargin: 10
                                    wrapMode: Text.Wrap
                                    text: visible ? app.t.code_more_lines.replace("%1", blk.modelData.more.toLocaleString(Qt.locale(), "f", 0)) : ""
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.italic: true
                                    color: msg.c.muted
                                }
                            }
                        }
                    }
                }
            }

            RowLayout {                  // a memory stored while answering, as « Memory updated » elsewhere: see or forget it
                visible: !msg.streaming && !!msg.message.memorized
                spacing: 6
                Icon { name: "history"; size: 14; color: msg.c.muted }
                Text {
                    text: app.t.memory_saved
                    font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.Medium
                    color: msg.c.muted
                }
                OButton { kind: "quiet"; text: app.t.memory_manage; height_: 24; onClicked: win.openProfile() }
            }
            Flow {                       // the ideas the answer ends with (« → … »): one click asks it
                readonly property var ideas: msg.last && !msg.streaming ? app.followups(msg.message.content || "") : []
                visible: ideas.length > 0 && !chat.busy && chat.pending.length === 0
                Layout.fillWidth: true
                spacing: 6
                Repeater {
                    model: parent.ideas
                    AbstractButton {
                        id: idea
                        required property string modelData
                        implicitWidth: ideaText.implicitWidth + 30; implicitHeight: 30
                        hoverEnabled: true
                        onClicked: chat.send(modelData)
                        Accessible.name: modelData
                        background: Rectangle {
                            radius: 15
                            color: idea.hovered ? msg.c.tint : msg.c.card
                            border.width: 1; border.color: idea.hovered ? msg.c.accentLine : msg.c.line
                        }
                        contentItem: Item {
                            Row {
                                anchors.centerIn: parent
                                spacing: 6
                                Icon { anchors.verticalCenter: parent.verticalCenter; name: "arrow"; size: 12; color: msg.c.accent }
                                Text {
                                    id: ideaText
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: idea.modelData
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                                    color: msg.c.text
                                }
                            }
                        }
                    }
                }
            }
            Row {                        // copy, read, another answer, the time; not while an action waits for a yes
                visible: !msg.streaming && (msg.message.content || "") !== "" && !(msg.last && chat.pending.length > 0 && !chat.busy)
                readonly property bool reading: chat.voice.speaking === String(msg.message.id)
                opacity: hover.hovered || msg.last || reading ? 1 : 0
                spacing: 2
                Behavior on opacity { NumberAnimation { duration: 120 } }
                // ‹ 2/3 ›: the earlier answers, to read again (the conversation goes on from the latest)
                Row {
                    visible: msg.versions.length > 1
                    anchors.verticalCenter: parent.verticalCenter
                    readonly property int at: msg.version < 0 ? msg.versions.length - 1 : msg.version
                    OButton { kind: "quiet"; iconName: "chevronLeft"; iconSize: 13; height_: 26; enabled: parent.at > 0; tip: app.t.version_previous
                              onClicked: msg.version = parent.at - 1 }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: (parent.at + 1) + "/" + msg.versions.length
                        font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.Medium
                        color: msg.c.muted
                    }
                    OButton { kind: "quiet"; iconName: "chevronRight"; iconSize: 13; height_: 26; enabled: parent.at < msg.versions.length - 1; tip: app.t.version_next
                              onClicked: msg.version = parent.at + 1 >= msg.versions.length - 1 ? -1 : parent.at + 1 }
                }
                OButton { kind: "quiet"; iconName: "copy"; iconSize: 15; height_: 28; tip: app.t.copy; onClicked: app.copy(msg.answer) }
                OButton {                    // the system's voice, on this device (ornis_voice: hidden without one)
                    visible: chat.voice.canSpeak
                    kind: "quiet"; iconName: parent.reading ? "stop" : "volume"; iconSize: 15; height_: 28
                    tip: parent.reading ? app.t.read_stop : app.t.read_aloud
                    onClicked: chat.voice.speak(String(msg.message.id), msg.answer)
                }
                OButton {                    // « Bifurquer » : a new conversation from here (this one stays as it is)
                    visible: /^\d+$/.test(String(msg.message.id)) && !chat.busy && !msg.olderShown
                    kind: "quiet"; iconName: "subtask"; iconSize: 15; height_: 28; tip: app.t.fork_tip
                    onClicked: chat.fork(String(msg.message.id))
                }
                OButton {                    // 👍 / 👎: a signal only (one row per answer in the cloud), again to take it back
                    visible: msg.votable
                    kind: "quiet"; iconName: "thumbUp"; iconSize: 15; height_: 28; tip: app.t.vote_up
                    onClicked: msg.voter.vote(String(msg.message.id), 1)
                    background: Rectangle { radius: 6; color: msg.message.vote === 1 ? msg.c.tint : parent.hovered ? msg.c.hover : "transparent" }
                }
                OButton {
                    visible: msg.votable
                    kind: "quiet"; iconName: "thumbDown"; iconSize: 15; height_: 28; tip: app.t.vote_down
                    onClicked: {
                        msg.whyEdited(msg.message.vote !== -1 ? { id: String(msg.message.id), reason: "", comment: "", share: false } : {})
                        msg.voter.vote(String(msg.message.id), -1)
                    }
                    background: Rectangle { radius: 6; color: msg.message.vote === -1 ? msg.c.tint : parent.hovered ? msg.c.hover : "transparent" }
                }
                OButton {
                    visible: msg.last && !chat.busy && chat.pending.length === 0
                    kind: "quiet"; iconName: "refresh"; iconSize: 15; height_: 28; tip: app.t.regenerate
                    onClicked: chat.regenerate()
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    leftPadding: 6
                    text: msg.message.when || ""
                    opacity: hover.hovered ? 1 : 0          // the time on hover only, as the other assistants
                    font.family: "Schibsted Grotesk"; font.pixelSize: 12
                    color: msg.c.faint
                }
            }
            // now and then (ornis_core/feedback.py): « Was it useful? », coloured, until a choice or ✕
            Rectangle {
                id: askCard
                visible: msg.votable && msg.message.ask === true && !(msg.message.vote || 0) && !msg.streaming
                Layout.fillWidth: true
                Layout.maximumWidth: 560
                implicitHeight: askRow.implicitHeight + 20
                radius: 12
                color: msg.c.tint
                border.width: 1; border.color: msg.c.accentLine
                opacity: visible ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: 180 } }
                RowLayout {
                    id: askRow
                    anchors.left: parent.left; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: 14; anchors.rightMargin: 6
                    spacing: 8
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Text { Layout.fillWidth: true; text: app.t.vote_ask; font.family: "Schibsted Grotesk"; font.pixelSize: 14
                               font.weight: Font.DemiBold; color: msg.c.tintText; wrapMode: Text.Wrap }
                        Text { Layout.fillWidth: true; text: app.t.vote_ask_sub; font.family: "Schibsted Grotesk"; font.pixelSize: 12
                               color: msg.c.muted; wrapMode: Text.Wrap }
                    }
                    OButton { kind: "secondary"; iconName: "thumbUp"; iconSize: 14; text: app.t.vote_yes
                              onClicked: msg.voter.answerCard(String(msg.message.id), 1) }
                    OButton { kind: "secondary"; iconName: "thumbDown"; iconSize: 14; text: app.t.vote_no
                              onClicked: { msg.whyEdited({ id: String(msg.message.id), reason: "", comment: "", share: false })
                                           msg.voter.answerCard(String(msg.message.id), -1) } }
                    OButton { kind: "quiet"; iconName: "close"; iconSize: 14; height_: 28; tip: app.t.vote_close
                              onClicked: msg.voter.answerCard(String(msg.message.id), 0) }
                }
            }
            // why a 👎 (optional): a reason, a few words, and the exchange only if ticked; nothing leaves before « Envoyer »
            Rectangle {
                id: whyCard
                visible: msg.whyOpen && msg.message.vote === -1
                readonly property string reason: msg.why.reason || ""
                Layout.fillWidth: true
                Layout.maximumWidth: 560
                implicitHeight: whyCol.implicitHeight + 24
                radius: 12
                color: msg.c.card
                border.width: 1; border.color: msg.c.line
                ColumnLayout {
                    id: whyCol
                    anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 12
                    spacing: 10
                    RowLayout {
                        Layout.fillWidth: true
                        Text { Layout.fillWidth: true; text: app.t.vote_why; font.family: "Schibsted Grotesk"; font.pixelSize: 14
                               font.weight: Font.DemiBold; color: msg.c.text }
                        OButton { kind: "quiet"; iconName: "close"; iconSize: 12; height_: 24; tip: app.t.close; onClicked: msg.whyEdited({}) }
                    }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 6
                        Repeater {
                            model: msg.reasons
                            AbstractButton {
                                id: reasonChip
                                required property string modelData
                                readonly property bool on: whyCard.reason === modelData
                                implicitWidth: reasonText.implicitWidth + 24; implicitHeight: 28
                                hoverEnabled: true
                                onClicked: msg.setWhy("reason", on ? "" : modelData)
                                Accessible.role: Accessible.RadioButton
                                Accessible.checked: on
                                Accessible.name: reasonText.text
                                background: Rectangle { radius: 14; color: reasonChip.on ? msg.c.tint : reasonChip.hovered ? msg.c.hover : "transparent"
                                                        border.width: 1; border.color: reasonChip.on ? msg.c.accentLine : msg.c.line }
                                contentItem: Text { id: reasonText; text: app.t["vote_" + reasonChip.modelData]; horizontalAlignment: Text.AlignHCenter
                                                    verticalAlignment: Text.AlignVCenter; font.family: "Schibsted Grotesk"; font.pixelSize: 13
                                                    color: reasonChip.on ? msg.c.tintText : msg.c.text }
                            }
                        }
                    }
                    OTextField { id: whyText; Layout.fillWidth: true; placeholderText: app.t.vote_comment; maximumLength: 500
                                 Component.onCompleted: text = msg.why.comment || ""
                                 onTextEdited: msg.setWhy("comment", text) }
                    OSwitch { id: whyShare; Layout.fillWidth: true; text: app.t.vote_share; checked: !!msg.why.share
                              onToggled: msg.setWhy("share", checked) }
                    Text { visible: whyShare.checked; Layout.fillWidth: true; text: msg.shareNote; wrapMode: Text.Wrap
                           font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: msg.c.muted }
                    RowLayout {
                        Layout.fillWidth: true
                        Item { Layout.fillWidth: true }
                        OButton {
                            kind: "primary"; text: app.t.vote_send
                            enabled: whyCard.reason !== "" || whyText.text.trim() !== "" || whyShare.checked
                            onClicked: { msg.voter.voteDetail(String(msg.message.id), whyCard.reason, whyText.text, whyShare.checked); msg.whyEdited({}) }
                        }
                    }
                }
            }
        }
    }
}
