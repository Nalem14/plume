// Ornis: where to start in the security review, or how to turn on two-factor authentication on a site.
// What is sent is shown first: site names and what is wrong, never a password.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: dialog
    property string kind
    property var query: ({})
    property int request: -1
    property string answer
    property string error
    width: Math.min(600, parent ? parent.width - 48 : 600)
    title: kind === "twofa" ? app.t.ornis_twofa_title.replace("%1", query.label || query.site || "") : app.t.ornis_plan_title

    function ask() {
        answer = ""
        error = ""
        request = ornis.ask(kind, query)
        open()
    }
    function twofa(site, label) {
        kind = "twofa"
        query = { site: site, label: label }
        ask()
    }
    function plan() {
        const review = vault.security
        const bySite = {}
        for (const k of ["breached", "reused", "weak", "twofa"])
            for (const r of review[k] || []) {
                const key = r.site || r.label
                bySite[key] = bySite[key] || { site: r.site, label: r.label, kinds: [] }
                if (bySite[key].kinds.indexOf(k) < 0)
                    bySite[key].kinds.push(k)
            }
        kind = "plan"
        query = { issues: Object.values(bySite) }
        ask()
    }
    Connections {
        target: ornis
        function onAnswered(id, kind, text) { if (id === dialog.request) dialog.answer = text }
        function onFailed(id, kind, message) { if (id === dialog.request) dialog.error = message }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 8
        Icon { name: "lock"; size: 15; color: theme.c.muted }
        Text {
            Layout.fillWidth: true
            text: app.t.ornis_privacy
            wrapMode: Text.WordWrap
            font.family: "Schibsted Grotesk"; font.pixelSize: 13
            color: theme.c.muted
        }
    }
    OrnisThinking { visible: dialog.answer === "" && dialog.error === "" }
    OrnisAnswer {
        visible: dialog.answer !== ""
        Text {
            visible: dialog.answer !== ""
            Layout.fillWidth: true
            text: dialog.answer
            textFormat: Text.MarkdownText
            wrapMode: Text.WordWrap
            lineHeight: 1.3
            font.family: "Schibsted Grotesk"; font.pixelSize: 15
            color: theme.c.text
            onLinkActivated: link => app.openUrl(link)
        }
    }
    Text {
        visible: dialog.error !== ""
        Layout.fillWidth: true
        text: dialog.error
        wrapMode: Text.WordWrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 14
        color: theme.c.saffronInk
    }
    Text {
        visible: dialog.answer !== ""
        Layout.fillWidth: true
        text: app.t.ornis_check
        wrapMode: Text.WordWrap
        font.family: "Schibsted Grotesk"; font.pixelSize: 13
        color: theme.c.faint
    }

    footer: [
        OButton { visible: dialog.error !== ""; kind: "quiet"; iconName: "refresh"; text: app.t.retry; onClicked: dialog.ask() },
        Item { Layout.fillWidth: true },
        OButton { kind: "primary"; text: app.t.done; onClicked: dialog.close() }
    ]
}
