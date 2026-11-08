// A site's icon (fetched by the cloud, kept on disk), or its initial on a tile of the Orneos families.
import QtQuick
import "components"

Rectangle {
    id: icon
    property string source
    property string initial: "?"
    property color tile: "#002FA7"
    property real size: 32
    property string glyph: ""                // an Orneos icon instead of the initial (Wi-Fi networks)
    readonly property bool hasImage: source !== "" && image.status === Image.Ready

    implicitWidth: size
    implicitHeight: size
    radius: Math.round(size * 0.24)
    color: hasImage ? "#FFFFFF" : tile
    border.width: hasImage ? 1 : 0
    border.color: theme.c.line

    Image {
        id: image
        anchors.centerIn: parent
        width: Math.round(icon.size * 0.68); height: width
        source: icon.source
        sourceSize.width: 64; sourceSize.height: 64
        smooth: true; mipmap: true
        asynchronous: true
        visible: icon.hasImage
    }
    Text {
        anchors.centerIn: parent
        visible: !icon.hasImage && icon.glyph === ""
        text: icon.initial
        font.family: "Schibsted Grotesk"; font.pixelSize: Math.round(icon.size * 0.46); font.weight: Font.DemiBold
        color: "#FFFFFF"
    }
    Icon {
        anchors.centerIn: parent
        visible: !icon.hasImage && icon.glyph !== ""
        name: icon.glyph; size: Math.round(icon.size * 0.56); color: "#FFFFFF"
    }
}
