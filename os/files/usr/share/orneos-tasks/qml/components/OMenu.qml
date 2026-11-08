// Ornis popup menu: an overlay card (the only place with a shadow), optional heading, then OMenuItems.
import QtQuick
import QtQuick.Controls
import QtQuick.Effects

Popup {
    id: menu
    property string heading
    property string subheading
    default property alias items: list.data
    readonly property var c: theme.c

    padding: 6
    implicitWidth: 264
    margins: 8                          // always inside the window, even opened near its edge
    property int maxListHeight: 440     // longer lists (folders) scroll
    // items made by a Repeater only exist once built: link every item to this menu when it opens
    onAboutToShow: {
        for (let i = 0; i < list.children.length; ++i)
            if (list.children[i].hasOwnProperty("menu"))
                list.children[i].menu = menu
    }

    enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 120; easing.type: Easing.OutCubic } }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 100 } }

    background: Item {
        RectangularShadow {
            anchors.fill: card
            radius: card.radius
            blur: 28; offset.y: 10
            color: menu.c.shadow
        }
        Rectangle {
            id: card
            anchors.fill: parent
            radius: 10
            color: menu.c.overlay
            border.width: 1; border.color: menu.c.overlayLine
        }
    }

    contentItem: Column {
        spacing: 0
        Column {
            visible: menu.heading !== ""
            width: parent.width
            topPadding: 8; bottomPadding: 10; leftPadding: 10; rightPadding: 10
            spacing: 2
            Text {
                width: parent.width - 20
                text: menu.heading
                font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.weight: Font.DemiBold
                color: menu.c.text; elide: Text.ElideRight
            }
            Text {
                width: parent.width - 20
                text: menu.subheading
                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                color: menu.c.muted; elide: Text.ElideRight
            }
        }
        Rectangle { visible: menu.heading !== ""; width: parent.width; height: 1; color: menu.c.hairline }
        Item { visible: menu.heading !== ""; width: 1; height: 6 }
        Flickable {
            width: parent.width
            height: Math.min(list.implicitHeight, menu.maxListHeight)
            contentHeight: list.implicitHeight
            interactive: contentHeight > height
            boundsBehavior: Flickable.StopAtBounds
            clip: interactive
            ScrollBar.vertical: ScrollBar { policy: parent.interactive ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff }
            Column {
                id: list
                width: parent.width
            }
        }
    }
}
