// Settings › Utilisation (the gauge at the bottom of the column opens it): Ornis's windows (session, week…: each one's
// share and when it renews, chat.limitView from ornis_limits.py) as in Mon compte › Abonnement, then the AI offers (Config::getAiOffers on orneos.eu). chat.usage comes from
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
    readonly property var resets: (ai && ai.resets) ? ai.resets : null
    readonly property int resetCount: resets ? Number(resets.available || 0) : 0
    readonly property bool resetReady: !!(resets && resets.ready)
    property bool sentAway: false          // the browser was opened to change the offer: read again on return
    property bool resetting: false
    spacing: 12

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

    // ---- the windows: each one's share and when it renews; who used them ---------------------------------------
    ColumnLayout {
        readonly property var lv: chat.limitView || ({})
        visible: (lv.windows || []).length > 0
        Component.onCompleted: chat.loadQuota()
        Layout.fillWidth: true
        spacing: 8
        Text {
            text: app.t.usage_hours
            font.family: "Schibsted Grotesk"; font.pixelSize: 12
            color: panel.c.muted
        }
        Repeater {
            model: parent.lv.windows || []
            ColumnLayout {
                id: win
                required property var modelData
                Layout.fillWidth: true
                spacing: 3
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10
                    Text {
                        Layout.preferredWidth: 150       // the bars start at the same place
                        text: win.modelData.name
                        elide: Text.ElideRight
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                        color: panel.c.text
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 6
                        radius: 3
                        color: panel.c.line
                        Rectangle {
                            width: parent.width * Math.min(1, win.modelData.percent / 100)
                            height: parent.height
                            radius: 3
                            color: win.modelData.level === "full" ? panel.c.danger : win.modelData.level === "warn" ? panel.c.saffron : panel.c.famCommunicate
                        }
                    }
                    Text {
                        text: win.modelData.used
                        font.family: "JetBrains Mono"; font.pixelSize: 12
                        color: win.modelData.level === "full" ? panel.c.danger : panel.c.muted
                    }
                }
                Text {
                    Layout.fillWidth: true
                    text: win.modelData.renew
                    wrapMode: Text.Wrap
                    font.family: "Schibsted Grotesk"; font.pixelSize: 12
                    color: panel.c.muted
                }
                Accessible.role: Accessible.StaticText
                Accessible.name: win.modelData.name + ", " + win.modelData.used + ", " + win.modelData.renew
            }
        }
        Text {
            visible: !!parent.lv.blocked
            Layout.fillWidth: true
            text: parent.lv.blocked ? parent.lv.blocked.when : ""
            wrapMode: Text.Wrap
            font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
            color: panel.c.text
        }
        Text {
            visible: !!parent.lv.sources
            Layout.fillWidth: true
            text: parent.lv.sources || ""
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
