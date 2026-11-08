// Ornis modal card: title, content, then the footer buttons (right-aligned, primary last). With a tint (the
// app's family), a short band fades along its top edge, as on the cards of the app.
import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Layouts

Popup {
    id: dialog
    property string title
    property color tint: "transparent"
    default property alias content: body.data
    property alias footer: footerRow.data
    readonly property var c: theme.c

    parent: Overlay.overlay
    anchors.centerIn: parent
    modal: true
    focus: true
    padding: 0
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    width: Math.min(560, parent ? parent.width - 48 : 560)
    height: Math.min(implicitHeight, parent ? parent.height - 48 : implicitHeight)

    Overlay.modal: Rectangle { color: dialog.c.scrim }
    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 140; easing.type: Easing.OutCubic }
            NumberAnimation { property: "scale"; from: 0.98; to: 1; duration: 140; easing.type: Easing.OutCubic }
        }
    }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 100 } }

    background: Item {
        RectangularShadow { anchors.fill: card; radius: card.radius; blur: 40; offset.y: 16; color: dialog.c.shadow }
        Rectangle { id: card; anchors.fill: parent; radius: 12; color: dialog.c.overlay; border.width: 1; border.color: dialog.c.overlayLine }
        Rectangle {
            visible: dialog.tint.a > 0
            x: 18; width: Math.min(card.width - 36, 240); height: 3; radius: 1.5
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: dialog.tint }
                GradientStop { position: 1; color: Qt.alpha(dialog.tint, 0) }
            }
        }
    }

    contentItem: ColumnLayout {
        spacing: 0
        Text { textFormat: Text.PlainText;
            visible: dialog.title !== ""
            Layout.fillWidth: true
            Layout.margins: 22; Layout.bottomMargin: 6
            text: dialog.title
            font.family: "Schibsted Grotesk"; font.pixelSize: 18; font.weight: Font.DemiBold
            color: dialog.c.text
            wrapMode: Text.WordWrap
        }
        ScrollView {
            id: scroller
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredHeight: body.implicitHeight + 32
            contentWidth: availableWidth
            // the margins too: without them, scrolled to the end, the last line stays cut under the edge
            contentHeight: body.implicitHeight + 32
            clip: true
            // a long dialog shows that it scrolls
            ScrollBar.vertical.policy: body.implicitHeight + 32 > scroller.height + 1 ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
            ColumnLayout {
                id: body
                width: scroller.availableWidth - 44
                x: 22; y: 12
                spacing: 12
            }
        }
        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: dialog.c.hairline; visible: footerRow.children.length > 0 }
        RowLayout {
            id: footerRow
            visible: children.length > 0
            Layout.fillWidth: true
            Layout.margins: 14; Layout.leftMargin: 22; Layout.rightMargin: 16
            spacing: 8
        }
    }
}
