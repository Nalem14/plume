// Initials on a tint picked from the name (Klein, saffron, vert-de-gris, brume), or the card's photo.
import QtQuick
import QtQuick.Effects

Item {
    id: avatar
    property string initials
    property int tint: 0
    property string photo
    property real size: 36
    property bool selected: false        // on a selected (tinted) row: the Klein tone turns white
    readonly property var c: theme.c
    readonly property var tones: [
        [c.tint, c.tintText], [c.saffronTint, c.saffronInk], [c.okTint, c.okInk], [c.hover, c.text]
    ]
    implicitWidth: size
    implicitHeight: size

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: avatar.selected && avatar.tint % 4 === 0 ? avatar.c.card : avatar.tones[avatar.tint % 4][0]
        visible: image.status !== Image.Ready
        Text {
            anchors.centerIn: parent
            text: avatar.initials
            font.family: "Schibsted Grotesk"; font.pixelSize: Math.round(avatar.size * 0.36); font.weight: Font.DemiBold
            color: avatar.tones[avatar.tint % 4][1]
        }
    }
    Image {
        id: image
        anchors.fill: parent
        // a data: picture of the card, or the small copy of it kept in the cache (file:)
        source: avatar.photo.startsWith("data:") || avatar.photo.startsWith("file:") ? avatar.photo : ""
        sourceSize: Qt.size(avatar.size * 2, avatar.size * 2)
        fillMode: Image.PreserveAspectCrop
        visible: false
        asynchronous: true
    }
    MultiEffect {
        anchors.fill: parent
        source: image
        visible: image.status === Image.Ready
        maskEnabled: true
        maskSource: mask
    }
    Item {
        id: mask
        anchors.fill: parent
        layer.enabled: true
        visible: false
        Rectangle { anchors.fill: parent; radius: width / 2 }
    }
}
