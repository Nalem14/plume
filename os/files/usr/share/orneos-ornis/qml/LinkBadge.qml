// A badge above the text of the composer (Work and Code): what « @ » linked (a file, a folder) or « / » chose
// (a skill, an MCP server). A click on × takes it away; it goes with the message.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Rectangle {
    id: badge
    property string label
    property string iconName: "note"
    property string tip
    property bool action: false            // « / » (tinted) rather than « @ »
    signal removeRequested()
    readonly property var c: theme.c
    height: 28
    width: Math.min(lbl.implicitWidth + 61, 300)
    radius: 14
    color: action ? c.tint : c.card
    border.width: 1
    border.color: action ? c.accentLine : c.line
    Accessible.role: Accessible.StaticText
    Accessible.name: label
    HoverHandler { id: hover }
    ToolTip.visible: hover.hovered && tip !== ""
    ToolTip.delay: 500
    ToolTip.text: tip
    RowLayout {
        id: row
        anchors.verticalCenter: parent.verticalCenter
        x: 8
        width: badge.width - 16
        spacing: 6
        Icon { name: badge.iconName; size: 13; color: badge.action ? badge.c.tintText : badge.c.muted }
        Text {
            id: lbl
            Layout.fillWidth: true
            text: badge.label
            elide: Text.ElideMiddle
            font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.Medium
            color: badge.action ? badge.c.tintText : badge.c.text
        }
        AbstractButton {
            implicitWidth: 16; implicitHeight: 16
            onClicked: badge.removeRequested()
            Accessible.name: app.t.delete
            contentItem: Icon { name: "close"; size: 11; color: badge.c.muted }
        }
    }
}
