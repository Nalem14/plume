// The signature of each address, formatted (pasted from elsewhere or written here). Saved in the cloud's
// Mail app for Orneos addresses (the web and Plume share it), by Plume for the other mailboxes.
// A designed signature (tables, pictures, styles) would be damaged by the text editor: pasted, it is kept
// as it is and shown as it will be received; to change it, paste another one or write a simple one.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtWebEngine
import "../components"

ODialog {
    id: dialog
    property string email
    property string original
    property bool replacing
    property string pasted              // a designed signature just pasted, kept as it is
    readonly property bool orneos: ((mail.account.identities || []).find(i => i.email === email) || {}).box === "orneos"
    readonly property string designedHtml: pasted !== "" ? pasted
                                           : !replacing && /<table|<img|style\s*=/i.test(original) ? original : ""
    readonly property bool designed: designedHtml !== ""
    signal saved(string email, string html)
    width: Math.min(620, parent ? parent.width - 48 : 620)
    title: plume.t.signature

    function openFor(address) {
        const list = mail.account.identities || []
        email = address || (list.length ? list[0].email : "")
        who.select(email)
        load()
        open()
        sig.area.forceActiveFocus()
    }
    function load() {
        const identity = (mail.account.identities || []).find(i => i.email === email) || {}
        original = identity.signature || ""
        replacing = false
        pasted = ""
        sig.load(original)
    }
    function preview() {
        return '<!doctype html><meta charset="utf-8"><style>html{color-scheme:light}body{margin:0;padding:12px 14px;'
               + 'background:#FFFFFF;font:15px/1.5 Arial,sans-serif;color:#0F2440;overflow:hidden}img{max-width:100%;height:auto}</style>'
               + designedHtml
    }

    // another designed signature pasted over the one shown
    Shortcut {
        sequences: [StandardKey.Paste]
        enabled: dialog.visible && dialog.designed
        onActivated: {
            const html = rich.designedClipboard()
            if (html !== "")
                dialog.pasted = html
        }
    }

    OComboBox {
        id: who
        visible: (mail.account.identities || []).length > 1
        Layout.fillWidth: true
        model: (mail.account.identities || []).map(i => ({ text: i.email, value: i.email }))
        onActivated: { dialog.email = currentValue; dialog.load() }
    }
    Text {
        Layout.fillWidth: true
        text: dialog.designed ? (dialog.pasted !== "" ? plume.t.signature_pasted : plume.t.signature_designed)
              : dialog.orneos ? plume.t.signature_hint : plume.t.signature_hint_box
        wrapMode: Text.Wrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 13
        color: dialog.c.muted
    }
    // the designed signature as it will be received: drawn by Chromium, on white paper
    Rectangle {
        visible: dialog.designed
        Layout.fillWidth: true
        Layout.preferredHeight: Math.min(320, Math.max(80, previewView.item ? previewView.item.shown : 80)) + 2
        radius: 8
        color: "#FFFFFF"
        border.width: 1
        border.color: dialog.c.line
        clip: true
        Loader {
            id: previewView
            anchors.fill: parent
            anchors.margins: 1
            active: !plume.noWebEngine && dialog.visible && dialog.designed
            sourceComponent: Component {
                WebEngineView {
                    id: web
                    readonly property real shown: contentsSize.height
                    settings.javascriptEnabled: false
                    settings.pluginsEnabled: false
                    settings.focusOnNavigationEnabled: false
                    profile: WebEngineProfile { offTheRecord: true }
                    onNavigationRequested: request => { if (request.navigationType === WebEngineNavigationRequest.LinkClickedNavigation) request.reject() }
                    Component.onCompleted: loadHtml(dialog.preview(), "about:blank")
                    Connections {
                        target: dialog
                        function onDesignedHtmlChanged() { if (dialog.designed) web.loadHtml(dialog.preview(), "about:blank") }
                    }
                }
            }
        }
    }
    RowLayout {
        visible: dialog.designed
        spacing: 8
        OButton {
            visible: dialog.orneos && dialog.pasted === ""
            height_: 30; iconName: "cloud"; text: plume.t.signature_in_cloud
            onClicked: { plume.openCloud("/apps/mail/"); dialog.close() }
        }
        OButton {
            height_: 30; kind: "quiet"; text: plume.t.signature_replace
            onClicked: { dialog.pasted = ""; dialog.replacing = true; sig.load(""); sig.area.forceActiveFocus() }
        }
    }
    Rectangle {
        visible: !dialog.designed
        Layout.fillWidth: true
        Layout.preferredHeight: 240
        radius: 8
        color: dialog.c.field
        border.width: sig.area.activeFocus ? 2 : 1
        border.color: sig.area.activeFocus ? dialog.c.action : dialog.c.line
        RichEditor {
            id: sig
            anchors.fill: parent
            anchors.margins: 2
            padding: 12
            fontSize: 14
            keepDesigned: true
            onDesignedPasted: html => dialog.pasted = html
        }
    }

    footer: [
        Item { Layout.fillWidth: true },
        OButton { text: plume.t.cancel; onClicked: dialog.close() },
        OButton {
            kind: "primary"; text: plume.t.save
            enabled: !dialog.designed || dialog.pasted !== ""
            opacity: enabled ? 1 : 0.5
            onClicked: {
                const html = dialog.pasted !== "" ? dialog.pasted : sig.exported().html
                mail.saveSignature(dialog.email, html)
                dialog.saved(dialog.email, html)
                dialog.close()
            }
        }
    ]
}
