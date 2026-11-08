// A smart list as a card (Aujourd'hui, Programmées…): a line glyph in the list's colour, the count in the data
// face, the name; the family band on its side. The chosen card takes its colour, and may carry its own ring.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

AbstractButton {
    id: card
    readonly property var c: theme.c
    property color tint: c.action
    property string iconName
    property string count
    property bool selected
    // instead of the glyph: a ring ([{from, to, color}] as Ring.qml), when the list measures something
    property var segments: null

    implicitHeight: 70
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    Accessible.name: text + (count !== "" ? ", " + count : "")

    background: Surface {
        raised: !card.selected
        color: card.hovered && !card.selected ? Qt.tint(card.c.card, Qt.alpha(card.c.text, 0.03)) : card.c.card
        radius: 10
        gradient: card.selected ? selectedFill : null
        Gradient {
            id: selectedFill
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: Qt.tint(card.c.card, Qt.alpha(card.tint, theme.dark ? 0.14 : 0.08)) }
            GradientStop { position: 1; color: Qt.tint(card.c.card, Qt.alpha(card.tint, theme.dark ? 0.26 : 0.18)) }
        }
        Rectangle {
            width: 3; radius: 1.5
            anchors { left: parent.left; top: parent.top; bottom: parent.bottom; topMargin: 8; bottomMargin: 8 }
            color: card.tint
        }
        Rectangle {
            anchors.fill: parent
            radius: 10; color: "transparent"
            border.width: card.selected ? 1.5 : 0
            border.color: Qt.alpha(card.tint, 0.55)
        }
        Rectangle {
            anchors.fill: parent; anchors.margins: -3
            radius: 13; color: "transparent"
            border.width: 2; border.color: card.c.saffron
            visible: card.visualFocus
        }
    }
    contentItem: ColumnLayout {
        spacing: 6
        RowLayout {
            Layout.leftMargin: 6
            Item {
                implicitWidth: 24; implicitHeight: 24
                Icon { visible: card.segments === null; anchors.centerIn: parent; name: card.iconName; size: 20; color: card.tint; hovered: card.hovered }
                Ring {
                    visible: card.segments !== null
                    anchors.fill: parent
                    segments: card.segments || []
                    separated: true
                    drawTrack: false
                    lineWidth: 3.2
                }
            }
            Item { Layout.fillWidth: true }
            Text {
                text: card.count
                font.family: "JetBrains Mono"; font.pixelSize: 22; font.weight: Font.Medium
                font.letterSpacing: -0.6
                color: card.c.text
            }
        }
        Text { textFormat: Text.PlainText;
            Layout.leftMargin: 6
            Layout.fillWidth: true
            text: card.text
            font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
            color: card.c.text
            elide: Text.ElideRight
        }
    }
    leftPadding: 10; rightPadding: 12; topPadding: 10; bottomPadding: 9
}
