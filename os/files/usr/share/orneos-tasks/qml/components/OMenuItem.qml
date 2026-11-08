import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

AbstractButton {
    id: item
    property string iconName
    property string dot                  // a colour: a round mark instead of an icon (tags, groups)
    property bool danger                 // a destructive action, in red
    property var menu
    property bool switchable             // an option: a switch on the right, the menu stays open
    property bool on
    signal triggered()
    readonly property var c: theme.c

    width: parent ? parent.width : implicitWidth
    implicitHeight: 36
    leftPadding: 10; rightPadding: 10
    hoverEnabled: true
    Accessible.name: text
    Accessible.checkable: switchable
    Accessible.checked: on
    onClicked: {
        if (menu && !switchable)
            menu.close()
        triggered()
    }

    background: Rectangle {
        radius: 6
        color: item.hovered || item.visualFocus ? item.c.hover : "transparent"
    }
    contentItem: RowLayout {
        spacing: 10
        Icon { visible: item.iconName !== "" && item.dot === ""; name: item.iconName; hovered: item.hovered || item.visualFocus; size: 18; color: item.danger ? item.c.danger : item.c.muted }
        Item {
            visible: item.dot !== ""
            implicitWidth: 18; implicitHeight: 18
            Rectangle { anchors.centerIn: parent; width: 10; height: 10; radius: 5; color: item.dot || "transparent" }
        }
        Text { textFormat: Text.PlainText;
            Layout.fillWidth: true
            text: item.text
            font.family: "Schibsted Grotesk"; font.pixelSize: 14
            color: item.danger ? item.c.danger : item.c.text
            elide: Text.ElideRight
        }
        Rectangle {
            visible: item.switchable
            implicitWidth: 30; implicitHeight: 17; radius: 8.5
            color: item.on ? item.c.action : item.c.line
            Rectangle {
                x: item.on ? parent.width - width - 2.5 : 2.5; anchors.verticalCenter: parent.verticalCenter
                width: 12; height: 12; radius: 6
                color: item.on ? item.c.actionText : item.c.card
                Behavior on x { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
            }
        }
    }
}
