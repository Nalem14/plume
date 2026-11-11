// Writing a message, in its own window: identity, recipients, subject, formatted text, the signature of
// the address it leaves from, the quoted message, attachments. Ctrl+Enter sends (a few seconds to cancel);
// closing keeps a draft in the Drafts folder. A heavy file can go as an Orneos link instead.
import QtCore as Std               // StandardPaths only: its Settings would hide ours
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import QtQuick.Window
import QtWebEngine
import "../components"

Window {
    id: composer
    readonly property var c: theme.c
    property var base: ({})
    property var attachments: []          // [{path, name, size}]
    property bool showCc: false
    property bool showBcc: false
    property bool done: false
    property string error
    property string heavy                 // a big file waiting for the "send a link" answer
    property string signature             // HTML, from the cloud's Mail app; follows the sender
    property bool signatureOff
    property string quoteText
    property string quoteHtml
    property bool quoteOpen
    property bool loading
    property alias writer: writer
    readonly property int heavyBytes: 20 * 1024 * 1024

    width: 780; height: 660
    minimumWidth: 560; minimumHeight: 420
    color: c.card
    title: subject.text || plume.t.new_message
    flags: Qt.Window

    function identity(email) {
        return (mail.account.identities || []).find(i => i.email.toLowerCase() === String(email).toLowerCase()) || {}
    }
    // the signature alone, as it is sent (on white paper in the dark: it was made for light mail)
    function signaturePage() {
        return '<!doctype html><meta charset="utf-8"><style>html{color-scheme:light}body{margin:0;padding:'
               + (theme.dark ? "10px 12px;background:#FFFFFF;border-radius:8px" : "0 8px;background:transparent")
               + ';font:15px/1.5 Arial,sans-serif;color:#0F2440;overflow:hidden}img{max-width:100%;height:auto}</style>'
               + '<div class="orneos-signature">' + signature + '</div>'
    }
    function htmlOf(text) {
        return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\n/g, "<br>")
    }

    // something written in it, not sent: kept as a draft before the composer takes another message
    function useTemplate(t) {
        if (!subject.text.trim() && t.subject)
            subject.text = t.subject
        editor.area.insert(editor.area.cursorPosition, t.html || htmlOf(t.text || ""))
        editor.area.forceActiveFocus()
    }
    function hasContent() {
        return to.addresses.length + cc.addresses.length + bcc.addresses.length + attachments.length > 0
            || subject.text.trim() !== "" || !editor.isEmpty()
    }
    function openWith(f) {
        if (visible && !done && !loading && hasContent())
            mail.saveDraft(fields())
        keeper.last = ""
        base = f || {}
        done = false
        error = ""
        heavy = ""
        writer.close()
        loading = true
        sender.select(f.from || "")
        loading = false
        signatureOff = !!f.draftId && !f.signature
        signature = f.signature !== undefined ? f.signature : (identity(sender.currentValue).signature || "")
        quoteText = f.quoteText || ""
        quoteHtml = f.quoteHtml || ""
        quoteOpen = String(f.subject || "").match(/^(Tr|Fwd|WG)\s*:/i) !== null
        to.addresses = f.to || []
        cc.addresses = f.cc || []
        bcc.addresses = f.bcc || []
        showCc = cc.addresses.length > 0
        showBcc = bcc.addresses.length > 0
        subject.text = f.subject || ""
        editor.load(f.html || (f.body ? htmlOf(f.body) : ""))
        attachments = (f.attachments || []).map(p => ({ path: p, name: String(p).split("/").pop(), size: mail.attachmentSize(p) }))
        show()
        raise()
        requestActivate()
        if (to.addresses.length === 0)
            to.forceActiveFocus()
        else {
            editor.area.forceActiveFocus()
            editor.area.cursorPosition = 0
        }
    }

    function fields() {
        to.commit(); cc.commit(); bcc.commit()
        const written = editor.exported()
        return Object.assign({}, base, {
            from: sender.currentValue, to: to.addresses, cc: cc.addresses, bcc: bcc.addresses,
            subject: subject.text, body: written.text, html: written.html,
            signature: signatureOff ? "" : signature, quoteText: quoteText, quoteHtml: quoteHtml,
            attachments: attachments.map(a => a.path)
        })
    }

    // the text speaks of an attachment and none is there (what was written only, not the quote)
    function forgotAttachment(f) {
        if (!plume.prefs.mail_attach_check || f.attachments.length > 0)
            return false
        const said = String(f.body || "") + " " + subject.text
        return /\b(pi[eè]ces?[ -]jointes?|ci-joint(e|es|s)?|en pj|joint[es]? (à|a) ce (mail|message|courriel)|attached|attachments?|enclosed|anbei|im anhang|angeh[äa]ngt)\b/i.test(said)
    }
    // « Envoyer plus tard »: at a time (seconds); the outbox keeps it until then
    function sendAt(at) {
        composer.base = Object.assign({}, composer.base, { sendAt: at })
        send()
    }
    function send(force) {
        const f = fields()
        if (f.to.length + f.cc.length + f.bcc.length === 0) {
            error = plume.t.no_recipient
            to.forceActiveFocus()
            return
        }
        if (force !== true && forgotAttachment(f)) {
            ask.ask(plume.t.attach_forgot_title, plume.t.attach_forgot_text,
                    [{ id: "attach", text: plume.t.attach }, { id: "send", text: plume.t.send_anyway, kind: "primary" }],
                    choice => { if (choice === "send") composer.send(true); else picker.open() })
            return
        }
        done = true
        mail.send(f)
        close()
    }

    function attach(urls) {
        let list = attachments.slice()
        for (const u of urls) {
            const path = String(u)
            if (path.indexOf("file:") !== 0 && path.indexOf("/") !== 0)
                continue                  // a picture dragged from a web page: not a file of this computer
            const size = mail.attachmentSize(path)
            list.push({ path: path, name: path.split("/").pop(), size: size })
            if (size > heavyBytes)
                heavy = path
        }
        attachments = list
    }

    onClosing: {
        keeper.stop()
        if (!done)
            mail.saveDraft(fields())
        else
            mail.clearComposing()
    }

    // what is written is kept on this computer every few seconds (Plume stopping, a power cut: it comes back)
    Timer {
        id: keeper
        property string last
        interval: 4000; repeat: true
        running: composer.visible && !composer.done
        onTriggered: {
            if (!composer.hasContent())
                return
            const written = editor.exported()
            const f = Object.assign({}, composer.base, {
                from: sender.currentValue, to: to.addresses.concat(to.pending()), cc: cc.addresses, bcc: bcc.addresses,
                subject: subject.text, body: written.text, html: written.html,
                signature: composer.signatureOff ? "" : composer.signature, quoteText: composer.quoteText, quoteHtml: composer.quoteHtml,
                attachments: composer.attachments.map(a => a.path)
            })
            const snapshot = JSON.stringify(f)
            if (snapshot !== last) {
                last = snapshot
                mail.keepComposing(f)
            }
        }
    }

    Connections {
        target: mail
        // (a message cancelled or refused comes back in a composer: MailView picks which)
        function onShareLinkReady(path, url) {
            if (!url || !composer.attachments.some(a => a.path === path))
                return
            composer.attachments = composer.attachments.filter(a => a.path !== path)
            editor.area.insert(editor.area.cursorPosition, '<br><a href="' + url + '">' + url + "</a><br>")
            composer.heavy = ""
        }
    }

    Shortcut { sequences: ["Ctrl+Return", "Ctrl+Enter"]; onActivated: composer.send() }
    Shortcut { sequence: "Escape"; onActivated: composer.close() }

    component Label_: Text {
        Layout.preferredWidth: 56
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: composer.c.muted
    }
    component Line_: Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: composer.c.hairline }

    DropArea {
        anchors.fill: parent
        onDropped: drop => { if (drop.hasUrls) composer.attach(drop.urls) }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        ColumnLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 24; Layout.rightMargin: 20; Layout.topMargin: 8
            spacing: 0
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 46
                spacing: 12
                Label_ { text: plume.t.from_label }
                OComboBox {
                    id: sender
                    Layout.fillWidth: true
                    model: (mail.account.identities || []).map(i => ({ text: (i.name ? i.name + "  <" + i.email + ">" : i.email), value: i.email }))
                    background: Item {}
                    onCurrentValueChanged: if (!composer.loading) composer.signature = composer.identity(currentValue).signature || ""
                }
            }
            Line_ {}
            RowLayout {
                Layout.fillWidth: true
                Layout.minimumHeight: 46
                spacing: 12
                Label_ { text: plume.t.to_label }
                RecipientField { id: to; Layout.fillWidth: true; placeholder: plume.t.guests_ph }
                OButton { visible: !composer.showCc; kind: "quiet"; height_: 28; text: plume.t.cc_label; onClicked: { composer.showCc = true; cc.forceActiveFocus() } }
                OButton { visible: !composer.showBcc; kind: "quiet"; height_: 28; text: plume.t.bcc_label; onClicked: { composer.showBcc = true; bcc.forceActiveFocus() } }
            }
            Line_ {}
            RowLayout {
                visible: composer.showCc
                Layout.fillWidth: true
                Layout.minimumHeight: 46
                spacing: 12
                Label_ { text: plume.t.cc_label }
                RecipientField { id: cc; Layout.fillWidth: true }
            }
            Line_ { visible: composer.showCc }
            RowLayout {
                visible: composer.showBcc
                Layout.fillWidth: true
                Layout.minimumHeight: 46
                spacing: 12
                Label_ { text: plume.t.bcc_label }
                RecipientField { id: bcc; Layout.fillWidth: true }
            }
            Line_ { visible: composer.showBcc }
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 46
                spacing: 12
                Label_ { text: plume.t.subject_label }
                TextField {
                    id: subject
                    Layout.fillWidth: true
                    background: null
                    leftPadding: 2
                    color: composer.c.text
                    font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.weight: Font.Medium
                    selectByMouse: true
                    onAccepted: editor.area.forceActiveFocus()
                }
            }
            Line_ {}
        }

        // the text, then the signature and the quoted message (one scroll)
        RichEditor {
            id: editor
            Layout.fillWidth: true
            Layout.fillHeight: true
            placeholder: plume.t.write_ph
            pictures: true
            onFilesPasted: urls => composer.attach(urls)
            below: [
                // the signature as it will be received: drawn by Chromium (tables, colours, buttons), like
                // in the reader. A click edits it.
                Item {
                    visible: composer.signature !== "" && !composer.signatureOff
                    width: parent.width
                    height: visible ? (signatureView.item ? signatureView.item.shown : signatureText.implicitHeight) + 12 : 0
                    Loader {
                        id: signatureView
                        x: 16; y: 4
                        width: parent.width - 40
                        height: item ? item.shown : 0
                        active: !plume.noWebEngine && parent.visible
                        sourceComponent: Component {
                            WebEngineView {
                                id: signatureWeb
                                readonly property real shown: Math.max(24, contentsSize.height)
                                backgroundColor: "transparent"
                                settings.javascriptEnabled: false
                                settings.pluginsEnabled: false
                                settings.focusOnNavigationEnabled: false
                                settings.showScrollBars: false
                                profile: WebEngineProfile { offTheRecord: true }
                                onNavigationRequested: request => { if (request.navigationType === WebEngineNavigationRequest.LinkClickedNavigation) request.reject() }
                                Component.onCompleted: loadHtml(composer.signaturePage(), "about:blank")
                                Connections {
                                    target: composer
                                    function onSignatureChanged() { signatureWeb.loadHtml(composer.signaturePage(), "about:blank") }
                                }
                                Connections {
                                    target: theme
                                    function onChanged() { signatureWeb.loadHtml(composer.signaturePage(), "about:blank") }
                                }
                            }
                        }
                    }
                    Text {
                        id: signatureText
                        visible: plume.noWebEngine
                        width: parent.width
                        leftPadding: 24; rightPadding: 24; topPadding: 4; bottomPadding: 8
                        textFormat: Text.RichText
                        text: composer.signature
                        wrapMode: Text.Wrap
                        font.family: "Schibsted Grotesk"; font.pixelSize: 15
                        color: composer.c.text
                        linkColor: composer.c.accent
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        hoverEnabled: true
                        ToolTip.text: plume.t.signature_edit
                        ToolTip.visible: containsMouse
                        ToolTip.delay: 600
                        onClicked: signatureEditor.openFor(sender.currentValue)
                    }
                },
                Column {
                    visible: composer.quoteText !== "" || composer.quoteHtml !== ""
                    width: parent.width
                    leftPadding: 20; rightPadding: 24; topPadding: 6; bottomPadding: 16
                    spacing: 6
                    Row {
                        spacing: 4
                        OButton {
                            kind: "quiet"; height_: 28
                            iconName: composer.quoteOpen ? "chevronDown" : "more"
                            text: plume.t.quote_show
                            onClicked: composer.quoteOpen = !composer.quoteOpen
                        }
                        OButton {
                            kind: "quiet"; height_: 28; implicitWidth: 28; iconName: "close"; iconSize: 13
                            ToolTip.text: plume.t.quote_remove
                            onClicked: { composer.quoteText = ""; composer.quoteHtml = "" }
                        }
                    }
                    Text {
                        visible: composer.quoteOpen
                        width: parent.width - 28
                        leftPadding: 6
                        text: composer.quoteText.replace(/^\n+/, "")
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        font.family: "Schibsted Grotesk"; font.pixelSize: 14
                        color: composer.c.muted
                    }
                }
            ]
        }

        OrnisWriter {
            id: writer
            Layout.fillWidth: true
            Layout.leftMargin: 20; Layout.rightMargin: 20; Layout.bottomMargin: 10
            editor: editor
            context: composer.quoteText
            mailFrom: {
                const who = composer.identity(sender.currentValue)
                return who.name ? who.name + " <" + sender.currentValue + ">" : String(sender.currentValue || "")
            }
            mailTo: to.addresses.concat(cc.addresses).join(", ")
            mailSubject: subject.text
            mailSigned: composer.signature !== "" && !composer.signatureOff
        }

        // attachments and the heavy-file question
        ColumnLayout {
            visible: composer.attachments.length > 0 || composer.heavy !== ""
            Layout.fillWidth: true
            Layout.leftMargin: 24; Layout.rightMargin: 24; Layout.bottomMargin: 8
            spacing: 8
            Rectangle {
                visible: composer.heavy !== ""
                Layout.fillWidth: true
                implicitHeight: 44
                radius: 8
                color: composer.c.saffronTint
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 8
                    spacing: 10
                    Icon { name: "cloud"; size: 18; color: composer.c.saffronInk }
                    Text {
                        Layout.fillWidth: true
                        text: plume.t.big_attachment
                        elide: Text.ElideRight
                        font.family: "Schibsted Grotesk"; font.pixelSize: 14
                        color: composer.c.saffronInk
                    }
                    OButton { height_: 30; kind: "primary"; text: plume.t.send_link; onClicked: mail.requestShareLink(composer.heavy) }
                    OButton { height_: 30; kind: "quiet"; iconName: "close"; implicitWidth: 30; Accessible.name: plume.t.close; onClicked: composer.heavy = "" }
                }
            }
            Flow {
                Layout.fillWidth: true
                spacing: 8
                Repeater {
                    model: composer.attachments
                    Rectangle {
                        required property var modelData
                        required property int index
                        height: 34; radius: 8
                        width: attRow.implicitWidth + 16
                        color: composer.c.bg
                        border.width: 1; border.color: composer.c.line
                        Row {
                            id: attRow
                            anchors.centerIn: parent
                            spacing: 8
                            Icon { anchors.verticalCenter: parent.verticalCenter; name: "clip"; size: 15; color: composer.c.muted }
                            Text { anchors.verticalCenter: parent.verticalCenter; text: modelData.name; font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: composer.c.text }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: modelData.size >= 1048576 ? (modelData.size / 1048576).toFixed(1) + " Mo" : Math.max(1, Math.round(modelData.size / 1024)) + " Ko"
                                font.family: "JetBrains Mono"; font.pixelSize: 11; color: composer.c.muted
                            }
                            OButton {
                                anchors.verticalCenter: parent.verticalCenter
                                kind: "quiet"; iconName: "close"; iconSize: 11; height_: 20; implicitWidth: 20
                                Accessible.name: plume.t.delete
                                onClicked: { const l = composer.attachments.slice(); l.splice(index, 1); composer.attachments = l }
                            }
                        }
                    }
                }
            }
        }

        Line_ {}
        RowLayout {
            Layout.fillWidth: true
            Layout.margins: 12; Layout.leftMargin: 24; Layout.rightMargin: 16
            spacing: 8
            OButton { kind: "primary"; height_: 38; iconName: "send"; text: plume.t.send; onClicked: { composer.base.sendAt = 0; composer.send() } }
            // « Envoyer plus tard »: tomorrow morning, Monday, or a day and a time
            OButton {
                id: laterButton
                height_: 38; implicitWidth: 38; iconName: "clock"
                tip: plume.t.send_later
                onClicked: { laterMenu.options = Array.from(mail.laterOptions("send")); laterMenu.open() }
                OMenu {
                    id: laterMenu
                    property var options: []
                    y: -height - 6
                    heading: plume.t.send_later
                    subheading: plume.t.send_later_hint
                    Repeater {
                        model: laterMenu.options
                        OMenuItem {
                            required property var modelData
                            text: modelData.label; iconName: "clock"
                            onTriggered: composer.sendAt(modelData.at)
                        }
                    }
                    OMenuItem { text: plume.t.later_pick; iconName: "calendar"; onTriggered: when.pickFor(plume.t.send_later, at => composer.sendAt(at)) }
                }
            }
            OButton { height_: 38; iconName: "clip"; text: plume.t.attach; onClicked: picker.open() }
            // templates: an answer written once, put in at the cursor (its subject too, when there is none yet)
            OButton {
                id: templateButton
                height_: 38; implicitWidth: 38; iconName: "note"
                tip: plume.t.templates
                onClicked: templateMenu.open()
                OMenu {
                    id: templateMenu
                    y: -height - 6
                    heading: plume.t.templates
                    Repeater {
                        model: mail.templates
                        OMenuItem {
                            required property var modelData
                            text: modelData.name; iconName: "note"
                            onTriggered: composer.useTemplate(modelData)
                        }
                    }
                    OMenuItem { enabled: !editor.isEmpty(); opacity: enabled ? 1 : 0.45; text: plume.t.template_save; iconName: "plus"
                                onTriggered: namePrompt.ask(plume.t.template_save_title, plume.t.template_save_text, plume.t.template_name_ph,
                                                            subject.text, plume.t.save, name => { const w = editor.exported(); mail.saveTemplate(name, { subject: subject.text, html: w.html, body: w.text }) }) }
                    Repeater {
                        model: mail.templates
                        OMenuItem {
                            required property var modelData
                            text: plume.t.template_delete.replace("%1", modelData.name); iconName: "trash"; danger: true
                            onTriggered: mail.deleteTemplate(modelData.name)
                        }
                    }
                }
            }
            OButton {
                id: ornisButton
                kind: "accent"; height_: 38; iconName: "ornis"; text: plume.t.ornis
                onClicked: { ornis.loadQuota(); ornisMenu.open() }
                OMenu {
                    id: ornisMenu
                    y: -height - 6
                    readonly property var tools: [
                        { id: "proofread", text: plume.t.ornis_proofread, icon: "check" },
                        { id: "professional", text: plume.t.ornis_professional, icon: "sparkle" },
                        { id: "friendly", text: plume.t.ornis_friendly, icon: "sparkle" },
                        { id: "concise", text: plume.t.ornis_concise, icon: "sparkle" },
                        { id: "expand", text: plume.t.ornis_expand, icon: "sparkle" }
                    ].concat(["fr", "en", "de", "es", "it"].filter(l => l !== plume.lang).slice(0, 3).map(l => (
                        { id: "translate:" + l, text: plume.t.ornis_translate.replace("%1", plume.t["lang_" + l]), icon: "arrow" })))
                    OMenuItem { text: plume.t.ornis_draft; iconName: "ornis"; onTriggered: writer.begin("draft", plume.t.ornis_draft.replace("…", "")) }
                    Rectangle { width: parent ? parent.width : 0; height: 1; color: composer.c.hairline }
                    Repeater {
                        model: ornisMenu.tools
                        OMenuItem {
                            required property var modelData
                            enabled: !editor.isEmpty()
                            opacity: enabled ? 1 : 0.45
                            text: modelData.text; iconName: modelData.icon
                            onTriggered: writer.begin(modelData.id, modelData.text)
                        }
                    }
                    OMenuItem { enabled: !editor.isEmpty(); opacity: enabled ? 1 : 0.45; text: plume.t.ornis_custom; iconName: "draft"; onTriggered: writer.begin("custom", plume.t.ornis_custom.replace("…", "")) }
                }
            }
            OButton {
                id: signatureButton
                height_: 38; implicitWidth: 38; iconName: "signature"
                ToolTip.text: plume.t.signature
                onClicked: signatureMenu.open()
                OMenu {
                    id: signatureMenu
                    y: -height - 6
                    OMenuItem { text: plume.t.signature_edit; iconName: "signature"; onTriggered: signatureEditor.openFor(sender.currentValue) }
                    OMenuItem {
                        visible: composer.signature !== ""
                        text: composer.signatureOff ? plume.t.signature_add : plume.t.signature_remove
                        iconName: composer.signatureOff ? "plus" : "close"
                        onTriggered: composer.signatureOff = !composer.signatureOff
                    }
                }
            }
            Text {
                visible: composer.error !== ""
                text: composer.error
                font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
                color: composer.c.danger
            }
            Item { Layout.fillWidth: true }
            Text { text: plume.t.send_keys; font.family: "JetBrains Mono"; font.pixelSize: 12; color: composer.c.muted }
            OButton {
                kind: "quiet"; iconName: "trash"; implicitWidth: 36
                Accessible.name: plume.t.discard
                onClicked: {
                    composer.done = true
                    if (composer.base.draftId)
                        mail.moveTo([composer.base.draftId], "trash")
                    mail.clearComposing()
                    composer.close()
                }
            }
        }
    }

    SignatureEditor {
        id: signatureEditor
        onSaved: (email, html) => {
            if (email.toLowerCase() === String(sender.currentValue).toLowerCase()) {
                composer.signature = html
                composer.signatureOff = false
            }
        }
    }

    ChoiceDialog { id: ask }
    WhenPicker { id: when }
    PromptDialog { id: namePrompt }

    FileDialog {
        id: picker
        currentFolder: Std.StandardPaths.writableLocation(Std.StandardPaths.HomeLocation)
        fileMode: FileDialog.OpenFiles
        onAccepted: composer.attach(selectedFiles)
    }
}
