// Today's Ornis allowance, discreet: the Ornis ring (it measures a quota: docs/ROADMAP.md › Anneau) and
// « x % de votre limite du jour », the explanation as a tip, the AI offers from 80 % on (the same gauge as the
// cloud, js/orneos.js ornisGauge). A click opens Settings › Utilisation: 24 h hour by hour and the AI offers.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import "components"

Item {
    id: gauge
    signal detailsRequested()
    readonly property var c: theme.c
    readonly property int percent: chat.quota.percent !== undefined ? chat.quota.percent : -1
    visible: percent >= 0
    implicitHeight: visible ? column.implicitHeight + 8 : 0

    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
    TapHandler { onTapped: gauge.detailsRequested() }
    Accessible.role: Accessible.Button
    Accessible.name: app.t.quota.replace("%1", gauge.percent) + ". " + app.t.usage_open_tip
    ToolTip.text: app.t.quota_tip + "\n" + app.t.usage_open_tip
    ToolTip.visible: hover.hovered
    ToolTip.delay: 450

    ColumnLayout {
        id: column
        anchors.left: parent.left; anchors.right: parent.right
        anchors.bottom: parent.bottom
        spacing: 4
        RowLayout {
            spacing: 8
            Ring {
                implicitWidth: 22; implicitHeight: 22
                lineWidth: 3.5
                trackColor: gauge.c.line
                segments: [{ from: 0, to: Math.max(0.02, gauge.percent / 100), color: gauge.percent >= 80 ? gauge.c.saffron : gauge.c.famCommunicate }]
            }
            Text {
                text: app.t.quota.replace("%1", gauge.percent)
                font.family: "JetBrains Mono"; font.pixelSize: 12
                color: gauge.c.muted
            }
        }
        Text {
            visible: gauge.percent >= 80
            text: app.t.quota_more
            font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.underline: plansMouse.containsMouse
            color: gauge.c.accent
            MouseArea { id: plansMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: gauge.detailsRequested() }
        }
    }
}
