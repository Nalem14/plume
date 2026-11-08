// Five steps, like the site's meter: red, saffron, then the greens of Orneos. Measured here, nothing leaves.
import QtQuick
import QtQuick.Layouts

RowLayout {
    id: meter
    property int score: 0          // 0 … 4
    property bool empty: false
    readonly property var c: theme.c
    readonly property color tone: score <= 0 ? c.danger : score === 1 ? c.danger : score === 2 ? c.saffron : c.ok
    spacing: 10

    Row {
        spacing: 3
        Repeater {
            model: 5
            Rectangle {
                required property int index
                width: 22; height: 4; radius: 2
                color: !meter.empty && index <= meter.score ? meter.tone : meter.c.line
                Behavior on color { ColorAnimation { duration: 160 } }
            }
        }
    }
    Text {
        visible: !meter.empty
        text: app.t["strength_" + meter.score]
        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.Medium
        color: meter.score <= 1 ? meter.c.danger : meter.score === 2 ? meter.c.saffronInk : meter.c.okInk
    }
}
