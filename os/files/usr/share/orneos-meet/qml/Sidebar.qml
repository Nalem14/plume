// The side column: the app's kicker, the search, « Nouvelle conversation », four cards (the home with the
// meetings of the day, what is unread, the mentions, the favourites), then the conversations (favourites first,
// then by activity) and at the foot the account and the settings. A conversation with a call going on shows it.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Rectangle {
    id: side
    readonly property var c: theme.c
    readonly property var counts: meet.counts
    signal openRoom(string token)
    signal newConversation()
    signal settingsRequested()
    signal callRoom(string token, bool video)
    signal homeWanted()
    signal roomSettingsWanted(string page)
    property bool showThreads: false     // the threads followed in every conversation, in place of the conversations
    readonly property int meetingsToday: (meet.home.events || []).filter(e => app.day(e.start) === app.t.today).length
    color: c.chrome

    function focusSearch() { search.forceActiveFocus(); search.selectAll() }
    function setSearch(text) { search.text = text; focusSearch() }
    function step(delta) {
        const rows = meet.rooms
        if (!rows.length) return
        let i = rows.findIndex(r => r.token === meet.current)
        i = Math.max(0, Math.min(rows.length - 1, i + delta))
        side.openRoom(rows[i].token)
        list.positionViewAtIndex(i, ListView.Contain)
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 14
        anchors.topMargin: 12
        anchors.bottomMargin: 0
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.bottomMargin: 12; Layout.topMargin: 4
            Text {
                Layout.fillWidth: true
                Layout.leftMargin: 4
                text: app.t.app_name
                font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                font.capitalization: Font.AllUppercase; font.letterSpacing: 0.9
                color: side.c.famCommunicate
            }
            Text {
                visible: meet.state === "offline"
                text: app.t.offline
                font.pixelSize: 12; color: side.c.saffronInk
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.bottomMargin: 10
            spacing: 8
            OTextField {
                id: search
                Layout.fillWidth: true
                iconName: "search"
                placeholderText: app.t.search_conversations
                onTextChanged: meet.setQuery(text)
                Keys.onDownPressed: list.forceActiveFocus()
                Keys.onReturnPressed: if (meet.rooms.length) side.openRoom(meet.rooms[0].token)
            }
            OButton {
                kind: "primary"
                iconName: "compose"
                tip: app.t.new_conversation + " (Ctrl+N)"
                onClicked: side.newConversation()
            }
        }
        GridLayout {
            Layout.fillWidth: true
            Layout.bottomMargin: 6
            columns: 2
            rowSpacing: 8; columnSpacing: 8
            SmartCard {
                Layout.fillWidth: true; Layout.preferredWidth: 1
                tint: side.c.famCommunicate; iconName: "today"; text: app.t.home
                count: side.meetingsToday ? String(side.meetingsToday) : ""
                selected: meet.current === "" && meet.filter === "all"
                // the home and every conversation again: a filter chosen before goes
                onClicked: { side.showThreads = false; meet.setFilter("all"); search.text = ""; side.homeWanted() }
            }
            Repeater {
                model: [
                    { value: "unread", icon: "inbox", text: app.t.filter_unread, count: side.counts.unread || 0, tint: side.c.famCommunicate },
                    { value: "mentions", icon: "bell", text: app.t.filter_mentions, count: side.counts.mentions || 0, tint: side.c.saffronInk },
                    { value: "favorites", icon: "star", text: app.t.filter_favorites, count: side.counts.favorites || 0, tint: side.c.famOrganize }
                ]
                SmartCard {
                    required property var modelData
                    Layout.fillWidth: true; Layout.preferredWidth: 1
                    tint: modelData.tint; iconName: modelData.icon; text: modelData.text
                    count: String(modelData.count)
                    selected: meet.filter === modelData.value
                    onClicked: { side.showThreads = false; meet.setFilter(meet.filter === modelData.value ? "all" : modelData.value) }
                }
            }
        }
        AbstractButton {
            id: threadsButton
            objectName: "threadsButton"
            Layout.fillWidth: true
            Layout.topMargin: 6
            implicitHeight: 40
            hoverEnabled: true
            Accessible.name: side.showThreads ? app.t.back_to_conversations : app.t.followed_threads
            onClicked: { side.showThreads = !side.showThreads; if (side.showThreads) meet.loadThreads() }
            background: Rectangle {
                radius: 10
                color: side.showThreads ? Qt.alpha(side.c.famCommunicate, theme.dark ? 0.18 : 0.08)
                       : threadsButton.hovered ? side.c.hover : "transparent"
            }
            contentItem: RowLayout {
                spacing: 10
                Icon { Layout.leftMargin: 10; name: side.showThreads ? "arrow" : "chat"; size: 16
                       rotation: side.showThreads ? 180 : 0; color: side.c.text }
                Text {
                    Layout.fillWidth: true
                    textFormat: Text.PlainText
                    text: side.showThreads ? app.t.back_to_conversations : app.t.followed_threads
                    font.pixelSize: 13; font.weight: Font.Medium
                    color: side.c.text
                    elide: Text.ElideRight
                }
            }
        }
        // the account's tags: a click shows only their conversations
        Flow {
            visible: meet.tags.length > 0 && !side.showThreads
            Layout.fillWidth: true
            Layout.topMargin: 6
            spacing: 6
            Repeater {
                model: meet.tags
                AbstractButton {
                    id: tagChip
                    required property var modelData
                    required property int index
                    readonly property bool on: meet.filter === "tag:" + modelData.id
                    readonly property color tone: side.c["tag" + (index % 5 + 1)]
                    implicitHeight: 28
                    implicitWidth: tagRow.implicitWidth + 18
                    hoverEnabled: true
                    Accessible.role: Accessible.CheckBox
                    Accessible.checked: on
                    Accessible.name: modelData.name
                    onClicked: meet.setFilter(on ? "all" : "tag:" + modelData.id)
                    background: Rectangle {
                        radius: 14
                        color: tagChip.on ? Qt.alpha(tagChip.tone, theme.dark ? 0.26 : 0.14) : tagChip.hovered ? side.c.hover : "transparent"
                        border.width: 1; border.color: tagChip.on ? Qt.alpha(tagChip.tone, 0.6) : side.c.line
                    }
                    contentItem: RowLayout {
                        id: tagRow
                        spacing: 6
                        Rectangle { Layout.leftMargin: 9; implicitWidth: 7; implicitHeight: 7; radius: 3.5; color: tagChip.tone }
                        Text { textFormat: Text.PlainText; text: tagChip.modelData.name; font.pixelSize: 12; color: side.c.text }
                        Text { Layout.rightMargin: 9; visible: tagChip.modelData.count > 0; text: tagChip.modelData.count; font.pixelSize: 11; color: side.c.faint }
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 10; Layout.bottomMargin: 6
            Layout.leftMargin: 6; Layout.rightMargin: 4
            Text { textFormat: Text.PlainText;
                Layout.fillWidth: true
                text: side.showThreads ? app.t.followed_threads : meet.filter === "unread" ? app.t.filter_unread : meet.filter === "mentions" ? app.t.filter_mentions
                      : meet.filter === "favorites" ? app.t.filter_favorites : meet.filter === "archived" ? app.t.filter_archived
                      : meet.filter.startsWith("tag:") ? ((meet.tags.find(t => "tag:" + t.id === meet.filter) || {}).name || app.t.conversations)
                      : app.t.conversations
                font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                font.capitalization: Font.AllUppercase; font.letterSpacing: 0.9
                color: side.c.faint
            }
            AbstractButton {
                visible: meet.filter !== "all" && !side.showThreads
                implicitHeight: 20; implicitWidth: allText.implicitWidth
                onClicked: meet.setFilter("all")
                contentItem: Text { id: allText; text: app.t.show_all; font.pixelSize: 12; color: side.c.action }
            }
        }

        // the threads followed in every conversation: a click opens the conversation and the thread beside it
        ListView {
            id: threadList
            visible: side.showThreads
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: meet.followedThreads
            spacing: 2
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            Text {
                visible: threadList.count === 0
                anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                text: app.t.no_threads
                wrapMode: Text.Wrap
                font.pixelSize: 13; color: side.c.muted
            }
            delegate: AbstractButton {
                id: trow
                required property var modelData
                readonly property bool active: meet.thread.id === modelData.id && meet.current === modelData.token
                width: ListView.view.width
                implicitHeight: 64
                hoverEnabled: true
                Accessible.name: modelData.title
                onClicked: { side.openRoom(modelData.token); meet.openThread(modelData.id, modelData.title) }
                background: Rectangle {
                    radius: 10
                    color: trow.active ? Qt.alpha(side.c.famCommunicate, theme.dark ? 0.18 : 0.08)
                           : trow.hovered ? side.c.hover : "transparent"
                }
                contentItem: RowLayout {
                    spacing: 10
                    Rectangle {
                        Layout.leftMargin: 10
                        implicitWidth: 40; implicitHeight: 40; radius: 20
                        color: Qt.alpha(side.c.famCommunicate, theme.dark ? 0.22 : 0.1)
                        Icon { anchors.centerIn: parent; name: "chat"; size: 18; color: side.c.famCommunicate }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.rightMargin: 14
                        spacing: 2
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            Text {
                                Layout.fillWidth: true
                                textFormat: Text.PlainText
                                text: trow.modelData.title + (trow.modelData.room ? " · " + trow.modelData.room : "")
                                elide: Text.ElideRight
                                font.pixelSize: 12; color: side.c.muted
                            }
                            Rectangle {
                                visible: trow.modelData.replies > 0
                                implicitHeight: 18; implicitWidth: replies.implicitWidth + 22; radius: 9
                                color: Qt.alpha(side.c.famCommunicate, theme.dark ? 0.25 : 0.12)
                                RowLayout {
                                    anchors.centerIn: parent
                                    spacing: 3
                                    Icon { name: "reply"; size: 11; color: side.c.action }
                                    Text { id: replies; text: trow.modelData.replies; font.pixelSize: 11; font.weight: Font.DemiBold; color: side.c.action }
                                }
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            Text {
                                Layout.fillWidth: true
                                textFormat: Text.PlainText
                                text: (trow.modelData.who ? trow.modelData.who + (app.lang === "fr" ? " : " : ": ") : "") + trow.modelData.text
                                elide: Text.ElideRight
                                font.pixelSize: 14; font.weight: Font.Medium; color: side.c.text
                            }
                            Text {
                                textFormat: Text.PlainText
                                text: app.short(trow.modelData.activity)
                                font.family: "JetBrains Mono"; font.pixelSize: 11; color: side.c.faint
                            }
                        }
                    }
                }
            }
        }

        ListView {
            id: list
            visible: !side.showThreads
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: meet.rooms
            spacing: 2
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            keyNavigationEnabled: true
            Keys.onReturnPressed: if (currentIndex >= 0) side.openRoom(meet.rooms[currentIndex].token)

            delegate: AbstractButton {
                id: row
                required property var modelData
                required property int index
                readonly property bool active: meet.current === modelData.token
                width: ListView.view.width
                implicitHeight: 64
                hoverEnabled: true
                Accessible.name: modelData.name
                onClicked: side.openRoom(modelData.token)
                background: Item {
                    Rectangle {
                        anchors.fill: parent
                        radius: 10
                        visible: !row.active
                        color: row.hovered ? side.c.hover : "transparent"
                    }
                    Surface {
                        anchors.fill: parent
                        visible: row.active
                        radius: 10
                        gradient: Gradient {
                            orientation: Gradient.Horizontal
                            GradientStop { position: 0; color: Qt.tint(side.c.card, Qt.alpha(side.c.famCommunicate, theme.dark ? 0.14 : 0.07)) }
                            GradientStop { position: 1; color: side.c.card }
                        }
                        Band {
                            anchors { left: parent.left; top: parent.top; bottom: parent.bottom; topMargin: 12; bottomMargin: 12 }
                            radius: 1.5
                            color: side.c.famCommunicate
                        }
                    }
                }
                contentItem: RowLayout {
                    spacing: 10
                    RoomAvatar {
                        Layout.leftMargin: 10
                        room: row.modelData
                        size: 40
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.rightMargin: 14         // the time and the counts: off the card's edge
                        spacing: 2
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            Text { textFormat: Text.PlainText;
                                Layout.fillWidth: true
                                text: row.modelData.name
                                elide: Text.ElideRight
                                font.pixelSize: 14
                                font.weight: row.modelData.unread > 0 ? Font.DemiBold : Font.Medium
                                color: side.c.text
                            }
                            Icon { visible: row.modelData.favorite; name: "star"; size: 12; color: side.c.saffron }
                            Icon { visible: row.modelData.muted; name: "bell"; size: 12; color: side.c.faint }
                            Text { textFormat: Text.PlainText;
                                text: app.short(row.modelData.activity)
                                font.family: "JetBrains Mono"; font.pixelSize: 11
                                color: row.modelData.unread > 0 ? side.c.action : side.c.faint
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            Rectangle {
                                visible: row.modelData.hasCall
                                implicitWidth: callLabel.implicitWidth + 16; implicitHeight: 20; radius: 10
                                color: side.c.ok
                                Text {
                                    id: callLabel
                                    anchors.centerIn: parent
                                    text: app.t.call_ongoing
                                    font.pixelSize: 11; font.weight: Font.DemiBold
                                    color: "white"
                                }
                            }
                            Text { textFormat: Text.PlainText;
                                Layout.fillWidth: true
                                visible: row.active && meet.typing.length > 0
                                text: app.typingText(meet.typing)
                                elide: Text.ElideRight
                                font.pixelSize: 13; font.italic: true
                                color: side.c.famCommunicate
                            }
                            Text {
                                Layout.fillWidth: true
                                visible: !(row.active && meet.typing.length > 0)
                                text: row.modelData.preview
                                elide: Text.ElideRight
                                maximumLineCount: 1
                                textFormat: Text.PlainText
                                font.pixelSize: 13
                                color: row.modelData.unread > 0 ? side.c.body : side.c.muted
                            }
                            Rectangle {
                                visible: row.modelData.unread > 0
                                implicitWidth: Math.max(20, unreadText.implicitWidth + 10); implicitHeight: 20; radius: 10
                                Layout.rightMargin: 8
                                color: row.modelData.mention || row.modelData.type === 1 ? side.c.action : side.c.hover
                                Text { textFormat: Text.PlainText;
                                    id: unreadText
                                    anchors.centerIn: parent
                                    text: row.modelData.mention && row.modelData.type !== 1 ? "@" : (row.modelData.unread > 99 ? "99+" : row.modelData.unread)
                                    font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.DemiBold
                                    color: row.modelData.mention || row.modelData.type === 1 ? side.c.actionText : side.c.text
                                }
                            }
                        }
                    }
                }
                TapHandler {
                    acceptedButtons: Qt.RightButton
                    onTapped: { side.openRoom(row.modelData.token); roomMenu.room = row.modelData; roomMenu.popupAt(row) }
                }
            }

            footer: AbstractButton {
                visible: (side.counts.archived || 0) > 0 && meet.filter !== "archived"
                width: ListView.view.width
                height: visible ? 40 : 0
                hoverEnabled: true
                onClicked: meet.setFilter("archived")
                background: Rectangle { radius: 8; color: parent.hovered ? side.c.hover : "transparent" }
                contentItem: RowLayout {
                    spacing: 10
                    Icon { Layout.leftMargin: 14; name: "archive"; size: 16; color: side.c.muted }
                    Text { Layout.fillWidth: true; text: app.t.filter_archived; font.pixelSize: 13; color: side.c.muted }
                    Text { Layout.rightMargin: 12; text: side.counts.archived || 0; font.family: "JetBrains Mono"; font.pixelSize: 12; color: side.c.faint }
                }
            }

            EmptyState {
                anchors.centerIn: parent
                width: parent.width - 20
                visible: list.count === 0 && meet.state !== "loading"
                iconName: "chat"
                title: search.text ? app.t.no_match : app.t.no_conversations
                lead: search.text ? "" : app.t.no_conversations_lead
                actionText: search.text ? "" : app.t.new_conversation
                onActivated: side.newConversation()
            }
            Column {
                anchors.fill: parent
                spacing: 8
                visible: list.count === 0 && meet.state === "loading"
                Repeater { model: 6; Skeleton { width: parent.width; height: 56 } }
            }
        }

        AccountBar {
            id: account
            Layout.fillWidth: true
            Layout.leftMargin: -14; Layout.rightMargin: -14
            name: app.profile.name || ""
            email: app.profile.email || ""
            initials: app.profile.initials || ""
            avatar: app.profile.avatar ? app.profile.avatar + (theme.dark ? "/dark" : "") : ""
            onSettingsRequested: side.settingsRequested()
            // our status, as the others see it: chosen here, its message beside
            readonly property var mine: meet.myStatus
            dot: side.statusColor(mine.status)
            detail: mine.message ? ((mine.icon ? mine.icon + " " : "") + mine.message) : ""
            OMenuItem { text: side.statusLabel("online", account.mine.status); dot: side.statusColor("online"); onTriggered: meet.setMyStatus("online") }
            OMenuItem { text: side.statusLabel("away", account.mine.status); dot: side.statusColor("away"); onTriggered: meet.setMyStatus("away") }
            OMenuItem { text: side.statusLabel("busy", account.mine.status); dot: side.statusColor("busy"); onTriggered: meet.setMyStatus("busy") }
            OMenuItem { text: side.statusLabel("dnd", account.mine.status); dot: side.statusColor("dnd"); onTriggered: meet.setMyStatus("dnd") }
            OMenuItem { text: side.statusLabel("invisible", account.mine.status); dot: side.statusColor("invisible"); onTriggered: meet.setMyStatus("invisible") }
            OMenuItem { text: account.mine.message ? (account.mine.icon ? account.mine.icon + " " : "") + account.mine.message : app.t.status_message
                        iconName: "edit"; onTriggered: statusDialog.start() }
            OMenuItem { text: app.t.open_in_cloud; iconName: "cloud"; onTriggered: app.openCloud("/apps/spreed/") }
        }
    }

    MeetMenu {
        id: roomMenu
        property var room: ({})
        OMenuItem {
            text: roomMenu.room.favorite ? app.t.unfavorite : app.t.favorite
            iconName: "star"
            onTriggered: meet.setFavorite(!roomMenu.room.favorite)
        }
        OMenuItem { text: app.t.call_audio; iconName: "phone"; onTriggered: side.callRoom(roomMenu.room.token, false) }
        OMenuItem { text: app.t.call_video; iconName: "video"; onTriggered: side.callRoom(roomMenu.room.token, true) }
        OMenuItem {
            text: roomMenu.room.muted ? app.t.unmute_conversation : app.t.mute_conversation
            iconName: "bell"
            onTriggered: meet.setNotify(roomMenu.room.muted ? 0 : 3)
        }
        OMenuItem {
            text: roomMenu.room.archived ? app.t.unarchive : app.t.archive
            iconName: "archive"
            onTriggered: meet.setArchived(!roomMenu.room.archived)
        }
        OMenuItem { text: app.t.mark_unread; iconName: "inbox"; onTriggered: meet.markUnread() }
        OMenuItem { text: app.t.copy_link; iconName: "link"; onTriggered: { app.copy(meet.room.link); toastOf(app.t.link_copied) } }
        OMenuItem { text: app.t.rs_tags; iconName: "tag"; visible: !!(meet.room.can || {}).tags; onTriggered: side.roomSettingsWanted("me") }
        OMenuItem { text: app.t.settings_conversation; iconName: "settings"; onTriggered: side.roomSettingsWanted("") }
        OMenuItem {
            text: app.t.leave_conversation; iconName: "export"; danger: true
            visible: meet.room.canLeave !== false
            onTriggered: choice.ask(app.t.leave_conversation, app.t.leave_lead, [
                { id: "cancel", text: app.t.cancel }, { id: "leave", text: app.t.leave, kind: "danger" }],
                id => { if (id === "leave") meet.leaveRoom() })
        }
        OMenuItem {
            text: app.t.delete_conversation; iconName: "trash"; danger: true
            visible: meet.room.canDelete === true
            onTriggered: choice.ask(app.t.delete_conversation, app.t.delete_lead, [
                { id: "cancel", text: app.t.cancel }, { id: "delete", text: app.t.delete_for_all, kind: "danger" }],
                id => { if (id === "delete") meet.deleteRoom() })
        }
    }
    function toastOf(text) { app.toast(text) }

    function statusColor(status) {
        return status === "online" ? theme.c.ok : status === "away" ? theme.c.saffron
             : status === "dnd" || status === "busy" ? theme.c.danger : status === "invisible" || status === "offline" ? theme.c.faint : ""
    }
    // the current one ticked
    function statusLabel(status, current) { return app.t["status_" + status] + (status === current ? "  ✓" : "") }
    StatusDialog { id: statusDialog; objectName: "statusDialog" }
}
