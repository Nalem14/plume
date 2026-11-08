// Getting a site's setup code: the QR it shows on screen (read from a picture of the screen, like macOS),
// an image or a link in the clipboard, or the setup key typed in.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ColumnLayout {
    id: capture
    readonly property var c: theme.c
    property string message
    property bool scanning: false
    property bool asked: false          // several captures may exist: only the one clicked takes the answer
    signal captured(string uri)
    spacing: 10

    function tryKey(text) {
        const found = vault.codeFor(text.trim())
        if (found.uri) {
            message = ""
            capture.captured(found.uri)
            return true
        }
        return false
    }

    Connections {
        target: scanner
        function onFound(how, text) {
            if (!capture.asked)
                return
            capture.asked = false
            capture.scanning = false
            if (text && capture.tryKey(text))
                return
            capture.message = how === "screen" ? app.t.otp_none_screen : app.t.otp_none_clipboard
        }
    }

    Text {
        Layout.fillWidth: true
        text: app.t.otp_how
        wrapMode: Text.WordWrap
        lineHeight: 1.25
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: capture.c.muted
    }
    RowLayout {
        spacing: 8
        OButton {
            visible: scanner.canScreen()
            kind: "primary"; iconName: "scan"
            text: app.t.otp_scan
            enabled: !capture.scanning
            onClicked: { capture.message = ""; capture.asked = true; capture.scanning = true; scanner.screen() }
        }
        OButton {
            iconName: "copy"
            text: app.t.otp_paste
            onClicked: { capture.message = ""; capture.asked = true; scanner.clipboard() }
        }
        OrnisThinking { visible: capture.scanning; text: app.t.otp_scanning }
    }
    OTextField {
        id: key
        Layout.fillWidth: true
        iconName: "key"
        placeholderText: app.t.otp_key_ph
        font.family: text ? "JetBrains Mono" : "Schibsted Grotesk"
        onTextChanged: {
            if (text.trim().length >= 16 && capture.tryKey(text))
                text = ""
        }
        onAccepted: if (!capture.tryKey(text)) capture.message = app.t.otp_bad_key
    }
    Text {
        visible: capture.message !== ""
        Layout.fillWidth: true
        text: capture.message
        wrapMode: Text.WordWrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 13
        color: capture.c.saffronInk
    }
}
