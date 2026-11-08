// SPDX-License-Identifier: GPL-2.0-or-later
// Mon Orneos on the desktop: the Drive's storage on the Ornis ring (it measures a quota: docs/ROADMAP.md
// › Anneau), and how much of Ornis is left over the rolling 24 h. Small: the ring and its percentage;
// wide or tall: the figures beside it, Ornis's gauge, and "More space" from 80 %.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PC3
import "strings.js" as S
import "ornis.js" as Ornis

Frame {
    id: root
    readonly property var feed: bridge
    readonly property var drive: bridge.result.drive || null
    readonly property var ornis: bridge.result.ornis || null
    readonly property int percent: drive ? drive.percent : 0
    // Saffron asks for attention, vermilion for action: the same thresholds as the cloud's warnings.
    readonly property color level: percent >= 95 ? Ornis.t.brand.vermillon : percent >= 80 ? Ornis.t.brand.safran : tint
    readonly property string plans: ({fr: "https://orneos.eu/fr/tarifs", de: "https://orneos.eu/de/preise"})[Qt.locale().name.slice(0, 2)]
                                    || "https://orneos.eu/en/pricing"

    family: "docs"
    context: S.tr("account")
    onOpened: bridge.launch("/usr/libexec/orneos-app files")

    Bridge { id: bridge; command: "/usr/libexec/orneos-widget account"; interval: 300000 }

    Skeleton {
        visible: bridge.result.state === "loading"
        Layout.fillWidth: true
        Layout.fillHeight: true
        rows: 2
        tone: Qt.alpha(Kirigami.Theme.textColor, 0.1)
    }
    PC3.Label {
        visible: !bridge.result.ready && bridge.result.state !== "loading"
        Layout.fillWidth: true
        text: S.tr(bridge.result.state === "signed_out" ? "signed_out" : "error")
        wrapMode: Text.WordWrap
        font: Kirigami.Theme.smallFont
        opacity: 0.75
    }
    PC3.Button {
        visible: !bridge.result.ready && bridge.result.state !== "loading"
        text: bridge.result.state === "signed_out" ? "Orneos Connect" : S.tr("retry")
        onClicked: bridge.result.state === "signed_out" ? bridge.launch("orneos-connect") : bridge.refresh()
    }

    GridLayout {
        visible: root.drive !== null
        Layout.fillWidth: true
        Layout.fillHeight: true
        flow: root.wide ? GridLayout.LeftToRight : GridLayout.TopToBottom
        columnSpacing: Kirigami.Units.largeSpacing * 2
        rowSpacing: Kirigami.Units.smallSpacing

        Item {
            Layout.alignment: root.wide ? Qt.AlignVCenter : Qt.AlignHCenter
            Layout.preferredWidth: Math.min(Kirigami.Units.gridUnit * (root.roomy ? 6.5 : 5.5), root.width - Kirigami.Units.largeSpacing * 2)
            Layout.preferredHeight: Layout.preferredWidth
            Ring {
                anchors.fill: parent
                trackColor: Qt.alpha(Kirigami.Theme.textColor, 0.12)
                segments: [{from: 0, to: root.percent / 100, color: root.level}]
            }
            ColumnLayout {
                anchors.centerIn: parent
                spacing: 0
                PC3.Label {
                    Layout.alignment: Qt.AlignHCenter
                    text: root.percent + " %"
                    font.pixelSize: parent.parent.width * 0.22
                    font.weight: Font.Bold
                    font.features: {"tnum": 1}
                }
                PC3.Label {
                    Layout.alignment: Qt.AlignHCenter
                    text: S.tr("storage")
                    opacity: 0.65
                    font: Kirigami.Theme.smallFont
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter
            spacing: Kirigami.Units.smallSpacing
            PC3.Label {
                Layout.fillWidth: true
                horizontalAlignment: root.wide ? Text.AlignLeft : Text.AlignHCenter
                text: root.drive ? S.fmt("storageOf", root.drive.usedText, root.drive.totalText) : ""
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }
            PC3.Label {
                visible: root.roomy && root.drive && root.drive.totalBytes > 0
                Layout.fillWidth: true
                horizontalAlignment: root.wide ? Text.AlignLeft : Text.AlignHCenter
                text: root.drive ? S.fmt("storageFree", root.free(root.drive.totalBytes - root.drive.usedBytes)) : ""
                opacity: 0.7
                font: Kirigami.Theme.smallFont
            }

            // Ornis: what is left of today's share.
            ColumnLayout {
                visible: root.roomy && root.ornis !== null
                Layout.fillWidth: true
                Layout.topMargin: Kirigami.Units.smallSpacing
                spacing: 4
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    OrnisStars {
                        color: Ornis.family("tools", root.dark)
                        implicitWidth: Kirigami.Units.iconSizes.small
                        implicitHeight: Kirigami.Units.iconSizes.small
                    }
                    PC3.Label {
                        Layout.fillWidth: true
                        text: "Ornis"
                        elide: Text.ElideRight
                        font.weight: Font.DemiBold
                        font.pointSize: Kirigami.Theme.defaultFont.pointSize * 0.85
                    }
                    PC3.Label {
                        text: root.ornis ? S.fmt("available", 100 - root.ornis.percent) : ""
                        font.pointSize: Kirigami.Theme.defaultFont.pointSize * 0.85
                        font.features: {"tnum": 1}
                        opacity: 0.75
                    }
                }
                Rectangle {
                    Layout.fillWidth: true
                    height: 6
                    radius: 3
                    color: Qt.alpha(Kirigami.Theme.textColor, 0.12)
                    Rectangle {
                        width: parent.width * (root.ornis ? root.ornis.percent / 100 : 0)
                        height: parent.height
                        radius: 3
                        color: root.ornis && root.ornis.percent >= 80 ? Ornis.t.brand.safran : Ornis.family("tools", root.dark)
                    }
                }
                PC3.Label {
                    Layout.fillWidth: true
                    text: S.tr("ornisUsage")
                    elide: Text.ElideRight
                    opacity: 0.6
                    font: Kirigami.Theme.smallFont
                }
            }
            PC3.Button {
                visible: root.roomy && root.percent >= 80
                Layout.alignment: root.wide ? Qt.AlignLeft : Qt.AlignHCenter
                text: S.tr("moreSpace")
                icon.name: "go-up"
                onClicked: bridge.launch("xdg-open " + bridge.quote(root.plans))
            }
        }
    }

    function free(bytes) {
        const gb = Math.max(0, bytes) / 1073741824;
        const unit = Qt.locale().name.slice(0, 2) === "fr" ? (gb >= 1 ? "Go" : "Mo") : (gb >= 1 ? "GB" : "MB");
        return gb >= 1 ? Number(gb).toLocaleString(Qt.locale(), "f", 1) + " " + unit
                       : Math.max(1, Math.round(gb * 1024)) + " " + unit;
    }
}
