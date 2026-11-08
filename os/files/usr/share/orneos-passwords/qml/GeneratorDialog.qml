// A password for anywhere (a Wi-Fi box, a form in another app): the style, the length, copy. Made here.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    title: app.t.generator
    width: Math.min(560, parent ? parent.width - 48 : 560)
    property string style: "strong"
    property string value: ""
    signal saveAs(string password)

    function make() { value = vault.generate(style, style === "words" ? words.value : length.value, symbols.checked) }
    onAboutToShow: make()

    Rectangle {
        Layout.fillWidth: true
        implicitHeight: shown.implicitHeight + 32
        radius: 8
        color: theme.c.bg
        border.width: 1; border.color: theme.c.line
        Text {
            id: shown
            anchors.left: parent.left; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
            anchors.margins: 16
            text: dialog.value
            wrapMode: Text.WrapAnywhere
            horizontalAlignment: Text.AlignHCenter
            font.family: "JetBrains Mono"; font.pixelSize: 19
            color: theme.c.text
        }
    }
    StrengthMeter { Layout.alignment: Qt.AlignHCenter; score: vault.strength(dialog.value, "", "") }

    OComboBox {
        Layout.fillWidth: true
        model: [{ text: app.t.style_strong, value: "strong" }, { text: app.t.style_random_short, value: "random" },
                { text: app.t.style_words, value: "words" }]
        Component.onCompleted: select("strong")
        onActivated: { dialog.style = currentValue; dialog.make() }
    }
    RowLayout {
        visible: dialog.style === "random"
        spacing: 12
        Text { text: app.t.length; font.family: "Schibsted Grotesk"; font.pixelSize: 14; color: theme.c.muted }
        Slider {
            id: length
            Layout.fillWidth: true
            from: 12; to: 64; stepSize: 1; value: 24
            onMoved: dialog.make()
        }
        Text { text: length.value; font.family: "JetBrains Mono"; font.pixelSize: 14; color: theme.c.text }
    }
    OSwitch {
        id: symbols
        visible: dialog.style === "random"
        checked: true
        text: app.t.symbols
        onToggled: dialog.make()
    }
    RowLayout {
        visible: dialog.style === "words"
        spacing: 12
        Text { text: app.t.words; font.family: "Schibsted Grotesk"; font.pixelSize: 14; color: theme.c.muted }
        Slider {
            id: words
            Layout.fillWidth: true
            from: 4; to: 8; stepSize: 1; value: 5
            onMoved: dialog.make()
        }
        Text { text: words.value; font.family: "JetBrains Mono"; font.pixelSize: 14; color: theme.c.text }
    }
    Text {
        Layout.fillWidth: true
        text: app.t["style_" + dialog.style + "_hint"]
        wrapMode: Text.WordWrap
        lineHeight: 1.25
        font.family: "Schibsted Grotesk"; font.pixelSize: 13
        color: theme.c.muted
    }

    footer: [
        OButton { kind: "quiet"; iconName: "refresh"; text: app.t.another; onClicked: dialog.make() },
        Item { Layout.fillWidth: true },
        OButton { iconName: "plus"; text: app.t.save_as_entry; onClicked: { dialog.close(); dialog.saveAs(dialog.value) } },
        OButton { kind: "primary"; iconName: "copy"; text: app.t.copy; onClicked: { app.copy(dialog.value, "password"); dialog.close() } }
    ]
}
