// Setting up a verification code: get the site's setup code (screen, clipboard, key), check the code it gives,
// then put it on its entry. Also what an otpauth:// link (from the browser) opens.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    property string uri
    property string entryId                 // the entry it is for, when known
    property var now: ({})
    property var candidates: []
    signal newEntryWith(string uri)
    signal attached(string id)
    width: Math.min(540, parent ? parent.width - 48 : 540)
    title: entryId ? app.t.otp_setup_for.replace("%1", vault.detail(entryId).label || "") : app.t.otp_setup

    function openWith(value, id) {
        entryId = id || ""
        uri = ""
        candidates = []
        if (value)
            take(value)
        open()
    }
    function take(value) {
        const found = vault.codeFor(value)
        if (!found.uri)
            return
        uri = found.uri
        now = found
        if (!entryId)
            candidates = vault.forOtp(found.uri)
    }
    function attach(id) {
        vault.addCode(id, uri)
        close()
        dialog.attached(id)
    }

    Timer {
        interval: 1000; repeat: true; running: dialog.opened && dialog.uri !== ""
        onTriggered: dialog.now = vault.codeFor(dialog.uri)
    }

    CodeCapture {
        visible: dialog.uri === ""
        Layout.fillWidth: true
        onCaptured: value => dialog.take(value)
    }

    // the code found: the site asks for it to finish its setup
    ColumnLayout {
        visible: dialog.uri !== ""
        Layout.fillWidth: true
        spacing: 12
        Text {
            Layout.fillWidth: true
            text: dialog.now.issuer || dialog.now.account ? [dialog.now.issuer, dialog.now.account].filter(x => x).join(" · ") : app.t.otp_found
            font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
            color: theme.c.text
        }
        RowLayout {
            spacing: 14
            Text {
                text: (dialog.now.code || "").replace(/^(\d{3})(\d{3,})$/, "$1 $2")
                font.family: "JetBrains Mono"; font.pixelSize: 30; font.weight: Font.Medium; font.letterSpacing: 1
                color: theme.c.text
            }
            CodeRing { size: 26; remaining: dialog.now.remaining || 0; period: dialog.now.period || 30 }
            OButton { kind: "quiet"; iconName: "copy"; text: app.t.copy; onClicked: app.copy(dialog.now.code || "", "code") }
        }
        Text {
            Layout.fillWidth: true
            text: app.t.otp_check
            wrapMode: Text.WordWrap
            lineHeight: 1.25
            font.family: "Schibsted Grotesk"; font.pixelSize: 13
            color: theme.c.muted
        }

        // where it goes (a link from the browser: the entries of that site first)
        Text {
            visible: !dialog.entryId
            Layout.topMargin: 6
            text: app.t.otp_where
            font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
            color: theme.c.muted
        }
        Repeater {
            model: dialog.entryId ? [] : dialog.candidates
            AbstractButton {
                id: pick
                required property var modelData
                Layout.fillWidth: true
                implicitHeight: 48
                hoverEnabled: true
                onClicked: dialog.attach(modelData.id)
                background: Rectangle { radius: 8; color: pick.hovered ? theme.c.hover : "transparent" }
                contentItem: RowLayout {
                    spacing: 10
                    SiteIcon { Layout.leftMargin: 8; size: 30; source: pick.modelData.icon || ""; initial: pick.modelData.initial; tile: pick.modelData.tile }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0
                        Text { Layout.fillWidth: true; elide: Text.ElideRight; text: pick.modelData.label; font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.weight: Font.DemiBold; color: theme.c.text }
                        Text { Layout.fillWidth: true; elide: Text.ElideRight; text: pick.modelData.username; font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: theme.c.muted }
                    }
                    Text { Layout.rightMargin: 10; text: app.t.otp_add_here; font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold; color: theme.c.accent }
                }
            }
        }
    }

    footer: [
        OButton { visible: dialog.uri !== ""; kind: "quiet"; text: app.t.otp_other; onClicked: { dialog.uri = ""; dialog.candidates = [] } },
        Item { Layout.fillWidth: true },
        OButton { text: app.t.cancel; onClicked: dialog.close() },
        OButton {
            visible: dialog.uri !== "" && !dialog.entryId
            iconName: "plus"; text: app.t.otp_new_entry
            onClicked: { const u = dialog.uri; dialog.close(); dialog.newEntryWith(u) }
        },
        OButton {
            visible: dialog.uri !== "" && !!dialog.entryId
            kind: "primary"; iconName: "check"; text: app.t.save
            onClicked: dialog.attach(dialog.entryId)
        }
    ]
}
