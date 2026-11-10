// Settings › Utilisation (the gauge at the bottom of the column opens it): Ornis over the rolling 24 hours, hour by
// hour as in Mon compte › Abonnement, then the AI offers (Config::getAiOffers on orneos.eu). chat.usage comes from
// the cloud (/ornis/usage, which asks orneos.eu for the offer). Changing the offer happens on orneos.eu, which knows
// the plan and the payment (app.openAiOffers: the offer chosen here is preselected there, one click to confirm);
// back in the app, the panel reads the usage again and the new limit shows at once.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ColumnLayout {
    id: panel
    readonly property var c: theme.c
    readonly property var u: chat.usage
    readonly property var ai: u.ai || null
    readonly property int percent: u.percent !== undefined && u.percent !== null ? u.percent
                                   : (chat.quota.percent !== undefined ? chat.quota.percent : -1)
    readonly property var hours: u.hours || []
    readonly property int peak: Math.max(1, ...(hours.length ? hours : [1]))
    readonly property var resets: (ai && ai.resets) ? ai.resets : null
    readonly property int resetCount: resets ? Number(resets.available || 0) : 0
    readonly property bool resetReady: !!(resets && resets.ready)
    property bool sentAway: false          // the browser was opened to change the offer: read again on return
    property bool resetting: false
    spacing: 12

    // Share of the plan's limit. The bar height stays relative to the busiest hour; the figure is what comes back.
    function share(n) {
        const limit = Number(panel.u.limit || 0)
        if (!(limit > 0) || !(n > 0)) return ""
        const pct = 100 * n / limit
        if (pct < 0.095) return app.t.usage_under
        const decimals = pct >= 9.95 ? 0 : 1
        let rounded = decimals === 0 ? Math.round(pct) : Math.round(pct * 10) / 10
        let shown = decimals
        if (shown === 1 && Math.abs(rounded - Math.round(rounded)) < 0.001) {
            shown = 0
            rounded = Math.round(rounded)
        }
        const text = Number(rounded).toLocaleString(Qt.locale(), "f", shown)
        const gap = Qt.locale().name.indexOf("en") === 0 ? "" : " "
        return text + gap + "%"
    }
    function hourLabel(i) {
        const d = new Date(Date.now() - (23 - i) * 3600 * 1000)
        return String(d.getHours()).padStart(2, "0")
    }
    function choose(key) {
        panel.sentAway = true
        app.openAiOffers(key)
    }

    Component.onCompleted: { chat.loadUsage(); chat.loadRegion() }
    Connections {
        target: Qt.application
        function onStateChanged() {
            if (Qt.application.state === Qt.ApplicationActive && panel.sentAway && panel.visible) {
                panel.sentAway = false
                chat.loadUsage()
            }
        }
    }
    onVisibleChanged: if (visible) { chat.loadUsage(); chat.loadRegion() }

    // ---- today ------------------------------------------------------------------------------------------------
    RowLayout {
        Layout.fillWidth: true
        spacing: 16
        Ring {
            implicitWidth: 64; implicitHeight: 64
            lineWidth: 6
            trackColor: panel.c.line
            segments: panel.percent >= 0 ? [{ from: 0, to: Math.max(0.02, panel.percent / 100),
                                               color: panel.percent >= 80 ? panel.c.saffron : panel.c.famCommunicate }] : []
            Text {
                anchors.centerIn: parent
                text: panel.percent >= 0 ? panel.percent + " %" : "–"
                font.family: "JetBrains Mono"; font.pixelSize: 13; font.weight: Font.DemiBold
                color: panel.c.text
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text {
                text: app.t.usage_title
                font.family: "Schibsted Grotesk"; font.pixelSize: 16; font.weight: Font.DemiBold
                color: panel.c.text
            }
            Text {
                Layout.fillWidth: true
                text: panel.percent >= 0 ? app.t.usage_used.replace("%1", panel.percent) + " · " + app.t.usage_window : app.t.usage_none
                wrapMode: Text.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                color: panel.c.muted
            }
            Text {
                visible: panel.ai !== null
                Layout.fillWidth: true
                // never in requests per day (it reads small): the plan, the offer and what it multiplies
                text: !panel.ai ? "" : panel.ai.offer
                      ? app.t.usage_with_offer.replace("%1", panel.ai.plan).replace("%2", (panel.ai.offers.find(o => o.key === panel.ai.offer) || {}).name || "")
                        + " · " + app.t.usage_asks.replace("%1", panel.ai.times)
                      : app.t.usage_plan_only.replace("%1", panel.ai.plan)
                wrapMode: Text.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                color: panel.c.muted
            }
        }
    }

    // ---- hour by hour: what is used now is freed 24 hours later -------------------------------------------------
    ColumnLayout {
        visible: panel.hours.length === 24
        Layout.fillWidth: true
        spacing: 4
        Text {
            text: app.t.usage_hours
            font.family: "Schibsted Grotesk"; font.pixelSize: 12
            color: panel.c.muted
        }
        Item {
            Layout.fillWidth: true
            implicitHeight: 64
            Row {
                id: bars
                anchors.fill: parent
                spacing: 2
                Repeater {
                    model: panel.hours
                    Item {
                        id: slot
                        required property int index
                        required property int modelData
                        width: (bars.width - 23 * bars.spacing) / 24
                        height: bars.height
                        HoverHandler { id: barHover }
                        Rectangle {
                            anchors.bottom: parent.bottom
                            width: parent.width
                            height: slot.modelData > 0 ? Math.max(4, parent.height * slot.modelData / panel.peak) : 2
                            radius: 2
                            color: slot.modelData === 0 ? panel.c.line
                                   : (panel.percent >= 80 ? panel.c.saffron : panel.c.famCommunicate)
                            opacity: barHover.hovered ? 1 : (slot.modelData > 0 ? 0.85 : 1)
                        }
                        ToolTip.visible: barHover.hovered
                        ToolTip.delay: 0
                        ToolTip.text: slot.modelData > 0
                            ? app.t.usage_hour_tip.replace("%1", panel.hourLabel(slot.index)).replace("%2", panel.share(slot.modelData)).replace("%3", slot.index + 1)
                            : app.t.usage_hour_none.replace("%1", panel.hourLabel(slot.index))
                        Accessible.role: Accessible.StaticText
                        Accessible.name: ToolTip.text
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Text { text: app.t.usage_axis_start; font.family: "Schibsted Grotesk"; font.pixelSize: 11; color: panel.c.muted }
            Item { Layout.fillWidth: true }
            Text { text: app.t.usage_axis_now; font.family: "Schibsted Grotesk"; font.pixelSize: 11; color: panel.c.muted }
        }
        Text {
            readonly property int first: panel.hours.findIndex(n => n > 0)
            visible: first >= 0
            Layout.fillWidth: true
            text: first < 0 ? "" : app.t.usage_release.replace("%1", panel.share(panel.hours[first])).replace("%2", first + 1)
            wrapMode: Text.Wrap
            font.family: "Schibsted Grotesk"; font.pixelSize: 12
            color: panel.c.muted
        }
    }
    Text {
        Layout.fillWidth: true
        text: app.t.quota_tip
        wrapMode: Text.Wrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 12
        color: panel.c.muted
    }

    // ---- a gifted reset, used when the person chooses (nothing happens until they confirm) -----------------
    ColumnLayout {
        visible: panel.resetCount > 0
        Layout.fillWidth: true
        spacing: 6
        Text {
            Layout.fillWidth: true
            text: app.plural("reset_count", panel.resetCount)
            wrapMode: Text.Wrap
            font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
            color: panel.c.text
        }
        Text {
            Layout.fillWidth: true
            text: panel.resetReady ? app.t.reset_hint : app.t.reset_early
            wrapMode: Text.Wrap
            font.family: "Schibsted Grotesk"; font.pixelSize: 13
            color: panel.c.muted
        }
        OButton {
            enabled: panel.resetReady && !panel.resetting
            kind: "primary"
            text: app.t.reset_use
            onClicked: confirmReset.ask(app.t.reset_confirm_title, app.t.reset_confirm, [
                { "id": "use", "text": app.t.reset_use, "kind": "primary" },
                { "id": "cancel", "text": app.t.cancel, "kind": "secondary" }
            ], function (id) {
                if (id === "use") {
                    panel.resetting = true
                    chat.useReset()
                }
            })
        }
    }
    Connections {
        target: chat
        function onResetSettled() { panel.resetting = false }
    }
    ChoiceDialog { id: confirmReset; parent: Overlay.overlay }

    // ---- the AI offers ---------------------------------------------------------------------------------------
    Text {
        Layout.topMargin: 10
        text: app.t.offers_title
        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
        font.capitalization: Font.AllUppercase; font.letterSpacing: 0.4
        color: panel.c.muted
    }
    Text {
        Layout.fillWidth: true
        text: !panel.ai ? app.t.offers_offline
              : panel.ai.mode === "member" ? (panel.ai.owner ? app.t.offers_member.replace("%1", panel.ai.owner) : app.t.offers_member_anon)
              : panel.ai.mode === "granted" ? app.t.offers_granted
              : panel.ai.mode === "checkout" ? app.t.offers_lead + " " + app.t.offers_need_plan
              : app.t.offers_lead
        wrapMode: Text.Wrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 13
        color: panel.c.text
    }
    GridLayout {
        id: offerGrid
        visible: panel.ai !== null && (panel.ai.offers || []).length > 0
        Layout.fillWidth: true
        columns: panel.width < 520 ? 1 : 3
        columnSpacing: 10; rowSpacing: 10
        Repeater {
            model: panel.ai ? panel.ai.offers : []
            Rectangle {
                id: card
                required property var modelData
                readonly property bool current: panel.ai && panel.ai.offer === modelData.key
                readonly property bool canChoose: panel.ai && ["personal", "owner", "checkout"].indexOf(panel.ai.mode) >= 0
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.alignment: Qt.AlignTop
                Layout.columnSpan: modelData.key === "ultra" ? offerGrid.columns : 1     // the big one, across
                Layout.preferredWidth: 1
                implicitHeight: cardBody.implicitHeight + 28
                radius: 12
                color: current ? panel.c.tint : panel.c.field
                border.width: current ? 2 : 1
                border.color: current ? panel.c.famCommunicate : modelData.key === "ultra" ? panel.c.saffron : panel.c.line
                ColumnLayout {
                    id: cardBody
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: 14 }
                    spacing: 6
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            Layout.fillWidth: true
                            text: card.modelData.name
                            font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.weight: Font.DemiBold
                            color: card.current ? panel.c.tintText : panel.c.text
                            elide: Text.ElideRight
                        }
                        Text {
                            visible: !card.current && card.modelData.key === "ultra"
                            text: app.t.offer_ultra_flag
                            font.family: "Schibsted Grotesk"; font.pixelSize: 11; font.weight: Font.DemiBold
                            color: panel.c.saffronInk || panel.c.saffron
                        }
                        Text {
                            visible: card.current
                            text: app.t.offer_current
                            font.family: "Schibsted Grotesk"; font.pixelSize: 11; font.weight: Font.DemiBold
                            color: panel.c.famCommunicate
                        }
                    }
                    Text {
                        text: (card.modelData.basis === "pro" ? app.t.offer_asks_pro : app.t.offer_asks).replace("%1", card.modelData.times)
                        font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
                        color: card.current ? panel.c.tintText : panel.c.text
                    }
                    Text {
                        text: card.modelData.price
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13
                        color: panel.c.muted
                    }
                    Text {
                        Layout.fillWidth: true
                        text: card.modelData.pitch
                        wrapMode: Text.Wrap
                        font.family: "Schibsted Grotesk"; font.pixelSize: 12
                        color: panel.c.muted
                    }
                    OButton {
                        visible: card.canChoose && !card.current
                        Layout.topMargin: 4
                        kind: card.modelData.key === "pro" ? "primary" : "secondary"
                        text: app.t.offer_choose
                        onClicked: panel.choose(card.modelData.key)
                    }
                }
            }
        }
    }
    RowLayout {
        visible: !panel.ai || panel.ai.mode !== "member"
        spacing: 8
        OButton {
            kind: "secondary"
            iconName: "star"
            text: panel.ai && panel.ai.offer ? app.t.offers_manage : app.t.offers_compare
            onClicked: panel.choose("")
        }
    }
    Text {
        visible: panel.ai !== null && panel.ai.mode !== "member"
        Layout.fillWidth: true
        text: app.t.offers_back
        wrapMode: Text.Wrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 12
        color: panel.c.muted
    }

    // ---- where Ornis runs (OrnisRegion of the cloud), discreetly at the bottom: Europe by default, « global » after
    // a warning that names each provider and country. Shown once a provider outside Europe is active (or chosen);
    // the cloud keeps the countries accepted, a country added later asks again (needs_consent).
    readonly property var reg: chat.region
    readonly property var regGlobal: (reg.regions || {}).global || {}
    readonly property string regCur: reg.region || "eu"
    readonly property bool regShown: !!regGlobal.available || regCur === "global"
    function regWho(providers) {
        return (providers || []).map(p => p.country_name ? p.name + " (" + p.country_name + ")" : p.name).join(", ")
    }
    function askGlobal() {
        const codes = (panel.regGlobal.providers || []).map(p => p.country).filter(c => !!c)
        regionWarn.ask(app.t.region_warn_title, app.t.region_warn.replace("%1", panel.regWho(panel.regGlobal.providers)), [
            { "id": "accept", "text": app.t.region_accept, "kind": "primary" },
            { "id": "cancel", "text": app.t.cancel, "kind": "secondary" }
        ], function (id) {
            if (id === "accept")
                chat.setRegion("global", codes)
        })
    }
    onRegCurChanged: regionBox.select(regCur)
    ChoiceDialog {
        id: regionWarn
        parent: Overlay.overlay
        onClosed: regionBox.select(panel.regCur)      // cancelled: the box shows the region in force again
    }
    RowLayout {
        visible: panel.regShown
        Layout.fillWidth: true
        Layout.topMargin: 14
        spacing: 16
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text {
                text: app.t.region_title
                font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                color: panel.c.text
            }
            Text {
                Layout.fillWidth: true
                text: (panel.regCur === "global" ? app.t.region_global_desc : app.t.region_eu_desc)
                      .replace("%1", panel.regWho(((panel.reg.regions || {})[panel.regCur] || {}).providers))
                wrapMode: Text.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                color: panel.c.muted
            }
            Text {
                visible: !!panel.reg.needs_consent
                Layout.fillWidth: true
                text: app.t.region_consent
                wrapMode: Text.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold
                color: panel.c.saffronInk || panel.c.saffron
            }
        }
        OComboBox {
            id: regionBox
            Layout.preferredWidth: 170
            Layout.alignment: Qt.AlignTop
            model: [{ text: app.t.region_eu, value: "eu" }, { text: app.t.region_global, value: "global" }]
            Component.onCompleted: select(panel.regCur)
            Accessible.name: app.t.region_title
            onActivated: {
                const v = currentValue
                if (v === panel.regCur && !(v === "global" && panel.reg.needs_consent))
                    return
                if (v === "eu")
                    chat.setRegion("eu", [])
                else
                    panel.askGlobal()
            }
        }
    }
}
