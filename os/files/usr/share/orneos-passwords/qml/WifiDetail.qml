// A Wi-Fi network this computer knows: its key on demand, and the QR code a phone scans to join it.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Rectangle {
    id: pane
    readonly property var c: theme.c
    property string uuid
    property var net: ({})
    property var secret: ({})
    property bool asking: false
    property bool refused: false
    color: c.bg

    onUuidChanged: {
        net = wifi.networks.find(n => n.uuid === uuid) || ({})
        secret = ({})
        refused = false
        asking = false
    }
    Connections {
        target: wifi
        function onKeyReady(id, data) {
            if (id !== pane.uuid)
                return
            pane.asking = false
            pane.secret = data
            pane.refused = !data.ssid
        }
        function onChanged() { pane.net = wifi.networks.find(n => n.uuid === pane.uuid) || ({}) }
    }

    ColumnLayout {
        anchors.centerIn: parent
        visible: !pane.net.uuid
        width: Math.min(360, parent.width - 48)
        spacing: 10
        Icon { Layout.alignment: Qt.AlignHCenter; name: "wifi"; size: 36; color: pane.c.faint }
        Text {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            text: wifi.networks.length ? app.t.wifi_pick : app.t.wifi_none
            wrapMode: Text.WordWrap
            lineHeight: 1.25
            font.family: "Schibsted Grotesk"; font.pixelSize: 15
            color: pane.c.muted
        }
    }

    ScrollView {
        id: scroller
        anchors.fill: parent
        visible: !!pane.net.uuid
        contentWidth: availableWidth
        clip: true
        ColumnLayout {
            x: Math.max(24, (scroller.availableWidth - width) / 2)
            width: Math.min(640, scroller.availableWidth - 48)
            spacing: 14
            Item { Layout.preferredHeight: 10 }
            RowLayout {
                spacing: 16
                SiteIcon { size: 60; glyph: "wifi"; tile: "#1A5F7A" }
                ColumnLayout {
                    spacing: 3
                    Text {
                        text: pane.net.name || ""
                        font.family: "Schibsted Grotesk"; font.pixelSize: 23; font.weight: Font.DemiBold
                        color: pane.c.text
                    }
                    Text {
                        text: pane.net.used ? app.t.wifi_used.replace("%1", app.ago(pane.net.used)) : app.t.wifi_saved
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13
                        color: pane.c.muted
                    }
                }
            }

            Card {
                FieldRow {
                    label: app.t.wifi_name
                    value: pane.secret.ssid || pane.net.name || ""
                    copyAs: "username"
                }
                FieldRow {
                    visible: !!pane.secret.ssid
                    label: app.t.password
                    value: pane.secret.key || ""
                    secret: true; mono: true
                    copyAs: "wifi"
                }
                FieldRow {
                    visible: !!pane.secret.ssid
                    label: app.t.wifi_security
                    value: pane.secret.security || app.t.wifi_open
                    last: true
                }
                OButton {
                    visible: !pane.secret.ssid
                    Layout.margins: 12
                    iconName: "eye"
                    text: pane.asking ? app.t.wifi_asking : app.t.wifi_reveal
                    enabled: !pane.asking
                    onClicked: { pane.asking = true; pane.refused = false; wifi.reveal(pane.uuid) }
                }
            }
            Text {
                visible: pane.refused
                Layout.fillWidth: true
                text: app.t.wifi_refused
                wrapMode: Text.WordWrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                color: pane.c.saffronInk
            }

            Card {
                visible: !!pane.secret.ssid && (pane.secret.qr || []).length > 0
                RowLayout {
                    Layout.fillWidth: true
                    Layout.margins: 18
                    spacing: 22
                    QrCode { rows: pane.secret.qr || []; size: 176 }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        Text {
                            Layout.fillWidth: true
                            text: app.t.wifi_qr_title
                            wrapMode: Text.WordWrap
                            font.family: "Schibsted Grotesk"; font.pixelSize: 16; font.weight: Font.DemiBold
                            color: pane.c.text
                        }
                        Text {
                            Layout.fillWidth: true
                            text: app.t.wifi_qr_lead
                            wrapMode: Text.WordWrap
                            lineHeight: 1.25
                            font.family: "Schibsted Grotesk"; font.pixelSize: 14
                            color: pane.c.muted
                        }
                    }
                }
            }
            Text {
                Layout.fillWidth: true
                text: app.t.wifi_local
                wrapMode: Text.WordWrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                color: pane.c.faint
            }
        }
    }
}
