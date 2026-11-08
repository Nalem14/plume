// A small number with − and + (every N weeks, after N times): typed or stepped, kept between from and to.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

Rectangle {
    id: stepper
    property int value: 1
    property int from: 1
    property int to: 99
    signal edited(int value)
    readonly property var c: theme.c
    implicitWidth: 112
    implicitHeight: 38
    radius: 6
    color: c.field
    border.width: input.activeFocus ? 2 : 1
    border.color: input.activeFocus ? c.action : c.line

    function set(v) {
        v = Math.max(from, Math.min(to, v))
        if (v !== value) edited(v)
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 3
        spacing: 0
        OButton {
            kind: "quiet"; text: "−"; height_: 30; implicitWidth: 30
            Accessible.name: "−"
            enabled: stepper.value > stepper.from
            onClicked: stepper.set(stepper.value - 1)
        }
        TextInput {
            id: input
            Layout.fillWidth: true
            horizontalAlignment: TextInput.AlignHCenter
            verticalAlignment: TextInput.AlignVCenter
            text: String(stepper.value)
            validator: IntValidator { bottom: stepper.from; top: stepper.to }
            selectByMouse: true
            font.family: "JetBrains Mono"; font.pixelSize: 14
            color: stepper.c.text
            onEditingFinished: stepper.set(parseInt(text) || stepper.from)
            Keys.onUpPressed: stepper.set(stepper.value + 1)
            Keys.onDownPressed: stepper.set(stepper.value - 1)
        }
        OButton {
            kind: "quiet"; iconName: "plus"; iconSize: 14; height_: 30; implicitWidth: 30
            Accessible.name: "+"
            enabled: stepper.value < stepper.to
            onClicked: stepper.set(stepper.value + 1)
        }
    }
}
