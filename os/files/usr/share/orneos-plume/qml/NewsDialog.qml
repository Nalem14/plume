// "Quoi de neuf": the Orneos announcements not read yet (news.py), once, like Discord's window of new features.
// The night sky of Ornis on top, one announcement per page (newest first), closing marks them read everywhere.
import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Layouts
import "components"

Popup {
    id: dialog
    readonly property var c: theme.c
    property bool ready: false          // the window is shown (Main.qml)
    readonly property var items: news.items
    property int index: 0
    property int shownGeneration: -1
    readonly property var item: items.length ? items[Math.min(index, items.length - 1)] : null

    parent: Overlay.overlay
    anchors.centerIn: parent
    modal: true
    focus: true
    padding: 0
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    width: Math.min(520, parent ? parent.width - 48 : 520)
    height: Math.min(column.implicitHeight, parent ? parent.height - 48 : column.implicitHeight)

    onClosed: news.markRead(shownGeneration)

    // shown once the window is there and nothing else is open
    Timer {
        id: later
        interval: 600
        onTriggered: {
            if (news.items.length && !dialog.opened && dialog.ready && !dialog.claiming) {
                dialog.claiming = true
                news.claim()                   // the first device today opens it (news/shown), then here
            }
        }
    }
    property bool claiming: false
    Connections {
        target: news
        function onClaimed(ok, generation) {
            dialog.claiming = false
            if (!ok) { news.drop(generation); return }
            if (generation !== news.generation || !news.items.length || dialog.opened) return
            dialog.shownGeneration = news.generation
            dialog.index = 0
            dialog.open()                      // claimed: shown even if the window lost the focus meanwhile
        }
        function onChanged() {
            if (dialog.shownGeneration !== news.generation && dialog.visible) dialog.close()
            if (news.items.length) later.restart()
        }
    }
    onReadyChanged: {
        news.setActive(ready)
        if (ready && news.items.length) later.restart()
    }
    Component.onCompleted: news.setActive(ready)

    function day(time) {
        return new Date(time * 1000).toLocaleDateString(Qt.locale(plume.locale), "dddd d MMMM")
    }

    Overlay.modal: Rectangle { color: dialog.c.scrim }
    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 180; easing.type: Easing.OutCubic }
            NumberAnimation { property: "scale"; from: 0.96; to: 1; duration: 220; easing.type: Easing.OutBack }
        }
    }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 120 } }

    background: Item {
        RectangularShadow { anchors.fill: card; radius: card.radius; blur: 48; offset.y: 18; color: dialog.c.shadow }
        Rectangle { id: card; anchors.fill: parent; radius: 14; color: dialog.c.overlay; border.width: 1; border.color: dialog.c.overlayLine }
    }

    contentItem: ColumnLayout {
        id: column
        spacing: 0

        // the night sky of Ornis: nuit → Prusse → Klein, a safran glow in the corner
        Item {
            Layout.fillWidth: true
            implicitHeight: head.implicitHeight + 44
            clip: true
            Rectangle {
                anchors.fill: parent; anchors.bottomMargin: -14     // rounded on top only
                radius: 14
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: "#0A1424" }
                    GradientStop { position: 0.55; color: "#0F2440" }
                    GradientStop { position: 1; color: "#002FA7" }
                }
            }
            Rectangle {
                anchors.right: parent.right; anchors.top: parent.top
                width: 220; height: 160; radius: 110; opacity: 0.22
                anchors.rightMargin: -80; anchors.topMargin: -90
                color: "#F0A202"
                layer.enabled: true
                layer.effect: MultiEffect { blurEnabled: true; blur: 1; blurMax: 64 }
            }
            ColumnLayout {
                id: head
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                anchors.margins: 22; anchors.topMargin: 22
                spacing: 12
                RowLayout {
                    spacing: 10
                    Rectangle {
                        implicitWidth: badge.implicitWidth + 20; implicitHeight: 22; radius: 11
                        color: "#F0A202"
                        Text {
                            id: badge; anchors.centerIn: parent; textFormat: Text.PlainText
                            text: plume.t.news_title.toUpperCase()
                            font.family: "Schibsted Grotesk"; font.pixelSize: 11; font.weight: Font.Bold; font.letterSpacing: 0.6
                            color: "#0A1424"
                        }
                    }
                    Text {
                        Layout.fillWidth: true; textFormat: Text.PlainText
                        text: dialog.item ? dialog.day(dialog.item.time) : ""
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13
                        color: Qt.rgba(1, 1, 1, 0.78)
                    }
                    ToolButton {
                        implicitWidth: 32; implicitHeight: 32
                        onClicked: dialog.close()
                        Accessible.name: plume.t.close
                        background: Rectangle { radius: 16; color: parent.hovered ? Qt.rgba(1, 1, 1, 0.24) : Qt.rgba(1, 1, 1, 0.12) }
                        contentItem: Text { text: "×"; color: "white"; font.pixelSize: 20; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    }
                }
                Text {
                    Layout.fillWidth: true; textFormat: Text.PlainText
                    text: dialog.item ? dialog.item.subject : ""
                    font.family: "Schibsted Grotesk"; font.pixelSize: 22; font.weight: Font.ExtraBold
                    color: "white"
                    wrapMode: Text.WordWrap
                }
            }
        }

        ScrollView {
            id: scroller
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredHeight: Math.min(body.implicitHeight + 36, 420)
            contentWidth: availableWidth
            contentHeight: body.implicitHeight + 36
            clip: true
            Text {
                id: body
                x: 24; y: 18
                width: scroller.availableWidth - 48
                // the announcement as HTML, rendered and escaped by the cloud (News::html: paragraphs, lists, bold, links)
                textFormat: Text.RichText
                text: dialog.item ? "<style>p, ul { margin-bottom: 10px } h4 { margin-top: 12px } a { color: " + dialog.c.accent + " }</style>" + dialog.item.html : ""
                font.family: "Schibsted Grotesk"; font.pixelSize: 15
                lineHeight: 1.18
                color: dialog.c.text
                linkColor: dialog.c.accent
                wrapMode: Text.WordWrap
                onLinkActivated: link => Qt.openUrlExternally(link)
                HoverHandler { cursorShape: body.hoveredLink ? Qt.PointingHandCursor : Qt.ArrowCursor }
            }
        }

        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: dialog.c.hairline }
        RowLayout {
            Layout.fillWidth: true
            Layout.margins: 16; Layout.leftMargin: 22
            spacing: 8
            OButton { kind: "quiet"; text: plume.t.news_all; iconName: "openExternal"; onClicked: { news.openAll(); dialog.close() } }
            Item { Layout.fillWidth: true }
            Text {
                visible: dialog.items.length > 1; textFormat: Text.PlainText
                text: plume.t.news_of.replace("%1", dialog.index + 1).replace("%2", dialog.items.length)
                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                color: dialog.c.muted
            }
            OButton { visible: dialog.index > 0; text: plume.t.news_prev; onClicked: dialog.index-- }
            OButton {
                visible: dialog.index < dialog.items.length - 1
                kind: "primary"; text: plume.t.news_next
                onClicked: dialog.index++
            }
            OButton {
                visible: dialog.index >= dialog.items.length - 1
                kind: "primary"; text: plume.t.news_ok
                onClicked: dialog.close()
            }
        }
    }

    Keys.onRightPressed: if (index < items.length - 1) index++
    Keys.onLeftPressed: if (index > 0) index--
}
