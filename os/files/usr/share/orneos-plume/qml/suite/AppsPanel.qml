// The other apps of Orneos, as in the cloud's rail and on Search: one tile per app (its family's colour), by
// group. First the modules of Plume opened from here (the Photothèque: native, offline, in this window); then the
// apps of the cloud, each with a small cloud on its tile: they open in the browser, signed in. The apps Plume shows
// in its rail are not repeated.
import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Layouts
import "../components"

Popup {
    id: panel
    readonly property var c: theme.c

    parent: Overlay.overlay
    x: 88
    y: Math.max(12, parent.height - height - 12)
    width: Math.min(560, parent.width - 100)
    height: Math.min(list.contentHeight + 76, parent.height - 24)
    padding: 0
    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    Overlay.modal: Rectangle { color: "transparent" }
    enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 120; easing.type: Easing.OutCubic } }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 90 } }

    background: Item {
        RectangularShadow { anchors.fill: card; radius: card.radius; blur: 40; offset.y: 16; color: panel.c.shadow }
        Rectangle { id: card; anchors.fill: parent; radius: 10; color: panel.c.overlay; border.width: 1; border.color: panel.c.overlayLine }
    }

    contentItem: ColumnLayout {
        spacing: 0
        Text {
            Layout.fillWidth: true
            Layout.margins: 20; Layout.bottomMargin: 2
            text: plume.t.apps
            font.family: "Schibsted Grotesk"; font.pixelSize: 17; font.weight: Font.DemiBold
            color: panel.c.text
        }
        Text {
            Layout.fillWidth: true
            Layout.leftMargin: 20; Layout.rightMargin: 20
            text: plume.t.apps_more
            font.family: "Schibsted Grotesk"; font.pixelSize: 13
            color: panel.c.muted
            wrapMode: Text.WordWrap
        }
        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.topMargin: 8
            clip: true
            model: suite.apps
            boundsBehavior: Flickable.StopAtBounds
            header: Column {
                width: ListView.view.width
                topPadding: 6
                spacing: 4
                visible: suite.grid.length > 0
                height: visible ? implicitHeight : 0
                Heading_ { text: plume.t.apps_native; lead: plume.t.apps_native_lead; glyph: "plume" }
                Flow {
                    x: 12
                    width: parent.width - 24
                    bottomPadding: 10
                    Repeater {
                        model: suite.grid
                        delegate: Tile {
                            required property var modelData
                            name: modelData.name
                            picture: modelData.icon
                            here: plume.module === modelData.key
                            tip: here ? plume.t.apps_open_here : ""
                            onClicked: { plume.setModule(modelData.key); panel.close() }
                        }
                    }
                }
            }
            ScrollBar.vertical: ScrollBar {}
            delegate: Column {
                required property var modelData
                width: ListView.view.width
                spacing: 4
                Text {
                    x: 20
                    text: modelData.name
                    font.family: "Schibsted Grotesk"; font.pixelSize: 11; font.weight: Font.DemiBold
                    font.letterSpacing: 0.6; font.capitalization: Font.AllUppercase
                    color: panel.c.faint
                }
                Flow {
                    x: 12
                    width: parent.width - 24
                    bottomPadding: 10
                    Repeater {
                        model: modelData.apps
                        delegate: Tile {
                            required property var modelData
                            name: modelData.name
                            picture: modelData.icon
                            cloud: true
                            tip: plume.t.apps_cloud_hint
                            onClicked: { plume.openCloud(modelData.url); panel.close() }
                        }
                    }
                }
            }
        }
    }

    // a section of the grid: its name and what it means (here, offline / in the browser)
    component Heading_: RowLayout {
        property string text
        property string lead
        property string glyph
        x: 20
        width: parent ? parent.width - 40 : 0
        height: 18
        spacing: 8
        Icon { name: parent.glyph; size: 14; color: panel.c.faint }
        Text {
            text: parent.text
            font.family: "Schibsted Grotesk"; font.pixelSize: 11; font.weight: Font.DemiBold
            font.letterSpacing: 0.6; font.capitalization: Font.AllUppercase
            color: panel.c.faint
        }
        Text {
            Layout.fillWidth: true
            text: "· " + parent.lead
            elide: Text.ElideRight
            font.family: "Schibsted Grotesk"; font.pixelSize: 11
            color: panel.c.faint
        }
    }
    // one app: its tile (the family's colour), its name; a cloud app wears a small cloud, the one open here a dot
    component Tile: AbstractButton {
        id: tile
        property string name
        property string picture
        property bool cloud: false
        property bool here: false
        property string tip
        width: 104; height: 84
        hoverEnabled: true
        focusPolicy: Qt.StrongFocus
        Accessible.name: name
        Accessible.description: tip
        ToolTip.visible: hovered && tip !== ""
        ToolTip.delay: 700
        ToolTip.text: tip
        background: Rectangle {
            radius: 8
            color: tile.here ? panel.c.card : tile.hovered ? panel.c.hover : "transparent"
            border.width: tile.visualFocus ? 2 : tile.here ? 1 : 0
            border.color: tile.visualFocus ? panel.c.saffron : panel.c.hairline
        }
        contentItem: Column {
            spacing: 6
            topPadding: 8
            Item {
                anchors.horizontalCenter: parent.horizontalCenter
                width: 40; height: 40
                Image {
                    anchors.fill: parent
                    source: tile.picture
                    sourceSize: Qt.size(40, 40)
                }
                // the cloud: opens in the browser
                Rectangle {
                    visible: tile.cloud
                    anchors.right: parent.right; anchors.bottom: parent.bottom
                    anchors.rightMargin: -5; anchors.bottomMargin: -4
                    width: 18; height: 18; radius: 9
                    color: panel.c.overlay
                    border.width: 1; border.color: panel.c.hairline
                    Icon { anchors.centerIn: parent; name: "cloud"; size: 11; color: panel.c.muted }
                }
                // open in this window
                Rectangle {
                    visible: tile.here
                    anchors.right: parent.right; anchors.bottom: parent.bottom
                    anchors.rightMargin: -3; anchors.bottomMargin: -3
                    width: 12; height: 12; radius: 6
                    color: panel.c.saffron
                    border.width: 2; border.color: panel.c.overlay
                }
            }
            Text {
                width: tile.width - 8
                anchors.horizontalCenter: parent.horizontalCenter
                text: tile.name
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                font.weight: tile.here ? Font.DemiBold : Font.Normal
                color: panel.c.text
            }
        }
    }
}
