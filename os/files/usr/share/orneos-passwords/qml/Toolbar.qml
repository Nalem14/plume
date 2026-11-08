// Above the list and the entry: where one is, large; offline, when the vault dates from; then the actions
// (generator, lock, a new entry). The account and the settings live at the foot of the side column.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Rectangle {
    id: bar
    readonly property var c: theme.c
    signal newRequested()
    signal settingsRequested()
    signal generatorRequested()

    implicitHeight: 64
    color: "transparent"

    readonly property string heading: {
        if (vault.query !== "")
            return app.t.results
        const cat = vault.category
        if (cat.indexOf("folder:") === 0) {
            const f = vault.folders.find(x => "folder:" + x.id === cat)
            return f ? f.label : app.t.cat_all
        }
        return app.t["cat_" + cat] || app.t.cat_all
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 18
        anchors.rightMargin: 14
        spacing: 10

        Text {
            Layout.fillWidth: true
            text: bar.heading
            elide: Text.ElideRight
            font.family: "Schibsted Grotesk"; font.pixelSize: 24; font.weight: Font.Bold; font.letterSpacing: -0.4
            color: bar.c.text
            Accessible.role: Accessible.Heading
        }

        // the sync stays out of sight: this only shows offline, with what waits to go up (a click tries again)
        AbstractButton {
            id: status
            visible: !vault.online
            implicitHeight: 22
            implicitWidth: statusRow.implicitWidth + 12
            hoverEnabled: true
            onClicked: vault.refresh()
            Accessible.name: statusText.text
            background: Rectangle {
                radius: 5
                color: !vault.online ? bar.c.saffronTint : (status.hovered ? bar.c.hover : "transparent")
            }
            contentItem: Row {
                id: statusRow
                spacing: 5
                anchors.centerIn: parent
                Icon {
                    id: statusIcon
                    anchors.verticalCenter: parent.verticalCenter
                    // The sync never shows (docs/REFONTE-ORNIS.md): only being offline, and what waits.
                    name: !vault.online ? "offline" : "cloud"
                    size: 13
                    color: !vault.online ? bar.c.saffronInk : bar.c.muted
                }
                Text {
                    id: statusText
                    anchors.verticalCenter: parent.verticalCenter
                    text: (vault.pending > 0 ? app.t.offline_pending.replace("%1", vault.pending) : app.t.offline)
                          + (vault.syncedAt ? " · " + app.t.synced_at.replace("%1", app.ago(vault.syncedAt)) : "")
                    font.family: "JetBrains Mono"; font.pixelSize: 12
                    color: !vault.online ? bar.c.saffronInk : bar.c.muted
                }
            }
        }

        OButton {
            kind: "quiet"; implicitWidth: 34
            iconName: "dice"
            tip: app.t.generator + "  (Ctrl+G)"
            onClicked: bar.generatorRequested()
        }
        OButton {
            visible: lock.available
            kind: "quiet"; implicitWidth: 34
            iconName: "lock"
            tip: app.t.lock_now + "  (Ctrl+L)"
            onClicked: lock.lock()
        }
        OButton {
            kind: "primary"
            iconName: "plus"
            text: app.t.new_entry
            tip: app.t.new_entry + "  (Ctrl+N)"
            onClicked: bar.newRequested()
        }
    }
}
