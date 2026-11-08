// A moment to come: the day (the next three weeks, in words) and the time (every quarter of an hour). `value` is
// a Unix timestamp; it starts at the next round hour (or `initial`).
import QtQuick
import QtQuick.Layouts
import "components"

RowLayout {
    id: picker
    property int initial: 0
    readonly property int value: {
        const d = day.currentValue === undefined ? 0 : day.currentValue
        const t = time.currentValue === undefined ? 0 : time.currentValue
        return Math.round(new Date(d).getTime() / 1000) + t * 60
    }
    spacing: 8

    function reset(at) {
        const when = new Date(at ? at * 1000 : Date.now() + 3600 * 1000)
        if (!at) when.setMinutes(0, 0, 0)
        const midnight = new Date(when.getFullYear(), when.getMonth(), when.getDate()).getTime()
        day.select(midnight)
        time.select(when.getHours() * 60 + Math.floor(when.getMinutes() / 15) * 15)
    }
    Component.onCompleted: reset(initial)

    OComboBox {
        id: day
        Layout.fillWidth: true
        model: {
            const out = []
            const now = new Date()
            for (let i = 0; i < 21; i++) {
                const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + i)
                out.push({ text: app.day(Math.round(d.getTime() / 1000) + 43200), value: d.getTime() })
            }
            return out
        }
    }
    OComboBox {
        id: time
        Layout.preferredWidth: 110
        model: {
            const out = []
            for (let m = 0; m < 24 * 60; m += 15) {
                const h = Math.floor(m / 60), mm = m % 60
                out.push({ text: (h < 10 ? "0" : "") + h + ":" + (mm < 10 ? "0" : "") + mm, value: m })
            }
            return out
        }
    }
}
