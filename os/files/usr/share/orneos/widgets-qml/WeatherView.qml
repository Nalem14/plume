// SPDX-License-Identifier: GPL-2.0-or-later
// Météo on the desktop: the cloud's weather (weather_status, met.no), for the place of the cloud's
// dashboard. Small: the sky, the temperature and the place; wide or tall: the next hours too.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PC3
import "strings.js" as S

Frame {
    id: root
    signal configureRequested()
    readonly property var feed: bridge
    readonly property var hours: bridge.result.hours || []
    readonly property var now: hours.length ? hours[0] : null
    readonly property var next: hours.slice(1, wide && tall ? 7 : 5)

    family: "media"
    context: S.tr("weather") + (bridge.result.place ? " · " + root.shortPlace(bridge.result.place) : "")
    onOpened: bridge.launch("/usr/libexec/orneos-app dashboard /apps/dashboard/")

    // met.no symbol → Breeze weather icon and a word for it.
    readonly property var skies: [
        ["thunder", "weather-storm", {fr: "Orage", en: "Thunder", de: "Gewitter"}],
        ["sleet", "weather-freezing-rain", {fr: "Neige fondue", en: "Sleet", de: "Schneeregen"}],
        ["snow", "weather-snow", {fr: "Neige", en: "Snow", de: "Schnee"}],
        ["showers", "weather-showers-scattered", {fr: "Averses", en: "Showers", de: "Schauer"}],
        ["rain", "weather-showers", {fr: "Pluie", en: "Rain", de: "Regen"}],
        ["fog", "weather-fog", {fr: "Brouillard", en: "Fog", de: "Nebel"}],
        ["partlycloudy", "weather-few-clouds", {fr: "Éclaircies", en: "Partly cloudy", de: "Teilweise bewölkt"}],
        ["fair", "weather-few-clouds", {fr: "Beau temps", en: "Fair", de: "Heiter"}],
        ["cloudy", "weather-many-clouds", {fr: "Nuageux", en: "Cloudy", de: "Bewölkt"}],
        ["clearsky", "weather-clear", {fr: "Ciel dégagé", en: "Clear", de: "Klar"}]
    ]
    function sky(symbol) { return skies.find(s => String(symbol).indexOf(s[0]) >= 0) || ["", "weather-none-available", {}]; }
    function icon(symbol) {
        const name = sky(symbol)[1];
        const night = /_night$/.test(symbol);
        return night && (name === "weather-clear" || name === "weather-few-clouds") ? name + "-night" : name;
    }
    function word(symbol) { const w = sky(symbol)[2]; return w[Qt.locale().name.slice(0, 2)] || w.en || ""; }
    function temp(value) { return value === null || value === undefined ? "–" : Math.round(value) + "°"; }
    function shortPlace(place) { return String(place).split(",")[0].trim(); }
    function hour(ts) { return new Date(ts * 1000).getHours() + S.tr("hourSuffix"); }

    Bridge { id: bridge; command: "/usr/libexec/orneos-widget weather"; interval: 900000 }

    Skeleton {
        visible: bridge.result.state === "loading"
        Layout.fillWidth: true
        Layout.fillHeight: true
        rows: 2
        lead: false
        tone: Qt.alpha(Kirigami.Theme.textColor, 0.1)
    }
    PC3.Label {
        visible: text !== ""
        Layout.fillWidth: true
        text: bridge.result.state === "noPlace" ? S.tr("noPlace")
              : !bridge.result.ready && bridge.result.state !== "loading" ? S.tr(bridge.result.state === "signed_out" ? "signed_out" : "error") : ""
        wrapMode: Text.WordWrap
        font: Kirigami.Theme.smallFont
        opacity: 0.75
    }
    PC3.Button {
        visible: bridge.result.state === "noPlace" || (!bridge.result.ready && bridge.result.state !== "loading")
        text: bridge.result.state === "noPlace" ? S.tr("place") : bridge.result.state === "signed_out" ? "Orneos Connect" : S.tr("retry")
        icon.name: bridge.result.state === "noPlace" ? "mark-location" : ""
        onClicked: bridge.result.state === "noPlace" ? root.configureRequested()
                   : bridge.result.state === "signed_out" ? bridge.launch("orneos-connect") : bridge.refresh()
    }

    // ── Now, then the next hours: beside it when the widget is wide but low, below it otherwise ──
    GridLayout {
        visible: root.now !== null
        Layout.fillWidth: true
        Layout.fillHeight: true
        columns: root.wide && !root.tall ? 2 : 1
        columnSpacing: Kirigami.Units.largeSpacing * 2
        rowSpacing: Kirigami.Units.smallSpacing
        ColumnLayout {
            Layout.alignment: Qt.AlignTop
            Layout.fillWidth: !root.wide || root.tall
            spacing: Kirigami.Units.smallSpacing
            RowLayout {
                visible: root.now !== null
                Layout.fillWidth: true
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Icon {
                    Layout.preferredWidth: Kirigami.Units.gridUnit * (root.roomy ? 3.6 : 3)
                    Layout.preferredHeight: Layout.preferredWidth
                    source: root.now ? root.icon(root.now.symbol) : ""
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    PC3.Label {
                        text: root.now ? root.temp(root.now.temp) : ""
                        color: root.tint
                        font.pixelSize: Kirigami.Units.gridUnit * (root.roomy ? 2.6 : 2.2)
                        font.weight: Font.Bold
                        font.features: {"tnum": 1}
                    }
                    PC3.Label {
                        Layout.fillWidth: true
                        text: root.now ? root.word(root.now.symbol) : ""
                        elide: Text.ElideRight
                        font.weight: Font.DemiBold
                    }
                }
            }
            PC3.Label {
                visible: root.now !== null && root.roomy
                Layout.fillWidth: true
                text: root.now ? [root.now.wind !== null && root.now.wind !== undefined ? S.fmt("wind", Math.round(root.now.wind * 3.6)) : "",
                                  root.now.rain ? S.fmt("rainMm", Number(root.now.rain).toLocaleString(Qt.locale(), "f", 1)) : ""].filter(x => x).join(" · ") : ""
                elide: Text.ElideRight
                opacity: 0.7
                font: Kirigami.Theme.smallFont
            }
        }
        RowLayout {
            visible: root.roomy && root.next.length > 0
            Layout.fillWidth: true
            Layout.alignment: root.tall ? Qt.AlignBottom : Qt.AlignVCenter
            spacing: 0
            Repeater {
                model: root.next
                delegate: ColumnLayout {
                    id: slot
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: 2
                    PC3.Label {
                        Layout.alignment: Qt.AlignHCenter
                        text: root.hour(slot.modelData.stamp)
                        opacity: 0.65
                        font: Kirigami.Theme.smallFont
                    }
                    Kirigami.Icon {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                        Layout.preferredHeight: Kirigami.Units.iconSizes.medium
                        source: root.icon(slot.modelData.symbol)
                    }
                    PC3.Label {
                        Layout.alignment: Qt.AlignHCenter
                        text: root.temp(slot.modelData.temp)
                        font.weight: Font.DemiBold
                        font.features: {"tnum": 1}
                    }
                }
            }
        }
    }
}
