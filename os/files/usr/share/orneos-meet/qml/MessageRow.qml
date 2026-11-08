// One message of the chat. Ours on the right in Klein, the others on the left on a card, with their photo and
// name on the first of a series; a day between two days; Talk's system lines in small in the middle. A row
// carries what answers it (the quoted message), its text, its files (images in preview), a poll, the
// reactions, its thread; a voice message (or any sound) plays here, a GIF moves, a link shows its preview.
// On hover, the quick reactions pinned (👍 👀 🎉 at first), « Répondre » and the rest in a menu (forward, pin,
// Notes, Tâches, remind, translate…). A picture opens in the viewer, another file in this computer's app.
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "components"

Item {
    id: row
    readonly property var c: theme.c
    required property var model
    required property int index
    readonly property var m: model
    readonly property bool mine: m.self
    readonly property bool hovering: hover.hovered || actions.hovered || moreMenu.opened || picker.opened
    property bool compact: false
    property bool inThread: false
    readonly property bool isVoice: m.voice && m.files.length > 0
    signal replyWanted(var message)
    signal editWanted(var message)
    signal quoteClicked(int id)
    signal mentionClicked(string kind, string id)
    signal imageWanted(var file, var album)
    signal forwardWanted(var message)
    signal threadWanted(var message)
    // who reacted, asked when a reaction is hovered: {emoji: [names]}
    property var reactors: ({})
    Connections {
        target: meet
        function onReactorsRead(id, names) { if (id === row.m.id) row.reactors = names }
    }
    // the first unread when the conversation opened: « Nouveaux messages » above it
    readonly property bool unreadLine: meet.firstUnread > 0 && row.m.id === meet.firstUnread
    // a translation by Ornis, under the bubble
    property int translateRequest: -1
    property string translation: ""
    Connections {
        target: ornis
        enabled: row.translateRequest >= 0
        function onAnswered(request, kind, text) { if (request === row.translateRequest) row.translation = text }
        function onFailed(request, kind, message) { if (request === row.translateRequest) { row.translateRequest = -1; app.toast(message) } }
    }

    width: ListView.view ? ListView.view.width : 400
    // a picture folded into the album of the message before it: shown there
    visible: !m.inAlbum
    implicitHeight: m.inAlbum ? 0 : column.implicitHeight + (m.grouped ? 2 : 8)
    readonly property var album: m.album || []

    HoverHandler { id: hover }

    ColumnLayout {
        id: column
        width: parent.width
        y: row.m.grouped ? 1 : 6
        spacing: 4

        // the day
        Text { textFormat: Text.PlainText;
            visible: row.m.day !== ""
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: 10; Layout.bottomMargin: 6
            text: row.m.day
            font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
            font.capitalization: Font.AllUppercase; font.letterSpacing: 0.8
            color: row.c.faint
        }

        // « Nouveaux messages »
        RowLayout {
            visible: row.unreadLine
            Layout.fillWidth: true
            Layout.leftMargin: row.compact ? 8 : 16; Layout.rightMargin: row.compact ? 8 : 16
            Layout.topMargin: 6; Layout.bottomMargin: 4
            spacing: 10
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: row.c.famCommunicate; opacity: 0.5 }
            Text {
                text: app.t.new_messages
                font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.DemiBold
                font.capitalization: Font.AllUppercase; font.letterSpacing: 0.8
                color: row.c.famCommunicate
            }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: row.c.famCommunicate; opacity: 0.5 }
        }

        // a line of Talk (joined, left, renamed, started a call…)
        Text {
            visible: row.m.system
            Layout.fillWidth: true
            Layout.leftMargin: 40; Layout.rightMargin: 40
            horizontalAlignment: Text.AlignHCenter
            text: row.m.html + "  <span style='color:" + row.c.faint + "'>" + app.clock(row.m.time) + "</span>"
            textFormat: Text.StyledText
            wrapMode: Text.Wrap
            font.pixelSize: 12
            color: row.c.muted
            linkColor: row.c.muted
            onLinkActivated: link => row.openLink(link)
        }

        RowLayout {
            visible: !row.m.system
            Layout.fillWidth: true
            Layout.leftMargin: row.compact ? 8 : 16
            Layout.rightMargin: row.compact ? 8 : 16
            layoutDirection: row.mine ? Qt.RightToLeft : Qt.LeftToRight
            spacing: 10

            // the photo, on the first of a series (others' messages only)
            Item {
                visible: !row.mine
                Layout.alignment: Qt.AlignTop
                implicitWidth: 32; implicitHeight: 32
                RoomAvatar {
                    visible: !row.m.grouped
                    size: 32
                    source: row.m.avatar
                    name: row.m.name
                }
            }

            ColumnLayout {
                id: bubbleColumn
                Layout.maximumWidth: Math.min(row.width * (row.compact ? 0.86 : 0.72), 680)
                Layout.alignment: row.mine ? Qt.AlignRight : Qt.AlignLeft
                spacing: 3

                Text {
                    visible: !row.mine && !row.m.grouped
                    text: row.m.name.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")   // a guest names himself
                          + "  <span style='color:" + row.c.faint + ";font-weight:400'>" + app.clock(row.m.time) + "</span>"
                    textFormat: Text.StyledText
                    font.pixelSize: 13; font.weight: Font.DemiBold
                    color: row.c.text
                }

                // the bubble: ours in Klein (a little light from the top), the others' on a raised card
                Item {
                    id: bubble
                    readonly property bool bare: row.m.emojiOnly && !row.m.parent && !row.m.files.length
                    Layout.alignment: row.mine ? Qt.AlignRight : Qt.AlignLeft
                    implicitWidth: Math.min(bubbleColumn.Layout.maximumWidth, Math.max(content.implicitWidth + 24, 60))
                    implicitHeight: content.implicitHeight + (bare ? 0 : 16)
                    opacity: row.m.pending ? 0.65 : 1
                    // a right click: the message's menu (« Copier l'image » for the picture under the pointer)
                    TapHandler {
                        acceptedButtons: Qt.RightButton
                        onTapped: point => {
                            row.menuFile = null
                            for (let i = 0; i < fileCards.count; i++) {
                                const card = fileCards.itemAt(i)
                                const p = card ? card.mapFromItem(bubble, point.position.x, point.position.y) : null
                                if (card && card.image && card.contains(p)) row.menuFile = card.file
                            }
                            for (let i = 0; i < albumTiles.count; i++) {
                                const tile = albumTiles.itemAt(i)
                                const p = tile ? tile.mapFromItem(bubble, point.position.x, point.position.y) : null
                                if (tile && tile.contains(p)) row.menuFile = tile.file
                            }
                            if (!row.menuFile) {
                                const pictures = (row.album.length > 1 ? row.album : row.m.files).filter(f => (f.preview || f.local) && String(f.mime).startsWith("image/"))
                                if (pictures.length === 1) row.menuFile = pictures[0]
                            }
                            moreMenu.popupAt(bubble, true)
                        }
                    }
                    Surface {
                        anchors.fill: parent
                        visible: !bubble.bare && !row.mine && !row.m.deleted
                        radius: 16
                        color: row.m.mentioned ? row.c.saffronTint : row.c.card
                        Rectangle {
                            anchors.fill: parent; radius: 16; color: "transparent"
                            border.width: row.m.mentioned || row.m.pinned ? 1.5 : 0
                            border.color: row.m.mentioned ? row.c.saffron : Qt.alpha(row.c.saffron, 0.6)
                        }
                    }
                    Rectangle {
                        anchors.fill: parent
                        visible: !bubble.bare && (row.mine || row.m.deleted)
                        radius: 16
                        color: row.m.deleted ? row.c.hover : row.c.action
                        gradient: row.mine && !row.m.deleted ? ours : null
                        Gradient {
                            id: ours
                            GradientStop { position: 0; color: Qt.lighter(row.c.action, theme.dark ? 1.08 : 1.22) }
                            GradientStop { position: 1; color: row.c.action }
                        }
                    }

                    ColumnLayout {
                        id: content
                        x: bubble.bare ? 0 : 12
                        y: bubble.bare ? 0 : 8
                        width: bubble.width - (bubble.bare ? 0 : 24)
                        spacing: 6

                        // what it answers
                        AbstractButton {
                            visible: !!row.m.parent
                            Layout.fillWidth: true
                            implicitHeight: quote.implicitHeight + 10
                            onClicked: row.quoteClicked(row.m.parent ? row.m.parent.id : 0)
                            background: Rectangle {
                                radius: 8
                                color: row.mine ? Qt.alpha("white", 0.14) : row.c.hover
                                Rectangle { width: 3; height: parent.height - 8; y: 4; x: 4; radius: 1.5; color: row.mine ? "white" : row.c.action }
                            }
                            contentItem: ColumnLayout {
                                id: quote
                                spacing: 1
                                Text { textFormat: Text.PlainText;
                                    Layout.fillWidth: true; Layout.leftMargin: 14; Layout.topMargin: 5
                                    text: row.m.parent ? row.m.parent.name : ""
                                    font.pixelSize: 12; font.weight: Font.DemiBold
                                    color: row.mine ? row.c.actionText : row.c.action
                                    elide: Text.ElideRight
                                }
                                Text {
                                    Layout.fillWidth: true; Layout.leftMargin: 14; Layout.bottomMargin: 5; Layout.rightMargin: 8
                                    text: row.m.parent ? (row.m.parent.deleted ? app.t.deleted_message : row.m.parent.text) : ""
                                    font.pixelSize: 12
                                    color: row.mine ? Qt.alpha(row.c.actionText, 0.85) : row.c.muted
                                    elide: Text.ElideRight
                                    maximumLineCount: 2
                                    wrapMode: Text.Wrap
                                    textFormat: Text.PlainText
                                }
                            }
                        }

                        // a voice message: play, its progress, its length
                        RowLayout {
                            visible: row.isVoice
                            Layout.preferredWidth: 240
                            spacing: 10
                            AbstractButton {
                                implicitWidth: 36; implicitHeight: 36
                                enabled: voice.available
                                onClicked: voice.play(row.m.key, row.m.files[0])
                                Accessible.name: app.t.voice_message
                                background: Rectangle { radius: 18; color: row.mine ? Qt.alpha("white", 0.22) : row.c.tint }
                                contentItem: Item {
                                    BusyIndicator { anchors.centerIn: parent; running: voice.loading === row.m.key; visible: running; implicitWidth: 22; implicitHeight: 22 }
                                    Icon {
                                        anchors.centerIn: parent; visible: voice.loading !== row.m.key
                                        name: voice.playing === row.m.key ? "close" : "play"; size: 16
                                        color: row.mine ? row.c.actionText : row.c.tintText
                                    }
                                }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 4
                                // a waveform drawn from the message's id (Talk does not give one): only a look
                                Row {
                                    spacing: 2
                                    Repeater {
                                        model: 28
                                        Rectangle {
                                            required property int index
                                            readonly property real level: 0.25 + 0.75 * Math.abs(Math.sin((row.m.id + 1) * (index + 3) * 0.37))
                                            width: 3; radius: 1.5
                                            height: 4 + 18 * level
                                            anchors.verticalCenter: parent.verticalCenter
                                            color: {
                                                const done = voice.playing === row.m.key && index / 28 < voice.progress
                                                return row.mine ? (done ? "white" : Qt.alpha("white", 0.45)) : (done ? row.c.action : row.c.accentLine)
                                            }
                                        }
                                    }
                                }
                                Text { textFormat: Text.PlainText;
                                    text: voice.playing === row.m.key ? app.duration(voice.position) : app.t.voice_message
                                    font.family: "JetBrains Mono"; font.pixelSize: 11
                                    color: row.mine ? Qt.alpha(row.c.actionText, 0.85) : row.c.muted
                                }
                            }
                        }

                        // the files
                        // pictures sent together (an album, WhatsApp-like): 2 side by side, 3 as one large and two, 4 and
                        // more as a square of four with « +N » on the last
                        Item {
                            id: albumGrid
                            visible: row.album.length > 1
                            readonly property int n: row.album.length
                            readonly property real gap: 3
                            readonly property real half: (width - gap) / 2
                            Layout.fillWidth: true
                            Layout.preferredWidth: 320
                            implicitWidth: 320
                            implicitHeight: !visible ? 0 : n === 2 ? 200 : n === 3 ? 180 + gap + half : 2 * half + gap
                            function tile(i) {
                                if (n === 2) return Qt.rect(i * (half + gap), 0, half, 200)
                                if (n === 3) return i === 0 ? Qt.rect(0, 0, width, 180) : Qt.rect((i - 1) * (half + gap), 180 + gap, half, half)
                                return Qt.rect((i % 2) * (half + gap), Math.floor(i / 2) * (half + gap), half, half)
                            }
                            Repeater {
                                id: albumTiles
                                model: albumGrid.visible ? row.album.slice(0, 4) : []
                                delegate: AbstractButton {
                                    id: tileButton
                                    required property var modelData
                                    required property int index
                                    readonly property rect r: albumGrid.tile(index)
                                    readonly property var file: modelData
                                    readonly property bool image: true
                                    x: r.x; y: r.y; width: r.width; height: r.height
                                    hoverEnabled: true
                                    Accessible.name: modelData.name || ""
                                    onClicked: row.imageWanted(modelData, row.album)
                                    contentItem: Item {
                                        clip: true
                                        Image {
                                            anchors.fill: parent
                                            source: tileButton.modelData.local ? tileButton.modelData.local : "image://meet/preview/" + tileButton.modelData.id
                                            sourceSize: Qt.size(480, 480)
                                            fillMode: Image.PreserveAspectCrop
                                            asynchronous: true
                                            Rectangle { anchors.fill: parent; color: row.c.hover; visible: parent.status !== Image.Ready }
                                        }
                                        Rectangle {
                                            anchors.fill: parent
                                            visible: tileButton.index === 3 && albumGrid.n > 4
                                            color: Qt.alpha("#0A192F", 0.55)
                                            Text {
                                                anchors.centerIn: parent
                                                text: "+" + (albumGrid.n - 3)
                                                font.pixelSize: 26; font.weight: Font.DemiBold; color: "white"
                                            }
                                        }
                                        Rectangle { anchors.fill: parent; color: "white"; opacity: tileButton.hovered ? 0.08 : 0 }
                                    }
                                    background: Item {}
                                }
                            }
                        }

                        Repeater {
                            id: fileCards
                            model: row.isVoice || row.album.length > 1 ? [] : row.m.files
                            delegate: FileCard {
                                required property var modelData
                                Layout.fillWidth: true
                                file: modelData
                                mine: row.mine
                                onOpened: row.openFile(modelData)
                                onSaveWanted: row.saveFile(modelData)
                            }
                        }

                        // the text
                        TextEdit {
                            visible: text !== "" && row.m.html !== "" && (row.m.gif === "" || gifImage.status === AnimatedImage.Error)
                            Layout.fillWidth: true
                            Layout.preferredWidth: Math.min(implicitWidth, bubbleColumn.Layout.maximumWidth - 24)
                            text: row.m.deleted ? "<i>" + app.t.deleted_message + "</i>" : row.m.html
                            textFormat: TextEdit.RichText
                            readOnly: true
                            selectByMouse: true
                            wrapMode: TextEdit.Wrap
                            font.pixelSize: bubble.bare ? 34 : 14
                            color: row.m.deleted ? row.c.muted : (row.mine ? row.c.actionText : row.c.body)
                            selectionColor: row.mine ? Qt.alpha("white", 0.35) : row.c.tint
                            selectedTextColor: row.mine ? row.c.actionText : row.c.text
                            onLinkActivated: link => row.openLink(link)
                            HoverHandler { cursorShape: parent.hoveredLink ? Qt.PointingHandCursor : Qt.IBeamCursor }
                        }

                        // a GIF of Giphy (sent as its link, like Talk web): it moves here
                        AnimatedImage {
                            id: gifImage
                            visible: row.m.gif !== ""
                            property string file: row.m.gif ? meet.gif(row.m.gif, false) : ""
                            Connections {
                                target: meet
                                enabled: row.m.gif !== "" && gifImage.file === ""
                                function onGifReady(id) { if (id === row.m.gif) gifImage.file = meet.gif(row.m.gif, false) }
                            }
                            Layout.preferredWidth: 260
                            Layout.preferredHeight: status === AnimatedImage.Ready && sourceSize.width ? 260 * sourceSize.height / sourceSize.width : 180
                            source: file
                            fillMode: Image.PreserveAspectFit
                            playing: row.visible && Qt.application.state === Qt.ApplicationActive
                            Rectangle { anchors.fill: parent; radius: 10; color: row.c.hover; visible: parent.status !== AnimatedImage.Ready
                                Text { anchors.centerIn: parent; text: "GIF"; font.family: "JetBrains Mono"; font.pixelSize: 12; color: row.c.faint } }
                        }

                        // a poll
                        PollCard {
                            visible: !!row.m.poll
                            Layout.fillWidth: true
                            pollId: row.m.poll ? row.m.poll.id : ""
                            question: row.m.poll ? row.m.poll.question : ""
                            mine: row.mine
                        }
                    }
                }

                // the preview of its first link (the cloud reads the page: this computer never calls the site)
                AbstractButton {
                    id: linkCard
                    property var info: row.m.link ? meet.preview(row.m.link) : ({})
                    Connections {
                        target: meet
                        enabled: row.m.link !== "" && !linkCard.info.title
                        function onPreviewReady(url) { if (url === row.m.link) linkCard.info = meet.preview(url) }
                    }
                    visible: !row.m.deleted && !!(info.title || info.text)
                    Layout.alignment: row.mine ? Qt.AlignRight : Qt.AlignLeft
                    Layout.preferredWidth: Math.min(bubbleColumn.Layout.maximumWidth, 420)
                    implicitHeight: Math.max(linkText.implicitHeight + 20, info.image ? 84 : 0)
                    hoverEnabled: true
                    onClicked: app.openUrl(row.m.link)
                    Accessible.name: info.title || row.m.link
                    background: Rectangle {
                        radius: 12
                        color: linkCard.hovered ? row.c.hover : row.c.card
                        border.width: 1; border.color: row.c.hairline
                        Rectangle { x: 6; y: 8; width: 3; height: parent.height - 16; radius: 1.5; color: row.c.famCommunicate }
                    }
                    contentItem: RowLayout {
                        spacing: 10
                        ColumnLayout {
                            id: linkText
                            Layout.fillWidth: true; Layout.leftMargin: 10
                            spacing: 2
                            Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: linkCard.info.site || ""; font.pixelSize: 11; color: row.c.faint; elide: Text.ElideRight }
                            Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: linkCard.info.title || ""; font.pixelSize: 13; font.weight: Font.DemiBold; color: row.c.text; elide: Text.ElideRight; maximumLineCount: 2; wrapMode: Text.Wrap }
                            Text { textFormat: Text.PlainText; Layout.fillWidth: true; visible: text !== ""; text: linkCard.info.text || ""; font.pixelSize: 12; color: row.c.muted; elide: Text.ElideRight; maximumLineCount: 2; wrapMode: Text.Wrap }
                        }
                        Image {
                            visible: !!linkCard.info.image && status === Image.Ready
                            Layout.preferredWidth: 72; Layout.preferredHeight: 72
                            source: linkCard.info.image || ""
                            sourceSize: Qt.size(144, 144)
                            fillMode: Image.PreserveAspectCrop
                            asynchronous: true
                        }
                    }
                }

                // its thread (Talk 25): how many answers, opens beside
                AbstractButton {
                    id: threadChip
                    visible: !row.inThread && row.m.thread > 0
                    Layout.alignment: row.mine ? Qt.AlignRight : Qt.AlignLeft
                    implicitHeight: 28
                    implicitWidth: threadRow.implicitWidth + 20
                    hoverEnabled: true
                    onClicked: meet.openThread(row.m.thread, row.m.threadTitle || row.m.plain.slice(0, 60))
                    background: Rectangle { radius: 14; color: threadChip.hovered ? row.c.tint : row.c.card; border.width: 1; border.color: row.c.accentLine }
                    contentItem: Row {
                        id: threadRow
                        leftPadding: 2
                        spacing: 6
                        Icon { name: "chat"; size: 14; color: row.c.tintText; anchors.verticalCenter: parent.verticalCenter }
                        Text { textFormat: Text.PlainText;
                            anchors.verticalCenter: parent.verticalCenter
                            text: (row.m.threadTitle ? row.m.threadTitle + " · " : "") + app.plural("replies_count", row.m.threadReplies)
                            font.pixelSize: 12; font.weight: Font.DemiBold; color: row.c.tintText
                        }
                    }
                }

                // Ornis's translation
                Rectangle {
                    visible: row.translateRequest >= 0
                    Layout.alignment: row.mine ? Qt.AlignRight : Qt.AlignLeft
                    Layout.maximumWidth: bubbleColumn.Layout.maximumWidth
                    implicitWidth: Math.min(bubbleColumn.Layout.maximumWidth, translated.implicitWidth + 24)
                    implicitHeight: translated.implicitHeight + 34
                    radius: 12
                    color: row.c.tint
                    Row {
                        x: 12; y: 8
                        spacing: 6
                        Icon { name: "ornis"; size: 13; color: row.c.tintText }
                        Text { text: row.translation === "" ? app.t.ornis_working : app.t.translation; font.pixelSize: 11; font.weight: Font.DemiBold; color: row.c.tintText }
                    }
                    Text {
                        id: translated
                        x: 12; y: 26
                        width: Math.min(implicitWidth, bubbleColumn.Layout.maximumWidth - 24)
                        text: row.translation
                        textFormat: Text.MarkdownText
                        wrapMode: Text.Wrap
                        font.pixelSize: 14
                        color: row.c.body
                    }
                }

                // reactions
                Flow {
                    visible: row.m.reactions.length > 0
                    Layout.alignment: row.mine ? Qt.AlignRight : Qt.AlignLeft
                    Layout.maximumWidth: bubbleColumn.Layout.maximumWidth
                    spacing: 4
                    Repeater {
                        model: row.m.reactions
                        AbstractButton {
                            id: reaction
                            required property var modelData
                            implicitHeight: 26
                            implicitWidth: reactionText.implicitWidth + 16
                            hoverEnabled: true
                            onClicked: meet.react(row.m.id, modelData.emoji)
                            onHoveredChanged: if (hovered) meet.loadReactors(row.m.id)
                            readonly property var names: row.reactors[modelData.emoji] || []
                            ToolTip.visible: hovered && names.length > 0
                            ToolTip.delay: 400
                            // names of others: never markup (the tooltip's label would read it)
                            ToolTip.text: (names.length > 12 ? names.slice(0, 12).join(", ") + " " + app.t.and_more.replace("%1", names.length - 12)
                                                             : names.join(", ")).replace(/&/g, "&amp;").replace(/</g, "&lt;")
                            Accessible.name: modelData.emoji + " " + modelData.count + (names.length ? " : " + names.join(", ") : "")
                            background: Rectangle {
                                radius: 13
                                color: reaction.modelData.self ? row.c.tint : (reaction.hovered ? row.c.hover : row.c.card)
                                border.width: 1
                                border.color: reaction.modelData.self ? row.c.accentLine : row.c.hairline
                            }
                            contentItem: Text { textFormat: Text.PlainText;
                                id: reactionText
                                text: reaction.modelData.emoji + " " + reaction.modelData.count
                                font.pixelSize: 13
                                color: reaction.modelData.self ? row.c.tintText : row.c.text
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                            }
                        }
                    }
                }

                // ours: sent / pending / read / not sent
                Row {
                    visible: row.mine && (row.m.failed || row.m.pending || row.m.edited || row.isLastMine)
                    Layout.alignment: Qt.AlignRight
                    spacing: 6
                    Text {
                        visible: row.m.edited && !row.m.deleted
                        text: app.t.edited
                        font.pixelSize: 11; color: row.c.faint
                    }
                    Text { textFormat: Text.PlainText;
                        visible: !row.m.failed
                        text: row.m.pending ? app.t.sending : (row.m.read ? app.t.read + " · " : "") + app.clock(row.m.time)
                        font.pixelSize: 11; color: row.c.faint
                    }
                    Text {
                        visible: row.m.failed
                        text: app.t.not_sent
                        font.pixelSize: 11; font.weight: Font.DemiBold; color: row.c.danger
                    }
                    Text {
                        visible: row.m.failed
                        text: "<a href='retry'>" + app.t.retry + "</a> · <a href='discard'>" + app.t.discard + "</a>"
                        textFormat: Text.StyledText
                        linkColor: row.c.action
                        font.pixelSize: 11
                        onLinkActivated: link => link === "retry" ? meet.retry(row.m.key) : meet.discard(row.m.key)
                    }
                }
                Text {
                    visible: !row.mine && row.m.edited && !row.m.deleted
                    text: app.t.edited
                    font.pixelSize: 11; color: row.c.faint
                }
            }
            Item { Layout.fillWidth: true }
        }
    }

    readonly property bool isLastMine: {
        const v = ListView.view
        if (!v || !mine) return false
        for (let i = index + 1; i < v.count; i++) if (v.model.get(i).self) return false
        return true
    }

    // on hover: quick reactions, answer, more
    Rectangle {
        id: actions
        property bool hovered: actionsHover.hovered
        visible: (row.hovering) && !row.m.system && !row.m.pending && !row.m.failed && !row.m.deleted && row.m.id > 0
        HoverHandler { id: actionsHover }
        anchors.top: parent.top
        anchors.topMargin: (row.m.day !== "" ? 34 : -6) + (row.unreadLine ? 28 : 0)
        x: row.mine ? Math.max(8, parent.width - bubble.width - width - 30) : Math.min(parent.width - width - 8, bubble.width + 66)
        width: actionsRow.implicitWidth + 8
        height: 34
        radius: 10
        color: row.c.overlay
        border.width: 1; border.color: row.c.overlayLine
        z: 3
        Row {
            id: actionsRow
            anchors.centerIn: parent
            spacing: 0
            Repeater {
                model: app.prefs.quick_reactions || []
                AbstractButton {
                    required property string modelData
                    width: 30; height: 30
                    onClicked: meet.react(row.m.id, modelData)
                    contentItem: Text { textFormat: Text.PlainText; text: parent.modelData; font.pixelSize: 16; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    background: Rectangle { radius: 8; color: parent.hovered ? row.c.hover : "transparent" }
                }
            }
            OButton { kind: "quiet"; iconName: "smile"; height_: 30; tip: app.t.react; onClicked: picker.popupAt(actions, true) }
            OButton { kind: "quiet"; iconName: "reply"; height_: 30; tip: app.t.reply; visible: row.m.replyable; onClicked: row.replyWanted(row.m) }
            OButton { kind: "quiet"; iconName: "more"; height_: 30; tip: app.t.more; onClicked: { row.menuFile = null; moreMenu.popupAt(actions, true) } }
        }
    }

    EmojiPicker { id: picker; reactions: true; onPicked: emoji => meet.react(row.m.id, emoji) }

    property var menuFile: null      // the picture the menu's « Copier l'image » copies
    MeetMenu {
        id: moreMenu
        OMenuItem { text: app.t.copy_image; iconName: "copy"; visible: !!row.menuFile; onTriggered: meet.copyImage(row.menuFile) }
        OMenuItem { text: app.t.reply; iconName: "reply"; visible: row.m.replyable; onTriggered: row.replyWanted(row.m) }
        OMenuItem { text: app.t.copy_text; iconName: "copy"; visible: row.m.plain !== ""; onTriggered: app.copy(row.m.plain) }
        OMenuItem { text: app.t.thread_from; iconName: "chat"; visible: !!meet.room.threads && !row.inThread && row.m.thread === 0 && row.m.replyable
                    onTriggered: row.threadWanted(row.m) }
        OMenuItem { text: app.t.forward; iconName: "forward"; onTriggered: row.forwardWanted(row.m) }
        OMenuItem { text: app.t.save_as; iconName: "download"; visible: row.m.files.length === 1 || !!row.menuFile
                    onTriggered: row.saveFile(row.menuFile || row.m.files[0]) }
        OMenuItem { text: app.t.translate; iconName: "globe"; visible: row.m.plain !== "" && !row.mine
                    onTriggered: { row.translation = ""; row.translateRequest = ornis.ask("translate", { text: row.m.plain }) } }
        OMenuItem { text: app.t.copy_link_message; iconName: "link"; onTriggered: { app.copy(meet.room.link + "#message_" + row.m.id); app.toast(app.t.link_copied) } }
        OMenuItem { text: row.m.pinned ? app.t.unpin : app.t.pin; iconName: "pushpin"
                    visible: !row.inThread && (!!meet.room.moderator || meet.room.type === 1)
                    onTriggered: meet.pin(row.m.id, !row.m.pinned) }
        OMenuItem { text: app.t.to_notes; iconName: "note"; visible: row.m.plain !== ""
                    onTriggered: app.toast(app.toNotes((row.m.name || app.t.app_name) + " · " + (meet.room.name || ""),
                                 row.m.plain + "\n\n[" + (meet.room.name || "Meet") + "](" + meet.room.link + "#message_" + row.m.id + ")")
                                 ? app.t.sent_to_notes : app.t.notes_unavailable) }
        OMenuItem { text: app.t.to_task; iconName: "checklist"; visible: row.m.plain !== ""
                    onTriggered: app.toast(app.toTasks([{ title: row.m.plain.split("\n")[0].slice(0, 120) }], meet.room.link + "#message_" + row.m.id)
                                 ? app.t.tasks_added : app.t.tasks_unavailable) }
        OMenuItem { text: app.t.remind_hour; iconName: "clock"; onTriggered: meet.remind(row.m.id, 3600) }
        OMenuItem { text: app.t.remind_tomorrow; iconName: "clock"; onTriggered: meet.remind(row.m.id, row.secondsToTomorrow()) }
        OMenuItem { text: app.t.edit; iconName: "edit"; visible: row.mine && !row.m.files.length && !row.m.poll; onTriggered: row.editWanted(row.m) }
        // in an album, the picture under the pointer (each one is its own message)
        OMenuItem { text: app.t.delete_message; iconName: "trash"; danger: true; visible: row.mine || meet.room.moderator
                    onTriggered: meet.remove(row.menuFile && row.menuFile.message ? row.menuFile.message : row.m.id) }
    }

    function secondsToTomorrow() {
        const now = new Date()
        const t = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 9, 0, 0)
        return Math.round((t - now) / 1000)
    }
    function openFile(file) {
        if (file.preview && String(file.mime).startsWith("image/")) row.imageWanted(file, [])
        else meet.openFile(file)
    }
    function saveFile(file) { saver.file = file; saver.open() }
    FileDialog {
        id: saver
        property var file: ({})
        fileMode: FileDialog.SaveFile
        title: app.t.save_as
        currentFile: "file:///" + (file.name || "")
        onAccepted: meet.saveFile(file, String(selectedFile))
    }
    function openLink(link) {
        if (link.startsWith("mention:")) {
            const parts = link.split(":")
            row.mentionClicked(parts[1], parts.slice(2).join(":"))
        } else if (link.startsWith("file:")) {
            const f = row.m.files.find(x => String(x.id) === link.slice(5))
            if (f) row.openFile(f); else meet.openInCloud(link.slice(5))
        } else {
            app.openUrl(link)
        }
    }
}
