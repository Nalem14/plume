// The Navigateur panel: the browser of the bot open in front (or the person's, in a Code session), live. The page is
// the browser's own window (BrowserWindow.qml) embedded here: you watch the bot work, take over with the mouse and
// keyboard, simulate a phone, open the inspector-free view of a site, and Annoter a part of the page to ask for a
// change. Closing the panel leaves the browser working unseen.
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import "components"

Item {
    id: pane
    property bool shownNow: false
    readonly property string owner: code.bot !== "" ? code.bot : "you"
    readonly property var c: theme.c
    property var st: ({})
    property string watching: ""
    function refresh() { st = browser ? browser.stateOf(owner) : ({}) }
    function watch() {
        if (!browser) return
        const want = shownNow ? owner : ""
        if (watching === want) return
        if (watching !== "") { frame.window = null; browser.setWatched(watching, false) }   // let go first, then hide it
        watching = want
        if (want !== "") {          // the window first (it may not exist yet), then usable, then here
            const w = browser.windowFor(want)
            browser.setWatched(want, true)
            frame.window = w
        }
        refresh()
    }
    onShownNowChanged: watch()
    onOwnerChanged: watch()
    Component.onDestruction: if (browser && watching !== "") browser.setWatched(watching, false)
    Connections { target: browser; function onChanged() { pane.refresh() } }
    // A dialog or menu of the window opened over the panel would be drawn under the page (a native window above the
    // window's items): the page steps aside while one is open.
    property bool covered: false
    function checkCovered() {
        const o = pane.Overlay.overlay
        let any = false
        if (o) for (let i = 0; i < o.children.length; ++i) {      // a dialog or a menu over the page (not a tooltip)
            const k = o.children[i]
            if (!k.visible || k.width < 120 || k.height < 80) continue
            const p = k.mapToItem(pane, 0, 0)
            if (p.x + k.width > 0 && p.x < pane.width && p.y + k.height > 0 && p.y < pane.height) any = true
        }
        covered = any
    }
    Timer { interval: 150; repeat: true; running: pane.shownNow; onTriggered: pane.checkCovered() }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        RowLayout {                                   // back, forward, reload, the address, the screen, Annoter
            Layout.fillWidth: true
            Layout.margins: 8
            spacing: 4
            OButton { kind: "quiet"; iconName: "chevronLeft"; iconSize: 15; height_: 30; enabled: !!pane.st.canBack
                      tip: app.t.browser_back; onClicked: browser.act(pane.owner, "back") }
            OButton { kind: "quiet"; iconName: "chevronRight"; iconSize: 15; height_: 30; enabled: !!pane.st.canForward
                      tip: app.t.browser_forward; onClicked: browser.act(pane.owner, "forward") }
            OButton { kind: "quiet"; iconName: pane.st.loading ? "close" : "refresh"; iconSize: 15; height_: 30
                      tip: pane.st.loading ? app.t.browser_stop : app.t.browser_reload
                      onClicked: browser.act(pane.owner, pane.st.loading ? "stop" : "reload") }
            OTextField {
                id: address
                objectName: "browserAddress"
                Layout.fillWidth: true
                font.pixelSize: 13
                placeholderText: app.t.browser_url_ph
                selectByMouse: true
                text: activeFocus ? text : (pane.st.url && pane.st.url !== "about:blank" ? pane.st.url : "")
                onAccepted: { browser.go(pane.owner, text); focus = false }
            }
            OButton {
                id: sizeBtn
                objectName: "browserSize"
                kind: pane.st.devW > 0 ? "secondary" : "quiet"; iconName: "devices"; iconSize: 15; height_: 30
                text: pane.st.devW > 0 ? pane.st.devW + "×" + pane.st.devH : ""
                tip: app.t.browser_devices
                onClicked: { sizeMenu.parent = sizeBtn; sizeMenu.x = sizeBtn.width - sizeMenu.width; sizeMenu.y = sizeBtn.height + 4
                             sizeMenu.open() }
            }
            OButton { objectName: "browserAnnotate"; kind: pane.st.annotating ? "secondary" : "quiet"; iconName: "edit"; iconSize: 15; height_: 30
                      tip: app.t.browser_annotate + "  (Ctrl+Shift+D)"; onClicked: browser.annotate(pane.owner, !pane.st.annotating) }
            OButton { kind: "quiet"; iconName: "openExternal"; iconSize: 14; height_: 30; tip: app.t.browser_external
                      enabled: !!pane.st.url && pane.st.url !== "about:blank"; onClicked: app.openLink(pane.st.url) }
        }
        OMenu {
            id: sizeMenu
            popupType: Popup.Window      // above the page: the page is a window of its own, an item would open under it
            Repeater {
                model: pane.st.presets || []
                OMenuItem {
                    required property var modelData
                    objectName: "preset-" + modelData.key
                    text: (app.t["browser_preset_" + modelData.key.replace("-", "_")] || modelData.key)
                          + (modelData.w ? "  " + modelData.w + "×" + modelData.h : "")
                    onTriggered: browser.preset(pane.owner, modelData.key)
                }
            }
        }

        Flow {                                        // the tabs, when there are several
            Layout.fillWidth: true
            Layout.leftMargin: 8; Layout.rightMargin: 8; Layout.bottomMargin: 6
            visible: (pane.st.tabs || []).length > 1
            spacing: 4
            Repeater {
                model: pane.st.tabs || []
                AbstractButton {
                    id: tabChip
                    required property var modelData
                    height: 26
                    width: Math.min(180, chipText.implicitWidth + 40)
                    onClicked: browser.switchTab(pane.owner, modelData.index)
                    background: Rectangle { radius: 7; color: tabChip.modelData.current ? pane.c.card : pane.c.hover
                                            border.width: tabChip.modelData.current ? 1 : 0; border.color: pane.c.line }
                    contentItem: RowLayout {
                        spacing: 4
                        Text { id: chipText; Layout.fillWidth: true; leftPadding: 8; elide: Text.ElideRight
                               text: tabChip.modelData.title || tabChip.modelData.url
                               font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: pane.c.text }
                        OButton { kind: "quiet"; iconName: "close"; iconSize: 10; height_: 20
                                  onClicked: { browser.switchTab(pane.owner, tabChip.modelData.index); browser.act(pane.owner, "closetab") } }
                    }
                }
            }
            OButton { kind: "quiet"; iconName: "plus"; iconSize: 12; height_: 26; tip: app.t.browser_new_tab
                      onClicked: browser.act(pane.owner, "newtab") }
        }

        Rectangle {                                   // « Orla lit la page », while the agent drives it
            Layout.fillWidth: true
            Layout.leftMargin: 8; Layout.rightMargin: 8; Layout.bottomMargin: 6
            visible: !!pane.st.activity
            implicitHeight: 30; radius: 8
            color: pane.c.tint
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10
                spacing: 8
                Icon { name: "globe"; size: 14; color: pane.c.tintText }
                Text { Layout.fillWidth: true; text: pane.st.activity || ""; elide: Text.ElideRight
                       font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: pane.c.tintText }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: pane.c.field
            WindowContainer {                         // the browser itself: its own window, live
                id: frame
                objectName: "browserFrame"
                anchors.fill: parent
                visible: !pane.covered
                window: null
            }
            Column {
                anchors.centerIn: parent
                width: parent.width - 48
                spacing: 10
                visible: !browser
                Icon { anchors.horizontalCenter: parent.horizontalCenter; name: "globe"; size: 28; color: pane.c.muted }
                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                       text: app.t.browser_unavailable; font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: pane.c.muted }
            }
        }
    }
    Shortcut { sequence: "Ctrl+Shift+D"; enabled: pane.shownNow && !!browser; onActivated: browser.annotate(pane.owner, !pane.st.annotating) }
}
