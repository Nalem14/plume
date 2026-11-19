// Ornis's limits, discreet: the Ornis ring (it measures a quota: docs/ROADMAP.md › Anneau) on the window that will stop
// Ornis first (« Session de 5 h · 48 % », chat.limitView, ornis_limits.py), every window and when it renews as a tip,
// the AI offers from 80 % on (the same gauge as the cloud, js/orneos.js ornisLimits). A click opens Settings ›
// Utilisation: each window and the AI offers.
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
    readonly property var lv: chat.limitView || ({})
    readonly property string line: lv.line || app.t.quota.replace("%1", gauge.percent)
    readonly property string tip: (lv.windows || []).map(w => w.name + " · " + w.used + " · " + w.renew).join("\n")
    visible: percent >= 0
    implicitHeight: visible ? column.implicitHeight + 8 : 0

    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
    TapHandler { onTapped: gauge.detailsRequested() }
    Accessible.role: Accessible.Button
    Accessible.name: gauge.line + ". " + (gauge.lv.detail || "") + " " + app.t.usage_open_tip
    ToolTip.text: (gauge.tip ? gauge.tip + "\n\n" : "") + app.t.quota_tip + "\n" + app.t.usage_open_tip
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
                segments: [{ from: 0, to: Math.max(0.02, gauge.percent / 100),
                             color: gauge.percent >= 100 ? gauge.c.danger : gauge.percent >= 80 ? gauge.c.saffron : gauge.c.famCommunicate }]
            }
            Text {
                text: gauge.line
                font.family: "JetBrains Mono"; font.pixelSize: 12
                color: gauge.lv.level === "full" ? gauge.c.danger : gauge.c.muted
            }
        }
        Text {
            // from 80 %: when it renews (or comes back), on its own line
            visible: gauge.percent >= 80 && !!gauge.lv.detail
            Layout.fillWidth: true
            text: gauge.lv.detail || ""
            elide: Text.ElideRight
            font.family: "Schibsted Grotesk"; font.pixelSize: 12
            color: gauge.c.muted
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
