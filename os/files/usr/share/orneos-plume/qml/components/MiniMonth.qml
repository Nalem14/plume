// The month at a glance: Monday first, today in Klein, the selected week tinted. Click a day to pick it.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "dates.js" as D

ColumnLayout {
    id: mini
    property date selected: new Date()
    property date shown: D.startOfMonth(selected)
    property bool weekBand: true
    signal picked(date day)
    readonly property var c: theme.c
    readonly property var loc: Qt.locale(plume.locale)
    readonly property date first: D.startOfWeek(D.startOfMonth(shown))
    spacing: 4

    onSelectedChanged: if (selected.getMonth() !== shown.getMonth() || selected.getFullYear() !== shown.getFullYear()) shown = D.startOfMonth(selected)

    RowLayout {
        Layout.fillWidth: true
        Text {
            Layout.fillWidth: true
            Layout.leftMargin: 4
            text: D.capitalize(mini.loc.standaloneMonthName(mini.shown.getMonth())) + " " + mini.shown.getFullYear()
            font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
            color: mini.c.text
        }
        OButton { kind: "quiet"; iconName: "chevronLeft"; iconSize: 16; height_: 26; implicitWidth: 26; Accessible.name: plume.t.previous; onClicked: mini.shown = D.addMonths(mini.shown, -1) }
        OButton { kind: "quiet"; iconName: "chevronRight"; iconSize: 16; height_: 26; implicitWidth: 26; Accessible.name: plume.t.next; onClicked: mini.shown = D.addMonths(mini.shown, 1) }
    }
    GridLayout {
        Layout.fillWidth: true
        columns: 7
        rowSpacing: 2
        columnSpacing: 0
        Repeater {
            model: 7
            Text {
                required property int index
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                text: mini.loc.dayName((index + 1) % 7, Locale.NarrowFormat).toUpperCase()
                font.family: "JetBrains Mono"; font.pixelSize: 11
                color: mini.c.muted
            }
        }
        Repeater {
            model: 42
            AbstractButton {
                id: cell
                required property int index
                readonly property date day: D.addDays(mini.first, index)
                readonly property bool today: D.sameDay(day, new Date())
                readonly property bool inMonth: day.getMonth() === mini.shown.getMonth()
                readonly property bool isSelected: D.sameDay(day, mini.selected)
                readonly property bool inWeek: mini.weekBand && D.sameDay(D.startOfWeek(day), D.startOfWeek(mini.selected))
                visible: index < 35 || D.addDays(mini.first, 35).getMonth() === mini.shown.getMonth()
                Layout.fillWidth: true
                implicitHeight: 28
                hoverEnabled: true
                Accessible.name: mini.loc.toString(day, Locale.LongFormat)
                onClicked: mini.picked(day)
                background: Rectangle {
                    anchors.centerIn: parent
                    width: 28; height: 28; radius: 14
                    color: cell.today ? mini.c.action : cell.isSelected || cell.inWeek ? mini.c.tint : cell.hovered ? mini.c.hover : "transparent"
                }
                contentItem: Text {
                    text: cell.day.getDate()
                    horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                    font.family: "JetBrains Mono"; font.pixelSize: 12
                    font.weight: cell.today || cell.isSelected ? Font.Medium : Font.Normal
                    color: cell.today ? mini.c.actionText : cell.inMonth ? mini.c.text : mini.c.faint
                }
            }
        }
    }
}
