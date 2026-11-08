// Ornis text field: 6 px corners, hairline border, Klein when focused, an optional leading icon.
// A search field (or clearable: true) gets a cross that empties it; Escape does the same.
import QtQuick
import QtQuick.Controls

TextField {
    id: field
    property string iconName
    property bool plain: false          // borderless, for titles inside a card
    property bool clearable: iconName === "search"
    readonly property bool showClear: clearable && text !== "" && enabled
    signal cleared()
    readonly property var c: theme.c

    implicitHeight: plain ? 44 : 38
    leftPadding: iconName === "ornis" ? 44 : iconName ? 38 : (plain ? 0 : 12)
    rightPadding: showClear ? 36 : (plain ? 0 : 12)
    color: c.text
    placeholderTextColor: c.muted
    selectionColor: c.tint
    selectedTextColor: c.text
    selectByMouse: true
    font.family: "Schibsted Grotesk"
    font.pixelSize: 15

    function clear() {
        text = ""
        cleared()
    }
    Keys.onEscapePressed: event => {
        if (showClear) { clear(); event.accepted = true }
        else event.accepted = false
    }

    AbstractButton {
        id: clearButton
        visible: field.showClear
        anchors.right: parent.right; anchors.rightMargin: 6
        anchors.verticalCenter: parent.verticalCenter
        width: 26; height: 26
        hoverEnabled: true
        focusPolicy: Qt.NoFocus
        Accessible.name: app.t.clear_field
        ToolTip.text: app.t.clear_field
        ToolTip.delay: 450
        ToolTip.visible: hovered
        onClicked: { field.clear(); field.forceActiveFocus() }
        background: Rectangle { radius: 13; color: clearButton.hovered ? field.c.hover : "transparent" }
        contentItem: Item { Icon { anchors.centerIn: parent; name: "close"; size: 13; color: field.c.muted } }
    }

    background: Rectangle {
        radius: 6
        color: field.plain ? "transparent" : field.c.field
        border.width: field.plain ? 0 : (field.activeFocus ? 2 : 1)
        border.color: field.activeFocus ? field.c.action : field.c.line
        Icon {
            visible: field.iconName !== ""
            x: field.iconName === "ornis" ? 8 : 12; anchors.verticalCenter: parent.verticalCenter
            name: field.iconName; size: field.iconName === "ornis" ? 24 : 18; hovered: field.activeFocus  // the mascot listens while you type
            color: field.iconName === "ornis" ? field.c.accent : field.c.muted
        }
        Rectangle {
            visible: field.plain
            anchors.bottom: parent.bottom; width: parent.width; height: field.activeFocus ? 2 : 1
            color: field.activeFocus ? field.c.action : field.c.line
        }
    }
}
