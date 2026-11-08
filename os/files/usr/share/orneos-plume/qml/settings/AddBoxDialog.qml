// Adding an external mailbox: with Google's or Microsoft's own page (in the browser, when their app is
// published), or with the address and the password (Plume finds the servers and checks them). When it
// cannot, the servers can be given by hand. Also asks a new password for a mailbox whose password changed,
// or signs a Google or Microsoft mailbox in again.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

ODialog {
    id: dialog
    readonly property var c: theme.c
    property string boxKey                // set: only a new password for this mailbox
    property bool checking
    property bool manual
    property string error
    property string note                  // what the provider asks for (app password, its sign-in page…)
    readonly property bool appPassword: note === "app_password" || note === "workspace"
    property string signingIn             // the provider whose page is open in the browser
    property bool reconnecting            // boxKey is signed in again with its provider's page
    property bool editing                 // boxKey's servers changed by hand (the password only if it changed too)
    property bool usePassword             // an app password rather than the provider's page (Google)
    // the address signs in with its provider's page (Plume knows its app); note and oauthProviders: to follow them
    readonly property string signInWith: boxKey || usePassword || manual ? "" : providerOf(note, mail.oauthProviders)
    readonly property var providerNames: ({ google: "Google", microsoft: "Microsoft" })
    function providerOf(_note, _apps) { return mail.oauthProviderOf(address.text) }
    width: Math.min(520, parent ? parent.width - 48 : 520)
    title: editing ? plume.t.box_servers_title : reconnecting ? plume.t.box_reconnect : boxKey ? plume.t.box_password_title : plume.t.box_add

    function openFor() {
        mail.loadOauth()
        editing = false
        boxKey = ""; checking = false; manual = false; error = ""; note = ""
        signingIn = ""; reconnecting = false; usePassword = false
        address.text = ""; password.text = ""; name.text = ""
        imapHost.text = ""; imapPort.text = "993"; smtpHost.text = ""; smtpPort.text = "465"; login.text = ""
        open()
        address.forceActiveFocus()
    }
    // the servers of a mailbox already added, to correct them (a provider that moved, a port that changed)
    function openServers(box) {
        const conf = mail.boxConfig(box.key)
        boxKey = box.key; editing = true; checking = false; manual = true; error = ""; note = ""
        signingIn = ""; reconnecting = false; usePassword = false
        address.text = box.address; password.text = ""
        imapHost.text = conf.imapHost || ""; imapPort.text = String(conf.imapPort || 993)
        smtpHost.text = conf.smtpHost || ""; smtpPort.text = String(conf.smtpPort || 465)
        imapSecurity.currentIndex = conf.imapSecurity === "starttls" ? 1 : 0
        smtpSecurity.currentIndex = conf.smtpSecurity === "starttls" ? 1 : 0
        login.text = conf.login || ""
        saveSent.checked = conf.saveSent !== false
        open()
        imapHost.forceActiveFocus()
    }
    function openPassword(box) {
        editing = false
        boxKey = box.key; checking = false; manual = false; error = ""; note = ""
        signingIn = ""; reconnecting = false; usePassword = false
        address.text = box.address; password.text = ""
        open()
        password.forceActiveFocus()
    }
    function openReconnect(box) {
        editing = false
        boxKey = box.key; checking = false; manual = false; error = ""; note = ""
        reconnecting = true; usePassword = false
        address.text = box.address; password.text = ""
        open()
        signIn(box.oauth)
    }
    function signIn(provider) {
        error = ""
        signingIn = provider
        if (reconnecting)
            mail.reconnectBox(boxKey)
        else
            mail.signInBox(provider, address.text.trim(), name.text.trim())
    }
    function stopSignIn() {
        mail.cancelSignIn()
        signingIn = ""
    }
    function submit() {
        if (checking || signingIn)
            return
        if (reconnecting) {
            signIn(mail.boxes.find(b => b.key === boxKey).oauth)
            return
        }
        if (signInWith) {
            signIn(signInWith)
            return
        }
        error = ""
        if (editing) {
            if (!imapHost.text.trim()) {
                error = plume.t.box_missing
                return
            }
            checking = true
            mail.updateBoxServers(boxKey, {
                password: password.text, imapHost: imapHost.text.trim(), imapPort: parseInt(imapPort.text) || 993,
                imapSecurity: imapSecurity.currentValue, smtpHost: smtpHost.text.trim(), smtpPort: parseInt(smtpPort.text) || 465,
                smtpSecurity: smtpSecurity.currentValue, login: login.text.trim() || address.text.trim(), saveSent: saveSent.checked
            })
            return
        }
        if (!address.text.trim() || !password.text) {
            error = plume.t.box_missing
            return
        }
        checking = true
        if (boxKey) {
            mail.setBoxPassword(boxKey, password.text)
            return
        }
        const fields = { address: address.text.trim(), password: password.text, name: name.text.trim() }
        if (manual) {
            Object.assign(fields, {
                imapHost: imapHost.text.trim(), imapPort: parseInt(imapPort.text) || 993, imapSecurity: imapSecurity.currentValue,
                smtpHost: smtpHost.text.trim(), smtpPort: parseInt(smtpPort.text) || 465, smtpSecurity: smtpSecurity.currentValue,
                login: login.text.trim() || address.text.trim()
            })
        }
        mail.addBox(fields)
    }

    // the provider of a domain of its own is found by its MX, once the address stops changing
    Timer {
        id: noteTimer
        interval: 400
        onTriggered: dialog.note = dialog.boxKey ? "" : mail.providerNote(address.text)
    }

    Connections {
        target: mail
        function onProviderFound(which, note) {
            if (!dialog.boxKey && which.toLowerCase() === address.text.trim().toLowerCase())
                dialog.note = note
        }
        function onBoxResult(ok, reason, which) {
            // signed in with a provider's page: the address is the one chosen there
            if (!dialog.opened || (!dialog.signingIn && which.toLowerCase() !== address.text.trim().toLowerCase()))
                return
            dialog.checking = false
            dialog.signingIn = ""
            if (ok) {
                dialog.close()
                plume.toast((dialog.editing ? plume.t.box_updated : dialog.reconnecting ? plume.t.box_reconnected : plume.t.box_added).replace("%1", which))
                return
            }
            if (reason === "cancelled")
                return
            dialog.error = plume.t["box_error_" + reason] || plume.t.box_error_notfound
            // the servers were not found, or one of them refused: they can be given by hand
            if (reason === "notfound" || reason.indexOf("smtp_") === 0 || reason === "offline" || reason === "server")
                dialog.manual = true
            if (reason === "auth")
                password.selectAll()
        }
    }

    onClosed: if (signingIn) stopSignIn()

    // the best known providers sign in with their own page: nothing to create, no password here
    ColumnLayout {
        visible: !dialog.boxKey && !dialog.manual && mail.oauthProviders.length > 0
        Layout.fillWidth: true
        spacing: 8
        Repeater {
            model: mail.oauthProviders
            OButton {
                required property string modelData
                Layout.fillWidth: true
                height_: 40
                enabled: !dialog.checking && !dialog.signingIn
                image: "../brands/" + modelData + ".svg"
                text: plume.t.box_signin.replace("%1", dialog.providerNames[modelData] || modelData)
                onClicked: { address.text = ""; dialog.signIn(modelData) }
            }
        }
        Text {
            Layout.fillWidth: true
            Layout.topMargin: 4
            text: plume.t.box_signin_or
            horizontalAlignment: Text.AlignHCenter
            font.family: "Schibsted Grotesk"; font.pixelSize: 13
            color: dialog.c.muted
        }
    }
    Text {
        Layout.fillWidth: true
        visible: !dialog.boxKey
        text: plume.t.box_add_lead
        wrapMode: Text.Wrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: dialog.c.muted
    }
    OTextField {
        id: address
        Layout.fillWidth: true
        enabled: !dialog.boxKey && !dialog.checking && !dialog.signingIn
        placeholderText: plume.t.box_address_ph
        inputMethodHints: Qt.ImhEmailCharactersOnly | Qt.ImhNoAutoUppercase
        onTextChanged: noteTimer.restart()
        onAccepted: password.forceActiveFocus()
    }
    OTextField {
        id: password
        visible: !dialog.signInWith && !dialog.reconnecting
        Layout.fillWidth: true
        enabled: !dialog.checking
        echoMode: TextInput.Password
        placeholderText: dialog.editing ? plume.t.box_password_keep_ph : dialog.appPassword ? plume.t.box_app_password_ph : plume.t.box_password_ph
        onAccepted: dialog.submit()
    }
    OTextField {
        id: name
        visible: !dialog.boxKey
        Layout.fillWidth: true
        enabled: !dialog.checking && !dialog.signingIn
        placeholderText: plume.t.box_name_ph
        onAccepted: dialog.submit()
    }

    // what the provider asks for (an app password), or why it cannot be added yet
    Rectangle {
        visible: (dialog.note !== "" || dialog.signInWith !== "") && !dialog.reconnecting
        Layout.fillWidth: true
        implicitHeight: noteText.implicitHeight + 20
        radius: 8
        color: dialog.appPassword || dialog.signInWith ? dialog.c.tint : dialog.c.saffronTint
        Text {
            id: noteText
            anchors.fill: parent; anchors.margins: 10
            text: dialog.signInWith ? plume.t.box_note_signin.replace("%1", dialog.providerNames[dialog.signInWith])
                : plume.t["box_note_" + dialog.note] || ""
            wrapMode: Text.Wrap
            font.family: "Schibsted Grotesk"; font.pixelSize: 13
            color: dialog.appPassword || dialog.signInWith ? dialog.c.tintText : dialog.c.saffronInk
            textFormat: Text.StyledText
            linkColor: color
            onLinkActivated: link => plume.openUrl(link)
        }
    }

    OButton {
        visible: dialog.signInWith === "google" && !dialog.signingIn
        kind: "quiet"; height_: 28; iconName: "lock"; iconSize: 15
        text: plume.t.box_use_password
        onClicked: { dialog.usePassword = true; password.forceActiveFocus() }
    }

    // servers by hand
    OButton {
        visible: !dialog.boxKey && !dialog.manual && !dialog.signingIn
        kind: "quiet"; height_: 28; iconName: "settings"; iconSize: 15
        text: plume.t.box_manual
        onClicked: dialog.manual = true
    }
    GridLayout {
        visible: dialog.manual && (!dialog.boxKey || dialog.editing)
        Layout.fillWidth: true
        columns: 3
        columnSpacing: 8; rowSpacing: 8
        Text { text: "IMAP"; font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold; color: dialog.c.muted }
        OTextField { id: imapHost; Layout.fillWidth: true; placeholderText: "imap.exemple.fr" }
        RowLayout {
            spacing: 6
            OTextField { id: imapPort; implicitWidth: 70; text: "993"; inputMethodHints: Qt.ImhDigitsOnly }
            OComboBox {
                id: imapSecurity
                implicitWidth: 120
                model: [{ text: "SSL/TLS", value: "ssl" }, { text: "STARTTLS", value: "starttls" }]
                onActivated: imapPort.text = currentValue === "ssl" ? "993" : "143"
            }
        }
        Text { text: "SMTP"; font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold; color: dialog.c.muted }
        OTextField { id: smtpHost; Layout.fillWidth: true; placeholderText: "smtp.exemple.fr" }
        RowLayout {
            spacing: 6
            OTextField { id: smtpPort; implicitWidth: 70; text: "465"; inputMethodHints: Qt.ImhDigitsOnly }
            OComboBox {
                id: smtpSecurity
                implicitWidth: 120
                model: [{ text: "SSL/TLS", value: "ssl" }, { text: "STARTTLS", value: "starttls" }]
                onActivated: smtpPort.text = currentValue === "ssl" ? "465" : "587"
            }
        }
        Text { text: plume.t.box_login; font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold; color: dialog.c.muted }
        OTextField { id: login; Layout.fillWidth: true; Layout.columnSpan: 2; placeholderText: address.text || plume.t.box_login_ph }
    }
    // Gmail and Outlook keep their own copy in Sent: Plume's would be a second one
    RowLayout {
        visible: dialog.editing
        Layout.fillWidth: true
        spacing: 12
        Text {
            Layout.fillWidth: true
            text: plume.t.box_save_sent
            wrapMode: Text.Wrap
            font.family: "Schibsted Grotesk"; font.pixelSize: 14; color: dialog.c.text
        }
        OSwitch { id: saveSent; checked: true }
    }

    Text {
        visible: dialog.error !== ""
        Layout.fillWidth: true
        text: dialog.error
        wrapMode: Text.Wrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.Medium
        color: dialog.c.danger
    }
    RowLayout {
        visible: dialog.checking || dialog.signingIn !== ""
        spacing: 10
        BusyIndicator { implicitWidth: 20; implicitHeight: 20; running: parent.visible }
        Text {
            Layout.fillWidth: true
            text: dialog.signingIn ? plume.t.box_signing_in : dialog.manual || dialog.boxKey ? plume.t.box_checking : plume.t.box_finding
            wrapMode: Text.Wrap
            font.family: "Schibsted Grotesk"; font.pixelSize: 14; color: dialog.c.muted
        }
    }

    footer: [
        Item { Layout.fillWidth: true },
        OButton { text: plume.t.cancel; onClicked: dialog.signingIn && !dialog.reconnecting ? dialog.stopSignIn() : dialog.close() },
        OButton {
            kind: "primary"
            enabled: !dialog.checking && !dialog.signingIn && (dialog.note !== "oauth" || dialog.signInWith !== "")
            opacity: enabled ? 1 : 0.5
            text: dialog.reconnecting ? plume.t.box_reconnect
                : dialog.signInWith ? plume.t.box_signin.replace("%1", dialog.providerNames[dialog.signInWith])
                : dialog.boxKey ? plume.t.save : plume.t.box_add_action
            onClicked: dialog.submit()
        }
    ]
}
