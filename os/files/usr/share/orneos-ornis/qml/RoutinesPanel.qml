// Floating retractable routines of the open bot: compact rows; edit via CronSheet.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Item {
    id: panel
    property string botId: ""
    property bool open: false
    readonly property var c: theme.c
    readonly property int count: list.count
    readonly property real sheetWidth: Math.min(260, parent ? parent.width * 0.28 : 260)

    function reload() { list.model = cron.botRoutines(botId) }
    function toggle() { open = !open }
    function close() { open = false }

    onBotIdChanged: { reload(); if (!botId) open = false }
    Connections { target: cron; function onChanged() { panel.reload() } }

    // Expanded floating sheet (opened from the header clock); floats over the conversation
    Rectangle {
        id: sheet
        visible: panel.botId !== "" && panel.open
        anchors { right: parent.right; top: parent.top; bottom: parent.bottom; margins: 10 }
        anchors.topMargin: 56 + 8   // under the Code header
        width: panel.sheetWidth
        z: 2
        color: panel.c.chrome
        border.width: 1; border.color: panel.c.line
        radius: 12
        // soft shadow to the left
        Rectangle {
            anchors { right: parent.left; top: parent.top; bottom: parent.bottom }
            width: 16
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: "transparent" }
                GradientStop { position: 1; color: Qt.rgba(0, 0, 0, theme.dark ? 0.28 : 0.08) }
            }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 12
            spacing: 8

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
                OButton {
                    kind: "quiet"; iconName: "close"; iconSize: 14; height_: 26
                    tip: app.t.bots_routines_close
                    onClicked: panel.close()
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
                Text {
                    visible: list.count === 0
                    anchors.centerIn: parent
                    width: parent.width - 16
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    text: app.t.bots_routines_empty
                    font.family: "Schibsted Grotesk"; font.pixelSize: 12
                    color: panel.c.muted
                }
            }
        }
    }
}
