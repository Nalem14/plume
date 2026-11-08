// The foot of every app's side column, always in the same place: the account (its menu opens upward) and
// the settings (also Ctrl+,). No app keeps its settings elsewhere: docs/REFONTE-ORNIS.md › Réglages.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: bar
    readonly property var c: theme.c
    property string name
    property string email
    property string initials
    property string settingsText: app.t.settings
    property string dot                  // a colour: our status on the picture (Meet), none when empty
    property string detail               // under the name instead of the address (a status message)
    signal settingsRequested()
    default property alias menuItems: menu.items
    // A temporary offer of Orneos (Plume sets `promo`, plume_core/promo.py): one thin line above the account,
    // never a window; « × » hides it everywhere. The other apps have no `promo`: nothing changes for them.
    readonly property var offer: typeof promo !== "undefined" && promo ? promo.offer : null

    implicitHeight: 56 + (offerLine.visible ? offerLine.height + 8 : 0)
    Rectangle { anchors.top: parent.top; width: parent.width; height: 1; color: bar.c.hairline }

    Rectangle {
        id: offerLine
        visible: bar.offer !== null && bar.offer !== undefined
        anchors.top: parent.top; anchors.topMargin: 8
        anchors.left: parent.left; anchors.right: parent.right
        height: 34
        radius: 8
        color: offerButton.hovered ? bar.c.hover : "transparent"
        border.width: offerButton.visualFocus ? 2 : 1
        border.color: offerButton.visualFocus ? bar.c.saffron : bar.c.hairline
        AbstractButton {
            id: offerButton
            anchors.left: parent.left; anchors.right: offerClose.left
            anchors.top: parent.top; anchors.bottom: parent.bottom
            hoverEnabled: true
            focusPolicy: Qt.StrongFocus
            Accessible.name: bar.offer ? bar.offer.text : ""
            onClicked: promo.open()
            ToolTip.text: bar.offer ? bar.offer.text : ""
            ToolTip.delay: 450
            ToolTip.visible: hovered && ToolTip.text !== ""
            contentItem: RowLayout {
                spacing: 8
                Icon { Layout.leftMargin: 10; name: "gift"; size: 16; color: bar.c.saffron }
                Text {
                    Layout.fillWidth: true
                    text: bar.offer ? bar.offer.headline : ""
                    font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold
                    color: bar.c.text
                    elide: Text.ElideRight
                }
            }
            background: null
        }
        OButton {
            id: offerClose
            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
            kind: "quiet"
            implicitWidth: 28; implicitHeight: 28
            iconName: "close"
            tip: bar.offer && bar.offer.hide ? bar.offer.hide : "×"
            onClicked: promo.dismiss()
        }
    }

    RowLayout {
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        height: 55
        spacing: 4
        AbstractButton {
            id: who
            Layout.fillWidth: true
            implicitHeight: 42
            hoverEnabled: true
            focusPolicy: Qt.StrongFocus
            Accessible.name: bar.name || bar.email
            onClicked: menu.opened ? menu.close() : menu.open()
            background: Rectangle {
                radius: 8
                color: who.hovered || menu.opened ? bar.c.hover : "transparent"
                border.width: who.visualFocus ? 2 : 0; border.color: bar.c.saffron
            }
            contentItem: RowLayout {
                spacing: 10
                Rectangle {
                    Layout.leftMargin: 6
                    implicitWidth: 30; implicitHeight: 30; radius: 15
                    color: bar.c.text
                    Text {
                        anchors.centerIn: parent
                        text: bar.initials
                        font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold
                        color: bar.c.chrome
                    }
                    Rectangle {
                        visible: bar.dot !== ""
                        anchors.right: parent.right; anchors.bottom: parent.bottom
                        anchors.rightMargin: -2; anchors.bottomMargin: -2
                        width: 12; height: 12; radius: 6
                        color: bar.dot || "transparent"
                        border.width: 2; border.color: bar.c.chrome
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Text {
                        Layout.fillWidth: true
                        text: bar.name || bar.email
                        font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
                        color: bar.c.text
                        elide: Text.ElideRight
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: bar.name !== "" && (bar.detail || bar.email) !== ""
                        text: bar.detail || bar.email
                        font.family: "Schibsted Grotesk"; font.pixelSize: 12
                        color: bar.c.muted
                        elide: Text.ElideRight
                    }
                }
            }
            OMenu {
                id: menu
                y: -height - 8
                x: 0
                implicitWidth: 300
                heading: bar.name
                subheading: bar.email
            }
        }
        OButton {
            kind: "quiet"
            implicitWidth: 34
            iconName: "settings"
            tip: bar.settingsText + "  (Ctrl+,)"
            onClicked: bar.settingsRequested()
        }
    }
}
