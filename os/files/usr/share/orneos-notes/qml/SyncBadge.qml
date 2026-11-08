// The sync is invisible while it works: this chip, on the line of figures under the heading, only shows when
// the cloud cannot be reached: how many changes wait to go up, and when the notes date from. A click tries again.
import QtQuick
import QtQuick.Controls
import "components"

AbstractButton {
    id: badge
    readonly property var c: theme.c
    readonly property bool shown: !notes.online
    visible: shown
    implicitHeight: 20
    implicitWidth: shown ? row.implicitWidth + 12 : 0
    hoverEnabled: true
    onClicked: notes.refresh()
    Accessible.name: label.text
    background: Rectangle { radius: 5; color: badge.hovered ? Qt.darker(badge.c.saffronTint, 1.04) : badge.c.saffronTint }
    contentItem: Item {
        Row {
            id: row
            spacing: 5
            anchors.centerIn: parent
            Icon { anchors.verticalCenter: parent.verticalCenter; name: "offline"; size: 13; color: badge.c.saffronInk }
            Text {
                id: label
                anchors.verticalCenter: parent.verticalCenter
                text: (notes.pending > 0 ? app.t.offline_pending.replace("%1", notes.pending) : app.t.offline)
                      + (notes.syncedAt ? " · " + app.t.synced_at.replace("%1", app.ago(notes.syncedAt)) : "")
                font.family: "JetBrains Mono"; font.pixelSize: 12
                color: badge.c.saffronInk
            }
        }
    }
}
