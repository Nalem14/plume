// A QR code drawn from its modules (rows of "0"/"1"), dark on white whatever the theme: phones read it.
import QtQuick

Rectangle {
    id: qr
    property var rows: []
    property real size: 180
    implicitWidth: size
    implicitHeight: size
    radius: 10
    color: "#FFFFFF"
    border.width: 1
    border.color: theme.c.line

    Canvas {
        id: canvas
        anchors.fill: parent
        anchors.margins: 14
        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            const n = qr.rows.length
            if (!n)
                return
            const cell = Math.floor(width / n)
            const offset = Math.floor((width - cell * n) / 2)
            ctx.fillStyle = "#0F2440"
            for (let y = 0; y < n; ++y)
                for (let x = 0; x < n; ++x)
                    if (qr.rows[y][x] === "1")
                        ctx.fillRect(offset + x * cell, offset + y * cell, cell, cell)
        }
    }
    onRowsChanged: canvas.requestPaint()
}
