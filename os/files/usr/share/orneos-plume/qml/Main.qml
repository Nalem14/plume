// Plume window: the quiet rail on the left, then the current module. Ctrl+K opens the palette.
// Every module keeps its account and settings at the foot of its side column (AccountBar), like the other apps.
// Notes, Tâches, Mots de passe, Ornis, Meet and the Photothèque are their own apps' views (suite.py), with their own
// sidebar and settings; the Photothèque opens from the grid of apps (the rail keeps the daily ones).
// Courrier, Agenda and Contacts of Orneos OS (plume.edition): the same window with one module, no rail, and the
// family band down its edge instead.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "components"
import "mail"
import "calendar"
import "contacts"
import "settings"
import "suite"

ApplicationWindow {
    id: win
    readonly property var c: theme.c
    // the order of the rail and of Ctrl+1…; the views below follow the same order
    readonly property var modules: plume.modules
    readonly property var allModules: ["mail", "calendar", "contacts", "meet", "notes", "tasks", "passwords", "ornis", "photos"]
    readonly property bool ownModule: ["mail", "calendar", "contacts"].indexOf(plume.module) >= 0
    property var filesWaiting: []
    // Ornis beside the module (Ctrl+J): kept open from one session to the next
    readonly property bool ornisShown: suite.ornisPanel && !!plume.prefs.ornis_panel && plume.module !== "ornis" && plume.connected
    function toggleOrnis(open) {
        plume.setPref("ornis_panel", open === undefined ? !plume.prefs.ornis_panel : open)
        if (plume.prefs.ornis_panel) Qt.callLater(() => { ornisSide.ensure(); if (ornisSide.view) ornisSide.view.focusInput() })
    }
    // what the module shows, for Ornis beside it: {kind, icon, label, text} ({} : nothing to join)
    function ornisAbout() {
        const t = plume.t
        if (plume.module === "mail") {
            const m = mail.current || {}
            const body = m.threadText || m.text || ""
            if (!m.messageId || !body) return {}
            const from = m.from || {}
            return { kind: "mail", icon: "mail", label: m.subject || t.no_subject || "…",
                     text: "From: " + (from.name || "") + " <" + (from.email || "") + ">\nSubject: " + (m.subject || "")
                           + (m.date ? "\nDate: " + m.date : "") + "\n\n" + body + (m.inviteText ? "\n\n" + m.inviteText : "") }
        }
        if (plume.module === "contacts") {
            const card = contactsView.card || {}
            if (!card.fn) return {}
            const list = key => (card[key] || []).map(x => x.value || x).filter(x => typeof x === "string" && x).join(", ")
            return { kind: "contact", icon: "contacts", label: card.fn,
                     text: "Contact: " + card.fn + (card.org ? "\nOrganisation: " + card.org : "")
                           + (list("emails") ? "\nEmails: " + list("emails") : "") + (list("phones") ? "\nPhones: " + list("phones") : "")
                           + (card.note ? "\nNote: " + card.note : "") }
        }
        if (plume.module === "notes" && notesHost.view && notesHost.view.ornisAbout)
            return notesHost.view.ornisAbout()
        if (plume.module === "calendar") {
            const items = calendarView.items || []
            const loc = Qt.locale(plume.locale)
            const range = loc.toString(calendarView.rangeStart, "d MMMM")
            const lines = items.slice(0, 60).map(e => "- " + loc.toString(new Date(e.startTs * 1000), e.allDay ? "ddd d MMM" : "ddd d MMM HH:mm")
                                                  + " · " + (e.title || "") + (e.location ? " (" + e.location + ")" : ""))
            return { kind: "calendar", icon: "calendar", label: t.ornis_about_calendar.replace("%1", range),
                     text: "Calendar shown in Plume from " + range + " (" + calendarView.rangeDays + " days):\n" + (lines.join("\n") || "(nothing)") }
        }
        return {}
    }
    function ornisIdeas() {
        const t = plume.t
        const about = ornisAbout()
        if (about.kind === "mail") return [{ text: t.ornis_idea_mail_summary, icon: "sparkle" }, { text: t.ornis_idea_mail_reply, icon: "reply" },
                                           { text: t.ornis_idea_mail_todo, icon: "checklist" }]
        if (about.kind === "contact") return [{ text: t.ornis_idea_contact_mail, icon: "mail" }, { text: t.ornis_idea_contact_last, icon: "history" }]
        if (about.kind === "calendar") return [{ text: t.ornis_idea_cal_brief, icon: "today" }, { text: t.ornis_idea_cal_free, icon: "clock" }]
        if (about.kind === "note") return [{ text: t.ornis_idea_note_summary, icon: "sparkle" }, { text: t.ornis_idea_note_mail, icon: "mail" },
                                           { text: t.ornis_idea_note_todo, icon: "checklist" }]
        return []
    }
    function updateOrnis() {
        if (!win.ornisShown || !ornisSide.view) return
        suite.setPanelAbout(plume.module, ornisAbout())
        ornisSide.view.ideas = ornisIdeas()
    }
    onOrnisShownChanged: { suite.setPanelShown(ornisShown); if (ornisShown) Qt.callLater(() => { ornisSide.ensure(); win.updateOrnis() }) }
    Connections { target: plume; function onChanged() { Qt.callLater(win.updateOrnis) } }
    Connections { target: mail; function onCurrentChanged() { Qt.callLater(win.updateOrnis) } }
    Connections { target: contactsView; function onCardChanged() { Qt.callLater(win.updateOrnis) } }
    Connections { target: calendarView; function onItemsChanged() { Qt.callLater(win.updateOrnis) } }
    Connections { target: notesHost.view; ignoreUnknownSignals: true; function onSelectedChanged() { Qt.callLater(win.updateOrnis) } function onAboutChanged() { Qt.callLater(win.updateOrnis) } }
    property string messageWaiting: ""

    width: plume.windowSize.width
    height: plume.windowSize.height
    minimumWidth: 900
    minimumHeight: 580
    visible: !plume.startHidden           // started with the session: the tray only
    visibility: plume.windowMaximized ? Window.Maximized : Window.Windowed
    title: plume.connected && plume.unread > 0 && plume.modules.indexOf("mail") >= 0
           ? plume.appName + " · " + plume.t.unread.replace("%1", plume.unread)
           : plume.appName
    color: c.chrome
    font.family: "Schibsted Grotesk"
    font.pixelSize: 14

    onClosing: close => {
        plume.saveWindow(width, height, visibility === Window.Maximized)
        if (plume.keepRunning) {               // the tray keeps Plume (reminders, new mail)
            close.accepted = false
            win.hide()
        }
    }

    Connections {
        target: mail
        function onChanged() {
            if (mail.state === "ready" && win.messageWaiting) {
                const id = win.messageWaiting
                win.messageWaiting = ""
                mail.openByMessageId(id)
            }
            if (mail.state === "ready" && win.filesWaiting.length) {
                const paths = win.filesWaiting
                win.filesWaiting = []
                mailView.composeFiles(paths)
            }
            if (mail.state === "ready" && !plume.prefs.ornis_asked && plume.modules.indexOf("mail") >= 0)
                askAutoSummary.start()
        }
    }

    // the first time mail is ready: should Ornis summarise new messages as they are opened? Asked once.
    Timer {
        id: askAutoSummary
        interval: 1500
        onTriggered: {
            if (plume.prefs.ornis_asked || autoSummaryQuestion.opened)
                return
            plume.setPref("ornis_asked", true)
            autoSummaryQuestion.ask(plume.t.ornis_first_title, plume.t.ornis_first_text,
                                    [{ id: "cancel", text: plume.t.ornis_first_no },
                                     { id: "yes", text: plume.t.ornis_first_yes, kind: "primary" }],
                                    () => { ornis.autoSummary = true })
        }
    }

    Connections {
        target: plume
        function onToast(message) { toast.show(message) }
        function onComposeRequested(uri) {
            if (mail.state === "ready")
                mailView.composeUri(uri)
            else
                plume.composeInCloud(uri)
        }
        function onFilesToSend(paths) {
            if (mail.state === "ready")
                mailView.composeFiles(paths)
            else
                win.filesWaiting = paths          // sent once the mailbox is connected
        }
        function onMessageRequested(id) {
            if (mail.state === "ready")
                mail.openByMessageId(id)
            else
                win.messageWaiting = id           // opened once the mailbox is connected
        }
        function onSettingsRequested(section) { settings.openAt(section) }
        function onActionRequested(id) {
            if (id === "new_message" && mail.state === "ready")
                mailView.compose("new")
            else if (id === "new_message")
                plume.composeInCloud("mailto:")
            else if (id === "new_event")
                calendarView.newEvent(null, false)
            else if (id === "new_contact")
                contactsView.newContact()
        }
        function onRaiseRequested() {
            if (!win.visible)
                win.show()
            if (win.visibility === Window.Minimized)
                win.showNormal()
            win.raise()
            win.requestActivate()
        }
    }

    function openPalette() { commandPalette.open() }

    function runAction(id) {
        if (id.indexOf("go_") === 0)
            plume.open(id.slice(3), "")
        else if (id === "apps")
            apps.open()
        else if (id.indexOf("orn:") === 0)              // Ctrl+K: Ornis (a conversation, a mode, Code, Activité)
            suite.ornisAction(id.slice(4))
        else if (id.indexOf("ornis_") === 0)
            mailView.askOrnis(id.slice(6))
        else if (id === "settings" || id === "add_box")
            settings.openAt(id === "add_box" ? "add_box" : "")
        else if (id === "new_message" || id === "new_event" || id === "new_contact")
            plume.open({ new_message: "mail", new_event: "calendar", new_contact: "contacts" }[id], "--" + id.replace("_", "-"))
    }

    Shortcut { sequence: "Ctrl+K"; onActivated: win.openPalette() }
    Shortcut { sequence: "Ctrl+J"; enabled: suite.ornisPanel && plume.module !== "ornis"; onActivated: win.toggleOrnis() }
    Shortcut { sequence: "Ctrl+,"; enabled: plume.connected && win.ownModule; onActivated: settings.openAt("") }
    Shortcut { sequence: "Ctrl+1"; onActivated: plume.setModule(win.modules[0]) }
    Shortcut { sequence: "Ctrl+2"; enabled: win.modules.length > 1; onActivated: plume.setModule(win.modules[1]) }
    Shortcut { sequence: "Ctrl+3"; enabled: win.modules.length > 2; onActivated: plume.setModule(win.modules[2]) }
    Shortcut { sequence: "Ctrl+4"; enabled: win.modules.length > 3; onActivated: plume.setModule(win.modules[3]) }
    Shortcut { sequence: "Ctrl+5"; enabled: win.modules.length > 4; onActivated: plume.setModule(win.modules[4]) }
    Shortcut { sequence: "Ctrl+6"; enabled: win.modules.length > 5; onActivated: plume.setModule(win.modules[5]) }
    Shortcut { sequence: "Ctrl+7"; enabled: win.modules.length > 6; onActivated: plume.setModule(win.modules[6]) }
    Shortcut { sequence: "Ctrl+8"; enabled: win.modules.length > 7; onActivated: plume.setModule(win.modules[7]) }
    Shortcut { sequence: "Ctrl+9"; enabled: win.modules.length > 8; onActivated: plume.setModule(win.modules[8]) }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Rail { Layout.fillHeight: true; visible: !plume.edition; ornisOpen: win.ornisShown
               onAppsRequested: apps.open(); onOrnisRequested: win.toggleOrnis() }
        Band {
            Layout.fillHeight: true
            visible: !!plume.edition
            color: plume.module === "calendar" ? win.c.famOrganize : win.c.famCommunicate
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // a new version downloaded and checked (updater.py): a strip like a title bar, and at its right the pill
            // « Mettre à jour » that glows until it is clicked (Plume goes, UpdateSplash says it is going in)
            Rectangle {
                id: updateBar
                Layout.fillWidth: true
                readonly property bool on: updater.state === "ready"
                visible: implicitHeight > 0
                implicitHeight: on ? 46 : 0
                Behavior on implicitHeight { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
                clip: true
                color: win.c.chrome
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: win.c.hairline }
                RowLayout {
                    anchors.right: parent.right; anchors.rightMargin: 14
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 12
                    Text {
                        textFormat: Text.PlainText
                        text: plume.t.update_ready.replace("%1", updater.version)
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.Medium
                        color: win.c.muted
                    }
                    AbstractButton {
                        id: updatePill
                        objectName: "updatePill"
                        implicitHeight: 32
                        implicitWidth: pillRow.implicitWidth + 26
                        hoverEnabled: true
                        Accessible.name: updater.replaces ? plume.t.update_restart : plume.t.update_install
                        onClicked: updater.installNow()
                        // the glow that breathes around it
                        Rectangle {
                            anchors.centerIn: parent
                            width: parent.width + 10; height: parent.height + 10; radius: height / 2
                            color: "transparent"
                            border.width: 3; border.color: Qt.alpha(win.c.ok, 0.45)
                            SequentialAnimation on opacity {
                                running: updateBar.on && Qt.application.state === Qt.ApplicationActive; loops: Animation.Infinite
                                NumberAnimation { from: 0.15; to: 1; duration: 900; easing.type: Easing.InOutSine }
                                NumberAnimation { from: 1; to: 0.15; duration: 900; easing.type: Easing.InOutSine }
                            }
                        }
                        background: Rectangle {
                            radius: height / 2
                            gradient: Gradient {
                                GradientStop { position: 0; color: Qt.lighter(win.c.ok, updatePill.hovered ? 1.25 : 1.12) }
                                GradientStop { position: 1; color: updatePill.pressed ? Qt.darker(win.c.ok, 1.1) : win.c.ok }
                            }
                        }
                        contentItem: Item {
                            Row {
                                id: pillRow
                                anchors.centerIn: parent
                                spacing: 8
                                Icon { anchors.verticalCenter: parent.verticalCenter; name: "download"; size: 16; color: win.c.okTint }
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    textFormat: Text.PlainText
                                    text: updater.replaces ? plume.t.update_now : plume.t.update_install
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.Bold
                                    color: win.c.okTint
                                }
                            }
                        }
                        ToolTip.visible: hovered
                        ToolTip.delay: 500
                        ToolTip.text: updater.replaces ? plume.t.update_restart_hint : plume.t.update_install
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: plume.connected || !win.ownModule
                spacing: 0
                StackLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: plume.connected || !win.ownModule
                    currentIndex: win.allModules.indexOf(plume.module)
                    MailView { id: mailView }
                    CalendarView { id: calendarView }
                    ContactsView { id: contactsView }
                    // their own welcome when signed out: they read the same account
                    ModuleHost { kind: "meet" }
                    ModuleHost { id: notesHost; kind: "notes" }
                    ModuleHost { kind: "tasks" }
                    ModuleHost { kind: "passwords" }
                    ModuleHost { kind: "ornis" }
                    ModuleHost { kind: "photos" }
                }
                // Ornis beside (Ctrl+J): the Ornis module's own conversation (suite.mountPanel), made when first opened
                Item {
                    id: ornisSide
                    property var view: null
                    visible: win.ornisShown
                    Layout.fillHeight: true
                    Layout.preferredWidth: Math.round(Math.max(340, Math.min(460, win.width * 0.3)))
                    function ensure() {
                        if (view || !visible) return
                        view = suite.mountPanel(ornisSide)
                        if (!view) return
                        view.anchors.fill = ornisSide
                        view.closeRequested.connect(() => win.toggleOrnis(false))
                        view.expandRequested.connect(() => suite.expandPanel())
                        win.updateOrnis()
                    }
                    onVisibleChanged: ensure()
                }
            }

            EmptyState {
                Layout.fillWidth: true
                Layout.fillHeight: true
                // Orneos OS: Orneos Connect; elsewhere, the cloud's sign-in page in the browser (signin.start)
                readonly property bool waiting: signin.state === "waiting"
                visible: !plume.connected && win.ownModule
                iconName: waiting ? "openExternal" : "lock"
                title: !signin.own ? plume.t.welcome_title : waiting ? plume.t.signin_wait_title : plume.t.signin_title
                lead: !signin.own ? plume.t.welcome_lead : waiting ? plume.t.signin_wait_lead
                      : signin.state === "error" ? signin.error : plume.t.signin_lead
                actionText: !signin.own ? plume.t.welcome_action : waiting ? plume.t.signin_reopen : plume.t.signin_action
                actionIcon: waiting ? "openExternal" : "arrow"
                secondaryText: waiting ? plume.t.cancel : ""
                onActivated: plume.openConnect()
                onSecondary: signin.cancel()
            }
        }
    }

    Toast { id: toast }
    UpdateSplash {}
    // back in front after hours (a computer asleep): one more look for an update
    onActiveChanged: if (active) updater.checkIfStale()

    Connections {
        target: mail
        function onSendQueued() { toast.show(plume.t.sending, plume.t.undo, () => mail.cancelSend(), 6) }
        // archived, deleted, moved: a few seconds to change one's mind
        function onMoveQueued(kind, count) {
            toast.show(plume.t["moved_" + kind] + (count > 1 ? " · " + plume.t.messages_count.replace("%1", count) : ""), plume.t.undo, () => mail.cancelMove(), 6)
        }
    }

    CommandPalette {
        id: commandPalette
        onAction: id => win.runAction(id)
    }

    SettingsDialog { id: settings }
    ChoiceDialog { id: autoSummaryQuestion }
    AppsPanel { id: apps }
    // "Quoi de neuf": the Orneos announcements not read yet, once (news.py; Plume and Courrier only)
    NewsDialog { ready: win.visible && win.active && win.visibility !== Window.Minimized && plume.connected }
}
