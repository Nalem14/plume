// Manage one local Code cron task (or create one): plain schedule + advanced crontab, prompt/script, history.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: sheet
    property string taskId: ""
    property bool advanced: false
    property string plainKind: "daily"
    property int hour: 8
    property int minute: 0
    property int weekday: 1
    property int everyMin: 15
    property string scheduleError: ""
    readonly property bool isNew: taskId === ""
    title: isNew ? app.t.cron_new : app.t.cron_manage
    tint: theme.c.famCommunicate

    function openFor(id) {
        taskId = id || ""
        advanced = false
        scheduleError = ""
        const t = taskId ? cron.get(taskId) : {}
        titleField.text = t.title || ""
        descField.text = t.description || ""
        idField.text = t.id || ""
        idField.readOnly = !!taskId
        kindBox.select(t.kind === "script" ? "script" : "chat")
        promptField.text = t.prompt || ""
        commandField.text = t.command || ""
        scheduleField.text = t.schedule || "0 8 * * *"
        pausedSwitch.checked = !!t.paused
        plainKind = "daily"; hour = 8; minute = 0; weekday = 1; everyMin = 15
        if (t.schedule) {
            const p = String(t.schedule).trim().split(/\s+/)
            if (p.length === 5) {
                const [mi, ho, dom, mon, dow] = p
                minute = parseInt(mi) || 0
                hour = parseInt(ho) || 0
                if (mi.indexOf("*/") === 0 && ho === "*" && dom === "*" && mon === "*" && dow === "*") {
                    plainKind = "every"; everyMin = parseInt(mi.slice(2)) || 15
                } else if (ho === "*" && dom === "*" && mon === "*" && dow === "*" && mi.indexOf("/") < 0) {
                    plainKind = "hourly"   // before daily: daily also has * * * on day/month/dow
                } else if (dom === "*" && mon === "*" && dow === "*") {
                    plainKind = "daily"
                } else if (dom === "*" && mon === "*" && dow === "1-5") {
                    plainKind = "weekdays"
                } else if (dom === "*" && mon === "*" && /^[0-6]$/.test(dow)) {
                    plainKind = "weekly"; weekday = parseInt(dow)
                } else {
                    advanced = true
                }
            } else {
                advanced = true
            }
        }
        if (!advanced) syncFromPlain()
        open()
        Qt.callLater(() => { if (plainBox) plainBox.select(sheet.plainKind); if (dowBox) dowBox.select(String(sheet.weekday)) })
    }

    function syncFromPlain() {
        if (advanced) return
        const expr = cron.plainSchedule(plainKind, hour, minute, weekday, everyMin)
        if (expr) scheduleField.text = expr
        scheduleError = ""
    }

    function applyScheduleField() {
        const v = cron.validateSchedule(scheduleField.text)
        if (String(v).startsWith("!")) { scheduleError = v.slice(1); return false }
        scheduleField.text = v
        scheduleError = ""
        return true
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 12

        OTextField { id: titleField; Layout.fillWidth: true; placeholderText: app.t.cron_title_ph }
        OTextField { id: descField; Layout.fillWidth: true; placeholderText: app.t.cron_desc_ph }
        RowLayout {
            Layout.fillWidth: true
            OTextField {
                id: idField; Layout.fillWidth: true
                placeholderText: app.t.cron_id_ph
                readOnly: !sheet.isNew
            }
            OButton {
                kind: "quiet"; text: app.t.copy
                enabled: idField.text !== ""
                onClicked: app.copy(idField.text)
            }
        }

        Text {
            text: app.t.cron_kind
            font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold
            color: theme.c.muted
        }
        OComboBox {
            id: kindBox
            Layout.fillWidth: true
            model: [
                { text: app.t.cron_kind_chat, value: "chat" },
                { text: app.t.cron_kind_script, value: "script" }
            ]
        }

        OTextArea {
            id: promptField
            visible: kindBox.currentIndex === 0
            Layout.fillWidth: true
            Layout.preferredHeight: 110
            placeholderText: app.t.cron_prompt_ph
        }
        OTextField {
            id: commandField
            visible: kindBox.currentIndex === 1
            Layout.fillWidth: true
            placeholderText: app.t.cron_command_ph
        }

        RowLayout {
            Layout.fillWidth: true
            Text {
                text: app.t.cron_schedule
                font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold
                color: theme.c.muted
            }
            Item { Layout.fillWidth: true }
            OButton {
                kind: "quiet"; height_: 26
                text: sheet.advanced ? app.t.cron_schedule_simple : app.t.cron_schedule_advanced
                onClicked: {
                    if (!sheet.advanced) applyScheduleField()
                    sheet.advanced = !sheet.advanced
                    if (!sheet.advanced) syncFromPlain()
                }
            }
        }

        ColumnLayout {
            visible: !sheet.advanced
            Layout.fillWidth: true
            spacing: 8
            OComboBox {
                id: plainBox
                Layout.fillWidth: true
                model: [
                    { text: app.t.cron_plain_daily, value: "daily" },
                    { text: app.t.cron_plain_weekdays, value: "weekdays" },
                    { text: app.t.cron_plain_weekly, value: "weekly" },
                    { text: app.t.cron_plain_hourly, value: "hourly" },
                    { text: app.t.cron_plain_every, value: "every" }
                ]
                onActivated: { sheet.plainKind = model[currentIndex].value; sheet.syncFromPlain() }
                Component.onCompleted: select(sheet.plainKind)
            }
            RowLayout {
                visible: sheet.plainKind !== "every"
                Layout.fillWidth: true
                Text { text: app.t.cron_at; color: theme.c.muted; font.pixelSize: 13; font.family: "Schibsted Grotesk" }
                OTextField {
                    // hourly = every hour at :MM — only the minute matters
                    visible: sheet.plainKind !== "hourly"
                    Layout.preferredWidth: 48; text: String(sheet.hour)
                    onEditingFinished: { sheet.hour = Math.max(0, Math.min(23, parseInt(text) || 0)); sheet.syncFromPlain() }
                }
                Text {
                    visible: sheet.plainKind !== "hourly"
                    text: "h"; color: theme.c.muted; font.pixelSize: 13
                }
                OTextField {
                    Layout.preferredWidth: 48; text: String(sheet.minute).padStart(2, "0")
                    onEditingFinished: { sheet.minute = Math.max(0, Math.min(59, parseInt(text) || 0)); sheet.syncFromPlain() }
                }
                Text {
                    visible: sheet.plainKind === "hourly"
                    text: "min"; color: theme.c.muted; font.pixelSize: 13; font.family: "Schibsted Grotesk"
                }
            }
            RowLayout {
                visible: sheet.plainKind === "every"
                Layout.fillWidth: true
                Text { text: app.t.cron_every_min; color: theme.c.muted; font.pixelSize: 13; font.family: "Schibsted Grotesk" }
                OTextField {
                    Layout.preferredWidth: 56; text: String(sheet.everyMin)
                    onEditingFinished: {
                        let n = Math.max(15, parseInt(text) || 15)
                        if (60 % n !== 0) n = 15
                        sheet.everyMin = n; text = String(n); sheet.syncFromPlain()
                    }
                }
            }
            RowLayout {
                visible: sheet.plainKind === "weekly"
                Layout.fillWidth: true
                Text { text: app.t.cron_weekday; color: theme.c.muted; font.pixelSize: 13; font.family: "Schibsted Grotesk" }
                OComboBox {
                    id: dowBox
                    Layout.fillWidth: true
                    model: [0,1,2,3,4,5,6].map(d => ({ text: app.t["cron_dow_" + d], value: String(d) }))
                    onActivated: { sheet.weekday = parseInt(model[currentIndex].value); sheet.syncFromPlain() }
                }
            }
            Text {
                Layout.fillWidth: true
                text: scheduleField.text
                font.family: "JetBrains Mono"; font.pixelSize: 12
                color: theme.c.faint
            }
        }

        ColumnLayout {
            visible: sheet.advanced
            Layout.fillWidth: true
            spacing: 6
            OTextField {
                id: scheduleField
                Layout.fillWidth: true
                placeholderText: "0 8 * * 1-5"
                font.family: "JetBrains Mono"
                onEditingFinished: sheet.applyScheduleField()
            }
            Text {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                text: sheet.scheduleError || (cron.labelOf(scheduleField.text) + (
                    cron.nextTimes(scheduleField.text).length
                        ? " · " + cron.nextTimes(scheduleField.text).join(" · ") : ""))
                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                color: sheet.scheduleError ? theme.c.danger : theme.c.muted
            }
            Text {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                text: app.t.cron_crontab_help
                font.family: "Schibsted Grotesk"; font.pixelSize: 11
                color: theme.c.faint
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Text { text: app.t.cron_paused_label; font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: theme.c.text; Layout.fillWidth: true }
            OSwitch { id: pausedSwitch }
        }

        ColumnLayout {
            visible: !sheet.isNew
            Layout.fillWidth: true
            spacing: 6
            Text {
                text: app.t.cron_history
                font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold
                color: theme.c.muted
            }
            Repeater {
                model: (cron.get(sheet.taskId).runs || []).slice(0, 8)
                delegate: RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    Text {
                        Layout.fillWidth: true
                        text: (modelData.when || "") + " · " + (modelData.status || "") + (modelData.summary ? " — " + modelData.summary : "")
                        elide: Text.ElideRight
                        font.family: "Schibsted Grotesk"; font.pixelSize: 12
                        color: theme.c.muted
                    }
                    OButton {
                        visible: !!modelData.session
                        kind: "quiet"; text: app.t.open; height_: 24
                        onClicked: { cron.openRun(cron.get(sheet.taskId).folder, modelData.session); sheet.close() }
                    }
                }
            }
        }
    }

    footer: [
        OButton {
            visible: !sheet.isNew
            kind: "quiet"; text: app.t.cron_delete
            onClicked: { cron.remove(sheet.taskId); sheet.close() }
        },
        Item { Layout.fillWidth: true },
        OButton { kind: "secondary"; text: app.t.cancel; onClicked: sheet.close() },
        OButton {
            kind: "primary"; text: app.t.save
            onClicked: {
                if (!sheet.applyScheduleField()) return
                const existing = sheet.taskId ? cron.get(sheet.taskId) : {}
                const err = cron.save({
                    id: idField.text.trim(),
                    title: titleField.text.trim(),
                    description: descField.text.trim(),
                    kind: (kindBox.model[kindBox.currentIndex] && kindBox.model[kindBox.currentIndex].value) || "chat",
                    prompt: promptField.text,
                    command: commandField.text,
                    schedule: scheduleField.text.trim(),
                    paused: pausedSwitch.checked,
                    folder: existing.folder || code.folder
                })
                if (err) { sheet.scheduleError = err; return }
                sheet.close()
            }
        }
    ]
}
