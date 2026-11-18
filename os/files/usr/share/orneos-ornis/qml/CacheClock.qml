// How long the model's provider keeps the start of this conversation in its cache (code.context.cache, 18/11/2026,
// as Claude Code's clock): while it does, the next message rereads it for a fortieth of the price; after, it is sent
// again at full price. Shown only once a miss would weigh (CACHE_SHOWN tokens), never while Ornis works nor for a bot.
// Hover or click: what it means, and « Résumer pendant mon absence » (a big conversation summed up just before the
// cache forgets it).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

AbstractButton {
    id: clock
    readonly property var c: theme.c
    property var info: ({})              // {at (s), ttl (s), input, cached, idle, idleMin}
    property bool busy: false
    signal idleToggled(bool on)
    readonly property int cacheShown: 8000
    property real now: Date.now() / 1000
    readonly property int tokens: info.input || 0
    readonly property real remaining: info.at ? info.at + (info.ttl || 0) - now : 0
    // warm, cold (expired), none (never sent from here: a conversation reopened), or "" (hidden)
    readonly property string state_: busy || tokens < cacheShown || !info.ttl ? "" : !info.at ? "none" : remaining > 0 ? "warm" : "cold"
    function span(seconds) {
        const m = Math.max(1, Math.round(seconds / 60))
        return m < 60 ? m + " min" : Math.floor(m / 60) + " h " + String(m % 60).padStart(2, "0")
    }
    function grouped(n) { return Number(n).toLocaleString(Qt.locale(app.lang), "f", 0) }
    readonly property string line: state_ === "warm" ? app.t.code_cache_warm.replace("%1", span(remaining))
                                   : state_ === "cold" ? app.t.code_cache_cold.replace("%1", span(now - info.at))
                                   : app.t.code_cache_none
    readonly property string hint: {
        if (state_ !== "warm")
            return app.t.code_cache_cold_hint.replace("%1", grouped(tokens))
        const hit = info.input ? Math.round(100 * (info.cached || 0) / info.input) : 0
        return app.t.code_cache_warm_hint.replace("%1", grouped(tokens)) + (hit ? " " + app.t.code_cache_hit.replace("%1", hit) : "")
    }

    Timer { interval: 15000; running: clock.state_ !== "" || clock.info.at > 0; repeat: true; onTriggered: clock.now = Date.now() / 1000 }
    onInfoChanged: now = Date.now() / 1000

    visible: state_ !== ""
    implicitWidth: 30; implicitHeight: 36
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    onClicked: pop.open()
    Accessible.role: Accessible.Button
    Accessible.name: line + " " + hint

    background: Rectangle {
        radius: 8
        color: clock.hovered ? clock.c.hover : "transparent"
        border.width: clock.visualFocus ? 2 : 0
        border.color: clock.c.saffron
    }
    contentItem: Item {
        Icon {
            anchors.centerIn: parent
            name: "clock"; size: 17
            color: clock.state_ === "warm" ? clock.c.muted : clock.c.saffronInk
        }
    }

    Timer { id: show; interval: 280; onTriggered: pop.open() }
    Timer { id: hide; interval: 160; onTriggered: if (!clock.hovered && !clock.activeFocus && !popHover.hovered) pop.close() }
    onHoveredChanged: hovered ? show.restart() : (show.stop(), hide.restart())
    onActiveFocusChanged: activeFocus ? pop.open() : hide.restart()

    Popup {
        id: pop
        parent: clock
        width: 300
        x: Math.min(0, -(width - clock.width) + 40)
        y: -implicitHeight - 10
        padding: 14
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle {
            radius: 12
            color: clock.c.overlay
            border.width: 1; border.color: clock.c.overlayLine
        }
        HoverHandler { id: popHover; onHoveredChanged: if (!hovered) hide.restart() }
        contentItem: ColumnLayout {
            spacing: 8
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Icon { name: "clock"; size: 15; color: clock.state_ === "warm" ? clock.c.muted : clock.c.saffronInk }
                Text {
                    Layout.fillWidth: true
                    text: clock.line
                    wrapMode: Text.Wrap
                    font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
                    color: clock.c.text
                }
            }
            Text {
                Layout.fillWidth: true
                text: clock.hint
                wrapMode: Text.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                color: clock.c.muted
            }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: clock.c.hairline }
            OSwitch {
                Layout.fillWidth: true
                text: app.t.code_cache_idle
                font.pixelSize: 13
                checked: clock.info.idle !== false
                onToggled: clock.idleToggled(checked)
            }
            Text {
                Layout.fillWidth: true
                text: app.t.code_cache_idle_hint
                wrapMode: Text.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                color: clock.c.muted
            }
        }
    }
}
