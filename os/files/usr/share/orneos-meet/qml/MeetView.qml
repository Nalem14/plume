// Meet: the conversations on the left, the chat of the one open in the middle (or the home, with the meetings
// to come), its details or a thread on the right when asked. A call takes the place of the chat (its chat can
// sit beside it); a call started here opens on « Prêt à rejoindre ? », an answered ring joins at once.
// The window of Meet (Main.qml) and the Meet module of Plume both show this view.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Item {
    id: win
    readonly property var c: theme.c
    readonly property bool shown: visible && app.connected
    property bool infoOpen: false
    property bool callChat: false
    // the call shows while its conversation is the open one; another opened meanwhile: its chat, with the
    // call in a small bar on top (the call goes on)
    readonly property bool callShown: calls.active && meet.current === calls.token
    function backToCall() { if (calls.active) meet.open(calls.token) }
    property bool viewKeys: true        // false in Plume: its rail carries the colour, no band
    property alias toast: toast
    signal raiseWanted()
    signal closeWanted()
    signal fullScreenWanted(bool on)

    // "token" or "token#id" (a link to one message: the conversation opens on it)
    function openRoom(token) {
        if (!token) return
        const parts = String(token).split("#")
        if (parts.length > 1 && parseInt(parts[1]) > 0) meet.openAt(parts[0], parseInt(parts[1]))
        else meet.open(parts[0])
        chat.focusComposer()
    }
    function startCall(token, video, now) {
        if (!token) return
        if (meet.current !== token) meet.open(token)
        calls.start(token, app.prefs.join_audio, video === undefined ? app.prefs.join_video : video, !now)
    }

    Connections {
        target: app
        function onToast(message) { toast.show(message) }
        function onRaiseRequested() { win.raiseWanted() }
        function onActionRequested(action, value) {
            if (action === "room") win.openRoom(value)
            else if (action === "call") win.startCall(value)
            else if (action === "answer" || action === "answer_video") { incoming.close(); win.startCall(value, action === "answer_video", true) }
            else if (action === "to") meet.openWith(value)
            else if (action === "address") { const d = JSON.parse(value); meet.openWithAddress(d.address, d.name || "", !!d.video) }
            else if (action === "decline") meet.declineRing(value)
            else if (action === "new") newConversation.start()
            else if (action === "search") sidebar.setSearch(value)
        }
    }
    Connections {
        target: meet
        function onDone(what, ok, message) {
            if (!ok) problem.tell(message)
            else if (message) toast.show(message)
        }
        function onMeetingReady(token) { win.startCall(token, true) }
        function onRoomChanged() { if (meet.thread.token && meet.thread.token !== meet.current) meet.closeThread() }
    }
    Connections {
        target: calls
        function onFailed(message) { problem.tell(message) }
        function onEvent(e) {
            if (e.type === "hand" && e.name) toast.show(app.t.raised_hand.replace("%1", e.name))
            else if (e.type === "forcedMute") toast.show(app.t.forced_mute)
            else if (e.type === "speakingWhileMuted" && !speakingTip.running) { speakingTip.start(); toast.show(app.t.speaking_muted) }
            else if (e.type === "error" && e.code === "no_media") toast.show(app.t.no_media)
            else if (e.type === "error" && e.code === "blur") toast.show(app.t.blur_unavailable)
            else if (e.type === "error" && e.code === "blur_slow") toast.show(app.t.blur_slow)
        }
    }
    Timer { id: speakingTip; interval: 30000 }

    Shortcut { sequence: "Ctrl+N"; enabled: win.shown; onActivated: newConversation.start() }
    Shortcut { sequence: "Ctrl+K"; enabled: win.shown; onActivated: sidebar.focusSearch() }
    Shortcut { sequence: "Ctrl+F"; enabled: win.shown && meet.current !== ""; onActivated: chat.openSearch() }
    Shortcut { sequence: "Ctrl+,"; enabled: win.shown; onActivated: settings.open() }
    Shortcut { sequence: "Ctrl+I"; enabled: win.shown && meet.current !== ""; onActivated: win.infoOpen = !win.infoOpen }
    Shortcut { sequence: "Ctrl+Shift+,"; enabled: win.shown && meet.current !== ""; onActivated: win.roomSettings("") }
    Shortcut { sequence: "Ctrl+D"; enabled: win.shown && calls.active; onActivated: calls.toggleAudio() }
    Shortcut { sequence: "Ctrl+E"; enabled: win.shown && calls.active; onActivated: calls.toggleVideo() }
    Shortcut { sequence: "Ctrl+Shift+H"; enabled: win.shown && calls.active; onActivated: calls.toggleHand() }
    Shortcut { sequence: "Alt+Up"; enabled: win.shown; onActivated: sidebar.step(-1) }
    Shortcut { sequence: "Alt+Down"; enabled: win.shown; onActivated: sidebar.step(1) }
    // push to talk: Space held while muted, outside a text field
    Item {
        focus: calls.active && !chat.typing
        Keys.onPressed: e => { if (e.key === Qt.Key_Space && !e.isAutoRepeat && calls.active && !calls.state.audio) { calls.send("audio", true); pushing.held = true; e.accepted = true } }
        Keys.onReleased: e => { if (e.key === Qt.Key_Space && !e.isAutoRepeat && pushing.held) { calls.send("audio", false); pushing.held = false; e.accepted = true } }
        QtObject { id: pushing; property bool held: false }
    }

    Rectangle { anchors.fill: parent; color: win.c.chrome }

    // not connected: Connect (Orneos OS) or the sign-in of Plume
    EmptyState {
        anchors.centerIn: parent
        visible: !app.connected
        iconName: "video"
        title: app.t.signed_out_title
        lead: app.t.signed_out_lead
        actionText: app.t.connect
        onActivated: app.openConnect()
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0
        visible: app.connected

        Band { Layout.fillHeight: true; visible: win.viewKeys; color: win.c.famCommunicate }
        Sidebar {
            id: sidebar
            Layout.preferredWidth: win.width < 980 ? 280 : 320
            Layout.fillHeight: true
            visible: !(win.callShown && win.width < 1000)
            onOpenRoom: token => win.openRoom(token)
            onNewConversation: newConversation.start()
            onSettingsRequested: settings.open()
            onCallRoom: (token, video) => win.startCall(token, video)
            onHomeWanted: { meet.close(); win.infoOpen = false }
            onRoomSettingsWanted: page => win.roomSettings(page)
        }
        Rectangle { Layout.fillHeight: true; implicitWidth: 1; color: win.c.hairline; visible: sidebar.visible }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            // the call, made only during a call: Chromium starts with the first call, not with the app
            Loader {
                id: stage
                anchors.fill: parent
                anchors.rightMargin: win.callChat && win.callShown ? Math.min(380, parent.width * 0.4) : 0
                active: calls.active
                visible: win.callShown
                source: "CallStage.qml"
                onLoaded: item.chatOpen = Qt.binding(() => win.callChat)
                Connections {
                    target: stage.item
                    ignoreUnknownSignals: true
                    function onChatWanted() { win.callChat = !win.callChat }
                    function onWriteWanted(user) { meet.openWith(user) }
                    function onFullScreenWanted(on) { win.fullScreenWanted(on) }
                }
            }

            // the call goes on while another conversation is open: back to it, the microphone, hang up
            Rectangle {
                id: callBar
                objectName: "callBar"
                z: 5
                visible: calls.active && !win.callShown
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.top: parent.top; anchors.topMargin: 10
                width: Math.min(parent.width - 24, callBarRow.implicitWidth + 24)
                height: 48; radius: 24
                color: "#0B1A33"
                border.width: 1; border.color: Qt.rgba(1, 1, 1, 0.1)
                RowLayout {
                    id: callBarRow
                    anchors.fill: parent
                    anchors.leftMargin: 16; anchors.rightMargin: 6
                    spacing: 8
                    Rectangle {
                        implicitWidth: 8; implicitHeight: 8; radius: 4; color: "#5FC2AC"
                        SequentialAnimation on opacity { running: callBar.visible; loops: Animation.Infinite
                            NumberAnimation { to: 0.35; duration: 900 } NumberAnimation { to: 1; duration: 900 } }
                    }
                    Text { textFormat: Text.PlainText
                        Layout.fillWidth: true
                        Layout.maximumWidth: 260
                        text: calls.name
                        elide: Text.ElideRight
                        font.pixelSize: 13; font.weight: Font.DemiBold; color: "#E8ECF3"
                    }
                    Text {
                        visible: calls.elapsed > 0
                        text: app.duration(calls.elapsed)
                        font.family: "JetBrains Mono"; font.pixelSize: 12; color: "#9AA8BF"
                    }
                    component BarButton: AbstractButton {
                        id: bb
                        property string iconName
                        property string tip
                        property color tint: "transparent"
                        implicitWidth: 36; implicitHeight: 36
                        hoverEnabled: true
                        ToolTip.visible: hovered; ToolTip.text: tip; ToolTip.delay: 500
                        Accessible.name: tip
                        background: Rectangle { radius: 18; color: bb.tint != "transparent" ? bb.tint : (bb.hovered ? Qt.rgba(1, 1, 1, 0.12) : "transparent") }
                        contentItem: Item { Icon { anchors.centerIn: parent; name: bb.iconName; size: 17; color: "#E8ECF3" } }
                    }
                    BarButton {
                        iconName: calls.state.audio ? "mic" : "micOff"
                        tint: calls.state.audio ? "transparent" : "#4A1C17"
                        tip: (calls.state.audio ? app.t.mute : app.t.unmute) + " (Ctrl+D)"
                        enabled: calls.state.hasAudio !== false
                        onClicked: calls.toggleAudio()
                    }
                    BarButton {
                        iconName: calls.state.video ? "video" : "videoOff"
                        tint: calls.state.video ? "transparent" : "#4A1C17"
                        tip: (calls.state.video ? app.t.camera_off : app.t.camera_on) + " (Ctrl+E)"
                        enabled: calls.state.hasVideo !== false
                        onClicked: calls.toggleVideo()
                    }
                    AbstractButton {
                        id: back
                        implicitHeight: 36
                        implicitWidth: backText.implicitWidth + 28
                        hoverEnabled: true
                        onClicked: win.backToCall()
                        background: Rectangle { radius: 18; color: back.hovered ? "#3D5BD6" : "#2A47B8" }
                        contentItem: Text { id: backText; text: app.t.back_to_call; font.pixelSize: 13; font.weight: Font.DemiBold; color: "white"
                                            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                    }
                    BarButton { iconName: "hangup"; tint: "#B8331C"; tip: app.t.hang_up; onClicked: calls.hangup() }
                }
            }

            HomePane {
                anchors.fill: parent
                anchors.topMargin: callBar.visible ? 68 : 0
                visible: meet.current === ""
                onNewConversation: newConversation.start()
                onCallRoom: (token, video) => win.startCall(token, video)
                onPlanWanted: meeting.start(null)
            }

            ChatPane {
                id: chat
                visible: (!win.callShown && meet.current !== "") || (win.callShown && win.callChat)
                anchors.top: parent.top
                anchors.topMargin: callBar.visible ? 68 : 0
                anchors.bottom: parent.bottom
                anchors.right: parent.right
                width: win.callShown ? Math.min(380, parent.width * 0.4) : parent.width
                compact: win.callShown
                infoOpen: win.infoOpen
                onInfoWanted: win.infoOpen = !win.infoOpen
                onCallWanted: video => win.startCall(meet.current, video)
                onNewConversation: newConversation.start()
                onPlanWanted: meeting.start(meet.room)
                onLaterWanted: text => schedule.start(text)
                onScheduledEdit: m => schedule.change(m)
                onBreakoutWanted: breakout.open()
                onRoomSettingsWanted: win.roomSettings("")
            }
        }

        Rectangle { Layout.fillHeight: true; implicitWidth: 1; color: win.c.hairline; visible: thread.visible }
        ThreadPane {
            id: thread
            Layout.preferredWidth: 380
            Layout.fillHeight: true
            visible: !!meet.thread.id && !win.callShown
            onCloseWanted: meet.closeThread()
        }

        Rectangle { Layout.fillHeight: true; implicitWidth: 1; color: win.c.hairline; visible: info.visible }
        RoomInfo {
            id: info
            Layout.preferredWidth: 340
            Layout.fillHeight: true
            visible: win.infoOpen && meet.current !== "" && !win.callShown && !thread.visible
            onCloseWanted: win.infoOpen = false
            onPlanWanted: meeting.start(meet.room)
            onSettingsWanted: page => win.roomSettings(page)
        }
    }

    IncomingCall { id: incoming; onAnswer: (token, video) => { win.raiseWanted(); win.startCall(token, video, true) } }   // a ring answered joins at once
    NewConversation { id: newConversation }
    MeetingDialog { id: meeting }
    ScheduleDialog { id: schedule }
    BreakoutDialog { id: breakout }
    SettingsDialog { id: settings }
    // the settings of the open conversation: built the first time they are asked for
    function roomSettings(page) {
        conversationSettings.active = true
        conversationSettings.item.openAt(page)
    }
    Loader { id: conversationSettings; active: false; sourceComponent: ConversationSettings { objectName: "conversationSettings" } }
    ChoiceDialog { id: choice }
    ODialog {
        id: problem
        property string message
        function tell(text) { message = text; open() }
        title: app.t.problem_title
        Text { textFormat: Text.PlainText;
            width: 360
            text: problem.message
            wrapMode: Text.Wrap
            color: win.c.text
            font.pixelSize: 14
        }
        footer: [OButton { kind: "primary"; text: app.t.ok; onClicked: problem.close() }]
    }
    Toast { id: toast }
}
