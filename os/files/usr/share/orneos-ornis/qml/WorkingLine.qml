// Ornis is working: one quiet line just above the message box, the same in the Discussions and in Code (as
// Claude's « Clauding… »): the mascot beating its wings, a bird's verb that changes every few seconds
// (« Ornis bat des ailes… », « picore… », « plane… »), the time since the question, and how to stop it.
// The verbs come from app.t.work_verbs ("a|b|c"), in the user's language.
import QtQuick
import QtQuick.Layouts
import "components"

Item {
    id: line
    property bool busy: false
    readonly property var c: theme.c
    readonly property var verbs: String(app.t.work_verbs || "").split("|").filter(v => v !== "")
    property int verb: 0
    property double started: 0
    property int seconds: 0
    implicitHeight: busy ? 26 : 0
    visible: busy
    Accessible.role: Accessible.StaticText
    Accessible.name: label.text

    onBusyChanged: {
        if (busy) {
            started = Date.now(); seconds = 0
            verb = verbs.length ? Math.floor(Math.random() * verbs.length) : 0
        }
    }
    Component.onCompleted: if (busy) { started = Date.now(); verb = verbs.length ? Math.floor(Math.random() * verbs.length) : 0 }

    Timer {
        interval: 1000; repeat: true; running: line.busy
        onTriggered: {
            line.seconds = Math.floor((Date.now() - line.started) / 1000)
            if (line.seconds > 0 && line.seconds % 5 === 0 && line.verbs.length > 1)    // a new verb every 5 s
                line.verb = (line.verb + 1 + Math.floor(Math.random() * (line.verbs.length - 1))) % line.verbs.length
        }
    }

    function elapsed(s) {
        if (s < 60) return s + " s"
        const m = Math.floor(s / 60), r = s % 60
        return m + " min " + (r < 10 ? "0" : "") + r
    }

    RowLayout {
        anchors.left: parent.left; anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: 6
        spacing: 8
        Item {                          // the bird hops while it works (still when « reduce motion » is on)
            implicitWidth: 18; implicitHeight: 18
            Icon {
                id: bird
                name: "ornis-mascot"; size: 18; thinking: true
                SequentialAnimation on y {
                    running: line.busy && Qt.styleHints.reduceMotion !== true
                    loops: Animation.Infinite
                    NumberAnimation { from: 0; to: -3; duration: 420; easing.type: Easing.InOutSine }
                    NumberAnimation { from: -3; to: 0; duration: 420; easing.type: Easing.InOutSine }
                }
            }
        }
        Text {
            id: label
            Layout.fillWidth: true
            text: (line.verbs[line.verb] || "") + "…"
            elide: Text.ElideRight
            font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.Medium
            color: line.c.accent
        }
        Text {
            text: line.elapsed(line.seconds) + " · " + app.t.work_stop
            font.family: "Schibsted Grotesk"; font.pixelSize: 12
            color: line.c.muted
        }
    }
}
