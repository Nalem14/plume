// Ornis button: "primary" (Klein), "secondary" (outlined), "accent" (Klein text, Ornis actions), "quiet",
// "danger" (a confirmation that destroys something: red, only in dialogs).
// An icon alone always says what it does (tip); danger: what cannot be undone easily turns red on hover.
import QtQuick
import QtQuick.Controls

AbstractButton {
    id: b
    property string kind: "secondary"
    property string iconName: ""
    property url image                   // a picture in colour instead of an icon (a provider's logo)
    property real iconSize: 18
    property int height_: 34
    property string tip                  // tooltip (and accessible name) of an icon-only button
    property bool danger

    readonly property var c: theme.c
    implicitHeight: height_
    implicitWidth: row.implicitWidth + (text ? 24 : 16)
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    Accessible.name: text || tip || ToolTip.text
    opacity: enabled ? 1 : 0.45          // not yet possible: seen at once (a form still to fill)

    background: Rectangle {
        radius: 6
        color: b.kind === "primary" ? (b.hovered ? b.c.actionHover : b.c.action)
             : b.kind === "danger" ? b.c.danger
             : b.kind === "quiet" ? (b.hovered ? b.c.hover : "transparent")
             : (b.hovered || b.down ? b.c.hover : b.c.card)
        border.width: b.kind === "primary" || b.kind === "quiet" || b.kind === "danger" ? 0 : 1
        opacity: b.kind === "danger" && b.hovered ? 0.88 : 1
        border.color: b.kind === "accent" ? b.c.accentLine : b.c.line
        Behavior on color { ColorAnimation { duration: 120; easing.type: Easing.OutCubic } }
        Rectangle {                      // focus ring: saffron, like the site
            anchors.fill: parent; anchors.margins: -3
            radius: 8; color: "transparent"
            border.width: 2; border.color: b.c.saffron
            visible: b.visualFocus
        }
    }

    contentItem: Item {
        implicitWidth: row.implicitWidth
        implicitHeight: row.implicitHeight
        Row {
            id: row
            anchors.centerIn: parent
            spacing: 7
            Image {
                anchors.verticalCenter: parent.verticalCenter
                visible: b.image.toString() !== ""
                source: b.image
                width: b.iconSize; height: b.iconSize
                sourceSize: Qt.size(b.iconSize * 2, b.iconSize * 2)
            }
            Icon {
                anchors.verticalCenter: parent.verticalCenter
                visible: b.iconName !== ""
                name: b.iconName
                hovered: b.hovered || b.visualFocus
                size: b.iconSize
                color: b.danger && b.hovered ? b.c.danger : label.color
            }
            Text {
                id: label
                anchors.verticalCenter: parent.verticalCenter
                visible: b.text !== ""
                text: b.text
                font.family: "Schibsted Grotesk"
                font.pixelSize: 14
                font.weight: b.kind === "primary" || b.kind === "danger" ? Font.DemiBold : Font.Medium
                color: b.kind === "primary" ? b.c.actionText
                     : b.kind === "danger" ? (theme.dark ? "#0A1424" : "#FFFFFF")
                     : b.kind === "accent" ? b.c.accent : b.c.text
            }
        }
    }

    ToolTip.text: tip
    ToolTip.delay: 450
    ToolTip.visible: hovered && ToolTip.text !== ""
}
