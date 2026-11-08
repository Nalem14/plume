// Ornis settings (Ctrl+,), kept on this computer (ornis.json) except « Personnaliser Ornis » (the cloud's). A window
// with its sections on the left, as in the other assistants: General (appearance, how the conversations behave),
// Personalisation (the cloud's profile), this computer (what Ornis may do without asking: ornis_consent, shared with
// « Ornis sur cet ordinateur »), today's allowance, the conversations themselves (delete them all), the shortcuts.
// Narrow, the sections become a row of tabs above the page.
import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Layouts
import "components"
import "shortcuts.js" as Shortcuts

Popup {
    id: dialog
    signal deleteAllRequested()
    signal profileRequested()          // « Personnaliser Ornis » (ProfileDialog, beside this one in the view)
    signal commandsRequested()         // « Mes commandes » (CommandsDialog)
    readonly property var c: theme.c
    property int tab: 0                // kept from one opening to the next
    readonly property bool narrow: width < 680
    readonly property var tabs: [
        { icon: "settings", text: app.t.settings_general },
        { icon: "user", text: app.t.settings_personal },
        { icon: "devices", text: app.t.settings_computer_tab },
        { icon: "ornis", text: app.t.settings_usage },
        { icon: "archive", text: app.t.settings_data },
        { icon: "hash", text: app.t.shortcuts }
    ]

    // the names of the keys as written on French and German keyboards
    function keyName(keys) { return Shortcuts.keyName(keys, app.lang, Qt.platform.os === "osx" || Qt.platform.os === "macos") }
    function show(index) { tab = index; open() }
    function showUsage() { show(3) }      // the usage panel (the gauge at the bottom of the column)
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
    width: Math.min(880, parent ? parent.width - 48 : 880)
    height: Math.min(620, parent ? parent.height - 48 : 620)

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
    Shortcut { sequence: "Ctrl+Tab"; enabled: dialog.opened; onActivated: dialog.tab = (dialog.tab + 1) % dialog.tabs.length }
    Shortcut { sequence: "Ctrl+Shift+Tab"; enabled: dialog.opened; onActivated: dialog.tab = (dialog.tab + dialog.tabs.length - 1) % dialog.tabs.length }

    // a heading between groups
    component Heading: Text {
        Layout.fillWidth: true
        Layout.topMargin: 14
        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
        font.capitalization: Font.AllUppercase; font.letterSpacing: 0.4
        color: dialog.c.muted
    }
    // a choice among a few (the selected one tinted), its label on the left
    component Choice: RowLayout {
        id: choice
        property string label
        property string pref               // a preference of ornis.json, or empty: `current` and `chosen` instead
        property var current: app.prefs[pref]
        signal chosen(var value)
        property var options: []           // [{value, text}]
        Layout.fillWidth: true
        spacing: 12
        Text {
            Layout.fillWidth: true
            text: choice.label
            font.family: "Schibsted Grotesk"; font.pixelSize: 14
            color: dialog.c.text
            wrapMode: Text.Wrap
        }
        Rectangle {
            implicitWidth: segments.implicitWidth + 6
            implicitHeight: 34
            radius: 8
            color: dialog.c.field
            border.width: 1; border.color: dialog.c.line
            Row {
                id: segments
                anchors.centerIn: parent
                spacing: 2
                Repeater {
                    model: choice.options
                    AbstractButton {
                        id: seg
                        required property var modelData
                        readonly property bool selected: choice.current === modelData.value
                        implicitWidth: segText.implicitWidth + 22
                        implicitHeight: 28
                        hoverEnabled: true
                        focusPolicy: Qt.StrongFocus
                        onClicked: choice.pref ? app.setPref(choice.pref, modelData.value) : choice.chosen(modelData.value)
                        Accessible.name: choice.label + " : " + modelData.text
                        Accessible.checked: selected
                        background: Rectangle {
                            radius: 6
                            color: seg.selected ? dialog.c.tint : seg.hovered ? dialog.c.hover : "transparent"
                            border.width: seg.visualFocus ? 2 : 0; border.color: dialog.c.saffron
                        }
                        contentItem: Text {
                            id: segText
                            text: seg.modelData.text
                            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13
                            font.weight: seg.selected ? Font.DemiBold : Font.Normal
                            color: seg.selected ? dialog.c.tintText : dialog.c.text
                        }
                    }
                }
            }
        }
    }
    // an option on or off, with a line saying what it does
    component Option: ColumnLayout {
        id: option
        property string label
        property string hint
        property string pref
        property bool byDefault: true
        Layout.fillWidth: true
        spacing: 2
        OSwitch {
            Layout.fillWidth: true
            text: option.label
            checked: option.byDefault ? app.prefs[option.pref] !== false : app.prefs[option.pref] === true
            onToggled: app.setPref(option.pref, checked)
        }
        Text {
            visible: option.hint !== ""
            Layout.fillWidth: true
            leftPadding: 46
            text: option.hint
            wrapMode: Text.Wrap
            font.family: "Schibsted Grotesk"; font.pixelSize: 12
            color: dialog.c.muted
        }
    }
    component Key: RowLayout {
        id: key
        property string keys
        property string label
        Layout.fillWidth: true
        spacing: 12
        Text {
            Layout.fillWidth: true
            text: key.label
            wrapMode: Text.Wrap
            font.family: "Schibsted Grotesk"; font.pixelSize: 13
            color: dialog.c.text
        }
        Rectangle {
            implicitWidth: keyText.implicitWidth + 14; implicitHeight: 24; radius: 5
            color: dialog.c.field
            border.width: 1; border.color: dialog.c.line
            Text {
                id: keyText
                anchors.centerIn: parent
                text: dialog.keyName(key.keys)
                font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.Medium
                color: dialog.c.muted
            }
        }
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
        onClicked: dialog.tab = index
        Keys.onDownPressed: dialog.tab = Math.min(dialog.tabs.length - 1, dialog.tab + 1)
        Keys.onUpPressed: dialog.tab = Math.max(0, dialog.tab - 1)
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
    // a page: its content scrolls under a fixed title
    component Page: ScrollView {
        id: page
        default property alias content: pageBody.data
        contentWidth: availableWidth
        contentHeight: pageBody.implicitHeight + 36
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ColumnLayout {
            id: pageBody
            x: dialog.narrow ? 20 : 28; y: 4
            width: Math.min(page.availableWidth - 2 * x, 620)
            spacing: 12
        }
    }

    contentItem: RowLayout {
        spacing: 0
        Accessible.role: Accessible.Dialog
        Accessible.name: app.t.settings
        // ---- the sections ------------------------------------------------------------------------------------
        Rectangle {
            visible: !dialog.narrow
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
                    Layout.leftMargin: 10; Layout.bottomMargin: 12
                    text: app.t.settings
                    font.family: "Schibsted Grotesk"; font.pixelSize: 18; font.weight: Font.DemiBold
                    color: dialog.c.text
                }
                Repeater {
                    model: dialog.tabs
                    TabButton { Layout.fillWidth: true }
                }
                Item { Layout.fillHeight: true }
                Text {
                    Layout.fillWidth: true; Layout.leftMargin: 10; Layout.rightMargin: 10
                    text: app.t.settings_where
                    wrapMode: Text.Wrap
                    font.family: "Schibsted Grotesk"; font.pixelSize: 11
                    color: dialog.c.faint
                }
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
                    text: dialog.narrow ? app.t.settings : dialog.tabs[dialog.tab].text
                    elide: Text.ElideRight
                    font.family: "Schibsted Grotesk"; font.pixelSize: 20; font.weight: Font.DemiBold
                    color: dialog.c.text
                    Accessible.role: Accessible.Heading
                }
                OButton { kind: "quiet"; iconName: "close"; tip: app.t.close; height_: 32; onClicked: dialog.close() }
            }
            Flickable {                                   // narrow: the sections as a row of tabs
                id: tabStrip
                visible: dialog.narrow
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
            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: dialog.c.hairline; visible: dialog.narrow }
            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.topMargin: 6
                currentIndex: dialog.tab

                Page {   // General
            Heading { text: app.t.settings_appearance; Layout.topMargin: 0 }
            Choice {
                label: app.t.theme; pref: "theme"
                options: [{ value: "system", text: app.t.theme_system }, { value: "light", text: app.t.theme_light },
                          { value: "dark", text: app.t.theme_dark }]
            }
            Choice {
                label: app.t.text_size; pref: "text_size"
                options: [{ value: "small", text: app.t.size_small }, { value: "normal", text: app.t.size_normal },
                          { value: "large", text: app.t.size_large }]
            }
            Choice {
                label: app.t.width; pref: "width"
                options: [{ value: "narrow", text: app.t.width_narrow }, { value: "normal", text: app.t.width_normal },
                          { value: "wide", text: app.t.width_wide }]
            }

            Heading { text: app.t.settings_chat }
            Option { label: app.t.enter_sends; hint: app.t.enter_sends_hint; pref: "enter_sends" }
            Option { label: app.t.remember_new; hint: app.t.remember_new_hint; pref: "remember_new"; byDefault: false }
            Option { label: app.t.show_tools; pref: "show_tools" }
            Option { label: app.t.reasoning_open; pref: "reasoning_open" }
            Choice {
                label: app.t.code_reasoning_label; pref: "code_reasoning"
                options: [{ value: "off", text: app.t.code_reasoning_off }, { value: "low", text: app.t.code_reasoning_low },
                          { value: "medium", text: app.t.code_reasoning_medium }, { value: "high", text: app.t.code_reasoning_high }]
            }
            Text {
                Layout.fillWidth: true
                text: app.t.code_reasoning_hint
                wrapMode: Text.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: dialog.c.muted
            }
            Option { label: app.t.suggestions_pref; pref: "suggestions" }
            Option { label: app.t.notify_pref; hint: app.t.notify_hint; pref: "notify" }

                }
                Page {   // Personalisation
            Text {
                Layout.fillWidth: true
                text: app.t.profile_lead
                wrapMode: Text.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                color: dialog.c.muted
            }
            OButton { text: app.t.profile_open; iconName: "user"; onClicked: dialog.profileRequested() }
            Text {
                Layout.fillWidth: true
                Layout.topMargin: 10
                text: app.t.commands_lead
                wrapMode: Text.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                color: dialog.c.muted
            }
            OButton { text: app.t.commands_open; iconName: "terminal"; onClicked: dialog.commandsRequested() }

                }
                Page {   // this computer
                    Text {
                        Layout.fillWidth: true
                        text: app.computerEnvironment
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.Medium
                        color: dialog.c.muted
                    }
            Option { label: app.t.local_tools; hint: app.t.local_tools_hint; pref: "local_tools" }
            Text {
                Layout.fillWidth: true
                text: app.t.computer_lead
                wrapMode: Text.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                color: dialog.c.muted
            }
            Choice {
                label: app.t.computer_mode
                current: app.computerMode
                onChosen: value => app.setComputerMode(value)
                options: [{ value: "ask", text: app.t.computer_ask }, { value: "auto", text: app.t.computer_auto },
                          { value: "full", text: app.t.computer_full }]
            }
            Text {
                Layout.fillWidth: true
                text: app.t["computer_" + app.computerMode + "_hint"]
                      + (app.computerUntil ? " " + app.t.computer_until.replace("%1", app.computerUntil) : "")
                wrapMode: Text.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                color: app.computerMode === "full" ? dialog.c.saffronInk : dialog.c.muted
            }
            RowLayout {
                spacing: 8
                OButton { text: app.t.computer_open; iconName: "devices"; onClicked: app.openComputer() }
                OButton { text: app.t.extensions_open; iconName: "sparkle"; onClicked: app.openExtensions() }
            }

                }
                Page {   // usage: 24 h hour by hour, the AI offers (the gauge of the column opens it)
            UsagePanel { Layout.fillWidth: true }
                }
                Page {   // the conversations
            Text {
                Layout.fillWidth: true
                text: app.t.data_lead
                wrapMode: Text.Wrap
                lineHeight: 1.25
                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                color: dialog.c.muted
            }
            RowLayout {
                spacing: 8
                OButton { text: app.t.open_cloud; iconName: "openExternal"; onClicked: app.openCloud("/apps/assistant/") }
                OButton {
                    enabled: chat.count > 0 && !chat.busy
                    opacity: enabled ? 1 : 0.5
                    text: app.t.delete_all; iconName: "trash"; danger: true
                    onClicked: dialog.deleteAllRequested()
                }
            }

                }
                Page {   // shortcuts
            Repeater {
                model: dialog.opened && dialog.tab === 5 ? Shortcuts.rows(app.t, chat.voice) : []
                Key { required property var modelData; keys: modelData[0]; label: modelData[1] }
            }

                }
            }
        }
    }
}
