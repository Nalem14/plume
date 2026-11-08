// A date in two clicks: today, tomorrow, the weekend, next week, or the month's grid. picked(iso) with
// "YYYY-MM-DD", or "" for no date.
import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Layouts
import "components"

Popup {
    id: picker
    readonly property var c: theme.c
    property string value: ""
    property date shown: new Date()
    signal picked(string iso)
    padding: 14
    width: 300
    margins: 8

    function iso(d) {
        return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0")
    }
    function choose(d) { picked(d ? iso(d) : ""); close() }
    function plus(n) { const d = new Date(); d.setDate(d.getDate() + n); return d }
    onAboutToShow: shown = value ? new Date(value.slice(0, 10) + "T12:00") : new Date()

    enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 120 } }
    background: Item {
        RectangularShadow { anchors.fill: card; radius: 10; blur: 28; offset.y: 10; color: picker.c.shadow }
        Rectangle { id: card; anchors.fill: parent; radius: 10; color: picker.c.overlay; border.width: 1; border.color: picker.c.overlayLine }
    }

    contentItem: ColumnLayout {
        spacing: 8
        GridLayout {
            Layout.fillWidth: true
            columns: 2; rowSpacing: 6; columnSpacing: 6
            OButton { Layout.fillWidth: true; height_: 30; iconName: "today"; iconSize: 15; text: app.t.today; onClicked: picker.choose(new Date()) }
            OButton { Layout.fillWidth: true; height_: 30; iconName: "sun"; iconSize: 15; text: app.t.tomorrow; onClicked: picker.choose(picker.plus(1)) }
            OButton {
                Layout.fillWidth: true; height_: 30; iconName: "calendar"; iconSize: 15; text: app.t.weekend
                onClicked: { const d = new Date(); d.setDate(d.getDate() + ((6 - d.getDay()) % 7 || 7)); picker.choose(d) }
            }
            OButton {
                Layout.fillWidth: true; height_: 30; iconName: "arrow"; iconSize: 15; text: app.t.next_week
                onClicked: { const d = new Date(); d.setDate(d.getDate() + ((8 - d.getDay()) % 7 || 7)); picker.choose(d) }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 4
            OButton { kind: "quiet"; implicitWidth: 30; height_: 30; iconName: "chevronLeft"; tip: app.t.previous; onClicked: picker.shown = new Date(picker.shown.getFullYear(), picker.shown.getMonth() - 1, 1) }
            Text {
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                text: app.t.months_long.split(",")[picker.shown.getMonth()] + " " + picker.shown.getFullYear()
                font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold; font.capitalization: Font.Capitalize
                color: picker.c.text
            }
            OButton { kind: "quiet"; implicitWidth: 30; height_: 30; iconName: "chevronRight"; tip: app.t.next; onClicked: picker.shown = new Date(picker.shown.getFullYear(), picker.shown.getMonth() + 1, 1) }
        }
        DayOfWeekRow {
            Layout.fillWidth: true
            locale: Qt.locale(app.lang)
            delegate: Text {
                required property string shortName
                text: shortName.slice(0, 2)
                horizontalAlignment: Text.AlignHCenter
                font.family: "Schibsted Grotesk"; font.pixelSize: 11; font.capitalization: Font.AllUppercase
                color: picker.c.muted
            }
        }
        MonthGrid {
            id: grid
            Layout.fillWidth: true
            month: picker.shown.getMonth()
            year: picker.shown.getFullYear()
            locale: Qt.locale(app.lang)
            delegate: AbstractButton {
                id: cell
                required property var model
                readonly property bool chosen: picker.value.slice(0, 10) === picker.iso(model.date)
                implicitHeight: 32
                hoverEnabled: true
                opacity: model.month === grid.month ? 1 : 0.35
                onClicked: picker.choose(model.date)
                background: Rectangle {
                    anchors.centerIn: parent
                    width: 30; height: 30; radius: 15
                    color: cell.chosen ? picker.c.action : cell.hovered ? picker.c.hover : "transparent"
                    border.width: cell.model.today && !cell.chosen ? 1 : 0
                    border.color: picker.c.accent
                }
                contentItem: Text {
                    text: cell.model.day
                    horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                    font.weight: cell.model.today ? Font.DemiBold : Font.Normal
                    color: cell.chosen ? picker.c.actionText : picker.c.text
                }
            }
        }
        OButton {
            visible: picker.value !== ""
            Layout.fillWidth: true
            kind: "quiet"; height_: 30; iconName: "close"; iconSize: 13; text: app.t.no_date
            onClicked: picker.choose(null)
        }
    }
}
