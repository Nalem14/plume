// A conversation's picture or a person's photo (the cloud draws it), the initials while it comes, and for a
// one-to-one the presence of the other person (online, away, do not disturb).
import QtQuick

Item {
    id: avatar
    readonly property var c: theme.c
    property var room: ({})
    property string source: room.avatar || ""
    property string name: room.name || ""
    property string status: room.status || ""
    property real size: 40
    implicitWidth: size
    implicitHeight: size

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: avatar.c.tint
        visible: image.status !== Image.Ready
        Text {
            anchors.centerIn: parent
            text: {
                const parts = String(avatar.name).replace(/[._]/g, " ").split(/\s+/).filter(p => p)
                if (!parts.length) return "?"
                return (parts.length === 1 ? parts[0].slice(0, 2) : parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
            }
            font.family: "Schibsted Grotesk"; font.pixelSize: Math.round(avatar.size * 0.36); font.weight: Font.DemiBold
            color: avatar.c.tintText
        }
    }
    // round already: the provider cuts it (meet_core/images.py)
    Image {
        id: image
        anchors.fill: parent
        // the cloud draws its pictures for a dark background too
        source: avatar.source && theme.dark && avatar.source.startsWith("image://meet/") ? avatar.source + "/dark" : avatar.source
        sourceSize: Qt.size(avatar.size * 2, avatar.size * 2)
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        smooth: true
        visible: status === Image.Ready
    }
    Rectangle {
        visible: avatar.status !== "" && avatar.status !== "offline" && avatar.status !== "invisible"
        width: Math.max(10, avatar.size * 0.3); height: width; radius: width / 2
        anchors.right: parent.right; anchors.bottom: parent.bottom
        border.width: 2; border.color: avatar.c.chrome
        color: avatar.status === "online" ? avatar.c.ok : (avatar.status === "dnd" || avatar.status === "busy" ? avatar.c.danger : avatar.c.saffron)
    }
}
