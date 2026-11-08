// Ornis drop-down: model of {text, value, color?}; the list is an overlay card like the menus.
import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Layouts

ComboBox {
    id: box
    readonly property var c: theme.c
    textRole: "text"
    valueRole: "value"
    implicitHeight: 38
    font.family: "Schibsted Grotesk"
    font.pixelSize: 15

    function select(value) {
        for (let i = 0; i < count; ++i)
            if (model[i] && model[i].value === value) { currentIndex = i; return }
    }

    background: Rectangle {
        radius: 6
        color: box.c.field
        border.width: box.visualFocus || box.popup.visible ? 2 : 1
        border.color: box.visualFocus || box.popup.visible ? box.c.action : (box.hovered ? box.c.accentLine : box.c.line)
    }
    contentItem: RowLayout {
        spacing: 10
        Rectangle {
            Layout.leftMargin: 12
            visible: !!(box.model[box.currentIndex] && box.model[box.currentIndex].color)
            implicitWidth: 12; implicitHeight: 12; radius: 3
            color: visible ? box.model[box.currentIndex].color : "transparent"
        }
        Text {
            Layout.fillWidth: true
            Layout.leftMargin: box.model[box.currentIndex] && box.model[box.currentIndex].color ? 0 : 12
            text: box.displayText
            font: box.font
            color: box.c.text
            elide: Text.ElideRight
            verticalAlignment: Text.AlignVCenter
        }
    }
    indicator: Icon {
        x: box.width - width - 10; anchors.verticalCenter: parent.verticalCenter
        name: "chevronDown"; size: 16; color: box.c.muted
    }
    delegate: ItemDelegate {
        id: option
        required property var modelData
        required property int index
        width: ListView.view ? ListView.view.width : box.width
        height: 36
        highlighted: box.highlightedIndex === index
        background: Rectangle { radius: 6; color: option.highlighted ? box.c.hover : "transparent" }
        contentItem: RowLayout {
            spacing: 10
            Rectangle {
                visible: !!option.modelData.color
                implicitWidth: 12; implicitHeight: 12; radius: 3
                color: option.modelData.color || "transparent"
            }
            Text {
                Layout.fillWidth: true
                text: option.modelData.text
                font.family: "Schibsted Grotesk"; font.pixelSize: 14
                font.weight: box.currentIndex === option.index ? Font.DemiBold : Font.Normal
                color: box.c.text
                elide: Text.ElideRight
            }
            Icon { visible: box.currentIndex === option.index; name: "check"; size: 16; color: box.c.accent }
        }
    }
    popup: Popup {
        y: box.height + 4
        width: Math.max(box.width, 200)
        implicitHeight: Math.min(contentItem.implicitHeight + 12, 320)
        padding: 6
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: box.popup.visible ? box.delegateModel : null
            currentIndex: box.highlightedIndex
        }
        background: Item {
            RectangularShadow { anchors.fill: card; radius: 10; blur: 24; offset.y: 8; color: box.c.shadow }
            Rectangle { id: card; anchors.fill: parent; radius: 10; color: box.c.overlay; border.width: 1; border.color: box.c.overlayLine }
        }
    }
}
