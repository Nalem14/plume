// What is left of a verification code's period: a ring that empties, Klein, then saffron the last 5 seconds.
import QtQuick

Canvas {
    id: ring
    property int remaining: 30
    property int period: 30
    property real size: 22
    readonly property color tone: remaining <= 5 ? theme.c.saffron : theme.c.action
    implicitWidth: size
    implicitHeight: size
    onRemainingChanged: requestPaint()
    onToneChanged: requestPaint()
    Connections { target: theme; function onChanged() { ring.requestPaint() } }

    onPaint: {
        const ctx = getContext("2d")
        ctx.reset()
        const r = width / 2 - 2
        ctx.lineWidth = 2.5
        ctx.strokeStyle = theme.c.line
        ctx.beginPath()
        ctx.arc(width / 2, height / 2, r, 0, 2 * Math.PI)
        ctx.stroke()
        ctx.strokeStyle = tone
        ctx.beginPath()
        const part = Math.max(0, Math.min(1, remaining / period))
        ctx.arc(width / 2, height / 2, r, -Math.PI / 2, -Math.PI / 2 + part * 2 * Math.PI)
        ctx.stroke()
    }
}
