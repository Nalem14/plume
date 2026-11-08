// A notice above an entry: what is wrong (danger, saffron), a suggestion (tint) or a state (muted), with its actions.
import QtQuick
import QtQuick.Layouts
import "components"

Rectangle {
    id: banner
    readonly property var c: theme.c
    property string tone: "saffron"
    property string iconName: "warning"
    property string title
    property string text
    default property alias actions: actionRow.data

    Layout.fillWidth: true
    implicitHeight: column.implicitHeight + 28
    radius: 10
    color: tone === "danger" ? c.dangerTint : tone === "saffron" ? c.saffronTint : tone === "tint" ? c.tint : c.card
    border.width: tone === "muted" ? 1 : 0
    border.color: c.line

    RowLayout {
        anchors.fill: parent
        anchors.margins: 14
        spacing: 12
        Icon {
            Layout.alignment: Qt.AlignTop
            name: banner.iconName; size: 22
            color: banner.tone === "danger" ? banner.c.danger : banner.tone === "saffron" ? banner.c.saffronInk
                 : banner.tone === "tint" ? banner.c.tintText : banner.c.muted
        }
        ColumnLayout {
            id: column
            Layout.fillWidth: true
            spacing: 4
            Text {
                Layout.fillWidth: true
                text: banner.title
                wrapMode: Text.WordWrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.weight: Font.DemiBold
                color: banner.c.text
            }
            Text {
                Layout.fillWidth: true
                visible: text !== ""
                text: banner.text
                wrapMode: Text.WordWrap
                lineHeight: 1.25
                font.family: "Schibsted Grotesk"; font.pixelSize: 14
                color: banner.c.muted
            }
            Flow {
                id: actionRow
                Layout.fillWidth: true
                Layout.topMargin: 6
                visible: visibleChildren.length > 0
                spacing: 8
            }
        }
    }
}
