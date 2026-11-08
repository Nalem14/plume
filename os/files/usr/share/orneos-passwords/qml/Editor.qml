// Creating or changing an entry, in place of its details. A new one starts with a strong password already
// suggested (shown, with its strength), like macOS; the dice offer the other styles.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Rectangle {
    id: editor
    readonly property var c: theme.c
    property string entryId            // "" for a new entry
    property var draft: ({})
    property bool active: false
    property var start: ({})
    property var extra: []             // custom fields being edited [{label, type, value}]
    property string otp: ""
    property var otpNow: ({})
    property bool capturing: false
    property bool discarded: false     // the changes were given up: leaving no longer asks
    signal finished(string id)
    color: c.bg

    readonly property var current: ({
        label: label.text, url: url.text, username: username.text, password: password.text, notes: notes.text,
        folder: folderBox.currentValue || "", otp: otp, fields: extra
    })
    readonly property bool dirty: active && !discarded && JSON.stringify(current) !== JSON.stringify(start)
    readonly property var reused: vault.reusedBy(password.text, entryId)

    function load() {
        if (!active)
            return
        const d = entryId ? vault.detail(entryId) : ({})
        label.text = d.label || draft.label || ""
        url.text = d.url || draft.url || ""
        username.text = d.username || draft.username || ""
        password.text = entryId ? (d.password || "") : (draft.password || vault.generate("strong", 20, true))
        password.shown = !entryId
        notes.text = d.notes || ""
        otp = d.otp || draft.otp || ""
        extra = (d.fields || []).map(f => ({ label: f.label, type: f.type, value: f.value }))
        folderBox.select(d.folder && vault.folders.some(f => f.id === d.folder) ? d.folder
                         : (vault.category.indexOf("folder:") === 0 && !entryId ? vault.category.slice(7) : ""))
        capturing = false
        discarded = false
        if (!entryId && otp && !label.text) {
            const found = vault.codeFor(otp)
            label.text = found.issuer || ""
            username.text = username.text || found.account || ""
        }
        start = current
        Qt.callLater(() => (entryId ? password : (label.text ? username : label)).forceActiveFocus())
    }
    onActiveChanged: load()
    onEntryIdChanged: load()

    function save() {
        if (!password.text && !username.text && !label.text && !url.text)
            return
        const id = vault.save(Object.assign({ id: entryId }, current))
        discarded = true
        editor.finished(id)
    }
    function cancel() {
        discarded = true
        editor.finished(entryId)
    }
    function confirmLeave(then) {
        if (!dirty)
            return true
        leave.ask(app.t.discard_title, app.t.discard_text,
                  [{ id: "cancel", text: app.t.keep_editing }, { id: "yes", text: app.t.discard, kind: "danger" }],
                  () => { editor.discarded = true; then() })
        return false
    }
    ChoiceDialog { id: leave }

    Timer {
        interval: 1000; repeat: true; running: editor.active && editor.otp !== ""
        triggeredOnStart: true
        onTriggered: editor.otpNow = vault.codeFor(editor.otp)
    }

    Shortcut { sequence: "Ctrl+S"; enabled: editor.active; onActivated: editor.save() }
    Shortcut { sequence: "Escape"; enabled: editor.active && !editor.dirty; onActivated: editor.cancel() }

    component FormRow: RowLayout {
        property string title
        property bool last: false
        default property alias field: holder.data
        Layout.fillWidth: true
        Layout.leftMargin: 16; Layout.rightMargin: 12
        Layout.topMargin: 8; Layout.bottomMargin: 8
        spacing: 12
        Text {
            Layout.preferredWidth: 128
            Layout.alignment: Qt.AlignTop
            Layout.topMargin: 10
            text: parent.title
            font.family: "Schibsted Grotesk"; font.pixelSize: 14
            color: editor.c.muted
            elide: Text.ElideRight
        }
        ColumnLayout { id: holder; Layout.fillWidth: true; spacing: 8 }
    }
    component Line: Rectangle { Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; implicitHeight: 1; color: editor.c.hairline }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        ScrollView {
            id: scroller
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth
            clip: true

            ColumnLayout {
                x: Math.max(24, (scroller.availableWidth - width) / 2)
                width: Math.min(640, scroller.availableWidth - 48)
                spacing: 14

                Item { Layout.preferredHeight: 10 }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 16
                    SiteIcon {
                        size: 60
                        source: vault.iconFor(siteOf(url.text))
                        initial: (label.text || url.text || "?").replace(/^https?:\/\/(www\.)?/, "").charAt(0).toUpperCase()
                        tile: "#002FA7"
                        function siteOf(u) {
                            const host = String(u || "").replace(/^[a-z]+:\/\//i, "").split(/[\/?#:]/)[0].replace(/^www\./, "").toLowerCase()
                            const parts = host.split(".")
                            return parts.length > 2 ? parts.slice(-2).join(".") : host
                        }
                    }
                    OTextField {
                        id: label
                        Layout.fillWidth: true
                        plain: true
                        font.pixelSize: 23; font.weight: Font.DemiBold
                        placeholderText: editor.entryId ? app.t.label : app.t.new_entry_title
                    }
                }

                Card {
                    FormRow {
                        title: app.t.website
                        OTextField { id: url; Layout.fillWidth: true; placeholderText: "exemple.fr"; inputMethodHints: Qt.ImhUrlCharactersOnly }
                    }
                    Line {}
                    FormRow {
                        title: app.t.username
                        OTextField { id: username; Layout.fillWidth: true; placeholderText: app.t.username_ph; inputMethodHints: Qt.ImhNoAutoUppercase }
                    }
                    Line {}
                    FormRow {
                        title: app.t.password
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 4
                            OTextField {
                                id: password
                                property bool shown: false
                                Layout.fillWidth: true
                                echoMode: shown ? TextInput.Normal : TextInput.Password
                                font.family: shown && text ? "JetBrains Mono" : "Schibsted Grotesk"
                                inputMethodHints: Qt.ImhSensitiveData | Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase
                            }
                            OButton {
                                kind: "quiet"; implicitWidth: 34; iconName: password.shown ? "eyeOff" : "eye"
                                tip: password.shown ? app.t.hide : app.t.show
                                onClicked: password.shown = !password.shown
                            }
                            OButton {
                                id: dice
                                kind: "quiet"; implicitWidth: 34; iconName: "dice"
                                tip: app.t.suggest
                                onClicked: suggestMenu.open()
                                OMenu {
                                    id: suggestMenu
                                    y: dice.height + 6
                                    x: dice.width - width
                                    implicitWidth: 300
                                    heading: app.t.suggest
                                    OMenuItem { text: app.t.style_strong; iconName: "shieldCheck"; onTriggered: { password.text = vault.generate("strong", 20, true); password.shown = true } }
                                    OMenuItem { text: app.t.style_random; iconName: "dice"; onTriggered: { password.text = vault.generate("random", 24, true); password.shown = true } }
                                    OMenuItem { text: app.t.style_nosymbols; iconName: "key"; onTriggered: { password.text = vault.generate("random", 20, false); password.shown = true } }
                                    OMenuItem { text: app.t.style_words; iconName: "note"; onTriggered: { password.text = vault.generate("words", 5, false); password.shown = true } }
                                }
                            }
                        }
                        StrengthMeter {
                            score: vault.strength(password.text, label.text, username.text)
                            empty: password.text === ""
                        }
                        Text {
                            visible: editor.reused.length > 0
                            Layout.fillWidth: true
                            text: app.t.reused_warning.replace("%1", editor.reused.join(", "))
                            wrapMode: Text.WordWrap
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13
                            color: editor.c.saffronInk
                        }
                    }
                    Line {}
                    FormRow {
                        title: app.t.code
                        // a code set: shown live, to check it is the one the site asks for
                        RowLayout {
                            visible: editor.otp !== ""
                            spacing: 10
                            Text {
                                text: (editor.otpNow.code || "").replace(/^(\d{3})(\d{3,})$/, "$1 $2")
                                font.family: "JetBrains Mono"; font.pixelSize: 20; font.weight: Font.Medium
                                color: editor.c.text
                            }
                            CodeRing { remaining: editor.otpNow.remaining || 0; period: editor.otpNow.period || 30 }
                            Item { Layout.fillWidth: true }
                            OButton { kind: "quiet"; text: app.t.remove; onClicked: editor.otp = "" }
                        }
                        Text {
                            visible: editor.otp !== ""
                            Layout.fillWidth: true
                            text: app.t.otp_check
                            wrapMode: Text.WordWrap
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13
                            color: editor.c.muted
                        }
                        OButton {
                            visible: editor.otp === "" && !editor.capturing
                            iconName: "qr"; text: app.t.otp_setup
                            onClicked: editor.capturing = true
                        }
                        CodeCapture {
                            visible: editor.otp === "" && editor.capturing
                            Layout.fillWidth: true
                            onCaptured: uri => { editor.otp = uri; editor.capturing = false }
                        }
                    }
                    Line {}
                    FormRow {
                        title: app.t.folder
                        OComboBox {
                            id: folderBox
                            Layout.fillWidth: true
                            model: [{ text: app.t.folder_none, value: "" }].concat(vault.folders.filter(f => !f.pending).map(f => ({ text: f.label, value: f.id })))
                        }
                    }
                }

                Card {
                    FormRow {
                        title: app.t.notes
                        OTextArea {
                            id: notes
                            Layout.fillWidth: true
                            Layout.minimumHeight: 90
                            placeholderText: app.t.notes_ph
                        }
                    }
                    Repeater {
                        model: editor.extra
                        ColumnLayout {
                            required property var modelData
                            required property int index
                            Layout.fillWidth: true
                            spacing: 0
                            Line {}
                            RowLayout {
                                Layout.fillWidth: true
                                Layout.leftMargin: 16; Layout.rightMargin: 12; Layout.topMargin: 8; Layout.bottomMargin: 8
                                spacing: 8
                                OTextField {
                                    Layout.preferredWidth: 128
                                    text: modelData.label
                                    placeholderText: app.t.field_name
                                    onTextEdited: { const x = editor.extra.slice(); x[index] = Object.assign({}, x[index], { label: text }); editor.extra = x }
                                }
                                OTextField {
                                    Layout.fillWidth: true
                                    text: modelData.value
                                    echoMode: modelData.type === "secret" && !activeFocus ? TextInput.Password : TextInput.Normal
                                    placeholderText: app.t.field_value
                                    onTextEdited: { const x = editor.extra.slice(); x[index] = Object.assign({}, x[index], { value: text }); editor.extra = x }
                                }
                                OButton {
                                    kind: "quiet"; implicitWidth: 34
                                    iconName: modelData.type === "secret" ? "lock" : "unlock"
                                    tip: modelData.type === "secret" ? app.t.field_secret : app.t.field_plain
                                    onClicked: { const x = editor.extra.slice(); x[index] = Object.assign({}, x[index], { type: modelData.type === "secret" ? "text" : "secret" }); editor.extra = x }
                                }
                                OButton {
                                    kind: "quiet"; implicitWidth: 34; iconName: "close"; tip: app.t.remove
                                    onClicked: { const x = editor.extra.slice(); x.splice(index, 1); editor.extra = x }
                                }
                            }
                        }
                    }
                    Line {}
                    OButton {
                        Layout.margins: 8
                        kind: "quiet"; iconName: "plus"
                        text: app.t.field_add
                        onClicked: editor.extra = editor.extra.concat([{ label: "", type: "text", value: "" }])
                    }
                }
                Item { Layout.preferredHeight: 20 }
            }
        }

        // the footer stays in view
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 60
            color: editor.c.chrome
            Rectangle { width: parent.width; height: 1; color: editor.c.line }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 18; anchors.rightMargin: 16
                spacing: 8
                OButton {
                    visible: editor.entryId !== ""
                    kind: "quiet"; iconName: "trash"; danger: true
                    text: app.t.delete_entry
                    onClicked: { editor.discarded = true; vault.trash(editor.entryId); editor.finished("") }
                }
                Text {
                    Layout.fillWidth: true
                    visible: !vault.online
                    text: app.t.offline_editing
                    elide: Text.ElideRight
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                    color: editor.c.saffronInk
                }
                Item { Layout.fillWidth: vault.online }
                OButton { text: app.t.cancel; onClicked: editor.dirty ? editor.confirmLeave(() => editor.finished(editor.entryId)) : editor.cancel() }
                OButton {
                    kind: "primary"; iconName: "check"
                    text: editor.entryId ? app.t.save : app.t.add
                    enabled: password.text !== "" || username.text !== "" || label.text !== "" || url.text !== ""
                    onClicked: editor.save()
                }
            }
        }
    }
}
