// Routines of the open bot: classic bench pane content (same shell as Fichiers / Terminal).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Item {
    id: panel
    property string botId: ""
    readonly property var c: theme.c
    readonly property int count: list.count

    function reload() { list.model = botId ? cron.botRoutines(botId) : [] }

    onBotIdChanged: reload()
    Component.onCompleted: reload()
    Connections { target: cron; function onChanged() { panel.reload() } }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 8
        visible: panel.botId !== ""

        RowLayout {
            Layout.fillWidth: true
            spacing: 6
            Text {
                Layout.fillWidth: true
                text: app.t.bots_routines
                font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                color: panel.c.text
            }
            OButton {
                kind: "quiet"; iconName: "plus"; iconSize: 14; height_: 26
                tip: app.t.bots_routine_add
                onClicked: cron.manage("")
            }
        }

        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 4
            model: []
            delegate: AbstractButton {
                id: row
                required property var modelData
                width: list.width
                implicitHeight: 52
                hoverEnabled: true
                onClicked: cron.manage(row.modelData.id)
                background: Rectangle {
                    radius: 10
                    color: row.hovered ? panel.c.hover : panel.c.card
                    border.width: 1; border.color: panel.c.line
                }
                contentItem: RowLayout {
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 6
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Text {
                            Layout.fillWidth: true
                            text: row.modelData.title
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                            color: panel.c.text
                        }
                        Text {
                            Layout.fillWidth: true
                            text: row.modelData.scheduleLabel || row.modelData.schedule
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 11
                            color: panel.c.muted
                        }
                    }
                    OButton {
                        kind: "quiet"; iconName: "bolt"; iconSize: 14; height_: 24
                        tip: app.t.bots_routine_run
                        enabled: !row.modelData.running
                        onClicked: cron.runNow(row.modelData.id)
                    }
                    OSwitch {
                        checked: !row.modelData.paused
                        onToggled: checked ? cron.resume(row.modelData.id) : cron.pause(row.modelData.id)
                    }
                }
            }
        }
        Text {
            visible: list.count === 0
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignHCenter
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            text: app.t.bots_routines_empty
            font.family: "Schibsted Grotesk"; font.pixelSize: 12
            color: panel.c.muted
        }
    }

    Text {
        visible: panel.botId === ""
        anchors.centerIn: parent
        width: parent.width - 32
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
        text: app.t.bots_routines_empty
        font.family: "Schibsted Grotesk"; font.pixelSize: 12
        color: panel.c.muted
    }
}
