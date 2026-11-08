// The details of a task, beside the list (like macOS's ⓘ): its title and notes, date and time, reminder,
// repeat (presets or one's own: every N days, some weekdays, until a date, a number of times), flag, priority,
// list, tags, place, link, subtasks (Ornis can suggest them), where it comes from (a mail, a note) and the mails,
// notes and tasks linked to it (dropped on it or « Lier à… »). Every change is saved at once; the title and the
// notes as one types (a sync or another task opened never takes away what is being typed).
// When, reminder, repeat and flag sit together on one card, each behind a line glyph in its colour (no filled
// squares: the brand is spent in the band and the ring, docs/REFONTE-ORNIS.md).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"
import "components/colors.js" as Colors

Rectangle {
    id: panel
    readonly property var c: theme.c
    property string key
    property var d: ({})
    readonly property bool editable: !d.readonly
    signal closed()
    signal deleteRequested(var keys)
    signal breakdown(string key)
    color: c.chrome

    // the title and the notes are filled here, not bound: a sync while one types must not put the old text back
    property string shownKey: ""
    function commitFor(k, before) {
        if (!k || before.readonly) return
        const t = title.text.trim()
        if (t && t !== (before.title || "")) tasks.edit(k, { title: t })
        if (notes.text !== (before.notesFull || "")) tasks.edit(k, { notes: notes.text })
    }
    function reload() {
        if (key !== shownKey) {
            const old = shownKey, before = d
            shownKey = key
            commitFor(old, before)          // what was typed in the task left goes to it
            d = key ? tasks.detail(key) : ({})
            title.text = d.title || ""
            notes.text = d.notesFull || ""
            return
        }
        d = key ? tasks.detail(key) : ({})
        if (!title.activeFocus) title.text = d.title || ""
        if (!notes.activeFocus) notes.text = d.notesFull || ""
    }
    onKeyChanged: reload()
    onVisibleChanged: if (!visible) commitFor(shownKey, d)
    Component.onDestruction: commitFor(shownKey, d)
    Connections { target: tasks; function onChanged() { if (panel.key) panel.reload() } }
    Timer { id: typing; interval: 1200; onTriggered: panel.commitFor(panel.shownKey, panel.d) }
    function set(fields) { if (panel.key && panel.editable) tasks.edit(panel.key, fields) }
    readonly property string day: (d.dueValue || "").slice(0, 10)
    readonly property string clock: (d.dueValue || "").length > 10 ? d.dueValue.slice(11, 16) : ""

    Rectangle { anchors.left: parent.left; width: 1; height: parent.height; color: panel.c.line }

    component Label_: Text {
        Layout.fillWidth: true
        font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
        font.capitalization: Font.AllUppercase; font.letterSpacing: 0.8
        color: panel.c.muted
    }
    component Glyph: Rectangle {
        property string icon
        property color tint
        implicitWidth: 28; implicitHeight: 28; radius: 8
        color: Qt.alpha(tint, theme.dark ? 0.22 : 0.12)
        Icon { anchors.centerIn: parent; name: parent.icon; size: 16; color: parent.tint }
    }
    component Line: RowLayout {
        Layout.fillWidth: true
        Layout.minimumHeight: 34
        spacing: 10
    }
    component Name: Text {
        Layout.fillWidth: true
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: panel.c.text
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: 1
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 18; Layout.rightMargin: 10
            Layout.preferredHeight: 52
            Text {
                Layout.fillWidth: true
                text: app.t.details
                font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                font.capitalization: Font.AllUppercase; font.letterSpacing: 0.9
                color: panel.c.famOrganize
            }
            OButton { kind: "quiet"; implicitWidth: 32; height_: 32; iconName: "close"; iconSize: 14; tip: app.t.close; onClicked: panel.closed() }
        }
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth
            clip: true

            ColumnLayout {
                width: parent.width
                spacing: 10

                Item { Layout.preferredHeight: 6 }
                TextArea {
                    id: title
                    Layout.fillWidth: true
                    Layout.leftMargin: 14; Layout.rightMargin: 14
                    readOnly: !panel.editable
                    wrapMode: TextEdit.Wrap
                    placeholderText: app.t.untitled
                    onTextChanged: if (activeFocus) typing.restart()
                    font.family: "Schibsted Grotesk"; font.pixelSize: 22; font.weight: Font.Bold
                    color: panel.c.text
                    selectionColor: panel.c.tint
                    background: null
                    onActiveFocusChanged: if (!activeFocus && text.trim() && text !== panel.d.title) panel.set({ title: text.trim() })
                    Keys.onReturnPressed: event => { notes.forceActiveFocus(); event.accepted = true }
                }
                TextArea {
                    id: notes
                    Layout.fillWidth: true
                    Layout.leftMargin: 14; Layout.rightMargin: 14
                    readOnly: !panel.editable
                    onTextChanged: if (activeFocus) typing.restart()
                    wrapMode: TextEdit.Wrap
                    placeholderText: app.t.notes_placeholder
                    placeholderTextColor: panel.c.faint
                    font.family: "Schibsted Grotesk"; font.pixelSize: 14
                    color: panel.c.body
                    selectionColor: panel.c.tint
                    background: Rectangle { radius: 8; color: notes.activeFocus ? panel.c.field : "transparent"; border.width: notes.activeFocus ? 1 : 0; border.color: panel.c.line }
                    onActiveFocusChanged: if (!activeFocus && text !== (panel.d.notesFull || "")) panel.set({ notes: text })
                }

                // the web addresses written in the notes, to open in one click
                Flow {
                    id: noteLinks
                    readonly property var urls: Array.from(new Set(notes.text.match(/https?:\/\/[^\s<>()"']+/g) || [])).slice(0, 6)
                    Layout.fillWidth: true
                    Layout.leftMargin: 18; Layout.rightMargin: 18
                    spacing: 6
                    visible: urls.length > 0
                    Repeater {
                        model: noteLinks.urls
                        AbstractButton {
                            id: urlChip
                            required property string modelData
                            implicitHeight: 24; implicitWidth: Math.min(urlText.implicitWidth, 220) + 34
                            hoverEnabled: true
                            onClicked: app.openUrl(modelData.replace(/[.,;:!?]+$/, ""))
                            Accessible.name: app.t.open_link + " " + modelData
                            ToolTip.text: modelData; ToolTip.visible: hovered; ToolTip.delay: 500
                            background: Rectangle { radius: 12; color: urlChip.hovered ? panel.c.tint : panel.c.card; border.width: 1; border.color: panel.c.line }
                            contentItem: Item { Row {
                                anchors.centerIn: parent
                                spacing: 5
                                Icon { anchors.verticalCenter: parent.verticalCenter; name: "link"; size: 13; color: panel.c.accent }
                                Text {
                                    id: urlText
                                    width: Math.min(implicitWidth, 220)
                                    text: urlChip.modelData.replace(/^https?:\/\/(www\.)?/, "").replace(/[.,;:!?]+$/, "")
                                    textFormat: Text.PlainText
                                    elide: Text.ElideRight
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: panel.c.text
                                }
                            } }
                        }
                    }
                }

                // where it comes from
                Flow {
                    Layout.fillWidth: true
                    Layout.leftMargin: 18; Layout.rightMargin: 18
                    spacing: 8
                    visible: !!panel.d.mail || (panel.d.note || "") !== "" || (panel.d.parentTitle || "") !== ""
                    OButton { visible: !!panel.d.mail; height_: 30; iconName: "mail"; iconSize: 15; text: app.t.open_mail + (panel.d.mailFrom ? " · " + panel.d.mailFrom : ""); onClicked: tasks.openMail(panel.key) }
                    OButton { visible: (panel.d.note || "") !== ""; height_: 30; iconName: "note"; iconSize: 15; text: app.t.open_note; onClicked: tasks.openNote(panel.key) }
                    OButton { visible: (panel.d.parentTitle || "") !== ""; height_: 30; iconName: "subtask"; iconSize: 15; text: app.t.subtask_of.replace("%1", panel.d.parentTitle || ""); onClicked: win.select(panel.d.parentKey, true) }
                }

                // the mails, notes and tasks linked to it: a click opens one; dropped here or « Lier à… » adds one
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 18; Layout.rightMargin: 18
                    spacing: 6
                    visible: (panel.d.links || []).length > 0 || panel.editable
                    RowLayout {
                        Layout.fillWidth: true
                        Label_ { text: app.t.links; Layout.fillWidth: true }
                        OButton { visible: panel.editable; kind: "quiet"; height_: 28; iconName: "plus"; iconSize: 15; text: app.t.link_add; onClicked: win.linkTask(panel.key) }
                    }
                    Repeater {
                        model: panel.d.links || []
                        AbstractButton {
                            id: linkLine
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: 36
                            hoverEnabled: true
                            onClicked: tasks.openLink(modelData.url)
                            Accessible.name: modelData.title
                            background: Rectangle { radius: 8; color: linkLine.hovered ? panel.c.hover : panel.c.card; border.width: 1; border.color: panel.c.hairline }
                            contentItem: RowLayout {
                                spacing: 8
                                Icon { Layout.leftMargin: 10; name: linkLine.modelData.icon; size: 16; color: panel.c.accent }
                                Text {
                                    Layout.fillWidth: true
                                    text: linkLine.modelData.title
                                    elide: Text.ElideRight
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.Medium
                                    color: panel.c.text
                                }
                                Text {
                                    text: app.t["link_kind_" + linkLine.modelData.kind] || ""
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 12
                                    color: panel.c.muted
                                }
                                AbstractButton {
                                    visible: panel.editable
                                    Layout.rightMargin: 6
                                    implicitWidth: 24; implicitHeight: 24
                                    hoverEnabled: true
                                    Accessible.name: app.t.link_remove
                                    ToolTip.text: app.t.link_remove; ToolTip.visible: hovered; ToolTip.delay: 500
                                    onClicked: tasks.removeLink(panel.key, linkLine.modelData.url)
                                    background: Rectangle { radius: 12; color: parent.hovered ? panel.c.hover : "transparent" }
                                    contentItem: Item { Icon { anchors.centerIn: parent; name: "close"; size: 10; color: panel.c.muted } }
                                }
                            }
                        }
                    }
                    Text {
                        visible: (panel.d.links || []).length === 0
                        Layout.fillWidth: true
                        text: app.t.link_hint
                        wrapMode: Text.Wrap
                        font.family: "Schibsted Grotesk"; font.pixelSize: 12
                        color: panel.c.faint
                    }
                }

                Surface {
                    Layout.fillWidth: true
                    Layout.leftMargin: 14; Layout.rightMargin: 14; Layout.topMargin: 4
                    Layout.preferredHeight: when.implicitHeight + 16
                ColumnLayout {
                    id: when
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8; leftMargin: 12; rightMargin: 12 }
                    spacing: 4

                    Line {
                        Glyph { icon: "calendar"; tint: panel.c.danger }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            Name { text: app.t.date }
                            Text {
                                visible: panel.day !== ""
                                text: app.dateLabel(panel.day)
                                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                                color: panel.d.dueState === "overdue" ? panel.c.danger : panel.c.accent
                                TapHandler { enabled: panel.editable; onTapped: dates.open() }
                            }
                        }
                        OSwitch {
                            checked: panel.day !== ""
                            enabled: panel.editable
                            onToggled: { if (checked) dates.open(); else panel.set({ due: "" }) }
                        }
                        DatePicker {
                            id: dates
                            y: 34
                            x: -width + 60
                            value: panel.day
                            onPicked: iso => panel.set({ due: iso ? iso + (panel.clock ? "T" + panel.clock : "") : "" })
                            onClosed: if (panel.day === "") panel.reload()
                        }
                    }
                    Line {
                        visible: panel.day !== ""
                        Glyph { icon: "clock"; tint: panel.c.famCommunicate }
                        Name { text: app.t.time }
                        TextField {
                            id: time
                            visible: panel.clock !== ""
                            implicitWidth: 76
                            text: panel.clock
                            inputMask: "99:99"
                            horizontalAlignment: Text.AlignHCenter
                            font.family: "Schibsted Grotesk"; font.pixelSize: 14
                            color: panel.c.text
                            background: Rectangle { radius: 6; color: panel.c.field; border.width: 1; border.color: time.activeFocus ? panel.c.action : panel.c.line }
                            onEditingFinished: {
                                const m = text.match(/^(\d{1,2}):(\d{2})$/)
                                if (m && +m[1] < 24 && +m[2] < 60) panel.set({ due: panel.day + "T" + m[1].padStart(2, "0") + ":" + m[2] })
                            }
                        }
                        OSwitch {
                            checked: panel.clock !== ""
                            enabled: panel.editable
                            // the reminder chosen keeps its meaning (that day ↔ at the time); none: reminded at the time
                            onToggled: panel.set(checked ? Object.assign({ due: panel.day + "T09:00" }, panel.d.alarmKey ? {} : { alarm: "0" })
                                                         : { due: panel.day })
                        }
                    }
                    Line {
                        Glyph { icon: "bell"; tint: panel.c.saffronInk }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            Name { text: app.t.reminder }
                            Text {
                                Layout.fillWidth: true
                                visible: panel.d.alarmKey === "custom" && (panel.d.alarmText || "") !== ""
                                text: panel.d.alarmText || ""
                                wrapMode: Text.WordWrap
                                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                                color: panel.c.accent
                            }
                        }
                        OComboBox {
                            id: alarmBox
                            implicitWidth: 170
                            enabled: panel.editable
                            // with a time: at the time or before it; a day only: that day or the day before, at 9:00;
                            // always: none, or a precise moment (possible without a date)
                            model: [{ text: app.t.reminder_none, value: "" }]
                                   .concat(panel.day === "" ? [] : panel.clock
                                           ? [{ text: app.t.reminder_at, value: "0" }, { text: app.t.reminder_15, value: "15" },
                                              { text: app.t.reminder_60, value: "60" }, { text: app.t.reminder_1440, value: "1440" }]
                                           : [{ text: app.t.reminder_day, value: "0" }, { text: app.t.reminder_eve, value: "1440" }])
                                   .concat(panel.d.alarmKey === "custom" ? [{ text: app.t.reminder_custom, value: "custom" }] : [])
                                   .concat([{ text: app.t.reminder_choose, value: "choose" }])
                            Component.onCompleted: select(panel.d.alarmKey || "")
                            onModelChanged: select(panel.d.alarmKey || "")
                            Connections { target: panel; function onDChanged() { alarmBox.select(panel.d.alarmKey || "") } }
                            onActivated: {
                                if (currentValue === "choose") { reminderDialog.openFor(panel.key, panel.d.alarmAt || "", panel.d.dueValue || ""); select(panel.d.alarmKey || "") }
                                else if (currentValue !== "custom") panel.set({ alarm: currentValue })
                            }
                        }
                    }
                    Line {
                        Glyph { icon: "repeat"; tint: panel.c.muted }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            Name { text: app.t.repeat }
                            Text {
                                Layout.fillWidth: true
                                visible: panel.d.repeatKey === "CUSTOM"
                                text: panel.d.repeatText || ""
                                wrapMode: Text.WordWrap
                                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                                color: panel.c.accent
                                TapHandler { enabled: panel.editable; onTapped: repeatDialog.openFor(panel.key, panel.d.rrule || panel.d.repeatKey || "") }
                            }
                        }
                        OComboBox {
                            id: repeatBox
                            implicitWidth: 170
                            enabled: panel.editable
                            model: [{ text: app.t.repeat_never, value: "" }, { text: app.t.repeat_daily, value: "DAILY" },
                                    { text: app.t.repeat_weekdays, value: "WEEKDAYS" }, { text: app.t.repeat_weekly, value: "WEEKLY" },
                                    { text: app.t.repeat_biweekly, value: "BIWEEKLY" }, { text: app.t.repeat_monthly, value: "MONTHLY" },
                                    { text: app.t.repeat_yearly, value: "YEARLY" }]
                                   .concat(panel.d.repeatKey === "CUSTOM" ? [{ text: app.t.repeat_custom, value: "CUSTOM" }] : [])
                                   .concat([{ text: app.t.repeat_choose, value: "choose" }])
                            Component.onCompleted: select(panel.d.repeatKey || "")
                            onModelChanged: select(panel.d.repeatKey || "")
                            Connections { target: panel; function onDChanged() { repeatBox.select(panel.d.repeatKey || "") } }
                            onActivated: {
                                if (currentValue === "choose") { repeatDialog.openFor(panel.key, panel.d.rrule || panel.d.repeatKey || ""); select(panel.d.repeatKey || "") }
                                else if (currentValue !== "CUSTOM") panel.set(Object.assign({ repeat: currentValue }, panel.day ? {} : { due: new Date().toISOString().slice(0, 10) }))
                            }
                        }
                    }
                    Line {
                        Glyph { icon: "flag"; tint: panel.c.saffronInk }
                        Name { text: app.t.flag }
                        OSwitch { checked: !!panel.d.flagged; enabled: panel.editable; onToggled: panel.set({ flagged: checked }) }
                    }
                }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 18; Layout.rightMargin: 18
                    spacing: 8
                    Label_ { text: app.t.priority; Layout.topMargin: 10 }
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 34
                        radius: 9
                        color: panel.c.bg
                        border.width: 1; border.color: panel.c.line
                    RowLayout {
                        anchors.fill: parent; anchors.margins: 3
                        spacing: 0
                        Repeater {
                            model: [{ v: 0, t: app.t.priority_0 }, { v: 9, t: app.t.priority_9 }, { v: 5, t: app.t.priority_5 }, { v: 1, t: app.t.priority_1 }]
                            AbstractButton {
                                id: seg
                                required property var modelData
                                required property int index
                                readonly property bool on: { const p = panel.d.priorityValue || 0; return modelData.v === 0 ? p === 0 : modelData.v === 1 ? (p >= 1 && p <= 4) : modelData.v === 5 ? p === 5 : p >= 6 }
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                enabled: panel.editable
                                hoverEnabled: true
                                onClicked: panel.set({ priority: modelData.v })
                                Accessible.role: Accessible.RadioButton
                                Accessible.checked: on
                                background: Rectangle {
                                    radius: 7
                                    color: seg.on ? panel.c.card : "transparent"
                                    border.width: seg.on && theme.dark ? 1 : 0; border.color: panel.c.line
                                }
                                contentItem: Text {
                                    text: seg.modelData.t
                                    horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                                    font.weight: seg.on ? Font.DemiBold : Font.Medium
                                    color: seg.on || seg.hovered ? panel.c.text : panel.c.muted
                                }
                            }
                        }
                    }
                    }

                    Label_ { text: app.t.list; Layout.topMargin: 6 }
                    OComboBox {
                        id: listBox
                        Layout.fillWidth: true
                        enabled: panel.editable
                        model: tasks.writableLists.map(l => ({ text: l.name, value: l.href, color: Colors.display(l.color, theme.dark) }))
                        Component.onCompleted: select(panel.d.list)
                        Connections { target: panel; function onDChanged() { listBox.select(panel.d.list) } }
                        onActivated: if (currentValue !== panel.d.list) tasks.move([panel.key], currentValue)
                    }

                    Label_ { text: app.t.tags; Layout.topMargin: 6 }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 6
                        Repeater {
                            model: panel.d.tags || []
                            AbstractButton {
                                id: tag
                                required property string modelData
                                implicitHeight: 26; implicitWidth: tagRow.implicitWidth + 16
                                hoverEnabled: true
                                enabled: panel.editable
                                onClicked: panel.set({ tags: (panel.d.tags || []).filter(x => x !== modelData) })
                                ToolTip.text: app.t.tag_remove; ToolTip.visible: hovered; ToolTip.delay: 600
                                background: Rectangle { radius: 13; color: tag.hovered ? panel.c.hover : panel.c.tint }
                                contentItem: Item { Row {
                                    id: tagRow
                                    anchors.centerIn: parent
                                    spacing: 5
                                    Text { text: "#" + tag.modelData; font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: panel.c.tintText }
                                    Icon { anchors.verticalCenter: parent.verticalCenter; name: "close"; size: 10; color: panel.c.tintText; opacity: tag.hovered ? 1 : 0.5 }
                                } }
                            }
                        }
                        TextField {
                            id: newTag
                            visible: panel.editable
                            implicitWidth: 120; implicitHeight: 26
                            placeholderText: app.t.tag_add
                            placeholderTextColor: panel.c.faint
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13
                            color: panel.c.text
                            background: Rectangle { radius: 13; color: "transparent"; border.width: 1; border.color: newTag.activeFocus ? panel.c.action : panel.c.line }
                            leftPadding: 10
                            onAccepted: {
                                const t = text.replace(/^#/, "").trim()
                                if (t) panel.set({ tags: (panel.d.tags || []).concat([t]) })
                                text = ""
                            }
                        }
                    }

                    Label_ { text: app.t.link; Layout.topMargin: 6; visible: !panel.d.mail }
                    OTextField {
                        Layout.fillWidth: true
                        visible: !panel.d.mail
                        text: panel.d.url || ""
                        readOnly: !panel.editable
                        placeholderText: "https://"
                        onEditingFinished: if (text !== (panel.d.url || "")) panel.set({ url: text })
                    }

                    Label_ { text: app.t.location; Layout.topMargin: 6; visible: panel.editable || (panel.d.location || "") !== "" }
                    OTextField {
                        Layout.fillWidth: true
                        visible: panel.editable || (panel.d.location || "") !== ""
                        iconName: "location"
                        text: panel.d.location || ""
                        readOnly: !panel.editable
                        placeholderText: app.t.location_placeholder
                        onEditingFinished: if (text !== (panel.d.location || "")) panel.set({ location: text })
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: 6
                        Label_ { text: app.t.subtasks }
                        OButton {
                            visible: panel.editable
                            kind: "accent"; height_: 28; iconName: "ornis"; iconSize: 15; text: app.t.ornis_breakdown
                            onClicked: panel.breakdown(panel.key)
                        }
                    }
                    Repeater {
                        model: panel.d.subtasks || []
                        RowLayout {
                            id: subRow
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.minimumHeight: 28
                            spacing: 10
                            HoverHandler { id: subHover }
                            AbstractButton {
                                implicitWidth: 18; implicitHeight: 18
                                enabled: panel.editable
                                onClicked: tasks.toggleDone(modelData.key)
                                background: Rectangle {
                                    radius: 9
                                    color: modelData.done ? Colors.display(modelData.listColor, theme.dark) : "transparent"
                                    border.width: modelData.done ? 0 : 1.5
                                    border.color: Colors.display(modelData.listColor, theme.dark)
                                    Icon { anchors.centerIn: parent; visible: modelData.done; name: "check"; size: 11; color: "#FFFFFF" }
                                }
                            }
                            Text {
                                Layout.fillWidth: true
                                text: modelData.title
                                elide: Text.ElideRight
                                font.family: "Schibsted Grotesk"; font.pixelSize: 14
                                font.strikeout: modelData.done
                                color: modelData.done ? panel.c.muted : panel.c.text
                                TapHandler { onTapped: win.select(modelData.key, true) }
                            }
                            Text {
                                visible: (subRow.modelData.due || "") !== ""
                                text: subRow.modelData.due || ""
                                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                                color: subRow.modelData.dueState === "overdue" ? panel.c.danger : panel.c.muted
                            }
                            AbstractButton {
                                visible: panel.editable
                                opacity: subHover.hovered || activeFocus ? 1 : 0
                                implicitWidth: 24; implicitHeight: 24
                                hoverEnabled: true
                                Accessible.name: app.t.subtask_remove
                                ToolTip.text: app.t.subtask_remove; ToolTip.visible: hovered; ToolTip.delay: 500
                                onClicked: panel.deleteRequested([subRow.modelData.key])
                                background: Rectangle { radius: 12; color: parent.hovered ? panel.c.hover : "transparent" }
                                contentItem: Item { Icon { anchors.centerIn: parent; name: "close"; size: 10; color: panel.c.muted } }
                            }
                        }
                    }
                    TextField {
                        id: newSub
                        Layout.fillWidth: true
                        visible: panel.editable
                        placeholderText: app.t.subtask_add
                        placeholderTextColor: panel.c.faint
                        font.family: "Schibsted Grotesk"; font.pixelSize: 14
                        color: panel.c.text
                        background: Rectangle { radius: 6; color: panel.c.field; border.width: 1; border.color: newSub.activeFocus ? panel.c.action : panel.c.line }
                        onAccepted: { if (text.trim()) tasks.add({ title: text.trim(), parentKey: panel.key }); text = "" }
                    }

                    Text {
                        Layout.fillWidth: true
                        Layout.topMargin: 14
                        visible: (panel.d.created || 0) > 0
                        text: app.t.created_on.replace("%1", app.short(panel.d.created || 0)) + (panel.d.done && panel.d.doneTs ? "  ·  " + app.t.done_on.replace("%1", app.short(panel.d.doneTs)) : "")
                        wrapMode: Text.WordWrap
                        font.family: "JetBrains Mono"; font.pixelSize: 11
                        color: panel.c.faint
                    }
                    OButton {
                        visible: panel.editable
                        Layout.topMargin: 4; Layout.bottomMargin: 20
                        kind: "quiet"; iconName: "trash"; danger: true; text: app.t.delete_task
                        onClicked: panel.deleteRequested([panel.key])
                    }
                }
            }
        }
    }

    // a mail (Plume), a note (Notes) or a task dropped on the details: linked to this task
    DropArea {
        anchors.fill: parent
        enabled: panel.editable && panel.key !== ""
        keys: ["application/x-orneos-link"]
        onDropped: drop => {
            if (tasks.addLinks(panel.key, drop.getDataAsString("application/x-orneos-link"))) app.toast(app.t.link_added)
            drop.acceptProposedAction()
        }
        Rectangle {
            anchors.fill: parent; anchors.margins: 8
            visible: parent.containsDrag
            radius: 12; color: "transparent"
            border.width: 2; border.color: panel.c.accent
            Rectangle { anchors.fill: parent; radius: 12; color: panel.c.tint; opacity: 0.35 }
        }
    }
}
