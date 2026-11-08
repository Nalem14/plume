// Two lists behind one switch, as in other assistants: the conversations, pinned first then newest first by day
// (the same ones as in the cloud and the top-bar panel), or the tasks Ornis runs on its own; a search for the one
// shown, today's allowance (the ring), and at the foot the account and the settings
// (AccountBar, the same place in every app). The mascot heads the app (docs/ORNIS-MASCOT.md).
// A row's actions: the « … » button, a right click, or the keyboard (F2 renames, Suppr deletes).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Rectangle {
    id: side
    property string view
    property string mode: "chats"        // chats | projects | tasks (Activité: a view over the last list)
    property string listMode: "chats"    // the list shown: chats | projects (Chat | Code)
    property bool searchOpen: false
    property string taskId               // the task shown on the right
    property string query
    signal chosen(string id)
    signal newChat()
    signal newProjectChat(string path)
    signal projectChosen(string id)        // a project of the Work mode: its page
    signal projectCreateRequested()
    signal codeChosen(string folder, string session)
    signal codeMenuRequested(var session, Item item, real x, real y)
    signal projectPickRequested()
    signal modeChosen(string mode)
    signal taskChosen(string id)
    signal jobChosen(string session)
    signal menuRequested(var session, Item item, real x, real y)
    signal deleteRequested(string id)
    signal renameRequested(string id, string title)
    signal settingsRequested()
    signal usageRequested()            // the gauge: Settings › Utilisation
    signal hideRequested()
    readonly property var c: theme.c
    color: c.chrome

    function focusSearch() { searchOpen = true; search.forceActiveFocus(); search.selectAll() }
    function closeSearch() { search.text = ""; searchOpen = false }
    // the tasks of the search, and whether the other list has answers not read yet (a dot on its side of the switch)
    // the Tasks list: the Work jobs (recent, live) then the scheduled tasks, each under its title
    readonly property var tasks: {
        const words = side.query.toLowerCase().split(/\s+/).filter(w => w)
        const match = text => words.every(w => text.toLowerCase().indexOf(w) >= 0)
        const jobs = chat.jobs.filter(j => match(j.title + " " + j.label)).map(j => ({
            kind: "job", id: "job:" + j.session, session: j.session, prompt: j.title, repeat: j.label,
            status: j.status, unread: j.unread, section: app.t.jobs_section }))
        const scheduled = chat.scheduled.filter(t => match(t.prompt + " " + t.repeat)).map(t => Object.assign({ kind: "task", section: app.t.scheduled_section }, t))
        // Code working in a folder of this computer (its session goes on while another conversation is open)
        const coding = code.busy && code.session && match((code.title || "") + " " + (code.folderName || ""))
            ? [{ kind: "code", id: "code:" + code.session, session: code.session, folder: code.folder, prompt: code.title || app.t.code_new,
                 repeat: app.t.mode_code + " · " + (code.folderName || ""), status: "running", unread: 0, section: app.t.jobs_section }] : []
        return coding.concat(jobs).concat(scheduled)
    }
    readonly property bool chatsUnread: chat.sessions.some(s => s.unread > 0)
    // what works in the background now (goals, research, Code): counted beside « Activité »
    readonly property int running: chat.jobs.filter(j => j.status === "running").length + (code.busy ? 1 : 0)
    readonly property bool tasksUnread: chat.scheduled.some(t => t.unread > 0) || chat.jobs.some(j => j.unread > 0)
    readonly property var shownList: listMode === "projects" ? projectList : list


    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 8

        // the app's name, then search and hide: icons, as in Vibe and ChatGPT (the list keeps the room)
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 2
            spacing: 2
            Icon { Layout.leftMargin: 2; name: "ornis-mascot"; size: 24 }
            Text {
                Layout.fillWidth: true
                Layout.leftMargin: 6
                text: app.t.app_name
                font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                font.capitalization: Font.AllUppercase; font.letterSpacing: 0.9
                color: side.c.famCommunicate
            }
            OButton {
                id: searchButton
                kind: "quiet"; iconName: "search"; iconSize: 17; height_: 30
                tip: (side.listMode === "projects" ? app.t.code_search : app.t.search_tip) + "  (Ctrl+F)"
                onClicked: side.searchOpen ? side.closeSearch() : side.focusSearch()
                background: Rectangle { radius: 8; color: side.searchOpen ? side.c.tint : searchButton.hovered ? side.c.hover : "transparent" }
            }
            OButton {                        // the views of the list: what to show, how to group it (Chat)
                id: viewButton
                visible: side.listMode === "chats"
                readonly property bool custom: chat.listFilter !== "all" || chat.listGroup !== "date"
                kind: "quiet"; iconName: "sort"; iconSize: 17; height_: 30; tip: app.t.list_view_tip
                onClicked: {
                    const at = viewButton.mapToItem(side, 0, viewButton.height + 4)
                    viewMenu.x = Math.min(at.x, side.width - viewMenu.implicitWidth - 8)
                    viewMenu.y = at.y
                    viewMenu.open()
                }
                background: Rectangle {
                    radius: 8
                    color: viewButton.custom ? side.c.tint : viewButton.hovered || viewMenu.opened ? side.c.hover : "transparent"
                    border.width: viewButton.custom ? 1 : 0; border.color: side.c.accentLine
                }
            }
            OButton {
                kind: "quiet"; iconName: "sidebar"; iconSize: 17; height_: 30; tip: app.t.hide_sidebar + "  (Ctrl+B)"
                onClicked: side.hideRequested()
            }
        }

        // the search, opened by its icon or Ctrl+F; Échap closes it
        OTextField {
            id: search
            Layout.fillWidth: true
            visible: side.searchOpen
            iconName: "search"
            placeholderText: side.listMode === "projects" ? app.t.code_search : app.t.search
            onTextChanged: { side.query = text; chat.setQuery(text) }
            Keys.onDownPressed: { side.shownList.currentIndex = 0; side.shownList.forceActiveFocus() }
            Keys.onEscapePressed: side.closeSearch()
        }
        // a view other than the default: said here, and undone in one click
        RowLayout {
            visible: side.listMode === "chats" && viewButton.custom
            Layout.fillWidth: true
            spacing: 6
            Text {
                Layout.fillWidth: true
                Layout.leftMargin: 4
                text: [chat.listFilter !== "all" ? app.t["filter_" + chat.listFilter] : "",
                       chat.listGroup !== "date" ? app.t["list_by_" + chat.listGroup] : ""].filter(x => x).join(" · ")
                elide: Text.ElideRight
                font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.Medium
                color: side.c.tintText
            }
            OButton {
                kind: "quiet"; iconName: "close"; iconSize: 12; height_: 22; tip: app.t.filter_reset
                onClicked: { chat.setListFilter("all"); chat.setListGroup("date") }
            }
        }

        // Chat | Code: the mode first (Claude, Vibe), a pill that slides to the one chosen
        Rectangle {
            id: segments
            visible: app.prefs.local_tools !== false
            Layout.fillWidth: true
            Layout.topMargin: 2
            implicitHeight: 36
            radius: 11
            color: side.c.field
            border.width: 1; border.color: side.c.line
            Accessible.role: Accessible.PageTabList
            Accessible.name: app.t.mode_switch
            readonly property real half: (width - 6) / 2
            Rectangle {                      // the pill under the mode chosen
                x: 3 + (side.listMode === "projects" ? segments.half : 0)
                y: 3
                width: segments.half; height: segments.height - 6
                radius: 8
                color: side.c.card
                border.width: 1; border.color: side.c.line
                Behavior on x { enabled: Qt.styleHints.reduceMotion !== true; NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
                Rectangle {                  // a hint of depth under it
                    z: -1
                    anchors { left: parent.left; right: parent.right; top: parent.top; topMargin: 2 }
                    height: parent.height; radius: parent.radius
                    color: Qt.rgba(0, 0, 0, theme.dark ? 0.35 : 0.06)
                }
            }
            Row {
                anchors.fill: parent
                anchors.margins: 3
                Repeater {
                    model: [
                        { key: "chats", label: app.t.seg_chat, icon: "chat", dot: side.chatsUnread },
                        { key: "projects", label: app.t.seg_code, icon: "code", dot: false }
                    ]
                    AbstractButton {
                        id: seg
                        required property var modelData
                        readonly property bool on: side.listMode === modelData.key
                        width: segments.half; height: parent.height
                        hoverEnabled: true
                        onClicked: side.modeChosen(modelData.key)
                        Accessible.role: Accessible.PageTab
                        Accessible.name: modelData.label + (modelData.dot ? ", " + app.t.unread : "")
                                         + (modelData.key === "projects" && !chat.paid ? ", " + app.t.seg_locked : "")
                        Accessible.selected: on
                        background: Rectangle {
                            radius: 8
                            color: !seg.on && seg.hovered ? side.c.hover : "transparent"
                            border.width: seg.visualFocus ? 2 : 0; border.color: side.c.saffron
                        }
                        contentItem: Item {
                            Row {
                                anchors.centerIn: parent
                                spacing: 7
                                Icon { anchors.verticalCenter: parent.verticalCenter; name: seg.modelData.icon; size: 15
                                       color: seg.on ? side.c.famCommunicate : side.c.muted
                                       Behavior on color { ColorAnimation { duration: 160 } } }
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: seg.modelData.label
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                                    font.weight: seg.on ? Font.DemiBold : Font.Medium
                                    color: seg.on ? side.c.text : side.c.muted
                                    Behavior on color { ColorAnimation { duration: 160 } }
                                }
                                Icon {                   // Code on a free plan: the plans open instead
                                    visible: seg.modelData.key === "projects" && !chat.paid
                                    anchors.verticalCenter: parent.verticalCenter
                                    name: "lock"; size: 12; color: side.c.muted
                                }
                                Rectangle {
                                    visible: seg.modelData.dot && !seg.on
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: 7; height: 7; radius: 3.5
                                    color: side.c.action
                                }
                            }
                        }
                    }
                }
            }
        }

        // what to do next, in the mode chosen, then the background work (a view, shown over either list)
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1
            AbstractButton {                 // « Nouvelle discussion » or « Nouvelle session »: follows Chat | Code
                id: newRow
                Layout.fillWidth: true
                implicitHeight: 36
                hoverEnabled: true
                onClicked: side.newChat()
                readonly property string label: side.listMode === "projects" ? app.t.new_session : app.t.new_discussion
                Accessible.name: label
                background: Rectangle {
                    radius: 8
                    color: newRow.down ? side.c.tint : newRow.hovered ? side.c.hover : "transparent"
                    Behavior on color { ColorAnimation { duration: 120 } }
                    border.width: newRow.visualFocus ? 2 : 0
                    border.color: side.c.saffron
                }
                contentItem: RowLayout {
                    spacing: 10
                    Rectangle {              // the « + » in a small tile of the family's colour: the way in
                        Layout.leftMargin: 2
                        implicitWidth: 22; implicitHeight: 22; radius: 7
                        color: side.c.famCommunicate
                        Icon { anchors.centerIn: parent; name: "plus"; size: 14; color: "white" }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: newRow.label
                        elide: Text.ElideRight
                        font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
                        color: side.c.text
                    }
                    Text {
                        visible: newRow.hovered
                        Layout.rightMargin: 8
                        text: "Ctrl+N"
                        font.family: "JetBrains Mono"; font.pixelSize: 11
                        color: side.c.muted
                    }
                }
            }
            AbstractButton {                 // Activité: what works in the background (objectifs, recherches, Code, tâches)
                id: activityRow
                readonly property bool on: side.mode === "tasks"
                Layout.fillWidth: true
                implicitHeight: 36
                hoverEnabled: true
                onClicked: side.modeChosen("tasks")
                Accessible.name: app.t.mode_tasks + (side.running > 0 ? ", " + app.plural("running_count", side.running) : "")
                                 + (side.tasksUnread ? ", " + app.t.unread : "")
                ToolTip.text: app.t.mode_tasks + "  (Ctrl+Shift+S)"; ToolTip.delay: 600; ToolTip.visible: hovered
                background: Rectangle {
                    radius: 8
                    color: activityRow.on ? side.c.card : activityRow.hovered ? side.c.hover : "transparent"
                    Behavior on color { ColorAnimation { duration: 120 } }
                    border.width: activityRow.visualFocus ? 2 : 0
                    border.color: side.c.saffron
                    Band {
                        visible: activityRow.on
                        anchors { left: parent.left; top: parent.top; bottom: parent.bottom; topMargin: 9; bottomMargin: 9 }
                        radius: 1.5
                        color: side.c.famCommunicate
                    }
                }
                contentItem: RowLayout {
                    spacing: 10
                    Item {
                        Layout.leftMargin: 2
                        implicitWidth: 22; implicitHeight: 22
                        Icon { anchors.centerIn: parent; name: "repeat"; size: 16; color: activityRow.on ? side.c.famCommunicate : side.c.muted }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: app.t.mode_tasks
                        elide: Text.ElideRight
                        font.family: "Schibsted Grotesk"; font.pixelSize: 14
                        font.weight: activityRow.on ? Font.DemiBold : Font.Normal
                        color: side.c.text
                    }
                    Rectangle {                  // « 2 en cours », with a beat
                        visible: side.running > 0
                        Layout.rightMargin: side.tasksUnread && !activityRow.on ? 0 : 6
                        implicitWidth: runRow.implicitWidth + 14; implicitHeight: 20
                        radius: 10
                        color: side.c.tint
                        Row {
                            id: runRow
                            anchors.centerIn: parent
                            spacing: 5
                            Rectangle {
                                anchors.verticalCenter: parent.verticalCenter
                                width: 6; height: 6; radius: 3
                                color: side.c.famCommunicate
                                SequentialAnimation on opacity {
                                    running: side.running > 0 && Qt.styleHints.reduceMotion !== true
                                    loops: Animation.Infinite
                                    NumberAnimation { from: 1; to: 0.3; duration: 650; easing.type: Easing.InOutSine }
                                    NumberAnimation { from: 0.3; to: 1; duration: 650; easing.type: Easing.InOutSine }
                                }
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: app.plural("running_count", side.running)
                                font.family: "Schibsted Grotesk"; font.pixelSize: 11; font.weight: Font.DemiBold
                                color: side.c.tintText
                            }
                        }
                    }
                    Rectangle {
                        visible: side.tasksUnread && !activityRow.on
                        Layout.rightMargin: 8
                        implicitWidth: 8; implicitHeight: 8; radius: 4
                        color: side.c.action
                    }
                }
            }
        }

        ListView {
            id: list
            visible: side.listMode === "chats"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: chat.sessions
            spacing: 1
            currentIndex: -1
            keyNavigationEnabled: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            readonly property var focused: currentIndex >= 0 && currentIndex < count ? chat.sessions[currentIndex] : null
            Keys.onReturnPressed: if (focused) side.chosen(focused.id)
            Keys.onDeletePressed: if (focused) side.deleteRequested(focused.id)
            Keys.onPressed: event => {
                if (event.key === Qt.Key_F2 && focused) { side.renameRequested(focused.id, focused.title); event.accepted = true }
                else if (event.key === Qt.Key_Menu && focused && currentItem) {
                    side.menuRequested(focused, currentItem, currentItem.width - 40, currentItem.height); event.accepted = true
                }
            }
            Keys.onUpPressed: event => { if (currentIndex <= 0) search.forceActiveFocus(); else decrementCurrentIndex() }

            // the Work mode's projects first, as in ChatGPT: a new one, then the most recent ones (their conversations
            // are under them, not in the list below; a search still finds them)
            header: ColumnLayout {
                width: ListView.view.width
                spacing: 1
                visible: !side.query
                height: visible ? implicitHeight : 0
                property bool showAll: false
                readonly property var shown: projects.items.slice(0, showAll ? 50 : 5)
                Text {
                    topPadding: 8; bottomPadding: 4; leftPadding: 10
                    text: app.t.projects_section
                    font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold
                    color: side.c.muted
                }
                AbstractButton {
                    id: newProj
                    Layout.fillWidth: true
                    implicitHeight: 36
                    hoverEnabled: true
                    onClicked: side.projectCreateRequested()
                    Accessible.name: app.t.project_new
                    background: Rectangle { radius: 7; color: newProj.hovered ? side.c.hover : "transparent" }
                    contentItem: RowLayout {
                        spacing: 9
                        Item { implicitWidth: 2 }
                        Icon { name: "folderPlus"; size: 16; color: side.c.muted }
                        Text { Layout.fillWidth: true; text: app.t.project_new; font.family: "Schibsted Grotesk"; font.pixelSize: 14; color: side.c.text }
                    }
                }
                Repeater {
                    model: parent.shown
                    AbstractButton {
                        id: projRow
                        required property var modelData
                        readonly property bool active: side.view === "project" && projects.opened === modelData.id
                                                       || side.view === "chat" && chat.project === modelData.id
                        readonly property var tones: [side.c.famCommunicate, side.c.famDocs, side.c.famOrganize, side.c.famMedia, side.c.famSpace, side.c.famTools]
                        Layout.fillWidth: true
                        implicitHeight: 36
                        hoverEnabled: true
                        onClicked: side.projectChosen(modelData.id)
                        Accessible.name: modelData.name + ", " + app.plural("project_chats", modelData.count)
                        ToolTip.text: modelData.folderSub ? modelData.name + "\n" + modelData.folderSub : modelData.name
                        ToolTip.visible: hovered
                        ToolTip.delay: 700
                        background: Rectangle {
                            radius: 7
                            color: projRow.active ? side.c.card : projRow.hovered ? side.c.hover : "transparent"
                        }
                        contentItem: RowLayout {
                            spacing: 9
                            Item { implicitWidth: 2 }
                            Rectangle {
                                implicitWidth: 20; implicitHeight: 20; radius: 6
                                color: projRow.tones[projRow.modelData.tone || 0]
                                Text { anchors.centerIn: parent; text: projRow.modelData.initial; font.family: "Schibsted Grotesk"; font.pixelSize: 11; font.weight: Font.Bold; color: "white" }
                            }
                            Text {
                                Layout.fillWidth: true
                                text: projRow.modelData.name
                                elide: Text.ElideRight
                                font.family: "Schibsted Grotesk"; font.pixelSize: 14
                                font.weight: projRow.active ? Font.DemiBold : Font.Normal
                                color: side.c.text
                            }
                            Text {
                                visible: projRow.modelData.count > 0
                                rightPadding: 8
                                text: projRow.modelData.count
                                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                                color: side.c.muted
                            }
                        }
                    }
                }
                AbstractButton {
                    visible: projects.items.length > 5
                    Layout.fillWidth: true
                    implicitHeight: 30
                    onClicked: parent.showAll = !parent.showAll
                    background: null
                    contentItem: Text {
                        leftPadding: 39
                        text: parent.parent.showAll ? app.t.project_show_less : app.t.project_show_more.replace("%1", projects.items.length - 5)
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13
                        color: side.c.muted
                    }
                }
            }

            section.property: "group"
            section.delegate: Text {
                required property string section
                width: ListView.view.width
                topPadding: 12; bottomPadding: 6; leftPadding: 10
                text: section
                font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold
                color: side.c.muted
            }
            delegate: AbstractButton {
                id: row
                required property var modelData
                required property int index
                readonly property bool active: side.view === "chat" && modelData.id === chat.current
                readonly property bool unread: (modelData.unread || 0) > 0     // answers not read yet (every device)
                readonly property bool keyed: row.Window.activeFocusItem === list && list.currentIndex === index
                width: ListView.view.width
                implicitHeight: 38
                hoverEnabled: true
                onClicked: { list.currentIndex = index; side.chosen(modelData.id) }
                Accessible.name: unread ? modelData.label + ", " + app.t.unread : modelData.label
                background: Rectangle {
                    radius: 7
                    color: row.active ? side.c.card : row.hovered || moreButton.down ? side.c.hover : "transparent"
                    Behavior on color { ColorAnimation { duration: 120 } }
                    border.width: row.keyed ? 2 : 0
                    border.color: side.c.saffron
                    Band {
                        visible: row.active
                        anchors { left: parent.left; top: parent.top; bottom: parent.bottom; topMargin: 8; bottomMargin: 8 }
                        radius: 1.5
                        color: side.c.famCommunicate
                    }
                }
                TapHandler {
                    acceptedButtons: Qt.RightButton
                    onTapped: event => side.menuRequested(row.modelData, row, event.position.x, event.position.y)
                }
                contentItem: RowLayout {
                    spacing: 8
                    Item { implicitWidth: 2 }
                    Icon {
                        visible: row.modelData.scheduled || row.modelData.pending || row.modelData.pinned
                        name: row.modelData.pending ? "warning" : row.modelData.scheduled ? "repeat" : "pushpin"
                        size: 15
                        color: row.modelData.pending ? side.c.saffronInk : side.c.muted
                    }
                    Text {
                        Layout.fillWidth: true
                        text: row.modelData.label
                        elide: Text.ElideRight
                        font.family: "Schibsted Grotesk"; font.pixelSize: 14
                        font.weight: row.active || row.unread ? Font.DemiBold : Font.Normal
                        color: side.c.text
                    }
                    Rectangle {
                        visible: (row.modelData.projectName || "") !== "" && !moreButton.visible && chat.listGroup !== "project"
                        implicitWidth: Math.min(78, wsTagRow.implicitWidth + 10)
                        implicitHeight: 19
                        radius: 6
                        color: side.c.tint
                        Row {
                            id: wsTagRow
                            anchors.centerIn: parent
                            spacing: 3
                            Icon {
                                anchors.verticalCenter: parent.verticalCenter
                                name: "folder"; size: 10
                                color: side.c.tintText
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                width: Math.min(54, implicitWidth)
                                text: row.modelData.projectName || ""
                                elide: Text.ElideRight
                                font.family: "Schibsted Grotesk"; font.pixelSize: 11; font.weight: Font.Medium
                                color: side.c.tintText
                            }
                        }
                    }
                    Rectangle {                  // a dot, as in every messenger
                        visible: row.unread && !moreButton.visible
                        implicitWidth: 8; implicitHeight: 8; radius: 4
                        color: side.c.action
                    }
                    OButton {
                        id: moreButton
                        visible: row.hovered || row.active || row.keyed
                        kind: "quiet"; iconName: "more"; iconSize: 16; height_: 26
                        tip: app.t.more
                        onClicked: side.menuRequested(row.modelData, moreButton, 0, moreButton.height + 4)
                    }
                }
            }

            Column {
                anchors.horizontalCenter: parent.horizontalCenter
                y: 24
                width: parent.width - 20
                spacing: 10
                visible: list.count === 0 && chat.count > 0 && (side.query || viewButton.custom)
                Text {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    text: side.query ? app.t.no_results : app.t.filter_empty
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                    color: side.c.muted
                }
                OButton {
                    visible: !side.query && viewButton.custom
                    anchors.horizontalCenter: parent.horizontalCenter
                    kind: "quiet"; text: app.t.filter_reset
                    onClicked: { chat.setListFilter("all"); chat.setListGroup("date") }
                }
            }
        }

        // Code: folders scroll above; local cron tasks stick below with their own scroll (Hermès-style)
        ColumnLayout {
            visible: side.listMode === "projects"
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

        ListView {
            id: projectList
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 2
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            currentIndex: -1
            model: code.folders.filter(p => {
                if (!side.query) return true
                const q = side.query.toLowerCase()
                return (p.name + " " + p.sub).toLowerCase().indexOf(q) >= 0
                    || code.recent.some(s => s.folder === p.path && (s.title || "").toLowerCase().indexOf(q) >= 0)
            })
            delegate: Column {
                id: folderBlock
                required property var modelData
                required property int index
                // its sessions (on this computer only), pinned first; a search keeps the ones it finds
                // Cron runs live under the Cron section; a search still finds them here
                readonly property var sessions: code.recent.filter(s => s.folder === modelData.path
                        && (!s.cron || side.query)
                        && (!side.query || (s.title || "").toLowerCase().indexOf(side.query.toLowerCase()) >= 0
                            || (modelData.name || "").toLowerCase().indexOf(side.query.toLowerCase()) >= 0))
                    .map(s => ({ id: s.id, label: s.title || app.t.code_new, when: s.when, folder: s.folder, title: s.title,
                                 pinned: !!s.pinned, unread: s.unread || 0, code: true }))
                readonly property bool folded: !side.query && (app.prefs.projects_folded || []).indexOf(modelData.path) >= 0
                readonly property bool holdsOpen: side.view === "code" && code.folder === modelData.path
                property bool showAll: false
                width: ListView.view.width
                topPadding: index === 0 ? 2 : 8
                spacing: 1

                AbstractButton {             // the heading: the folder's name; a click folds or unfolds it
                    id: head
                    width: parent.width
                    implicitHeight: 32
                    hoverEnabled: true
                    onClicked: app.toggleProjectFold(folderBlock.modelData.path)
                    Accessible.name: folderBlock.modelData.name + ", " + app.plural("project_chats", folderBlock.sessions.length)
                                     + ", " + (folderBlock.folded ? app.t.project_unfold : app.t.project_fold)
                    ToolTip.visible: hovered && !headPlus.hovered && !headMore.hovered
                    ToolTip.delay: 700
                    ToolTip.text: folderBlock.modelData.missing ? folderBlock.modelData.path + "\n" + app.t.project_missing : folderBlock.modelData.path
                    background: Rectangle { radius: 8; color: head.hovered || folderMenu.opened ? side.c.hover : "transparent"
                        Behavior on color { ColorAnimation { duration: 120 } } }
                    TapHandler {
                        acceptedButtons: Qt.RightButton
                        onTapped: event => { folderMenu.x = Math.min(event.position.x, head.width - folderMenu.implicitWidth); folderMenu.y = event.position.y; folderMenu.open() }
                    }
                    contentItem: RowLayout {
                        spacing: 7
                        Item { implicitWidth: 2 }
                        Icon {
                            name: "chevronDown"; size: 12; color: side.c.faint
                            rotation: folderBlock.folded ? -90 : 0
                            Behavior on rotation { enabled: Qt.styleHints.reduceMotion !== true; NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
                        }
                        Icon {
                            name: "folder"; size: 15
                            color: folderBlock.holdsOpen ? side.c.famCommunicate : side.c.muted
                            opacity: folderBlock.modelData.missing ? 0.45 : 1
                        }
                        Text {
                            Layout.fillWidth: true
                            text: folderBlock.modelData.name
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                            color: folderBlock.modelData.missing ? side.c.muted : folderBlock.holdsOpen ? side.c.text : side.c.muted
                            font.strikeout: !!folderBlock.modelData.missing
                        }
                        Text {                   // folded: how many it hides
                            visible: folderBlock.folded && folderBlock.sessions.length > 0 && !head.hovered
                            Layout.rightMargin: 8
                            text: folderBlock.sessions.length
                            font.family: "Schibsted Grotesk"; font.pixelSize: 11
                            font.features: { "tnum": 1 }
                            color: side.c.faint
                        }
                        OButton {
                            id: headPlus
                            visible: head.hovered || folderMenu.opened
                            enabled: !folderBlock.modelData.missing
                            kind: "quiet"; iconName: "plus"; iconSize: 15; height_: 24
                            tip: app.t.folder_new_session
                            onClicked: side.newProjectChat(folderBlock.modelData.path)
                        }
                        OButton {
                            id: headMore
                            visible: head.hovered || folderMenu.opened
                            Layout.rightMargin: 2
                            kind: "quiet"; iconName: "more"; iconSize: 15; height_: 24
                            tip: app.t.more
                            onClicked: { folderMenu.x = head.width - folderMenu.implicitWidth; folderMenu.y = head.height + 2; folderMenu.open() }
                        }
                    }
                    OMenu {
                        id: folderMenu
                        OMenuItem { text: app.t.folder_new_session; iconName: "plus"; enabled: !folderBlock.modelData.missing
                                    onTriggered: side.newProjectChat(folderBlock.modelData.path) }
                        OMenuItem { text: app.t.project_open_folder; iconName: "folder"; enabled: !folderBlock.modelData.missing
                                    onTriggered: app.openFolder(folderBlock.modelData.path) }
                        OMenuItem { text: folderBlock.folded ? app.t.project_unfold : app.t.project_fold
                                    iconName: folderBlock.folded ? "expand" : "collapse"
                                    onTriggered: app.toggleProjectFold(folderBlock.modelData.path) }
                        Rectangle { width: parent ? parent.width : 0; height: 1; color: side.c.hairline }
                        OMenuItem { text: app.t.project_remove; iconName: "close"; onTriggered: code.forgetFolder(folderBlock.modelData.path) }
                    }
                }

                Repeater {                   // the sessions: plain rows, the open one as in Chat
                    model: folderBlock.folded ? [] : folderBlock.sessions.slice(0, folderBlock.showAll || side.query ? 50 : 5)
                    AbstractButton {
                        id: sRow
                        required property var modelData
                        readonly property bool current: side.view === "code" && modelData.id === code.session
                        width: folderBlock.width
                        implicitHeight: 34
                        hoverEnabled: true
                        onClicked: side.codeChosen(modelData.folder, modelData.id)
                        Accessible.name: modelData.label + (modelData.unread ? ", " + app.t.unread : "")
                        background: Rectangle {
                            radius: 8
                            color: sRow.current ? side.c.card : sRow.hovered ? side.c.hover : "transparent"
                    Behavior on color { ColorAnimation { duration: 120 } }
                            Band {
                                visible: sRow.current
                                anchors { left: parent.left; top: parent.top; bottom: parent.bottom; topMargin: 9; bottomMargin: 9 }
                                radius: 1.5
                                color: side.c.famCommunicate
                            }
                        }
                        TapHandler {
                            acceptedButtons: Qt.RightButton
                            onTapped: event => side.codeMenuRequested(sRow.modelData, sRow, event.position.x, event.position.y)
                        }
                        contentItem: RowLayout {
                            spacing: 7
                            Item { implicitWidth: 42 }   // under the folder's name
                            Text {
                                Layout.fillWidth: true
                                text: sRow.modelData.label
                                elide: Text.ElideRight
                                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                                font.weight: sRow.current || sRow.modelData.unread ? Font.DemiBold : Font.Normal
                                color: side.c.text
                            }
                            Rectangle {
                                visible: sRow.modelData.unread > 0
                                implicitWidth: 7; implicitHeight: 7; radius: 3.5
                                color: side.c.action
                            }
                            Rectangle {              // Ornis works in it now: a beat instead of the time
                                visible: code.busy && sRow.modelData.id === code.session
                                implicitWidth: 7; implicitHeight: 7; radius: 3.5
                                color: side.c.famCommunicate
                                SequentialAnimation on opacity {
                                    running: parent.visible && Qt.styleHints.reduceMotion !== true
                                    loops: Animation.Infinite
                                    NumberAnimation { from: 1; to: 0.3; duration: 650; easing.type: Easing.InOutSine }
                                    NumberAnimation { from: 0.3; to: 1; duration: 650; easing.type: Easing.InOutSine }
                                }
                            }
                            Icon { visible: sRow.modelData.pinned && !sRow.hovered; name: "pushpin"; size: 12; color: side.c.faint }
                            Text {                   // today its time, else its day (« 04/11 »): the title keeps the room
                                visible: !(code.busy && sRow.modelData.id === code.session) && !sRow.hovered
                                text: String(sRow.modelData.when || "").split(" ")[0]
                                font.family: "Schibsted Grotesk"; font.pixelSize: 11
                                font.features: { "tnum": 1 }
                                color: side.c.faint
                            }
                            OButton {
                                id: sMore
                                visible: sRow.hovered
                                kind: "quiet"; iconName: "more"; iconSize: 15; height_: 24
                                tip: app.t.more
                                onClicked: side.codeMenuRequested(sRow.modelData, sMore, 0, sMore.height + 4)
                            }
                            Item { implicitWidth: 2 }
                        }
                    }
                }
                AbstractButton {             // more of them
                    id: moreSessions
                    visible: !folderBlock.folded && !side.query && folderBlock.sessions.length > 5
                    x: 44
                    implicitHeight: 26
                    implicitWidth: moreLabel.implicitWidth + 16
                    hoverEnabled: true
                    onClicked: folderBlock.showAll = !folderBlock.showAll
                    background: Rectangle { radius: 7; color: moreSessions.hovered ? side.c.hover : "transparent" }
                    contentItem: Text {
                        id: moreLabel
                        leftPadding: 8
                        text: folderBlock.showAll ? app.t.project_show_less : app.t.project_show_more.replace("%1", folderBlock.sessions.length - 5)
                        font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.Medium
                        color: side.c.accent
                        verticalAlignment: Text.AlignVCenter
                    }
                }
                AbstractButton {             // nothing in it yet: the way to start
                    id: startHere
                    visible: !folderBlock.folded && folderBlock.sessions.length === 0 && !folderBlock.modelData.missing && !side.query
                    width: folderBlock.width
                    implicitHeight: 30
                    hoverEnabled: true
                    onClicked: side.newProjectChat(folderBlock.modelData.path)
                    background: Rectangle { radius: 8; color: startHere.hovered ? side.c.hover : "transparent" }
                    contentItem: RowLayout {
                        spacing: 7
                        Item { implicitWidth: 40 }
                        Icon { name: "plus"; size: 12; color: startHere.hovered ? side.c.accent : side.c.faint }
                        Text {
                            Layout.fillWidth: true
                            text: app.t.folder_start
                            font.family: "Schibsted Grotesk"; font.pixelSize: 12
                            color: startHere.hovered ? side.c.accent : side.c.faint
                        }
                    }
                }
            }

            footer: Item {
                width: ListView.view.width
                height: projectList.count > 0 ? openRow.implicitHeight + 14 : 0
                visible: projectList.count > 0
                AbstractButton {             // another folder to work in
                    id: openRow
                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                    implicitHeight: 34
                    hoverEnabled: true
                    onClicked: side.projectPickRequested()
                    Accessible.name: app.t.projects_add
                    background: Rectangle { radius: 8; color: openRow.hovered ? side.c.hover : "transparent" }
                    contentItem: RowLayout {
                        spacing: 7
                        Item { implicitWidth: 21 }
                        Icon { name: "folderPlus"; size: 15; color: openRow.hovered ? side.c.accent : side.c.muted }
                        Text {
                            Layout.fillWidth: true
                            text: app.t.projects_add
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13
                            color: openRow.hovered ? side.c.accent : side.c.muted
                        }
                    }
                }
            }

            Column {                         // no folder yet
                anchors.horizontalCenter: parent.horizontalCenter
                y: 28
                width: parent.width - 20
                spacing: 12
                visible: projectList.count === 0
                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: 48; height: 48; radius: 14
                    color: side.c.tint
                    Icon { anchors.centerIn: parent; name: "code"; size: 22; color: side.c.tintText }
                }
                Text {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    text: side.query ? app.t.no_results : app.t.code_tab_lead
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                    color: side.c.muted
                }
                OButton {
                    visible: !side.query
                    anchors.horizontalCenter: parent.horizontalCenter
                    kind: "secondary"; iconName: "folderPlus"; text: app.t.projects_add
                    onClicked: side.projectPickRequested()
                }
            }
        }

        // sticky Cron block: own scroll, under the folders
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: cronBox.height
            Layout.maximumHeight: Math.max(120, parent.height * 0.38)
            color: "transparent"
            Column {
                id: cronBox
                width: parent.width
                Rectangle { width: parent.width; height: 1; color: side.c.hairline }
                RowLayout {
                    width: parent.width
                    height: 30
                    spacing: 6
                    Item { implicitWidth: 4 }
                    Icon { name: "clock"; size: 13; color: side.c.faint }
                    Text {
                        text: app.t.cron_section
                        font.family: "Schibsted Grotesk"; font.pixelSize: 11; font.weight: Font.DemiBold
                        font.capitalization: Font.AllUppercase
                        color: side.c.faint
                    }
                    Item { Layout.fillWidth: true }
                    OButton {
                        kind: "quiet"; iconName: "plus"; iconSize: 14; height_: 24
                        tip: app.t.cron_new
                        onClicked: cron.manage("")
                    }
                    Item { implicitWidth: 2 }
                }
                ListView {
                    id: cronList
                    width: parent.width
                    height: Math.min(contentHeight, Math.max(72, side.height * 0.32))
                    clip: true
                    spacing: 1
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                    model: cron.tasks.filter(t => {
                        if (!side.query) return true
                        const q = side.query.toLowerCase()
                        return (t.title + " " + t.id + " " + (t.scheduleLabel || "")).toLowerCase().indexOf(q) >= 0
                    })
                    delegate: Column {
                        id: cronBlock
                        required property var modelData
                        width: ListView.view.width
                        property bool showAll: false
                        AbstractButton {
                            id: cronHead
                            width: parent.width
                            implicitHeight: 34
                            hoverEnabled: true
                            opacity: modelData.paused ? 0.55 : 1
                            onClicked: cron.toggleExpand(modelData.id)
                            background: Rectangle { radius: 8; color: cronHead.hovered ? side.c.hover : "transparent" }
                            contentItem: RowLayout {
                                spacing: 6
                                Item { implicitWidth: 2 }
                                Icon {
                                    name: "chevronDown"; size: 11; color: side.c.faint
                                    rotation: modelData.expanded ? 0 : -90
                                    Behavior on rotation { enabled: Qt.styleHints.reduceMotion !== true; NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: modelData.title
                                    elide: Text.ElideRight
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                                    font.weight: Font.DemiBold
                                    color: side.c.text
                                }
                                Text {
                                    visible: !!modelData.pending && !modelData.running
                                    text: app.t.cron_pending
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 10
                                    color: side.c.faint
                                }
                                Rectangle {
                                    visible: modelData.running
                                    implicitWidth: 7; implicitHeight: 7; radius: 3.5
                                    color: side.c.famCommunicate
                                    SequentialAnimation on opacity {
                                        running: parent.visible && Qt.styleHints.reduceMotion !== true
                                        loops: Animation.Infinite
                                        NumberAnimation { from: 1; to: 0.3; duration: 650; easing.type: Easing.InOutSine }
                                        NumberAnimation { from: 0.3; to: 1; duration: 650; easing.type: Easing.InOutSine }
                                    }
                                }
                                OButton {
                                    visible: cronHead.hovered || modelData.running
                                    kind: "quiet"; iconName: "bolt"; iconSize: 14; height_: 24
                                    tip: app.t.cron_run_now
                                    enabled: !modelData.running && !modelData.paused
                                    onClicked: cron.runNow(modelData.id)
                                }
                                OButton {
                                    visible: cronHead.hovered
                                    kind: "quiet"; iconName: "clock"; iconSize: 14; height_: 24
                                    tip: app.t.cron_manage
                                    onClicked: cron.manage(modelData.id)
                                }
                                Item { implicitWidth: 2 }
                            }
                        }
                        Repeater {
                            model: modelData.expanded ? (cronBlock.showAll ? modelData.sessions : modelData.shownSessions) : []
                            AbstractButton {
                                id: cronRun
                                required property var modelData
                                width: cronBlock.width
                                implicitHeight: 30
                                hoverEnabled: true
                                onClicked: cron.openRun(modelData.folder, modelData.id)
                                background: Rectangle {
                                    radius: 8
                                    color: (side.view === "code" && modelData.id === code.session) ? side.c.card
                                           : cronRun.hovered ? side.c.hover : "transparent"
                                }
                                contentItem: RowLayout {
                                    spacing: 6
                                    Item { implicitWidth: 42 }
                                    Text {
                                        Layout.fillWidth: true
                                        text: modelData.status === "running" && modelData.summary
                                              ? modelData.summary
                                              : (modelData.when || modelData.summary || modelData.id)
                                        elide: Text.ElideRight
                                        font.family: "Schibsted Grotesk"; font.pixelSize: 12
                                        color: side.c.text
                                    }
                                    Text {
                                        visible: modelData.status && modelData.status !== "ok"
                                        text: modelData.status
                                        font.family: "Schibsted Grotesk"; font.pixelSize: 10
                                        color: side.c.faint
                                    }
                                    Item { implicitWidth: 4 }
                                }
                            }
                        }
                        AbstractButton {
                            visible: modelData.expanded && modelData.moreSessions > 0
                            x: 44
                            implicitHeight: 24
                            implicitWidth: cronMoreLabel.implicitWidth + 16
                            onClicked: cronBlock.showAll = !cronBlock.showAll
                            contentItem: Text {
                                id: cronMoreLabel
                                leftPadding: 8
                                text: cronBlock.showAll ? app.t.project_show_less
                                      : app.t.project_show_more.replace("%1", modelData.moreSessions)
                                font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.Medium
                                color: side.c.accent
                            }
                        }
                    }
                    Column {
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: 8
                        width: parent.width - 16
                        visible: cronList.count === 0
                        Text {
                            width: parent.width
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.Wrap
                            text: app.t.cron_empty
                            font.family: "Schibsted Grotesk"; font.pixelSize: 12
                            color: side.c.faint
                        }
                    }
                }
            }
        }
        } // ColumnLayout Code + Cron


        QuotaGauge { Layout.fillWidth: true; Layout.leftMargin: 4; onDetailsRequested: side.usageRequested() }
        OMenu {
            id: viewMenu
            parent: side
            implicitWidth: 236
            heading: app.t.list_show
            Repeater {
                model: ["all", "unread", "pinned", "projects", "loose", "pending", "remembered", "jobs", "archived"]
                OMenuItem {
                    required property string modelData
                    visible: (modelData !== "projects" && modelData !== "loose") || projects.items.length > 0
                    text: app.t["filter_" + modelData]
                    iconName: chat.listFilter === modelData ? "check" : ""
                    leftPadding: chat.listFilter === modelData ? 10 : 38
                    onTriggered: chat.setListFilter(modelData)
                }
            }
            Rectangle { width: parent ? parent.width : 0; height: 9; color: "transparent"
                Rectangle { anchors.centerIn: parent; width: parent.width - 12; height: 1; color: side.c.line } }
            Text {
                leftPadding: 10; topPadding: 2; bottomPadding: 4
                text: app.t.list_group_by
                font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: Font.DemiBold
                color: side.c.muted
            }
            Repeater {
                model: app.prefs.local_tools !== false ? ["date", "project", "status"] : ["date", "status"]
                OMenuItem {
                    required property string modelData
                    text: app.t["group_" + modelData]
                    iconName: chat.listGroup === modelData ? "check" : ""
                    leftPadding: chat.listGroup === modelData ? 10 : 38
                    onTriggered: chat.setListGroup(modelData)
                }
            }
        }
        AccountBar {
            Layout.fillWidth: true
            Layout.leftMargin: -4; Layout.rightMargin: -4; Layout.bottomMargin: -6
            name: app.profile.name || ""
            email: app.profile.email || ""
            initials: app.profile.initials || ""
            onSettingsRequested: side.settingsRequested()
            OMenuItem { text: app.t.open_cloud; iconName: "cloud"; onTriggered: app.openCloud("") }
            OMenuItem { text: app.t.quota_more; iconName: "star"; onTriggered: side.usageRequested() }
            OMenuItem { text: app.t.reconnect; iconName: "refresh"; onTriggered: app.openConnect() }
        }
    }
}
