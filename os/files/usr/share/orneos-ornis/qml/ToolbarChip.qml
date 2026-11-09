// One chip of the message box's toolbar, the same in Chat and Code: the mode on the left (Agent, Plan, Ask…), what Ornis
// may do on its own on the right (its permissions). One colour logic everywhere:
//   plain   — the default (Agent; asks before acting): no fill, the icon in the accent or muted
//   tint    — a chosen variant (Ask, Objectif, Recherche; edits without asking): Klein tint
//   saffron — read only or acting alone (Plan; Autonome): saffron, the strongest signal
import QtQuick
import QtQuick.Controls
import "components"

AbstractButton {
    id: chip
    property string iconName: ""
    property string label: ""
    property string detail: ""            // « · Lecture seule » after the label, when there is room
    property string tone: "plain"         // plain | tint | saffron
    property bool showLabel: true
    property bool chevron: true
    property bool mascot: false           // the AI stars of Agent: the mascot shows on hover (ORNIS-MASCOT.md)
    property bool menuOpen: false
    property string tip: ""
    readonly property var c: theme.c
    readonly property color ink: tone === "saffron" ? c.saffronInk : tone === "tint" ? c.tintText : c.text
    implicitWidth: row.implicitWidth + (showLabel ? 18 : 14); implicitHeight: 28
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    Accessible.role: Accessible.ButtonMenu
    Accessible.name: label + (detail ? " " + detail : "")
    Accessible.description: tip
    ToolTip.text: tip; ToolTip.delay: 500; ToolTip.visible: hovered && tip !== ""
    opacity: enabled ? 1 : 0.6
    background: Rectangle {
        radius: 14
        color: chip.tone === "saffron" ? chip.c.saffronTint : chip.tone === "tint" ? chip.c.tint
               : chip.hovered || chip.menuOpen ? chip.c.hover : "transparent"
        border.width: chip.visualFocus ? 2 : chip.tone === "plain" ? 0 : 1
        border.color: chip.visualFocus || chip.tone === "saffron" ? chip.c.saffron : chip.c.accentLine
        Behavior on color { ColorAnimation { duration: 140 } }
    }
    contentItem: Item {
        Row {
            id: row
            anchors.centerIn: parent
            spacing: 5
            Icon {
                anchors.verticalCenter: parent.verticalCenter
                name: chip.iconName; size: 14
                hovered: chip.mascot && chip.hovered
                color: chip.tone === "plain" ? (chip.mascot ? chip.c.accent : chip.hovered ? chip.c.text : chip.c.muted) : chip.ink
            }
            Text {
                visible: chip.showLabel && chip.label !== ""
                anchors.verticalCenter: parent.verticalCenter
                text: chip.label
                font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                color: chip.tone === "plain" && !chip.mascot ? (chip.hovered ? chip.c.text : chip.c.muted) : chip.ink
            }
            Text {
                visible: chip.showLabel && chip.detail !== ""
                anchors.verticalCenter: parent.verticalCenter
                text: "· " + chip.detail
                font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.Medium
                color: chip.ink
            }
            Icon {
                visible: chip.chevron
                anchors.verticalCenter: parent.verticalCenter
                name: "chevronDown"; size: 12
                color: chip.tone === "plain" ? chip.c.muted : chip.ink
            }
        }
    }
}
