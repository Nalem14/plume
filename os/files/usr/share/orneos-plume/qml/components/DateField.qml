// A date shown in words; a click opens the month to pick another.
import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import "dates.js" as D

AbstractButton {
    id: field
    property date value: new Date()
    readonly property var c: theme.c
    implicitHeight: 38
    implicitWidth: 170
    hoverEnabled: true
    Accessible.name: label.text
    onClicked: picker.open()

    background: Rectangle {
        radius: 6
        color: field.c.field
        border.width: picker.visible || field.visualFocus ? 2 : 1
        border.color: picker.visible || field.visualFocus ? field.c.action : field.hovered ? field.c.accentLine : field.c.line
    }
    contentItem: Text {
        id: label
        leftPadding: 12; rightPadding: 12
        text: D.capitalize(Qt.locale(plume.locale).toString(field.value, "ddd d MMM yyyy"))
        font.family: "Schibsted Grotesk"; font.pixelSize: 15
        color: field.c.text
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    Popup {
        id: picker
        y: field.height + 4
        width: 260
        padding: 12
        background: Item {
            RectangularShadow { anchors.fill: card; radius: 10; blur: 24; offset.y: 8; color: field.c.shadow }
            Rectangle { id: card; anchors.fill: parent; radius: 10; color: field.c.overlay; border.width: 1; border.color: field.c.overlayLine }
        }
        contentItem: MiniMonth {
            selected: field.value
            weekBand: false
            onPicked: day => {
                field.value = new Date(day.getFullYear(), day.getMonth(), day.getDate(), field.value.getHours(), field.value.getMinutes())
                picker.close()
            }
        }
    }
}
