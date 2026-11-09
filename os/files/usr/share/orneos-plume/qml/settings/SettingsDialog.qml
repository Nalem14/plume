// Plume's settings (the gear of the column, Ctrl+,), as in the Ornis app: the sections on the left, one page each.
// Those of the module shown: Courrier (its mailboxes, reading, writing, privacy), Agenda; then the account, with
// Plume's start and updates. Narrow, the sections become a row of tabs above the page. Every choice applies at once.
import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Layouts
import "../components"
import "../mail"

Popup {
    id: dialog
    readonly property var c: theme.c
    readonly property bool narrow: width < 680
    // the module shown (in the suite, the one open; in an app of Orneos OS, the app's)
    readonly property bool mailShown: plume.module === "mail"
    readonly property bool calendarShown: plume.module === "calendar"
    readonly property var tabs: (mailShown ? [
        { key: "boxes", icon: "inbox", text: plume.t.settings_tab_boxes },
        { key: "reading", icon: "mail", text: plume.t.settings_tab_reading },
        { key: "writing", icon: "edit", text: plume.t.settings_tab_writing },
        { key: "privacy", icon: "shield", text: plume.t.settings_tab_privacy }
    ] : calendarShown ? [
        { key: "calendar", icon: "calendar", text: plume.t.calendar }
    ] : []).concat([{ key: "account", icon: "user", text: plume.t.settings_tab_account }])
    property string tabKey: ""                 // kept from one opening to the next
    readonly property int tab: Math.max(0, tabs.findIndex(t => t.key === tabKey))
    readonly property string shown: tabs[tab].key

    function openAt(section) {
        if (section === "boxes" || section === "add_box")
            tabKey = "boxes"
        else if (tabs.some(t => t.key === section))     // « account »: the updates, the start
            tabKey = section
        open()
        if (section === "add_box")
            addBox.openFor()
    }
    function go(index) { tabKey = tabs[(index + tabs.length) % tabs.length].key }
    onTabChanged: Qt.callLater(() => {                // narrow: the chosen tab scrolled into the row
        const b = tabRow.children[tab]
        if (!dialog.narrow || !b)
            return
        if (b.x < tabStrip.contentX)
            tabStrip.contentX = b.x
        else if (b.x + b.width > tabStrip.contentX + tabStrip.width)
            tabStrip.contentX = Math.min(tabStrip.contentWidth - tabStrip.width, b.x + b.width - tabStrip.width)
    })

    parent: Overlay.overlay
    anchors.centerIn: parent
    modal: true
    focus: true
    padding: 0
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    width: Math.min(tabs.length > 1 ? 880 : 640, parent ? parent.width - 48 : 880)
    height: Math.min(640, parent ? parent.height - 48 : 640)

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

    // keyboard: Ctrl+Tab / Ctrl+Shift+Tab or the arrows on the list go from section to section
    Shortcut { sequence: "Ctrl+Tab"; enabled: dialog.opened; onActivated: dialog.go(dialog.tab + 1) }
    Shortcut { sequence: "Ctrl+Shift+Tab"; enabled: dialog.opened; onActivated: dialog.go(dialog.tab - 1) }

    // a heading between groups
    component Heading: Text {
        Layout.fillWidth: true
        Layout.topMargin: 14
        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
        font.capitalization: Font.AllUppercase; font.letterSpacing: 0.4
        color: dialog.c.muted
    }
    // a line under a heading, saying what the group is for
    component Lead: Text {
        Layout.fillWidth: true
        wrapMode: Text.Wrap
        lineHeight: 1.2
        font.family: "Schibsted Grotesk"; font.pixelSize: 13
        color: dialog.c.muted
    }
    // options that go together, on a card
    component Group: Rectangle {
        default property alias rows: groupBody.data
        Layout.fillWidth: true
        implicitHeight: groupBody.implicitHeight + 28
        radius: 10
        color: dialog.c.card
        border.width: 1; border.color: dialog.c.hairline
        ColumnLayout {
            id: groupBody
            x: 16; y: 14
            width: parent.width - 32
            spacing: 14
        }
    }
    // the label of a row and its line on why
    component Label_: ColumnLayout {
        property string label
        property string hint
        Layout.fillWidth: true
        spacing: 2
        Text {
            visible: parent.label !== ""
            Layout.fillWidth: true
            text: parent.label
            wrapMode: Text.Wrap
            font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.Medium
            color: dialog.c.text
        }
        Text {
            visible: parent.hint !== ""
            Layout.fillWidth: true
            text: parent.hint
            wrapMode: Text.Wrap
            font.family: "Schibsted Grotesk"; font.pixelSize: 12
            color: dialog.c.muted
        }
    }
    // one option: what it does, a line on why, the switch on the right
    component Option: RowLayout {
        id: option
        property string label
        property string hint
        property bool checked
        signal toggled(bool value)
        Layout.fillWidth: true
        spacing: 16
        Label_ { label: option.label; hint: option.hint }
        OSwitch {
            checked: option.checked
            Accessible.name: option.label
            onToggled: option.toggled(checked)
        }
    }
    // one choice among a few: what it sets, the list on the right
    component Choice: RowLayout {
        id: choice
        property string label
        property string hint
        property var options: []            // [{text, value}]
        property var value
        signal picked(var value)
        Layout.fillWidth: true
        spacing: 16
        Label_ { label: choice.label; hint: choice.hint }
        OComboBox {
            Layout.preferredWidth: 220
            model: choice.options
            Accessible.name: choice.label
            onModelChanged: select(choice.value)
            Component.onCompleted: select(choice.value)
            onActivated: choice.picked(currentValue)
        }
    }
    component Line_: Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: dialog.c.hairline }
    // a mailbox: its mark, its address and what it is, its buttons
    component BoxRow: RowLayout {
        id: boxRow
        property string address
        property string detail
        property bool warn
        property string icon: "inbox"
        property color mark: dialog.c.hover
        property color markInk: dialog.c.text
        default property alias buttons: boxButtons.data
        Layout.fillWidth: true
        spacing: 12
        Rectangle {
            implicitWidth: 34; implicitHeight: 34; radius: 8
            color: boxRow.mark
            Icon { anchors.centerIn: parent; name: boxRow.icon; size: 18; color: boxRow.markInk }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 0
            Text { Layout.fillWidth: true; text: boxRow.address; elide: Text.ElideMiddle; font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.Medium; color: dialog.c.text }
            Text { Layout.fillWidth: true; text: boxRow.detail; elide: Text.ElideRight; font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: boxRow.warn ? dialog.c.danger : dialog.c.muted }
        }
        RowLayout { id: boxButtons; spacing: 4 }
    }

    // a section of the list on the left (or a tab of the row, narrow)
    component TabButton: AbstractButton {
        id: tb
        required property int index
        required property var modelData
        readonly property bool current: dialog.tab === index
        hoverEnabled: true
        focusPolicy: Qt.StrongFocus
        implicitHeight: 36
        implicitWidth: tbRow.implicitWidth + 24
        onClicked: dialog.tabKey = modelData.key
        Keys.onDownPressed: dialog.go(Math.min(dialog.tabs.length - 1, dialog.tab + 1))
        Keys.onUpPressed: dialog.go(Math.max(0, dialog.tab - 1))
        Accessible.role: Accessible.PageTab
        Accessible.name: modelData.text
        Accessible.selected: current
        background: Rectangle {
            radius: 8
            color: tb.current ? dialog.c.tint : tb.hovered ? dialog.c.hover : "transparent"
            border.width: tb.visualFocus ? 2 : 0; border.color: dialog.c.saffron
        }
        contentItem: Item {
            RowLayout {
                id: tbRow
                anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12
                spacing: 10
                Icon { name: tb.modelData.icon; size: 17; color: tb.current ? dialog.c.tintText : dialog.c.muted }
                Text {
                    Layout.fillWidth: true
                    text: tb.modelData.text
                    elide: Text.ElideRight
                    font.family: "Schibsted Grotesk"; font.pixelSize: 14
                    font.weight: tb.current ? Font.DemiBold : Font.Normal
                    color: tb.current ? dialog.c.tintText : dialog.c.text
                }
            }
        }
    }
    // a page: its content scrolls under a fixed title; only the one shown is made
    component Page: Loader {
        id: pageLoader
        property string key
        default property Component body
        active: dialog.opened && dialog.shown === key
        visible: active
        Layout.fillWidth: true
        Layout.fillHeight: true
        sourceComponent: ScrollView {
            id: page
            contentWidth: availableWidth
            contentHeight: pageBody.implicitHeight + 36
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ColumnLayout {
                id: pageBody
                x: dialog.narrow ? 20 : 28; y: 4
                width: Math.min(page.availableWidth - 2 * x, 620)
                spacing: 12
                Loader { Layout.fillWidth: true; sourceComponent: pageLoader.body }
            }
        }
    }

    contentItem: RowLayout {
        spacing: 0
        Accessible.role: Accessible.Dialog
        Accessible.name: plume.t.settings
        // ---- the sections ------------------------------------------------------------------------------------
        Rectangle {
            visible: !dialog.narrow && dialog.tabs.length > 1
            Layout.fillHeight: true
            Layout.preferredWidth: 232
            radius: 14
            color: dialog.c.chrome
            Rectangle { anchors.right: parent.right; width: 14; height: parent.height; color: parent.color }   // square on the page side
            Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: dialog.c.hairline }
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 12; anchors.topMargin: 18
                spacing: 2
                Text {
                    Layout.fillWidth: true
                    Layout.leftMargin: 10; Layout.bottomMargin: 12
                    text: plume.t.settings
                    elide: Text.ElideRight
                    font.family: "Schibsted Grotesk"; font.pixelSize: 18; font.weight: Font.DemiBold
                    color: dialog.c.text
                }
                Repeater {
                    model: dialog.tabs
                    TabButton { Layout.fillWidth: true }
                }
                Item { Layout.fillHeight: true }
            }
        }
        // ---- the page ----------------------------------------------------------------------------------------
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: dialog.narrow ? 20 : 28; Layout.rightMargin: 12
                Layout.topMargin: 14; Layout.bottomMargin: 6
                Text {
                    Layout.fillWidth: true
                    text: dialog.narrow || dialog.tabs.length === 1 ? plume.t.settings : dialog.tabs[dialog.tab].text
                    elide: Text.ElideRight
                    font.family: "Schibsted Grotesk"; font.pixelSize: 20; font.weight: Font.DemiBold
                    color: dialog.c.text
                    Accessible.role: Accessible.Heading
                }
                OButton { kind: "quiet"; iconName: "close"; tip: plume.t.close; height_: 32; onClicked: dialog.close() }
            }
            Flickable {                                   // narrow: the sections as a row of tabs
                id: tabStrip
                visible: dialog.narrow && dialog.tabs.length > 1
                Layout.fillWidth: true
                Layout.preferredHeight: 44
                Layout.leftMargin: 14; Layout.rightMargin: 14
                contentWidth: tabRow.implicitWidth
                flickableDirection: Flickable.HorizontalFlick
                boundsBehavior: Flickable.StopAtBounds
                clip: true
                Row {
                    id: tabRow
                    spacing: 4
                    Repeater { model: dialog.narrow ? dialog.tabs : []; TabButton {} }
                }
            }
            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: dialog.c.hairline; visible: tabStrip.visible }
            Item { Layout.preferredHeight: 6 }

            // ---- Courrier: the mailboxes Plume reads -----------------------------------------------------------
            Page {
                key: "boxes"
                ColumnLayout {
                    spacing: 12
                    Group {
                        // the Orneos mailbox, always first
                        BoxRow {
                            address: mail.account.address || plume.profile.email || ""
                            detail: plume.t.box_orneos
                            icon: "mail"; mark: dialog.c.tint; markInk: dialog.c.accent
                            OButton {
                                // its name only shows above its folders once there are other mailboxes
                                visible: mail.boxes.length > 0
                                kind: "quiet"; height_: 30; implicitWidth: 30; iconName: "edit"; iconSize: 15
                                tip: plume.t.box_rename
                                onClicked: renamePrompt.ask(plume.t.box_rename_title, plume.t.box_rename_text, "", mail.boxLabel("orneos"),
                                                            plume.t.box_rename_go, value => mail.renameBox("orneos", value))
                            }
                        }
                        Repeater {
                            model: mail.boxes
                            BoxRow {
                                id: boxRow
                                required property var modelData
                                readonly property string status: modelData.status
                                address: modelData.address
                                detail: status === "auth" ? (modelData.oauth ? plume.t.box_status_oauth : plume.t.box_status_auth)
                                    : status === "offline" ? plume.t.box_status_offline
                                    : status === "connecting" ? plume.t.box_status_connecting
                                    : modelData.imapHost
                                warn: status === "auth"
                                icon: status === "ready" ? "inbox" : "lock"
                                mark: status === "ready" ? dialog.c.hover : dialog.c.saffronTint
                                markInk: status === "ready" ? dialog.c.text : dialog.c.saffronInk
                                OButton {
                                    visible: boxRow.status === "auth"
                                    height_: 30; text: boxRow.modelData.oauth ? plume.t.box_reconnect : plume.t.box_password
                                    onClicked: boxRow.modelData.oauth ? addBox.openReconnect(boxRow.modelData) : addBox.openPassword(boxRow.modelData)
                                }
                                OButton {
                                    kind: "quiet"; height_: 30; implicitWidth: 30; iconName: "edit"; iconSize: 15
                                    tip: plume.t.box_rename
                                    onClicked: renamePrompt.ask(plume.t.box_rename_title, plume.t.box_rename_text, "", mail.boxLabel(boxRow.modelData.key),
                                                                plume.t.box_rename_go, value => mail.renameBox(boxRow.modelData.key, value))
                                }
                                OButton {
                                    visible: !boxRow.modelData.oauth
                                    kind: "quiet"; height_: 30; implicitWidth: 30; iconName: "settings"; iconSize: 15
                                    tip: plume.t.box_servers
                                    onClicked: addBox.openServers(boxRow.modelData)
                                }
                                OButton {
                                    kind: "quiet"; height_: 30; implicitWidth: 30; iconName: "trash"; iconSize: 15; danger: true
                                    tip: plume.t.box_remove
                                    onClicked: confirm.ask(plume.t.box_remove_title.replace("%1", boxRow.modelData.address), plume.t.box_remove_text,
                                                           [{ id: "cancel", text: plume.t.cancel }, { id: "go", text: plume.t.box_remove, kind: "danger" }],
                                                           () => mail.removeBox(boxRow.modelData.key))
                                }
                            }
                        }
                    }
                    OButton {
                        enabled: mail.state === "ready"
                        iconName: "plus"; text: plume.t.box_add
                        onClicked: addBox.openFor()
                    }
                    Lead { text: plume.t.box_add_hint }
                }
            }

            // ---- Courrier: reading -------------------------------------------------------------------------
            Page {
                key: "reading"
                ColumnLayout {
                    spacing: 12
                    Heading { text: plume.t.settings_new_mail; Layout.topMargin: 0 }
                    Group {
                        Option {
                            label: plume.t.pref_notify
                            hint: plume.t.pref_notify_hint
                            checked: mail.notifyNew
                            onToggled: value => mail.notifyNew = value
                        }
                        Line_ {}
                        Option {
                            label: plume.t.ornis_auto
                            hint: plume.t.ornis_auto_hint
                            checked: ornis.autoSummary
                            onToggled: value => ornis.autoSummary = value
                        }
                    }
                    Heading { text: plume.t.settings_list }
                    Group {
                        Option {
                            label: plume.t.pref_threads
                            hint: plume.t.pref_threads_hint
                            checked: mail.conversations
                            onToggled: value => mail.conversations = value
                        }
                        Line_ {}
                        Choice {
                            label: plume.t.pref_read_delay
                            hint: plume.t.pref_read_delay_hint
                            options: [0, 2, 5].map(v => ({ text: plume.t["read_delay_" + v], value: v }))
                            value: plume.prefs.mail_read_delay || 0
                            onPicked: value => plume.setPref("mail_read_delay", value)
                        }
                        Line_ {}
                        Option {
                            label: plume.t.pref_advance
                            hint: plume.t.pref_advance_hint
                            checked: !!plume.prefs.mail_advance
                            onToggled: value => plume.setPref("mail_advance", value)
                        }
                    }
                }
            }

            // ---- Courrier: writing -------------------------------------------------------------------------
            Page {
                key: "writing"
                ColumnLayout {
                    spacing: 12
                    Heading { text: plume.t.settings_sending; Layout.topMargin: 0 }
                    Group {
                        Option {
                            label: plume.t.pref_attach_check
                            hint: plume.t.pref_attach_check_hint
                            checked: plume.prefs.mail_attach_check !== false
                            onToggled: value => plume.setPref("mail_attach_check", value)
                        }
                    }
                    Heading { text: plume.t.settings_signatures }
                    Group {
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 16
                            Label_ { hint: plume.t.signatures_lead }
                            OButton { enabled: mail.state === "ready"; iconName: "signature"; text: plume.t.signatures; onClicked: signatures.openFor("") }
                        }
                    }
                    Heading { text: plume.t.templates }
                    Group {
                        Label_ { hint: mail.templates.length ? plume.t.templates_lead : plume.t.templates_none + " " + plume.t.templates_lead }
                        Repeater {
                            model: mail.templates
                            RowLayout {
                                id: templateRow
                                required property var modelData
                                Layout.fillWidth: true
                                spacing: 10
                                Icon { name: "quote"; size: 16; color: dialog.c.muted }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 0
                                    Text { Layout.fillWidth: true; text: templateRow.modelData.name; elide: Text.ElideRight; font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.Medium; color: dialog.c.text }
                                    Text {
                                        visible: !!templateRow.modelData.subject
                                        Layout.fillWidth: true
                                        text: templateRow.modelData.subject || ""
                                        elide: Text.ElideRight
                                        font.family: "Schibsted Grotesk"; font.pixelSize: 12
                                        color: dialog.c.muted
                                    }
                                }
                                OButton {
                                    kind: "quiet"; height_: 28; implicitWidth: 28; iconName: "trash"; iconSize: 14; danger: true
                                    tip: plume.t.template_delete.replace("%1", templateRow.modelData.name)
                                    onClicked: mail.deleteTemplate(templateRow.modelData.name)
                                }
                            }
                        }
                    }
                    Heading { text: plume.t.settings_away }
                    Group {
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 16
                            Label_ { hint: plume.t.autoreply_lead }
                            OButton { iconName: "reply"; text: plume.t.autoreply; onClicked: mail.openAutoreply() }
                        }
                    }
                }
            }

            // ---- Courrier: privacy --------------------------------------------------------------------------
            Page {
                key: "privacy"
                ColumnLayout {
                    spacing: 12
                    Heading { text: plume.t.settings_safety; Layout.topMargin: 0 }
                    Group {
                        Option {
                            label: plume.t.pref_confirm
                            hint: plume.t.pref_confirm_hint
                            checked: !!plume.prefs.mail_confirm
                            onToggled: value => plume.setPref("mail_confirm", value)
                        }
                    }
                    // the senders whose pictures load on their own: one can be taken off
                    Heading { text: plume.t.trusted_senders }
                    Group {
                        Label_ { hint: mail.trustedSenders.length ? plume.t.trusted_senders_hint : plume.t.trusted_none }
                        Repeater {
                            model: mail.trustedSenders
                            RowLayout {
                                required property string modelData
                                Layout.fillWidth: true
                                spacing: 10
                                Icon { name: "image"; size: 16; color: dialog.c.muted }
                                Text {
                                    Layout.fillWidth: true
                                    text: parent.modelData
                                    elide: Text.ElideMiddle
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 14
                                    color: dialog.c.text
                                }
                                OButton {
                                    kind: "quiet"; height_: 28; implicitWidth: 28; iconName: "close"; iconSize: 12
                                    tip: plume.t.trusted_remove
                                    onClicked: mail.untrust(parent.modelData)
                                }
                            }
                        }
                    }
                }
            }

            // ---- Agenda --------------------------------------------------------------------------------------
            Page {
                key: "calendar"
                ColumnLayout {
                    spacing: 12
                    Heading { text: plume.t.settings_views; Layout.topMargin: 0 }
                    Group {
                        Choice {
                            label: plume.t.pref_cal_view
                            options: ["day", "week", "month", "agenda"].map(v => ({ text: plume.t["view_" + v], value: v }))
                            value: plume.prefs.cal_view
                            onPicked: value => plume.setPref("cal_view", value)
                        }
                        Line_ {}
                        Choice {
                            label: plume.t.pref_cal_day_start
                            hint: plume.t.pref_cal_day_start_hint
                            options: [5, 6, 7, 8, 9, 10].map(h => ({ text: Qt.formatTime(new Date(2000, 0, 1, h, 0), Qt.locale(plume.locale), Locale.ShortFormat), value: h }))
                            value: plume.prefs.cal_day_start
                            onPicked: value => plume.setPref("cal_day_start", value)
                        }
                        Line_ {}
                        Option {
                            label: plume.t.pref_cal_tasks
                            hint: plume.t.pref_cal_tasks_hint
                            checked: plume.prefs.cal_tasks !== false
                            onToggled: value => plume.setPref("cal_tasks", value)
                        }
                    }
                    Heading { text: plume.t.settings_new_event }
                    Group {
                        Choice {
                            label: plume.t.pref_cal_default
                            hint: plume.t.pref_cal_default_hint
                            options: [{ text: plume.t.pref_cal_default_auto, value: 0 }].concat(
                                         agenda.calendars.filter(c => !c.readonly).map(c => ({ text: c.name, value: c.id, color: c.color })))
                            value: plume.prefs.cal_default
                            onPicked: value => plume.setPref("cal_default", value)
                        }
                        Line_ {}
                        Choice {
                            label: plume.t.pref_cal_duration
                            options: [[15, "15 min"], [30, "30 min"], [45, "45 min"], [60, "1 h"], [90, "1 h 30"], [120, "2 h"]].map(d => ({ text: d[1], value: d[0] }))
                            value: plume.prefs.cal_duration
                            onPicked: value => plume.setPref("cal_duration", value)
                        }
                        Line_ {}
                        Choice {
                            label: plume.t.pref_cal_reminder
                            options: ["", "0", "10", "30", "60", "1440"].map(v => ({ text: plume.t["reminder_" + v], value: v }))
                            value: plume.prefs.cal_reminder
                            onPicked: value => plume.setPref("cal_reminder", value)
                        }
                    }
                }
            }

            // ---- the account, and Plume itself ------------------------------------------------------------------
            Page {
                key: "account"
                ColumnLayout {
                    spacing: 12
                    Heading { text: plume.t.account; Layout.topMargin: 0 }
                    Group {
                        BoxRow {
                            address: plume.profile.name || plume.profile.email || ""
                            detail: plume.profile.name ? plume.profile.email || "" : ""
                            icon: "user"; mark: dialog.c.tint; markInk: dialog.c.accent
                        }
                        Flow {
                            Layout.fillWidth: true
                            spacing: 8
                            OButton { iconName: "user"; text: plume.t.account_manage; onClicked: plume.openAccount() }
                            OButton { visible: !signin.canSignOut; kind: "quiet"; iconName: "refresh"; text: plume.t.reconnect; onClicked: plume.openConnect() }
                            // Plume signed this computer in (no Orneos Connect): it signs it out too
                            OButton {
                                visible: signin.canSignOut
                                kind: "quiet"; iconName: "lock"; text: plume.t.sign_out
                                onClicked: confirm.ask(plume.t.sign_out_title, plume.t.sign_out_text,
                                                       [{ id: "cancel", text: plume.t.cancel }, { id: "yes", text: plume.t.sign_out, kind: "danger" }],
                                                       () => { dialog.close(); signin.signOut() })
                            }
                        }
                    }
                    // Windows, macOS, Linux without Orneos OS: Plume in the tray can open with the session (the
                    // tray's entry too); on Orneos OS, the system's apps already do
                    Heading { visible: plume.keepRunning; text: plume.t.settings_startup }
                    Group {
                        visible: plume.keepRunning
                        Option {
                            label: plume.t.tray_autostart
                            hint: plume.t.pref_autostart_hint
                            checked: plume.autostart
                            onToggled: value => plume.setAutostart(value)
                        }
                    }
                    // Windows, macOS, AppImage: Plume updates itself (updater.py); the packages of the system follow theirs
                    Heading { visible: updater.enabled; text: plume.t.updates }
                    Group {
                        visible: updater.enabled
                        Label_ { label: plume.t.update_current.replace("%1", updater.current); hint: plume.t.update_auto }
                        // « Rechercher les mises à jour »: what it finds, then the download, then « Mettre à jour »
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12
                            OButton {
                                objectName: "checkUpdates"
                                visible: updater.state !== "ready"
                                kind: "secondary"; iconName: "refresh"
                                text: plume.t.update_check
                                enabled: updater.status !== "checking" && updater.state !== "downloading"
                                onClicked: updater.checkNow()
                            }
                            OButton {
                                visible: updater.state === "ready"
                                kind: "primary"; iconName: "download"
                                text: updater.replaces ? plume.t.update_now : plume.t.update_install
                                onClicked: { dialog.close(); updater.installNow() }
                            }
                            BusyIndicator {
                                visible: updater.status === "checking" || updater.state === "downloading"
                                running: visible
                                implicitWidth: 20; implicitHeight: 20
                            }
                            Text {
                                Layout.fillWidth: true
                                textFormat: Text.PlainText
                                wrapMode: Text.Wrap
                                font.pixelSize: 13
                                text: updater.state === "ready" ? plume.t.update_ready.replace("%1", updater.version)
                                    : updater.state === "downloading" ? plume.t.update_downloading_pct.replace("%1", updater.version).replace("%2", Math.round(updater.progress * 100))
                                    : updater.status === "checking" ? plume.t.update_checking
                                    : updater.status === "uptodate" ? plume.t.update_uptodate
                                    : updater.status === "failed" ? plume.t.update_failed : ""
                                color: updater.status === "failed" ? dialog.c.danger : updater.state === "ready" || updater.status === "uptodate" ? dialog.c.okInk : dialog.c.muted
                            }
                        }
                        Line_ {}
                        Option {
                            label: plume.t.update_unstable
                            checked: updater.channel === "unstable"
                            onToggled: value => updater.setChannel(value ? "unstable" : "stable")
                        }
                    }
                }
            }
        }
    }

    AddBoxDialog { id: addBox }
    SignatureEditor { id: signatures }
    ChoiceDialog { id: confirm }
    PromptDialog { id: renamePrompt }
}
