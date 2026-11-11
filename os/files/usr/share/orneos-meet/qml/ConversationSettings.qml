// The settings of the open conversation, in short pages (a column of pages on the left, like Slack's): what
// it is (picture, name, description, link), what it does for me (notifications, important, sensitive, tags,
// favourite, archive), then the moderators' pages: who may come in (accounts, guests by link, password, e-mail
// invitations, lobby), what the participants may do, the messages (ephemeral, history), the bots, and at the
// end leave or delete. A page only shows what this cloud and this role can change; only the open page is built.
import QtCore as Std               // StandardPaths only: its Settings would hide ours
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Effects
import QtQuick.Layouts
import "components"

Popup {
    id: dialog
    readonly property var c: theme.c
    readonly property var room: meet.room
    readonly property var can: room.can || ({})
    readonly property bool mod: !!room.moderator
    readonly property bool group: room.type === 2 || room.type === 3
    readonly property bool showPreserve: !!(room.owner && can.preserve && (room.preserved || room.objectType === "event"
                                                                           || room.objectType === "instant_meeting"))
    property string page: "general"
    property string token: ""
    readonly property var pages: [
        { id: "general", icon: "info", text: app.t.rs_general, shown: true },
        { id: "me", icon: "bell", text: app.t.rs_me, shown: true },
        { id: "access", icon: "globe", text: app.t.rs_access, shown: mod && group },
        { id: "permissions", icon: "shield", text: app.t.rs_permissions, shown: mod && group && !!can.permissions },
        { id: "messages", icon: "chat", text: app.t.rs_messages, shown: mod },
        { id: "bots", icon: "sparkle", text: app.t.rs_bots, shown: mod && group && (meet.roomSettings.bots || []).length > 0 },
        { id: "danger", icon: "warning", text: app.t.rs_danger, shown: room.canLeave !== false || room.canDelete === true || showPreserve }
    ].filter(p => p.shown)

    function openAt(which) {
        token = meet.current
        page = which && pages.some(p => p.id === which) ? which : "general"
        meet.loadRoomSettings()
        if (can.tags) meet.loadTags()
        open()
    }
    // another conversation opened (a link, a call), or this one gone: these settings are no longer its
    Connections {
        target: meet
        enabled: dialog.opened
        function onRoomChanged() { if (meet.current !== dialog.token) dialog.close() }
    }

    parent: Overlay.overlay
    anchors.centerIn: parent
    modal: true
    focus: true
    padding: 0
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    width: Math.min(880, parent ? parent.width - 48 : 880)
    height: Math.min(660, parent ? parent.height - 48 : 660)
    Overlay.modal: Rectangle { color: dialog.c.scrim }
    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 140; easing.type: Easing.OutCubic }
            NumberAnimation { property: "scale"; from: 0.98; to: 1; duration: 140; easing.type: Easing.OutCubic }
        }
    }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 100 } }
    background: Item {
        RectangularShadow { anchors.fill: card; radius: card.radius; blur: 40; offset.y: 16; color: dialog.c.shadow }
        Rectangle { id: card; anchors.fill: parent; radius: 14; color: dialog.c.overlay; border.width: 1; border.color: dialog.c.overlayLine }
    }

    // ---- the pieces of a page ------------------------------------------------------------------------------
    // a group of settings on a card, with its title and what it is about
    component Group: ColumnLayout {
        id: group
        property string title
        property string lead
        default property alias rows: box.data
        Layout.fillWidth: true
        spacing: 6
        Text {
            visible: group.title !== ""
            Layout.fillWidth: true
            Layout.leftMargin: 4
            textFormat: Text.PlainText
            text: group.title
            font.pixelSize: 13; font.weight: Font.DemiBold; color: dialog.c.text
        }
        Text {
            visible: group.lead !== ""
            Layout.fillWidth: true
            Layout.leftMargin: 4; Layout.bottomMargin: 2
            textFormat: Text.PlainText
            text: group.lead
            font.pixelSize: 12; color: dialog.c.muted; wrapMode: Text.Wrap
        }
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: box.implicitHeight + 12
            radius: 12
            color: dialog.c.card
            border.width: 1; border.color: dialog.c.hairline
            ColumnLayout { id: box; x: 6; y: 6; width: parent.width - 12; spacing: 0 }
        }
    }
    // a setting on or off: the whole line switches it
    component SwitchRow: AbstractButton {
        id: sw
        property string iconName
        property string lead
        property bool on
        signal toggled(bool value)
        Layout.fillWidth: true
        implicitHeight: Math.max(48, texts.implicitHeight + 20)
        hoverEnabled: true
        Accessible.role: Accessible.CheckBox
        Accessible.checked: on
        Accessible.description: lead
        onClicked: if (enabled) toggled(!on)
        background: Rectangle { radius: 8; color: (sw.hovered || sw.visualFocus) && sw.enabled ? dialog.c.hover : "transparent" }
        contentItem: RowLayout {
            spacing: 12
            Icon { visible: sw.iconName !== ""; Layout.leftMargin: 8; Layout.alignment: Qt.AlignTop; Layout.topMargin: 2
                   name: sw.iconName; size: 18; color: dialog.c.muted }
            ColumnLayout {
                id: texts
                Layout.fillWidth: true
                Layout.leftMargin: sw.iconName === "" ? 8 : 0
                spacing: 2
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: sw.text; font.pixelSize: 14
                       color: sw.enabled ? dialog.c.text : dialog.c.faint; wrapMode: Text.Wrap }
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; visible: text !== ""; text: sw.lead
                       font.pixelSize: 12; color: dialog.c.muted; wrapMode: Text.Wrap }
            }
            OSwitch {
                Layout.rightMargin: 4
                enabled: sw.enabled
                checked: sw.on
                // the line's value stays the truth (an answer of the cloud may put it back)
                onToggled: { sw.toggled(checked); checked = Qt.binding(() => sw.on) }
            }
        }
    }
    // one choice among a few: a round mark, a title and what it means
    component ChoiceRow: AbstractButton {
        id: choice
        property string iconName
        property string lead
        property bool selected
        Layout.fillWidth: true
        implicitHeight: Math.max(48, choiceTexts.implicitHeight + 20)
        hoverEnabled: true
        Accessible.role: Accessible.RadioButton
        Accessible.checked: selected
        Accessible.description: lead
        background: Rectangle { radius: 8; color: choice.selected ? dialog.c.tint : choice.hovered || choice.visualFocus ? dialog.c.hover : "transparent" }
        contentItem: RowLayout {
            spacing: 12
            Rectangle {
                Layout.leftMargin: 8; Layout.alignment: Qt.AlignTop; Layout.topMargin: 2
                implicitWidth: 18; implicitHeight: 18; radius: 9
                color: "transparent"
                border.width: choice.selected ? 5 : 1.5
                border.color: choice.selected ? dialog.c.action : dialog.c.line
                Behavior on border.width { NumberAnimation { duration: 100 } }
            }
            Icon { visible: choice.iconName !== ""; Layout.alignment: Qt.AlignTop; Layout.topMargin: 1
                   name: choice.iconName; size: 18; color: choice.selected ? dialog.c.tintText : dialog.c.muted }
            ColumnLayout {
                id: choiceTexts
                Layout.fillWidth: true
                spacing: 2
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: choice.text; font.pixelSize: 14
                       font.weight: choice.selected ? Font.Medium : Font.Normal
                       color: choice.selected ? dialog.c.tintText : dialog.c.text; wrapMode: Text.Wrap }
                Text { textFormat: Text.PlainText; Layout.fillWidth: true; visible: text !== ""; text: choice.lead
                       font.pixelSize: 12; color: dialog.c.muted; wrapMode: Text.Wrap }
            }
        }
    }
    // a line with its own button on the right (copy, choose a file, delete…)
    component ActionRow: RowLayout {
        id: action
        property string iconName
        property string text
        property string lead
        default property alias buttons: actionButtons.data
        Layout.fillWidth: true
        Layout.topMargin: 6; Layout.bottomMargin: 6
        spacing: 12
        Icon { visible: action.iconName !== ""; Layout.leftMargin: 8; Layout.alignment: Qt.AlignTop; Layout.topMargin: 2
               name: action.iconName; size: 18; color: dialog.c.muted }
        ColumnLayout {
            Layout.fillWidth: true
            Layout.leftMargin: action.iconName === "" ? 8 : 0
            spacing: 2
            Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: action.text; font.pixelSize: 14; color: dialog.c.text; wrapMode: Text.Wrap }
            Text { textFormat: Text.PlainText; Layout.fillWidth: true; visible: text !== ""; text: action.lead
                   font.pixelSize: 12; color: dialog.c.muted; wrapMode: Text.Wrap }
        }
        RowLayout { id: actionButtons; Layout.rightMargin: 4; spacing: 6 }
    }
    component Line: Rectangle { Layout.fillWidth: true; Layout.leftMargin: 8; Layout.rightMargin: 8; implicitHeight: 1; color: dialog.c.hairline }

    contentItem: RowLayout {
        spacing: 0

        // ---- the pages -------------------------------------------------------------------------------------
        Rectangle {
            Layout.fillHeight: true
            Layout.preferredWidth: 236
            color: dialog.c.chrome
            radius: 14
            Rectangle { anchors.right: parent.right; width: 14; height: parent.height; color: parent.color }   // square on the page side
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 14
                spacing: 2
                RowLayout {
                    Layout.fillWidth: true
                    Layout.bottomMargin: 14
                    spacing: 10
                    RoomAvatar { room: dialog.room; size: 40 }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0
                        Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: dialog.room.name || ""
                               font.pixelSize: 15; font.weight: Font.DemiBold; color: dialog.c.text; elide: Text.ElideRight }
                        Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: app.t.settings_conversation
                               font.pixelSize: 12; color: dialog.c.muted; elide: Text.ElideRight }
                    }
                }
                Repeater {
                    model: dialog.pages
                    AbstractButton {
                        id: tab
                        required property var modelData
                        readonly property bool current: dialog.page === modelData.id
                        Layout.fillWidth: true
                        implicitHeight: 38
                        hoverEnabled: true
                        Accessible.role: Accessible.PageTab
                        Accessible.name: modelData.text
                        Accessible.selected: current
                        onClicked: dialog.page = modelData.id
                        background: Rectangle {
                            radius: 9
                            color: tab.current ? Qt.alpha(dialog.c.famCommunicate, theme.dark ? 0.2 : 0.1) : tab.hovered ? dialog.c.hover : "transparent"
                            Rectangle { visible: tab.current; x: 0; y: 9; width: 3; height: parent.height - 18; radius: 1.5; color: dialog.c.famCommunicate }
                        }
                        contentItem: RowLayout {
                            spacing: 10
                            Icon { Layout.leftMargin: 10; name: tab.modelData.icon; size: 17
                                   color: tab.modelData.id === "danger" ? dialog.c.danger : tab.current ? dialog.c.famCommunicate : dialog.c.muted }
                            Text {
                                Layout.fillWidth: true
                                textFormat: Text.PlainText
                                text: tab.modelData.text
                                font.pixelSize: 14; font.weight: tab.current ? Font.DemiBold : Font.Normal
                                color: tab.modelData.id === "danger" ? dialog.c.danger : dialog.c.text
                                elide: Text.ElideRight
                            }
                        }
                    }
                }
                Item { Layout.fillHeight: true }
                Text {
                    Layout.fillWidth: true
                    visible: !dialog.mod && dialog.group
                    textFormat: Text.PlainText
                    text: app.t.rs_not_moderator
                    font.pixelSize: 12; color: dialog.c.faint; wrapMode: Text.Wrap
                }
            }
        }

        // ---- the open page ---------------------------------------------------------------------------------
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 28; Layout.rightMargin: 14; Layout.topMargin: 16; Layout.bottomMargin: 4
                Text {
                    Layout.fillWidth: true
                    textFormat: Text.PlainText
                    text: (dialog.pages.find(p => p.id === dialog.page) || {}).text || ""
                    font.family: "Schibsted Grotesk"; font.pixelSize: 20; font.weight: Font.DemiBold
                    color: dialog.c.text
                }
                OButton { kind: "quiet"; iconName: "close"; tip: app.t.close; onClicked: dialog.close() }
            }
            ScrollView {
                id: scroller
                Layout.fillWidth: true
                Layout.fillHeight: true
                contentWidth: availableWidth
                contentHeight: pageLoader.implicitHeight + 40
                clip: true
                Loader {
                    id: pageLoader
                    x: 28; y: 12
                    width: scroller.availableWidth - 56
                    sourceComponent: ({ general: generalPage, me: mePage, access: accessPage, permissions: permissionsPage,
                                        messages: messagesPage, bots: botsPage, danger: dangerPage })[dialog.page] || generalPage
                    onLoaded: scroller.ScrollBar.vertical.position = 0
                }
            }
        }
    }

    // ---- Général: what the conversation is ------------------------------------------------------------------
    property string emoji: ""
    property string emojiColor: ""
    Component {
        id: generalPage
        ColumnLayout {
            spacing: 22
            Group {
                RowLayout {
                    Layout.fillWidth: true
                    Layout.margins: 10
                    spacing: 16
                    RoomAvatar { room: dialog.room; size: 76 }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        OTextField {
                            Layout.fillWidth: true
                            visible: dialog.mod && dialog.room.type !== 1 && dialog.room.type !== 6
                            text: dialog.room.name || ""
                            font.pixelSize: 17; font.weight: Font.DemiBold
                            placeholderText: app.t.rs_name
                            Accessible.name: app.t.rs_name
                            onEditingFinished: if (text.trim() && text !== dialog.room.name) meet.rename(text)
                        }
                        Text {
                            Layout.fillWidth: true
                            visible: !(dialog.mod && dialog.room.type !== 1 && dialog.room.type !== 6)
                            textFormat: Text.PlainText
                            text: dialog.room.name || ""
                            font.pixelSize: 17; font.weight: Font.DemiBold; color: dialog.c.text; wrapMode: Text.Wrap
                        }
                        Text {
                            Layout.fillWidth: true
                            textFormat: Text.PlainText
                            text: [app.t["rs_type_" + (dialog.room.type || 2)] || "", dialog.room.type === 6 ? ""
                                   : app.plural("participants", meet.participants.length)].filter(x => x).join(" · ")
                            font.pixelSize: 12; color: dialog.c.muted
                        }
                    }
                }
                // the picture: an emoji on a colour, or a picture of this computer
                Line { visible: pictureRow.visible }
                ColumnLayout {
                    id: pictureRow
                    visible: dialog.mod && dialog.group && !!dialog.can.avatar
                    Layout.fillWidth: true
                    Layout.margins: 8
                    spacing: 10
                    RowLayout {
                        spacing: 8
                        OButton { id: emojiButton; iconName: "smile"; text: app.t.rs_avatar_emoji; onClicked: emojiPicker.popupAt(emojiButton, true) }
                        OButton { iconName: "image"; text: app.t.rs_avatar_picture; onClicked: pictureDialog.open() }
                        OButton { visible: !!dialog.room.customAvatar; kind: "quiet"; iconName: "trash"; tip: app.t.rs_avatar_remove
                                  onClicked: { dialog.emoji = ""; meet.removeAvatar() } }
                    }
                    // once an emoji is chosen: its background
                    RowLayout {
                        visible: dialog.emoji !== ""
                        spacing: 6
                        Text { textFormat: Text.PlainText; text: app.t.rs_avatar_color; font.pixelSize: 12; color: dialog.c.muted; Layout.rightMargin: 4 }
                        Repeater {
                            model: ["", "002FA7", "2F7D6D", "8A5A00", "1A5F7A", "7A3B6E", "C8381E", "0F2440"]
                            AbstractButton {
                                id: swatch
                                required property string modelData
                                implicitWidth: 26; implicitHeight: 26
                                hoverEnabled: true
                                Accessible.name: modelData || app.t.rs_avatar_auto
                                onClicked: { dialog.emojiColor = modelData; meet.setAvatarEmoji(dialog.emoji, modelData) }
                                background: Rectangle {
                                    radius: 13
                                    color: swatch.modelData ? "#" + swatch.modelData : dialog.c.tint
                                    border.width: dialog.emojiColor === swatch.modelData ? 2 : 0
                                    border.color: dialog.c.text
                                    Text { anchors.centerIn: parent; visible: !swatch.modelData; text: "A"; font.pixelSize: 11; font.weight: Font.DemiBold; color: dialog.c.tintText }
                                }
                            }
                        }
                    }
                    Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: app.t.rs_avatar_lead; font.pixelSize: 12; color: dialog.c.faint; wrapMode: Text.Wrap }
                }
            }

            Group {
                visible: dialog.room.type !== 1 && dialog.room.type !== 6 && (dialog.mod || (dialog.room.description || "") !== "")
                title: app.t.rs_description
                OTextArea {
                    id: description
                    Layout.fillWidth: true
                    Layout.margins: 4
                    Layout.minimumHeight: 84
                    text: dialog.room.description || ""
                    readOnly: !dialog.mod
                    placeholderText: app.t.add_description
                    wrapMode: TextArea.Wrap
                    font.pixelSize: 14
                    onEditingFinished: if (text !== (dialog.room.description || "")) meet.setDescription(text.slice(0, 2000))
                }
                Text {
                    visible: description.activeFocus
                    Layout.alignment: Qt.AlignRight
                    Layout.rightMargin: 8; Layout.bottomMargin: 4
                    text: description.length + " / 2000"
                    font.pixelSize: 11; color: description.length > 2000 ? dialog.c.danger : dialog.c.faint
                }
            }

            Group {
                visible: dialog.room.type !== 6
                title: app.t.rs_link
                lead: dialog.room["public"] ? app.t.rs_link_public : app.t.rs_link_members
                ActionRow {
                    iconName: "link"
                    text: String(dialog.room.link || "").replace(/^https?:\/\//, "")
                    OButton { iconName: "copy"; text: app.t.copy; onClicked: { app.copy(dialog.room.link); app.toast(app.t.link_copied) } }
                }
            }
        }
    }

    // ---- Pour moi: what the conversation does for me ------------------------------------------------------
    Component {
        id: mePage
        ColumnLayout {
            spacing: 22
            Group {
                title: app.t.notifications
                lead: app.t.rs_notify_lead
                Repeater {
                    model: [
                        { level: 1, icon: "bell", text: app.t.notify_always, lead: app.t.rs_notify_always },
                        { level: 2, icon: "bell", text: app.t.rs_notify_mentions, lead: app.t.rs_notify_mentions_lead },
                        { level: 3, icon: "close", text: app.t.rs_notify_never, lead: app.t.rs_notify_never_lead },
                        { level: 0, icon: "settings", text: app.t.notify_default, lead: dialog.room.type === 1 ? app.t.rs_notify_default_one : app.t.rs_notify_default_group }
                    ]
                    ChoiceRow {
                        required property var modelData
                        iconName: modelData.icon
                        text: modelData.text
                        lead: modelData.lead
                        selected: (dialog.room.notify || 0) === modelData.level
                        onClicked: meet.setNotify(modelData.level)
                    }
                }
                Line { visible: !!(dialog.can.calls || dialog.can.important || dialog.can.sensitive) }
                SwitchRow {
                    visible: !!dialog.can.calls && dialog.room.type !== 6
                    iconName: "phone"; text: app.t.rs_notify_calls; lead: app.t.rs_notify_calls_lead
                    on: !!dialog.room.notifyCalls
                    onToggled: v => meet.setNotifyCalls(v)
                }
                SwitchRow {
                    visible: !!dialog.can.important
                    iconName: "flag"; text: app.t.rs_important; lead: app.t.rs_important_lead
                    on: !!dialog.room.important
                    onToggled: v => meet.setImportant(v)
                }
                SwitchRow {
                    visible: !!dialog.can.sensitive
                    iconName: "eye"; text: app.t.rs_sensitive; lead: app.t.rs_sensitive_lead
                    on: !!dialog.room.sensitive
                    onToggled: v => meet.setSensitive(v)
                }
            }

            Group {
                title: app.t.rs_tidy
                SwitchRow { iconName: "star"; text: app.t.rs_favorite; lead: app.t.rs_favorite_lead; on: !!dialog.room.favorite; onToggled: v => meet.setFavorite(v) }
                SwitchRow { iconName: "archive"; text: app.t.rs_archived; lead: app.t.rs_archived_lead; on: !!dialog.room.archived; onToggled: v => meet.setArchived(v) }
            }

            Group {
                visible: !!dialog.can.tags
                title: app.t.rs_tags
                lead: app.t.rs_tags_lead
                Flow {
                    Layout.fillWidth: true
                    Layout.margins: 8
                    spacing: 6
                    Repeater {
                        model: meet.tags
                        AbstractButton {
                            id: chip
                            required property var modelData
                            required property int index
                            readonly property bool on: (dialog.room.tagIds || []).indexOf(modelData.id) >= 0
                            readonly property color tone: dialog.c["tag" + (index % 5 + 1)]
                            implicitHeight: 30
                            implicitWidth: chipRow.implicitWidth + 20
                            hoverEnabled: true
                            Accessible.role: Accessible.CheckBox
                            Accessible.checked: on
                            Accessible.name: modelData.name
                            onClicked: meet.setTag(modelData.id, !on)
                            TapHandler { acceptedButtons: Qt.RightButton; onTapped: tagMenu.openFor(chip.modelData, chip) }
                            background: Rectangle {
                                radius: 15
                                color: chip.on ? Qt.alpha(chip.tone, theme.dark ? 0.26 : 0.14) : chip.hovered ? dialog.c.hover : "transparent"
                                border.width: 1; border.color: chip.on ? Qt.alpha(chip.tone, 0.6) : dialog.c.line
                            }
                            contentItem: RowLayout {
                                id: chipRow
                                spacing: 6
                                Rectangle { Layout.leftMargin: 10; implicitWidth: 8; implicitHeight: 8; radius: 4; color: chip.tone }
                                Text { textFormat: Text.PlainText; text: chip.modelData.name; font.pixelSize: 13; color: dialog.c.text }
                                Icon { Layout.rightMargin: 10; visible: chip.on; name: "check"; size: 13; color: chip.tone }
                            }
                        }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Layout.margins: 8
                    spacing: 8
                    OTextField {
                        id: newTag
                        Layout.fillWidth: true
                        placeholderText: app.t.rs_tag_new
                        onAccepted: if (text.trim()) { meet.createTag(text); text = "" }
                    }
                    OButton { iconName: "plus"; text: app.t.add; enabled: newTag.text.trim() !== ""
                              onClicked: { meet.createTag(newTag.text); newTag.text = "" } }
                }
            }
        }
    }

    // ---- Accès: who may come in --------------------------------------------------------------------------
    Component {
        id: accessPage
        ColumnLayout {
            spacing: 22
            Group {
                title: app.t.rs_who
                SwitchRow {
                    visible: !!dialog.can.listable
                    iconName: "people"; text: app.t.rs_listable; lead: app.t.rs_listable_lead
                    on: (dialog.room.listable || 0) > 0
                    onToggled: v => meet.setListable(v ? 1 : 0)
                }
                SwitchRow {
                    iconName: "globe"; text: app.t.public_link; lead: app.t.public_link_lead
                    on: !!dialog.room["public"]
                    onToggled: v => meet.setPublic(v)
                }
                ColumnLayout {
                    visible: !!dialog.room["public"]
                    Layout.fillWidth: true
                    spacing: 0
                    Line {}
                    SwitchRow {
                        iconName: "lock"; text: app.t.password
                        lead: dialog.room.hasPassword ? app.t.password_on : app.t.password_lead
                        on: !!dialog.room.hasPassword
                        onToggled: v => { if (v) passwordDialog.ask(); else meet.setPassword("") }
                    }
                    ActionRow {
                        visible: !!dialog.room.hasPassword
                        text: app.t.rs_password_change
                        OButton { text: app.t.rs_change; onClicked: passwordDialog.ask() }
                    }
                    ActionRow {
                        iconName: "link"
                        text: String(dialog.room.link || "").replace(/^https?:\/\//, "")
                        OButton { iconName: "copy"; text: app.t.copy; onClicked: { app.copy(dialog.room.link); app.toast(app.t.link_copied) } }
                    }
                }
            }

            Group {
                visible: !!dialog.can.csv || (dialog.room.emailGuests || 0) > 0
                title: app.t.rs_email_invites
                lead: app.t.rs_email_invites_lead
                ActionRow {
                    visible: (dialog.room.emailGuests || 0) > 0
                    iconName: "mail"
                    text: app.plural("rs_email_guests", dialog.room.emailGuests || 0)
                    OButton { text: app.t.rs_resend; onClicked: meet.resendInvitations(0) }
                }
                ActionRow {
                    visible: !!dialog.can.csv
                    iconName: "import"
                    text: app.t.rs_csv
                    lead: app.t.rs_csv_lead
                    OButton { text: app.t.rs_csv_choose; onClicked: csvDialog.open() }
                }
            }

            Group {
                title: app.t.lobby
                SwitchRow {
                    iconName: "clock"; text: app.t.rs_lobby; lead: app.t.lobby_lead
                    on: dialog.room.lobby === 1
                    onToggled: v => meet.setLobby(v)
                }
                ColumnLayout {
                    visible: dialog.room.lobby === 1
                    Layout.fillWidth: true
                    Layout.margins: 8; Layout.leftMargin: 38
                    spacing: 8
                    Text {
                        Layout.fillWidth: true
                        textFormat: Text.PlainText
                        text: dialog.room.lobbyTimer ? app.t.lobby_opens.replace("%1", app.when(dialog.room.lobbyTimer)) : app.t.lobby_no_timer
                        font.pixelSize: 12; color: dialog.c.muted; wrapMode: Text.Wrap
                    }
                    WhenPicker { id: lobbyWhen; Layout.fillWidth: true }
                    RowLayout {
                        spacing: 8
                        OButton { text: app.t.lobby_set_timer; onClicked: meet.setLobbyTimer(lobbyWhen.value) }
                        OButton { visible: !!dialog.room.lobbyTimer; kind: "quiet"; text: app.t.lobby_clear_timer; onClicked: meet.setLobbyTimer(0) }
                    }
                }
            }
        }
    }

    // ---- Autorisations: what the participants may do (moderators may do everything) ---------------------
    property bool customPermissions: false
    onPageChanged: customPermissions = false
    Component {
        id: permissionsPage
        ColumnLayout {
            id: perms
            spacing: 22
            readonly property int value: (dialog.room.defaultPermissions || 0) & ~1
            readonly property string preset: dialog.customPermissions ? "custom" : value === 0 || value === 510 ? "all"
                                             : value === 388 ? "restricted" : "custom"
            Group {
                title: app.t.rs_perm_title
                lead: app.t.rs_perm_lead
                ChoiceRow { iconName: "unlock"; text: app.t.rs_perm_all; lead: app.t.rs_perm_all_lead; selected: perms.preset === "all"
                            onClicked: { dialog.customPermissions = false; if (perms.preset !== "all") meet.setDefaultPermissions(0) } }
                ChoiceRow { iconName: "lock"; text: app.t.rs_perm_restricted; lead: app.t.rs_perm_restricted_lead; selected: perms.preset === "restricted"
                            onClicked: { dialog.customPermissions = false; if (perms.preset !== "restricted") meet.setDefaultPermissions(388) } }
                ChoiceRow { iconName: "settings"; text: app.t.rs_perm_custom; lead: app.t.rs_perm_custom_lead; selected: perms.preset === "custom"
                            onClicked: dialog.customPermissions = true }
                PermissionsEditor {
                    visible: perms.preset === "custom"
                    Layout.fillWidth: true
                    Layout.leftMargin: 30; Layout.bottomMargin: 4
                    value: perms.value === 0 ? 510 : perms.value
                    // nothing at all would be read as Talk's default (everything): one box stays
                    onEdited: v => meet.setDefaultPermissions(v === 0 ? 4 : v)
                }
            }
            Group {
                title: app.t.rs_writing
                SwitchRow {
                    visible: !!dialog.can.mentions
                    iconName: "people"; text: app.t.rs_mention_all; lead: app.t.rs_mention_all_lead
                    on: !!dialog.room.mentionModerators
                    onToggled: v => meet.setMentionModerators(v)
                }
                SwitchRow {
                    iconName: "lock"; text: app.t.rs_lock; lead: app.t.read_only_lead
                    on: !!dialog.room.readOnly
                    onToggled: v => meet.setReadOnly(v)
                }
            }
        }
    }

    // ---- Messages: how long they stay -------------------------------------------------------------------
    Component {
        id: messagesPage
        ColumnLayout {
            spacing: 22
            Group {
                title: app.t.expiration
                lead: app.t.rs_expiration_lead
                Flow {
                    Layout.fillWidth: true
                    Layout.margins: 8
                    spacing: 6
                    Repeater {
                        model: [[0, app.t.expire_off], [3600, app.t.expire_1h], [28800, app.t.expire_8h], [86400, app.t.expire_1d],
                                [604800, app.t.expire_1w], [2419200, app.t.expire_4w]]
                        AbstractButton {
                            id: delay
                            required property var modelData
                            readonly property bool on: (dialog.room.expiration || 0) === modelData[0]
                            implicitHeight: 32; implicitWidth: delayText.implicitWidth + 28
                            hoverEnabled: true
                            Accessible.role: Accessible.RadioButton
                            Accessible.checked: on
                            Accessible.name: modelData[1]
                            onClicked: if (!on) meet.setExpiration(modelData[0])
                            background: Rectangle { radius: 16; color: delay.on ? dialog.c.action : delay.hovered ? dialog.c.hover : "transparent"
                                                    border.width: delay.on ? 0 : 1; border.color: dialog.c.line }
                            contentItem: Text { id: delayText; textFormat: Text.PlainText; text: delay.modelData[1]; font.pixelSize: 13
                                                horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                                                color: delay.on ? dialog.c.actionText : dialog.c.text }
                        }
                    }
                }
            }
            Group {
                visible: !!dialog.can.clear
                title: app.t.rs_history
                ActionRow {
                    iconName: "trash"
                    text: app.t.rs_clear
                    lead: app.t.rs_clear_lead
                    OButton { kind: "danger"; text: app.t.rs_clear_short
                              onClicked: choice.ask(app.t.rs_clear, app.t.rs_clear_lead, [
                                  { id: "cancel", text: app.t.cancel }, { id: "clear", text: app.t.rs_clear_short, kind: "danger" }],
                                  id => { if (id === "clear") meet.clearHistory() }) }
                }
            }
        }
    }

    // ---- Robots: the call summary first in the user's language, the other languages folded ----------------
    property bool otherBots: false
    Component {
        id: botsPage
        ColumnLayout {
            id: bots
            spacing: 22
            readonly property var all: meet.roomSettings.bots || []
            readonly property var first: all.filter(b => b.mine || b.state !== 0)
            readonly property var rest: all.filter(b => !b.mine && b.state === 0)
            function about(b) { const i = b.description.indexOf(" - "); return i > 0 ? b.description.slice(i + 3) : b.description }
            Group {
                title: app.t.rs_bots_title
                lead: app.t.rs_bots_lead
                Repeater {
                    model: bots.first.length ? bots.first : bots.rest
                    SwitchRow {
                        required property var modelData
                        iconName: "sparkle"
                        text: modelData.name
                        lead: bots.about(modelData) + (modelData.state === 2 ? " · " + app.t.rs_bot_always : "")
                        on: modelData.state !== 0
                        enabled: modelData.state !== 2
                        onToggled: v => meet.setBot(modelData.id, v)
                    }
                }
                AbstractButton {
                    visible: bots.first.length > 0 && bots.rest.length > 0
                    Layout.fillWidth: true
                    implicitHeight: 40
                    hoverEnabled: true
                    onClicked: dialog.otherBots = !dialog.otherBots
                    background: Rectangle { radius: 8; color: parent.hovered ? dialog.c.hover : "transparent" }
                    contentItem: RowLayout {
                        spacing: 10
                        Icon { Layout.leftMargin: 8; name: dialog.otherBots ? "collapse" : "expand"; size: 16; color: dialog.c.muted }
                        Text { textFormat: Text.PlainText; Layout.fillWidth: true; font.pixelSize: 13; color: dialog.c.action
                               text: app.plural("rs_bots_other", bots.rest.length) }
                    }
                }
                Repeater {
                    model: dialog.otherBots && bots.first.length ? bots.rest : []
                    SwitchRow {
                        required property var modelData
                        iconName: "globe"
                        text: modelData.name
                        lead: bots.about(modelData)
                        on: modelData.state !== 0
                        onToggled: v => meet.setBot(modelData.id, v)
                    }
                }
            }
        }
    }

    // ---- Quitter, supprimer -------------------------------------------------------------------------------
    Component {
        id: dangerPage
        ColumnLayout {
            spacing: 22
            Group {
                visible: dialog.showPreserve
                title: app.t.rs_keep
                SwitchRow {
                    iconName: "pin"; text: app.t.rs_preserve; lead: app.t.rs_preserve_lead
                    on: !!dialog.room.preserved
                    onToggled: v => meet.setPreserved(v)
                }
            }
            Group {
                title: app.t.rs_leave_or_delete
                ActionRow {
                    visible: dialog.room.canLeave !== false
                    iconName: "export"
                    text: app.t.leave_conversation
                    lead: app.t.leave_lead
                    OButton { kind: "secondary"; danger: true; text: app.t.leave
                              onClicked: choice.ask(app.t.leave_conversation, app.t.leave_lead, [
                                  { id: "cancel", text: app.t.cancel }, { id: "leave", text: app.t.leave, kind: "danger" }],
                                  id => { if (id === "leave") { dialog.close(); meet.leaveRoom() } }) }
                }
                Line { visible: dialog.room.canLeave !== false && dialog.room.canDelete === true }
                ActionRow {
                    visible: dialog.room.canDelete === true
                    iconName: "trash"
                    text: app.t.delete_conversation
                    lead: app.t.delete_lead
                    OButton { kind: "danger"; text: app.t.delete_for_all
                              onClicked: choice.ask(app.t.delete_conversation, app.t.delete_lead, [
                                  { id: "cancel", text: app.t.cancel }, { id: "delete", text: app.t.delete_for_all, kind: "danger" }],
                                  id => { if (id === "delete") { dialog.close(); meet.deleteRoom() } }) }
                }
            }
        }
    }

    // ---- around the pages ---------------------------------------------------------------------------------
    EmojiPicker { id: emojiPicker; onPicked: e => { dialog.emoji = e; meet.setAvatarEmoji(e, dialog.emojiColor) } }
    FileDialog {
        id: pictureDialog
        currentFolder: Std.StandardPaths.writableLocation(Std.StandardPaths.PicturesLocation)
        title: app.t.rs_avatar_picture
        nameFilters: [app.t.rs_images + " (*.png *.jpg *.jpeg *.webp *.gif *.bmp *.heic *.avif)"]
        onAccepted: { dialog.emoji = ""; meet.setAvatarFile(String(selectedFile)) }
    }
    FileDialog {
        id: csvDialog
        currentFolder: Std.StandardPaths.writableLocation(Std.StandardPaths.HomeLocation)
        title: app.t.rs_csv
        nameFilters: ["CSV (*.csv)"]
        onAccepted: meet.importEmails(String(selectedFile), true)
    }
    // a CSV: first counted, then invited once the moderator agrees
    Connections {
        target: meet
        function onEmailsImported(r) {
            if (!r.ok) { app.toast(r.message || app.t.csv_failed); return }
            if (!r.testRun) { app.toast(app.plural("rs_csv_done", r.invites)); return }
            if (!r.invites) { app.toast(app.t.rs_csv_nobody); return }
            const notes = [r.duplicates ? app.plural("rs_csv_duplicates", r.duplicates) : "",
                           r.invalid ? app.plural("rs_csv_invalid", r.invalid) : ""].filter(x => x).join(" ")
            choice.ask(app.plural("rs_csv_confirm", r.invites), (app.t.rs_csv_confirm_lead + " " + notes).trim(), [
                { id: "cancel", text: app.t.cancel }, { id: "go", text: app.t.rs_csv_send, kind: "primary" }],
                id => { if (id === "go") meet.importEmails(r.file, false) })
        }
    }
    MeetMenu {
        id: tagMenu
        property var tag: ({})
        function openFor(t, item) { tag = t; popupAt(item, true) }
        OMenuItem { text: app.t.rs_tag_rename; iconName: "edit"; onTriggered: tagRename.ask(tagMenu.tag) }
        OMenuItem { text: app.t.rs_tag_delete; iconName: "trash"; danger: true
                    onTriggered: choice.ask(app.t.rs_tag_delete, app.t.rs_tag_delete_lead.replace("%1", tagMenu.tag.name), [
                        { id: "cancel", text: app.t.cancel }, { id: "delete", text: app.t.rs_tag_delete, kind: "danger" }],
                        id => { if (id === "delete") meet.deleteTag(tagMenu.tag.id) }) }
    }
    ODialog {
        id: tagRename
        property var tag: ({})
        function ask(t) { tag = t; tagName.text = t.name; open(); tagName.forceActiveFocus(); tagName.selectAll() }
        title: app.t.rs_tag_rename
        OTextField { id: tagName; Layout.fillWidth: true; onAccepted: renameOk.clicked() }
        footer: [
            OButton { text: app.t.cancel; onClicked: tagRename.close() },
            OButton { id: renameOk; kind: "primary"; text: app.t.save; enabled: tagName.text.trim() !== ""
                      onClicked: { meet.renameTag(tagRename.tag.id, tagName.text); tagRename.close() } }
        ]
    }
    ODialog {
        id: passwordDialog
        function ask() { passwordField.text = ""; open(); passwordField.forceActiveFocus() }
        title: app.t.password
        Text { Layout.fillWidth: true; textFormat: Text.PlainText; text: app.t.rs_password_lead; wrapMode: Text.Wrap; font.pixelSize: 13; color: dialog.c.muted }
        OTextField { id: passwordField; Layout.fillWidth: true; echoMode: TextInput.Password; placeholderText: app.t.password
                     onAccepted: if (passwordOk.enabled) passwordOk.clicked() }
        footer: [
            OButton { text: app.t.cancel; onClicked: passwordDialog.close() },
            OButton { id: passwordOk; kind: "primary"; text: app.t.save; enabled: passwordField.text !== ""
                      onClicked: { meet.setPassword(passwordField.text); passwordField.text = ""; passwordDialog.close() } }
        ]
    }
}
