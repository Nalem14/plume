// A time: type it ("9", "9h30", "14:15") or pick one every 15 minutes.
import QtQuick
import QtQuick.Controls
import QtQuick.Effects

TextField {
    id: field
    property string value: "09:00"
    readonly property var c: theme.c
    readonly property var steps: {
        const out = []
        for (let m = 0; m < 24 * 60; m += 15)
            out.push(String(Math.floor(m / 60)).padStart(2, "0") + ":" + String(m % 60).padStart(2, "0"))
        return out
    }

    function normalize(text) {
        const m = String(text).trim().toLowerCase().match(/^(\d{1,2})(?:\s*[:h.]\s*(\d{1,2}))?$/)
        if (!m)
            return value
        const h = Math.min(23, parseInt(m[1])), mi = Math.min(59, parseInt(m[2] || "0"))
        return String(h).padStart(2, "0") + ":" + String(mi).padStart(2, "0")
    }

    implicitHeight: 38
    implicitWidth: 92
    text: value
    horizontalAlignment: Text.AlignHCenter
    font.family: "JetBrains Mono"; font.pixelSize: 14
    color: c.text
    selectByMouse: true
    onActiveFocusChanged: if (activeFocus) { list.open(); selectAll() } else value = normalize(text)
    onAccepted: { value = normalize(text); text = value; list.close() }
    onValueChanged: text = value

    background: Rectangle {
        radius: 6
        color: field.c.field
        border.width: field.activeFocus ? 2 : 1
        border.color: field.activeFocus ? field.c.action : field.c.line
    }

    Popup {
        id: list
        y: field.height + 4
        width: field.width
        height: 220
        padding: 4
        background: Item {
            RectangularShadow { anchors.fill: card; radius: 10; blur: 24; offset.y: 8; color: field.c.shadow }
            Rectangle { id: card; anchors.fill: parent; radius: 10; color: field.c.overlay; border.width: 1; border.color: field.c.overlayLine }
        }
        contentItem: ListView {
            id: view
            clip: true
            model: field.steps
            Component.onCompleted: positionViewAtIndex(Math.max(0, field.steps.indexOf(field.value) - 2), ListView.Beginning)
            delegate: AbstractButton {
                id: step
                required property string modelData
                width: view.width; height: 30
                hoverEnabled: true
                onClicked: { field.value = modelData; field.text = modelData; list.close(); field.focus = false }
                background: Rectangle { radius: 6; color: step.modelData === field.value ? field.c.tint : step.hovered ? field.c.hover : "transparent" }
                contentItem: Text {
                    text: step.modelData
                    horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                    font.family: "JetBrains Mono"; font.pixelSize: 13
                    color: field.c.text
                }
            }
        }
    }
}
