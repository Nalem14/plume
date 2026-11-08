// SPDX-License-Identifier: GPL-2.0-or-later
// The frame of an Orneos widget: the family band on the left, the context line (family colour) and the
// layout chosen from the size the user gives the widget (small, wide, tall). docs/REFONTE-ORNIS.md.
import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PC3
import "ornis.js" as Ornis

Item {
    id: frame
    // Family of design/tokens.json (communicate, organize, tools…), for the band and the context line.
    property string family: "communicate"
    property string context: ""
    // Ornis: the two stars before the context line.
    property bool ai: false
    // A button at the end of the context line (new message, quick note…), hidden when empty.
    property string actionIcon: ""
    property string actionText: ""
    signal action()
    signal opened()
    default property alias content: body.data

    readonly property bool dark: Kirigami.Theme.backgroundColor.hslLightness < 0.5
    readonly property color tint: Ornis.family(family, dark)
    readonly property bool wide: width >= Kirigami.Units.gridUnit * 15
    readonly property bool tall: height >= Kirigami.Units.gridUnit * 12
    readonly property bool roomy: wide || tall

    Layout.minimumWidth: Kirigami.Units.gridUnit * 8
    Layout.minimumHeight: Kirigami.Units.gridUnit * 8
    Layout.preferredWidth: Kirigami.Units.gridUnit * 19
    Layout.preferredHeight: Kirigami.Units.gridUnit * 12

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: frame.opened()
    }
    Rectangle { width: 3; radius: 1.5; anchors { left: parent.left; top: parent.top; bottom: parent.bottom } color: frame.tint }

    ColumnLayout {
        anchors { fill: parent; leftMargin: Kirigami.Units.largeSpacing }
        spacing: Kirigami.Units.smallSpacing
        RowLayout {
            Layout.fillWidth: true
            OrnisStars {
                visible: frame.ai
                color: frame.tint
                implicitWidth: Kirigami.Units.iconSizes.small
                implicitHeight: Kirigami.Units.iconSizes.small
            }
            PC3.Label {
                Layout.fillWidth: true
                text: frame.context
                color: frame.tint
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }
            PC3.ToolButton {
                visible: frame.actionIcon !== "" && frame.roomy
                icon.name: frame.actionIcon
                Accessible.name: frame.actionText
                PC3.ToolTip.text: frame.actionText
                PC3.ToolTip.visible: hovered
                onClicked: frame.action()
            }
        }
        ColumnLayout {
            id: body
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Kirigami.Units.smallSpacing
        }
    }
}
