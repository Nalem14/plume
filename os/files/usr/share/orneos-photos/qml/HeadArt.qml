// The picture of the head, where Tâches has its ring: the view's newest photos as three prints fanned out on
// the card, the cover of an album, a place or a memory as one larger print, a person's face in a ring of the
// media family. Each print: a light frame, a soft shadow, the picture rounded inside.
import QtQuick
import QtQuick.Effects
import "components"

Item {
    id: art
    readonly property var c: theme.c
    property var covers: []
    readonly property bool face: covers.length > 0 && covers[0].round === true
    readonly property bool single: covers.length === 1 || face
    readonly property color paper: theme.dark ? "#E9EDF3" : "#FFFFFF"
    // the head's card where the art sits (Hero's tint, already a tenth faded there): what a face's corners are painted with
    property color ground: Qt.tint(c.card, Qt.alpha(c.famMedia, (theme.dark ? 0.16 : 0.11) * 0.9))
    visible: covers.length > 0
    implicitWidth: covers.length === 0 ? 0 : face ? 86 : single ? 80 : 104
    implicitHeight: covers.length === 0 ? 0 : 86

    component Print: Item {
        id: sheet
        property string address
        property real side: 60
        property bool round: false
        width: sheet.side; height: sheet.side
        RectangularShadow {
            visible: !sheet.round           // its round edge would be cut by the corners painted around a face
            anchors.fill: frame
            radius: frame.radius
            blur: 14; spread: -3; offset.y: 5
            color: art.c.elev
        }
        Rectangle {
            id: frame
            anchors.fill: parent
            radius: sheet.round ? width / 2 : 9
            color: art.paper
            Rectangle {
                anchors.fill: parent; anchors.margins: 3
                radius: sheet.round ? width / 2 : 6
                color: Qt.tint(art.c.line, Qt.alpha(art.c.famMedia, 0.18))
                Thumb {
                    anchors.fill: parent
                    address: sheet.address
                    sourceSize: Qt.size(256, 256)
                    fillMode: Image.PreserveAspectCrop
                    asynchronous: true
                    opacity: status === Image.Ready ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: 200 } }
                }
                Corners { anchors.fill: parent; radius: parent.radius; color: art.paper }
            }
            // a face: the square of the picture must not show around the white rim either
            Corners { visible: sheet.round; anchors.fill: parent; radius: frame.radius; color: art.ground }
        }
    }

    // a person: the face in the family's ring (over the face's painted corners)
    Print { visible: art.face; anchors.centerIn: parent; side: 74; round: true; address: art.face ? art.covers[0].address : "" }
    Rectangle {
        visible: art.face
        anchors.centerIn: parent
        width: 86; height: 86; radius: 43
        color: "transparent"
        border.width: 2.5; border.color: art.c.famMedia
    }
    // an album, a place, a memory: its cover
    Print {
        visible: art.single && !art.face
        anchors.centerIn: parent
        side: 74
        rotation: -3
        address: art.single && !art.face ? art.covers[0].address : ""
    }
    // the library, a list: the newest photos, fanned out
    Repeater {
        model: art.single ? [] : art.covers.slice(0, 3).reverse()
        Print {
            required property var modelData
            required property int index
            readonly property int n: Math.min(3, art.covers.length)
            readonly property int rank: n - 1 - index          // 0: the newest, in front
            side: 62
            x: 21 + (rank === 1 ? -17 : rank === 2 ? 19 : 0)
            y: 12 + (rank === 0 ? 2 : -2)
            rotation: rank === 1 ? -11 : rank === 2 ? 9 : -1
            address: modelData.address
        }
    }
}
