// The shared Ornis thinking pose, animated only during a request.
import QtQuick

Row {
    id: thinking
    property bool running: visible
    property bool showMascot: true
    property string text: app.t.ornis_working
    readonly property var c: theme.c
    spacing: 10

    Image {
        visible: thinking.showMascot
        anchors.verticalCenter: parent.verticalCenter
        width: 32; height: 32
        source: "../../../orneos/mascot/thinking-v1.png"
        fillMode: Image.PreserveAspectFit
        // Gentle breathing only while working; a static pose remains when motion is disabled.
        SequentialAnimation on opacity {
            running: thinking.running && thinking.visible && Qt.styleHints.reduceMotion !== true
            loops: Animation.Infinite
            NumberAnimation { from: 1; to: 0.65; duration: 900 }
            NumberAnimation { from: 0.65; to: 1; duration: 900 }

        }
    }
    Text {
        anchors.verticalCenter: parent.verticalCenter
        text: thinking.text
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: thinking.c.muted
    }
}
