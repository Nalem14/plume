// One line of an entry: a small label, the value, and what can be done with it. A click copies the value
// (that is what one comes for); secrets stay as dots until the eye or a hover of half a second.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

AbstractButton {
    id: field
    readonly property var c: theme.c
    property string label
    property string value
    property string copyAs: "username"         // what app.copy says it copied ("password", "code"… are secrets)
    property bool secret: false
    property bool mono: false
    property bool revealed: false
    property bool multiline: false
    property bool link: false                  // the value opens in the browser (the copy is on its own button)
    property bool last: false
    default property alias trailing: extra.data
    readonly property bool showing: !secret || revealed || peekShown

    property bool peekShown: false
    signal opened()

    Layout.fillWidth: true
    implicitHeight: Math.max(60, column.implicitHeight + 22)
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    Accessible.name: label
    onClicked: link ? field.opened() : app.copy(value, copyAs)
    onHoveredChanged: {
        if (hovered && secret) peek.restart()
        else { peek.stop(); peekShown = false }
    }
    Timer { id: peek; interval: 550; onTriggered: field.peekShown = true }

    background: Rectangle {
        color: field.hovered ? field.c.hover : "transparent"
        Rectangle { visible: !field.last; anchors.bottom: parent.bottom; x: 16; width: parent.width - 32; height: 1; color: field.c.hairline }
        Rectangle {
            anchors.fill: parent; anchors.margins: 2; radius: 6; color: "transparent"
            border.width: 2; border.color: field.c.saffron; visible: field.visualFocus
        }
    }

    contentItem: RowLayout {
        spacing: 10
        ColumnLayout {
            id: column
            Layout.fillWidth: true
            Layout.leftMargin: 16
            spacing: 3
            Text {
                text: field.label
                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                color: field.c.muted
            }
            Text {
                Layout.fillWidth: true
                text: field.showing ? field.value : "•".repeat(Math.min(16, Math.max(8, field.value.length)))
                wrapMode: field.multiline ? Text.Wrap : Text.NoWrap
                elide: field.multiline ? Text.ElideNone : Text.ElideRight
                textFormat: Text.PlainText
                font.family: field.mono && field.showing ? "JetBrains Mono" : "Schibsted Grotesk"
                font.pixelSize: field.mono && field.showing ? 15 : 15.5
                font.letterSpacing: field.showing ? 0 : 1.5
                color: field.link ? field.c.accent : field.c.text
            }
        }
        RowLayout {
            id: extra
            spacing: 2
        }
        OButton {
            visible: field.secret
            kind: "quiet"; implicitWidth: 32; height_: 32; iconSize: 17
            iconName: field.revealed ? "eyeOff" : "eye"
            tip: field.revealed ? app.t.hide : app.t.show
            onClicked: field.revealed = !field.revealed
        }
        OButton {
            Layout.rightMargin: 10
            kind: "quiet"; implicitWidth: 32; height_: 32; iconSize: 17
            iconName: "copy"
            tip: app.t.copy
            opacity: field.hovered || field.visualFocus || hovered ? 1 : 0.0
            onClicked: app.copy(field.value, field.copyAs)
        }
    }
}
