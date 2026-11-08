// The selected entry: what is wrong with it first (and how to fix it), then its fields, each copied with a
// click; the verification code turns with its ring. The editor takes the same place.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Rectangle {
    id: detail
    readonly property var c: theme.c
    property string entryId
    property string mode: "view"
    property var draft: ({})
    property var d: ({})
    property var otp: ({})
    property var history: []
    property bool historyOpen: false
    property bool historyLoading: false
    signal editRequested()
    signal done(string id)
    signal shareRequested(string id)
    signal codeRequested(string id, string uri)
    signal ornisTwofa(string site, string label)
    signal importRequested()
    color: c.bg

    function reload() {
        d = entryId ? vault.detail(entryId) : ({})
        otp = d.otp ? vault.code(entryId) : ({})
    }
    // a warning with its own filled button (« Changer sur le site », « Configurer un code ») comes first
    readonly property bool fixFirst: (d.issues || []).some(i => i === "twofa" ? d.editable === true : !!d.link && d.editable === true)
    function confirmLeave(then) { return editor.confirmLeave(then) }

    onEntryIdChanged: { historyOpen = false; history = []; reload() }
    Connections {
        target: vault
        function onChanged() { detail.reload() }
        function onHistoryReady(id, rows) {
            if (id === detail.entryId) { detail.history = rows; detail.historyLoading = false }
        }
        function onDone(what, ok, message) { if (what === "history") detail.historyLoading = false }
    }
    Timer {
        interval: 1000; repeat: true
        running: detail.visible && detail.mode === "view" && !!detail.d.otp && !lock.locked
        onTriggered: detail.otp = vault.code(detail.entryId)
    }

    // ---- nothing selected --------------------------------------------------------------------------------
    ColumnLayout {
        anchors.centerIn: parent
        visible: detail.mode === "view" && !detail.d.id
        width: Math.min(360, parent.width - 48)
        spacing: 10
        Icon { Layout.alignment: Qt.AlignHCenter; name: "key"; size: 36; color: detail.c.faint }
        Text {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            text: vault.counts.all ? app.t.pick_entry : app.t.first_entry
            wrapMode: Text.WordWrap
            font.family: "Schibsted Grotesk"; font.pixelSize: 15
            color: detail.c.muted
        }
        OButton {
            visible: !vault.counts.all
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: 6
            text: app.t.import_title; iconName: "import"
            onClicked: detail.importRequested()
        }
    }

    Editor {
        id: editor
        anchors.fill: parent
        visible: detail.mode !== "view"
        active: detail.mode !== "view"
        entryId: detail.mode === "edit" ? detail.entryId : ""
        draft: detail.draft
        onFinished: id => detail.done(id)
    }

    // ---- the entry ---------------------------------------------------------------------------------------
    ScrollView {
        id: scroller
        anchors.fill: parent
        visible: detail.mode === "view" && !!detail.d.id
        contentWidth: availableWidth
        clip: true

        ColumnLayout {
            x: Math.max(24, (scroller.availableWidth - width) / 2)
            width: Math.min(640, scroller.availableWidth - 48)
            spacing: 14

            Item { Layout.preferredHeight: 10 }

            // header: the site's tile, where it is kept, the name, when it changed; Modifier is the one filled
            // action unless a warning below has its own fix
            Hero {
                Layout.fillWidth: true
                tint: detail.c.famTools
                titleSize: 26
                kicker: detail.d.sharedBy ? app.t.shared_by.replace("%1", detail.d.sharedBy)
                      : detail.d.folderName || detail.d.site || app.t.password
                title: detail.d.label || ""
                meta: detail.d.edited ? app.t.changed_ago.replace("%1", app.ago(detail.d.edited)) : ""
                leading: SiteIcon {
                    size: 52
                    source: detail.d.icon || ""
                    initial: detail.d.initial || ""
                    tile: detail.d.tile || detail.c.famCommunicate
                }
                OButton {
                    visible: detail.d.editable === true
                    kind: detail.fixFirst ? "secondary" : "primary"
                    iconName: "edit"
                    text: detail.width >= 600 ? app.t.edit : ""
                    tip: detail.width >= 600 ? "" : app.t.edit
                    onClicked: detail.editRequested()
                }
                OButton {
                    visible: !detail.d.trashed && !detail.d.sharedIn
                    kind: "quiet"; implicitWidth: 34
                    iconName: "share"; tip: app.t.share
                    onClicked: detail.shareRequested(detail.entryId)
                }
                OButton {
                    id: moreButton
                    visible: !detail.d.trashed
                    kind: "quiet"; implicitWidth: 34
                    iconName: "more"; tip: app.t.more
                    onClicked: moreMenu.open()
                    OMenu {
                        id: moreMenu
                        y: moreButton.height + 6
                        x: moreButton.width - width
                        OMenuItem { text: detail.d.favorite ? app.t.favorite_remove : app.t.favorite_add; iconName: "star"; onTriggered: vault.toggleFavorite(detail.entryId) }
                        OMenuItem { visible: detail.d.editable === true; text: app.t.move_to; iconName: "folder"; onTriggered: moveDialog.open() }
                        OMenuItem { visible: !!detail.d.link; text: app.t.change_on_site; iconName: "refresh"; onTriggered: vault.changePassword(detail.entryId) }
                        OMenuItem { text: app.t.open_cloud; iconName: "cloud"; onTriggered: app.openCloud("/apps/passwords/") }
                        OMenuItem { visible: !!((detail.d.issues && detail.d.issues.length) || detail.d.ignored); text: detail.d.ignored ? app.t.warnings_show : app.t.warnings_hide; iconName: "shield"; onTriggered: vault.ignore(detail.entryId, !detail.d.ignored) }
                        OMenuItem { text: app.t.delete_entry; iconName: "trash"; onTriggered: vault.trash(detail.entryId) }
                    }
                }
            }

            // in the trash
            Banner {
                visible: !!detail.d.trashed
                tone: "muted"; iconName: "trash"
                title: app.t.in_trash
                text: app.t.in_trash_lead
                OButton { text: app.t.restore; iconName: "restore"; onClicked: vault.restore(detail.entryId) }
                OButton {
                    kind: "quiet"; text: app.t.delete_forever
                    onClicked: purgeQuestion.ask(app.t.delete_forever_title, app.t.delete_forever_text,
                                                 [{ id: "cancel", text: app.t.cancel }, { id: "yes", text: app.t.delete_forever, kind: "danger" }],
                                                 () => vault.purge(detail.entryId))
                }
            }

            // what is wrong, most serious first
            Repeater {
                model: (detail.d.issues || []).filter(i => i !== "twofa")
                Banner {
                    required property string modelData
                    required property int index
                    tone: modelData === "breached" ? "danger" : "saffron"
                    iconName: "warning"
                    title: app.t["issue_" + modelData + "_title"]
                    text: modelData === "reused" && detail.d.reusedWith && detail.d.reusedWith.length
                          ? app.t.issue_reused_with.replace("%1", detail.d.reusedWith.join(", "))
                          : app.t["issue_" + modelData + "_lead"]
                    OButton {
                        visible: index === 0 && !!detail.d.link && detail.d.editable === true
                        kind: "primary"; iconName: "refresh"
                        text: app.t.change_on_site
                        onClicked: { vault.changePassword(detail.entryId); detail.editRequested() }
                    }
                }
            }
            Banner {
                visible: (detail.d.issues || []).indexOf("twofa") >= 0 && detail.d.editable === true
                tone: "tint"; iconName: "shieldCheck"
                title: app.t.issue_twofa_title
                text: app.t.issue_twofa_lead
                OButton { kind: "primary"; iconName: "qr"; text: app.t.otp_setup; onClicked: detail.codeRequested(detail.entryId, "") }
                OButton { kind: "accent"; iconName: "ornis"; text: app.t.ornis_howto; onClicked: detail.ornisTwofa(detail.d.site, detail.d.label) }
            }

            // the fields
            Card {
                FieldRow {
                    visible: !!detail.d.username
                    label: app.t.username
                    value: detail.d.username || ""
                    copyAs: "username"
                }
                FieldRow {
                    id: passwordRow
                    label: app.t.password
                    value: detail.d.password || ""
                    copyAs: "password"
                    secret: true
                    mono: true
                    last: !detail.d.otp && !detail.d.link
                    StrengthMeter {
                        visible: passwordRow.hovered || passwordRow.revealed
                        score: detail.d.strength || 0
                        empty: !detail.d.password
                    }
                }
                AbstractButton {
                    id: codeRow
                    visible: !!detail.d.otp
                    Layout.fillWidth: true
                    implicitHeight: 64
                    hoverEnabled: true
                    onClicked: app.copy(detail.otp.code || "", "code")
                    Accessible.name: app.t.code
                    background: Rectangle {
                        color: codeRow.hovered ? detail.c.hover : "transparent"
                        Rectangle { visible: !!detail.d.link; anchors.bottom: parent.bottom; x: 16; width: parent.width - 32; height: 1; color: detail.c.hairline }
                    }
                    contentItem: RowLayout {
                        spacing: 12
                        ColumnLayout {
                            Layout.leftMargin: 16
                            Layout.fillWidth: true
                            spacing: 3
                            Text { text: app.t.code; font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: detail.c.muted }
                            Text {
                                text: (detail.otp.code || "").replace(/^(\d{3})(\d{3,})$/, "$1 $2")
                                font.family: "JetBrains Mono"; font.pixelSize: 22; font.weight: Font.Medium; font.letterSpacing: 1
                                color: (detail.otp.remaining || 30) <= 5 ? detail.c.saffronInk : detail.c.text
                            }
                        }
                        Item { Layout.fillWidth: true }
                        Text {
                            text: (detail.otp.remaining || 0) + " s"
                            font.family: "JetBrains Mono"; font.pixelSize: 12
                            color: detail.c.muted
                        }
                        CodeRing {
                            Layout.rightMargin: 4
                            remaining: detail.otp.remaining || 0
                            period: detail.otp.period || 30
                        }
                        OButton {
                            Layout.rightMargin: 10
                            kind: "quiet"; implicitWidth: 32; height_: 32; iconSize: 17
                            iconName: "copy"; tip: app.t.copy
                            onClicked: app.copy(detail.otp.code || "", "code")
                        }
                    }
                }
                FieldRow {
                    visible: !!detail.d.link
                    label: app.t.website
                    value: detail.d.url || ""
                    link: true
                    last: true
                    onOpened: app.openUrl(detail.d.link)
                }
            }

            // a code to set up (sites that do not appear in the review's list too)
            OButton {
                visible: !detail.d.otp && detail.d.editable === true && (detail.d.issues || []).indexOf("twofa") < 0
                kind: "quiet"; iconName: "qr"
                text: app.t.otp_setup
                onClicked: detail.codeRequested(detail.entryId, "")
            }

            Card {
                visible: (detail.d.fields || []).length > 0 || !!detail.d.notes
                Repeater {
                    model: detail.d.fields || []
                    FieldRow {
                        required property var modelData
                        required property int index
                        label: modelData.label || app.t.field
                        value: modelData.value
                        secret: modelData.type === "secret"
                        mono: modelData.type === "secret"
                        copyAs: modelData.type === "secret" ? "field" : "username"
                        link: modelData.type === "url"
                        onOpened: app.openUrl(modelData.value)
                        last: index === (detail.d.fields || []).length - 1 && !detail.d.notes
                    }
                }
                FieldRow {
                    visible: !!detail.d.notes
                    label: app.t.notes
                    value: detail.d.notes || ""
                    multiline: true
                    last: true
                }
            }

            // sharing
            Card {
                visible: (detail.d.shares || []).length > 0
                Text {
                    Layout.leftMargin: 16; Layout.topMargin: 12
                    text: app.t.shared_with
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                    color: detail.c.muted
                }
                Repeater {
                    model: detail.d.shares || []
                    RowLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.leftMargin: 16; Layout.rightMargin: 10
                        Layout.topMargin: 4; Layout.bottomMargin: 6
                        spacing: 10
                        Icon { name: "user"; size: 18; color: detail.c.muted }
                        Text {
                            Layout.fillWidth: true
                            text: modelData.name
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 15
                            color: detail.c.text
                        }
                        Text {
                            text: modelData.editable ? app.t.share_can_edit : app.t.share_read_only
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13
                            color: detail.c.muted
                        }
                    }
                }
                Item { Layout.preferredHeight: 6 }
            }

            // older passwords (the cloud keeps every revision)
            ColumnLayout {
                Layout.fillWidth: true
                visible: !detail.d.trashed && detail.entryId.indexOf("local-") !== 0
                spacing: 8
                OButton {
                    kind: "quiet"; iconName: "history"
                    text: detail.historyOpen ? app.t.history_hide : app.t.history
                    onClicked: {
                        detail.historyOpen = !detail.historyOpen
                        if (detail.historyOpen) { detail.historyLoading = true; vault.loadHistory(detail.entryId) }
                    }
                }
                OrnisThinking { visible: detail.historyOpen && detail.historyLoading; text: app.t.history_loading }
                Text {
                    visible: detail.historyOpen && !detail.historyLoading && detail.history.length <= 1
                    text: app.t.history_none
                    font.family: "Schibsted Grotesk"; font.pixelSize: 14
                    color: detail.c.muted
                }
                Card {
                    visible: detail.historyOpen && !detail.historyLoading && detail.history.length > 1
                    Repeater {
                        model: detail.history.slice(1)
                        FieldRow {
                            required property var modelData
                            required property int index
                            label: app.ago(modelData.edited)
                            value: modelData.password
                            secret: true; mono: true
                            copyAs: "password"
                            last: index === detail.history.length - 2
                            OButton {
                                visible: detail.d.editable === true
                                kind: "quiet"; height_: 30
                                text: app.t.history_use
                                onClicked: vault.usePassword(detail.entryId, modelData.password)
                            }
                        }
                    }
                }
            }

            Text {
                Layout.fillWidth: true
                Layout.topMargin: 4
                text: [detail.d.created ? app.t.created_on.replace("%1", app.ago(detail.d.created)) : "",
                       detail.d.pending ? app.t.pending_one : ""].filter(x => x).join("  ·  ")
                font.family: "JetBrains Mono"; font.pixelSize: 12
                color: detail.c.faint
            }
            Item { Layout.preferredHeight: 24 }
        }
    }

    ChoiceDialog { id: purgeQuestion }

    ODialog {
        id: moveDialog
        title: app.t.move_to
        width: Math.min(420, parent ? parent.width - 48 : 420)
        OComboBox {
            id: folderBox
            Layout.fillWidth: true
            model: [{ text: app.t.folder_none, value: "" }].concat(vault.folders.filter(f => !f.pending).map(f => ({ text: f.label, value: f.id })))
        }
        onAboutToShow: folderBox.select(detail.d.folder && vault.folders.some(f => f.id === detail.d.folder) ? detail.d.folder : "")
        footer: [
            Item { Layout.fillWidth: true },
            OButton { text: app.t.cancel; onClicked: moveDialog.close() },
            OButton { kind: "primary"; text: app.t.move; onClicked: { vault.moveTo(detail.entryId, folderBox.currentValue); moveDialog.close() } }
        ]
    }
}
