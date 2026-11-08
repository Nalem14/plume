// One event in the time grid: a tint of its calendar's colour, title then time. An invitation still
// waiting for an answer is only outlined; a declined one is faded and struck through.
import QtQuick
import QtQuick.Controls
import "../components"
import "../components/colors.js" as Colors

AbstractButton {
    id: block
    property var occ
    property bool cutTop: false        // began the day before / goes on the next day (after midnight)
    property bool cutBottom: false
    readonly property var c: theme.c
    readonly property color tone: Colors.display(occ.color, theme.dark)
    readonly property bool waiting: occ.myStatus === "NEEDS-ACTION"
    readonly property bool declined: occ.myStatus === "DECLINED"
    readonly property bool compact: height < 40

    hoverEnabled: true
    opacity: declined ? 0.55 : 1
    readonly property string label: occ.title || plume.t.untitled
    Accessible.name: label + ", " + timeText.text

    background: Rectangle {
        radius: 6
        topLeftRadius: block.cutTop ? 0 : 6; topRightRadius: block.cutTop ? 0 : 6
        bottomLeftRadius: block.cutBottom ? 0 : 6; bottomRightRadius: block.cutBottom ? 0 : 6
        color: Qt.rgba(block.tone.r, block.tone.g, block.tone.b, block.waiting ? 0.05 : (theme.dark ? 0.30 : 0.15) + (block.hovered ? 0.06 : 0))
        border.width: block.waiting ? 1.5 : 1
        border.color: Qt.rgba(block.tone.r, block.tone.g, block.tone.b, block.waiting ? 0.9 : 0.45)
        Rectangle {
            anchors.fill: parent; anchors.margins: -2; radius: 8; color: "transparent"
            border.width: 2; border.color: block.c.saffron; visible: block.visualFocus
        }
    }
    contentItem: Item {
        clip: true
        Column {
            x: 8; y: block.compact ? (block.height - height) / 2 : 5
            width: parent.width - 12
            spacing: 1
            Text {
                width: parent.width
                text: block.compact ? block.label + "  " + timeText.text : block.label
                elide: Text.ElideRight
                maximumLineCount: block.compact ? 1 : Math.max(1, Math.floor((block.height - 22) / 16))
                wrapMode: block.compact ? Text.NoWrap : Text.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                font.strikeout: block.declined
                color: block.c.text
            }
            Text {
                id: timeText
                visible: !block.compact
                text: Qt.formatTime(new Date(block.occ.start), "HH:mm") + " – " + Qt.formatTime(new Date(block.occ.end), "HH:mm")
                font.family: "JetBrains Mono"; font.pixelSize: 11
                color: block.c.muted
            }
            Text {
                visible: !block.compact && block.occ.location !== "" && block.height > 70
                width: parent.width
                text: block.occ.location
                elide: Text.ElideRight
                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                color: block.c.muted
            }
        }
        Icon {
            visible: block.occ.meet !== "" && block.height > 48 && block.width > 70
            anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 6
            name: "video"; size: 14; color: block.tone
        }
    }
}
