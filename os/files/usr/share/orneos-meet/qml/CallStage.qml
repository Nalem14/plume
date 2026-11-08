// The call: the page of the engine (meet_core/engine, Chromium's WebRTC) draws the people; around it, in QML,
// the name and the duration on top, and the bar: microphone, camera, screen, hand, reactions, layout, the chat
// beside, the devices and the blur, breakout rooms, hang up. The stage is always dark (the faces light it).
// Before joining, « Prêt à rejoindre ? »: our picture in a card, the microphone's level, the devices, the blur,
// who is already there, « Rejoindre ». While it connects, a quiet card says so.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtWebEngine
import QtWebChannel
import "components"

Rectangle {
    id: stage
    objectName: "callStage"
    readonly property var c: theme.c
    readonly property var s: calls.state
    readonly property bool preview: calls.phase === "preview"
    readonly property bool connecting: calls.phase === "preparing" || calls.phase === "ready" || calls.phase === "joining"
    // the stage's own ink: light on the night, whatever the theme
    readonly property color ink: "#E8ECF3"
    readonly property color inkMuted: "#9AA8BF"
    readonly property color glass: Qt.rgba(0.06, 0.11, 0.2, 0.86)
    readonly property color glassLine: Qt.rgba(1, 1, 1, 0.08)
    readonly property var inCall: meet.participants.filter(p => p.inCall > 0 && !p.self)
    property bool fullScreen: false
    property bool chatOpen: false          // the chat beside (MeetView): its messages are seen
    property bool peopleOpen: false
    property string pinnedKey: ""
    property int unseenChat: 0             // messages of the call's conversation while its chat is closed
    onChatOpenChanged: if (chatOpen) unseenChat = 0
    Connections {
        target: meet
        function onArrivedHere(count) { if (!stage.chatOpen && meet.current === calls.token) stage.unseenChat += count }
    }
    Connections {
        target: calls
        function onEvent(e) { if (e.type === "tileMenu") tileMenu.show(e) }
    }
    // everyone in the call, ourselves first, raised hands next (in the order they rose), then by name
    readonly property var callPeople: {
        const own = { session: "self", key: "self", self: true, name: app.profile.name || app.t.stage_you, userId: app.profile.user || "",
                      audio: !!stage.s.audio, video: !!stage.s.video, hand: !!stage.s.hand, speaking: !!stage.s.speaking, screen: !!stage.s.screen }
        const others = (stage.s.people || []).map(p => Object.assign({ key: p.session, self: false }, p))
        others.sort((a, b) => (b.hand - a.hand) || String(a.name).localeCompare(String(b.name)))
        return [own].concat(others)
    }
    signal chatWanted()
    signal writeWanted(string user)
    signal fullScreenWanted(bool on)
    color: "#060D1A"

    // the card of « Prêt à rejoindre ? » (our picture goes in it)
    readonly property bool wide: width > 900
    Item {
        id: frame
        x: stage.wide ? 40 : 24
        y: stage.wide ? 40 : 24
        width: stage.wide ? stage.width * 0.58 - 60 : stage.width - 48
        height: stage.wide ? stage.height - 80 : Math.max(180, stage.height - panel.implicitHeight - 72)
    }

    // the page, loaded at once (the camera comes before the call)
    Rectangle {
        id: webClip
        x: stage.preview ? frame.x : 0
        y: stage.preview ? frame.y : 0
        width: stage.preview ? frame.width : stage.width
        height: stage.preview ? frame.height : stage.height
        radius: stage.preview ? 20 : 0
        color: "transparent"
        clip: true
        WebEngineView {
            id: web
            anchors.fill: parent
            backgroundColor: stage.color
            settings.playbackRequiresUserGesture: false
            settings.screenCaptureEnabled: true
            settings.localContentCanAccessRemoteUrls: true
            settings.localContentCanAccessFileUrls: true
            settings.javascriptCanAccessClipboard: false
            settings.showScrollBars: false
            onPermissionRequested: permission => {
                const media = [WebEnginePermission.PermissionType.MediaAudioCapture, WebEnginePermission.PermissionType.MediaVideoCapture,
                               WebEnginePermission.PermissionType.MediaAudioVideoCapture, WebEnginePermission.PermissionType.DesktopVideoCapture,
                               WebEnginePermission.PermissionType.DesktopAudioVideoCapture]
                if (media.indexOf(permission.permissionType) >= 0 && String(permission.origin).startsWith("file://")) permission.grant()
                else permission.deny()
            }
            onDesktopMediaRequested: request => screenPicker.ask(request)
            onNewWindowRequested: request => app.openUrl(String(request.requestedUrl))
            onJavaScriptConsoleMessage: (level, message) => { if (level === WebEngineView.ErrorMessageLevel) console.warn("call:", message) }
            Connections {
                target: calls
                function onChanged() { stage.attach() }
            }
            Component.onCompleted: stage.attach()
        }
        // the camera is off: our initials in the card
        ColumnLayout {
            anchors.centerIn: parent
            visible: stage.preview && !stage.s.video
            spacing: 12
            Rectangle {
                Layout.alignment: Qt.AlignHCenter
                implicitWidth: 104; implicitHeight: 104; radius: 52
                gradient: Gradient { GradientStop { position: 0; color: "#2A47B8" } GradientStop { position: 1; color: "#002FA7" } }
                Text { anchors.centerIn: parent; text: app.profile.initials || ""; font.pixelSize: 38; font.weight: Font.DemiBold; color: "white" }
            }
            Text { Layout.alignment: Qt.AlignHCenter; text: stage.s.hasVideo === false ? app.t.no_camera : app.t.camera_is_off; color: stage.inkMuted; font.pixelSize: 14 }
        }
    }
    // the page speaks to Python through the bridge of the call (window.bridge)
    WebChannel { id: channel }
    property var registered: null
    function attach() {
        const call = calls.call
        if (registered) { channel.deregisterObject(registered); registered = null }
        if (!call) { web.url = "about:blank"; return }
        const load = () => {
            channel.registerObject("bridge", call.bridgeObject)
            registered = call.bridgeObject
            web.webChannel = channel
            web.url = call.url
        }
        if (call.bridgeObject) load(); else call.ready.connect(load)
    }

    component Round: AbstractButton {
        id: round
        property string iconName
        property string tip
        property bool on: true
        property bool lit: false
        property real size: 46
        property int badge: 0
        implicitWidth: size; implicitHeight: size
        hoverEnabled: true
        ToolTip.visible: hovered && tip !== ""
        ToolTip.text: tip
        ToolTip.delay: 500
        Accessible.name: tip
        background: Rectangle {
            radius: round.size / 2
            color: !round.on ? "#4A1C17" : (round.lit ? Qt.rgba(0.49, 0.58, 1, 0.28) : (round.hovered ? Qt.rgba(1, 1, 1, 0.12) : Qt.rgba(1, 1, 1, 0.05)))
            border.width: round.visualFocus ? 2 : (round.lit ? 1 : 0)
            border.color: round.visualFocus ? "#F0A202" : Qt.rgba(0.6, 0.67, 1, 0.5)
        }
        contentItem: Item {
            Icon { anchors.centerIn: parent; name: round.iconName; size: 20; color: round.on ? stage.ink : "#FF8A70" }
            Rectangle {
                visible: round.badge > 0
                anchors.right: parent.right; anchors.top: parent.top; anchors.margins: -2
                implicitWidth: Math.max(18, badgeText.implicitWidth + 8); implicitHeight: 18; radius: 9
                color: "#F0A202"
                Text { id: badgeText; anchors.centerIn: parent; text: round.badge > 99 ? "99+" : round.badge; font.pixelSize: 10; font.weight: Font.Bold; color: "#1A1200" }
            }
        }
        opacity: enabled ? 1 : 0.4
    }

    // ---- before the call -------------------------------------------------------------------------------
    Rectangle {
        id: panel
        visible: stage.preview
        x: stage.wide ? stage.width * 0.58 : 24
        y: stage.wide ? (stage.height - implicitHeight) / 2 : frame.y + frame.height + 24
        width: stage.wide ? stage.width * 0.42 - 40 : stage.width - 48
        implicitHeight: panelColumn.implicitHeight + 48
        radius: 20
        color: stage.glass
        border.width: 1; border.color: stage.glassLine
        ColumnLayout {
            id: panelColumn
            x: 24; y: 24
            width: parent.width - 48
            spacing: 14
            Text {
                text: app.t.ready_kicker
                font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                font.capitalization: Font.AllUppercase; font.letterSpacing: 0.9
                color: "#8A9EFF"
            }
            Text { textFormat: Text.PlainText;
                Layout.fillWidth: true
                text: calls.name
                wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight
                font.family: "Schibsted Grotesk"; font.pixelSize: 26; font.weight: Font.Bold; font.letterSpacing: -0.5
                color: stage.ink
            }
            RowLayout {
                spacing: -8
                Repeater {
                    model: stage.inCall.slice(0, 4)
                    Rectangle {
                        required property var modelData
                        implicitWidth: 32; implicitHeight: 32; radius: 16; color: stage.color
                        RoomAvatar { anchors.centerIn: parent; size: 28; source: parent.modelData.avatar; name: parent.modelData.name }
                    }
                }
                Text {
                    Layout.leftMargin: stage.inCall.length ? 18 : 0
                    text: stage.inCall.length === 0 ? app.t.nobody_yet
                          : stage.inCall.length === 1 ? app.t.one_in_call.replace("%1", stage.inCall[0].name)
                          : app.t.many_in_call.replace("%1", stage.inCall[0].name).replace("%2", stage.inCall.length - 1)
                    font.pixelSize: 14; color: stage.inkMuted
                }
            }
            RowLayout {
                Layout.topMargin: 6
                spacing: 10
                Round {
                    iconName: stage.s.audio ? "mic" : "micOff"; on: !!stage.s.audio
                    enabled: stage.s.hasAudio !== false
                    tip: stage.s.audio ? app.t.mute : app.t.unmute
                    onClicked: calls.toggleAudio()
                }
                Round {
                    iconName: stage.s.video ? "video" : "videoOff"; on: !!stage.s.video
                    enabled: stage.s.hasVideo !== false
                    tip: stage.s.video ? app.t.camera_off : app.t.camera_on
                    onClicked: calls.toggleVideo()
                }
                Round {
                    iconName: "sparkle"; lit: !!stage.s.blur
                    enabled: stage.s.hasVideo !== false
                    tip: stage.s.blur ? app.t.blur_off : app.t.blur_on
                    onClicked: calls.setBlur(!stage.s.blur)
                    BusyIndicator { anchors.centerIn: parent; running: calls.blurLoading; visible: running; implicitWidth: 40; implicitHeight: 40 }
                }
                // the microphone's level
                Row {
                    Layout.leftMargin: 6
                    spacing: 3
                    Repeater {
                        model: 10
                        Rectangle {
                            required property int index
                            width: 5; height: 6 + index * 2; radius: 2
                            anchors.bottom: parent.bottom
                            color: stage.s.audio && calls.level * 10 > index ? (index > 7 ? "#F0A202" : "#5FC2AC") : Qt.rgba(1, 1, 1, 0.12)
                        }
                    }
                }
            }
            Repeater {
                model: [["audioinput", app.t.microphone, "mic"], ["videoinput", app.t.camera, "camera"]]
                ColumnLayout {
                    id: kind
                    required property var modelData
                    readonly property var list: calls.devices.filter(d => d.kind === modelData[0] && d.id !== "default" && d.id !== "communications")
                    visible: list.length > 1
                    Layout.fillWidth: true
                    spacing: 4
                    Text { textFormat: Text.PlainText; text: kind.modelData[1]; font.pixelSize: 12; font.weight: Font.DemiBold; color: stage.inkMuted }
                    OComboBox {
                        Layout.fillWidth: true
                        model: kind.list.map(d => ({ text: d.label || app.t.device_unnamed, value: d.id }))
                        currentIndex: Math.max(0, kind.list.findIndex(d => d.id === (app.prefs[kind.modelData[2]] || "")))
                        onActivated: index => calls.send(kind.modelData[2], kind.list[index].id)
                    }
                }
            }
            RowLayout {
                Layout.topMargin: 8
                Layout.fillWidth: true
                spacing: 10
                OButton { text: app.t.cancel; height_: 44; onClicked: calls.hangup() }
                AbstractButton {
                    id: joinButton
                    Layout.fillWidth: true
                    implicitHeight: 48
                    hoverEnabled: true
                    focus: stage.preview
                    onClicked: calls.join()
                    Keys.onReturnPressed: calls.join()
                    Accessible.name: app.t.join_now
                    background: Rectangle {
                        radius: 12
                        gradient: Gradient {
                            GradientStop { position: 0; color: joinButton.hovered ? "#3D5BD6" : "#2A47B8" }
                            GradientStop { position: 1; color: "#002FA7" }
                        }
                        border.width: joinButton.visualFocus ? 2 : 0; border.color: "#F0A202"
                    }
                    contentItem: RowLayout {
                        spacing: 8
                        Item { Layout.fillWidth: true }
                        Icon { name: "video"; size: 20; color: "white" }
                        Text { text: app.t.join_now; font.pixelSize: 16; font.weight: Font.DemiBold; color: "white" }
                        Item { Layout.fillWidth: true }
                    }
                }
            }
        }
    }

    // ---- connecting --------------------------------------------------------------------------------------
    Rectangle {
        anchors.centerIn: parent
        visible: stage.connecting
        width: 320; height: 120; radius: 18
        color: stage.glass
        border.width: 1; border.color: stage.glassLine
        ColumnLayout {
            anchors.centerIn: parent
            spacing: 10
            BusyIndicator { Layout.alignment: Qt.AlignHCenter; running: stage.connecting; implicitWidth: 32; implicitHeight: 32 }
            Text { textFormat: Text.PlainText; Layout.alignment: Qt.AlignHCenter; text: app.t.call_connecting.replace("%1", calls.name); color: stage.ink; font.pixelSize: 14 }
        }
    }

    // ---- top: who, how long -------------------------------------------------------------------------------
    Rectangle {
        visible: !stage.preview
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 14 }
        height: 44; radius: 22
        color: stage.glass
        border.width: 1; border.color: stage.glassLine
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 18; anchors.rightMargin: 8
            spacing: 10
            Rectangle {
                implicitWidth: 8; implicitHeight: 8; radius: 4
                color: stage.s.published ? "#5FC2AC" : "#F0A202"
                SequentialAnimation on opacity { running: !stage.s.published; loops: Animation.Infinite
                    NumberAnimation { to: 0.3; duration: 700 } NumberAnimation { to: 1; duration: 700 } }
            }
            Text { textFormat: Text.PlainText; Layout.fillWidth: true; text: calls.name; elide: Text.ElideRight; font.pixelSize: 14; font.weight: Font.DemiBold; color: stage.ink }
            Rectangle {
                visible: !!meet.room.breakout
                implicitWidth: brText.implicitWidth + 16; implicitHeight: 22; radius: 11
                color: Qt.rgba(0.49, 0.58, 1, 0.22)
                Text { id: brText; anchors.centerIn: parent; text: app.t.kind_breakout; font.pixelSize: 11; font.weight: Font.DemiBold; color: "#C3CEFF" }
            }
            Text {
                visible: calls.elapsed > 0
                text: app.duration(calls.elapsed)
                font.family: "JetBrains Mono"; font.pixelSize: 13; color: stage.inkMuted
            }
            // the quality of the connection: three bars, the detail on hover
            Item {
                id: qualityBars
                visible: calls.quality.level > 0
                implicitWidth: 18; implicitHeight: 16
                readonly property int lvl: calls.quality.level || 0
                readonly property color tint: lvl >= 3 ? "#5FC2AC" : lvl === 2 ? "#F0A202" : "#FF8A70"
                Row {
                    anchors.bottom: parent.bottom
                    spacing: 2
                    Repeater {
                        model: 3
                        Rectangle {
                            required property int index
                            anchors.bottom: parent.bottom
                            width: 4; height: 6 + index * 4; radius: 1
                            color: qualityBars.lvl > index ? qualityBars.tint : Qt.rgba(1, 1, 1, 0.18)
                        }
                    }
                }
                HoverHandler { id: qualityHover }
                ToolTip.visible: qualityHover.hovered
                ToolTip.delay: 300
                ToolTip.text: (qualityBars.lvl >= 3 ? app.t.quality_good : qualityBars.lvl === 2 ? app.t.quality_fair : app.t.quality_poor)
                              + " · " + app.t.quality_detail.replace("%1", calls.quality.rtt || 0).replace("%2", calls.quality.loss || 0)
                Accessible.role: Accessible.Indicator
                Accessible.name: ToolTip.text
            }
            Rectangle { implicitWidth: 1; implicitHeight: 18; color: stage.glassLine }
            Icon { name: "people"; size: 15; color: stage.inkMuted }
            Text {
                text: (stage.s.people || []).length + 1
                font.family: "JetBrains Mono"; font.pixelSize: 13; color: stage.inkMuted
            }
            AbstractButton {
                implicitWidth: 32; implicitHeight: 32
                hoverEnabled: true
                ToolTip.visible: hovered; ToolTip.text: stage.fullScreen ? app.t.exit_full_screen : app.t.full_screen; ToolTip.delay: 500
                onClicked: { stage.fullScreen = !stage.fullScreen; stage.fullScreenWanted(stage.fullScreen) }
                background: Rectangle { radius: 16; color: parent.hovered ? Qt.rgba(1, 1, 1, 0.1) : "transparent" }
                contentItem: Item { Icon { anchors.centerIn: parent; name: stage.fullScreen ? "collapse" : "expand"; size: 16; color: stage.ink } }
            }
        }
    }

    // ---- the bar -----------------------------------------------------------------------------------------
    Rectangle {
        id: bar
        visible: !stage.preview
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 18
        width: barRow.implicitWidth + 20
        height: 64
        radius: 32
        color: stage.glass
        border.width: 1; border.color: stage.glassLine

        RowLayout {
            id: barRow
            anchors.centerIn: parent
            spacing: 6
            Round {
                iconName: stage.s.audio ? "mic" : "micOff"
                on: !!stage.s.audio
                enabled: stage.s.hasAudio !== false
                tip: (stage.s.audio ? app.t.mute : app.t.unmute) + " (Ctrl+D)"
                onClicked: calls.toggleAudio()
            }
            Round {
                iconName: stage.s.video ? "video" : "videoOff"
                on: !!stage.s.video
                enabled: stage.s.hasVideo !== false
                tip: (stage.s.video ? app.t.camera_off : app.t.camera_on) + " (Ctrl+E)"
                onClicked: calls.toggleVideo()
            }
            Round {
                iconName: "screen"; lit: !!stage.s.screen
                tip: stage.s.screen ? app.t.stop_sharing : app.t.share_screen
                onClicked: calls.toggleScreen()
            }
            Round {
                iconName: "hand"; lit: !!stage.s.hand
                tip: (stage.s.hand ? app.t.lower_hand : app.t.raise_hand) + " (Ctrl+Maj+H)"
                onClicked: calls.toggleHand()
            }
            Round {
                id: reactButton
                iconName: "smile"
                tip: app.t.react
                onClicked: reactions.popupAbove(reactButton)
            }
            Rectangle { implicitWidth: 1; implicitHeight: 28; color: stage.glassLine }
            Round {
                iconName: app.prefs.layout === "speaker" ? "speaker" : "grid"
                tip: app.prefs.layout === "speaker" ? app.t.layout_grid : app.t.layout_speaker
                onClicked: calls.send("layout", app.prefs.layout === "speaker" ? "grid" : "speaker")
            }
            Round {
                iconName: "people"; lit: stage.peopleOpen
                tip: app.t.call_people
                badge: (stage.s.people || []).filter(p => p.hand).length
                onClicked: stage.peopleOpen = !stage.peopleOpen
            }
            Round {
                iconName: "chat"; lit: stage.chatOpen
                tip: app.t.chat_beside
                badge: stage.chatOpen ? 0 : stage.unseenChat
                onClicked: stage.chatWanted()
            }
            Round {
                id: moreButton
                iconName: "settings"
                tip: app.t.call_settings
                onClicked: { calls.send("devices"); devices.popupAbove(moreButton) }
            }
            Rectangle { implicitWidth: 1; implicitHeight: 28; color: stage.glassLine }
            AbstractButton {
                id: hangup
                implicitWidth: 68; implicitHeight: 46
                hoverEnabled: true
                ToolTip.visible: hovered; ToolTip.text: app.t.hang_up + (meet.room.moderator ? " · " + app.t.hold_end_all : ""); ToolTip.delay: 500
                Accessible.name: app.t.hang_up
                onClicked: calls.hangup()
                onPressAndHold: if (meet.room.moderator) endMenu.popupAbove(hangup)
                background: Rectangle {
                    radius: 23
                    gradient: Gradient {
                        GradientStop { position: 0; color: hangup.hovered ? "#E5533A" : "#D8452B" }
                        GradientStop { position: 1; color: "#B8331C" }
                    }
                }
                contentItem: Item { Icon { anchors.centerIn: parent; name: "hangup"; size: 22; color: "white" } }
            }
        }
    }

    // ---- the network went: the call waits for it --------------------------------------------------------------
    Rectangle {
        visible: !stage.preview && !stage.connecting && !!stage.s.reconnecting
        anchors.horizontalCenter: parent.horizontalCenter
        y: 70
        width: cutRow.implicitWidth + 32; height: 40; radius: 20
        color: "#4A3200"
        border.width: 1; border.color: Qt.rgba(0.94, 0.64, 0.01, 0.5)
        RowLayout {
            id: cutRow
            anchors.centerIn: parent
            spacing: 10
            BusyIndicator { running: parent.parent.visible; implicitWidth: 22; implicitHeight: 22 }
            Text { text: app.t.call_reconnecting; color: "#FFE2A8"; font.pixelSize: 13; font.weight: Font.DemiBold }
        }
        Accessible.role: Accessible.AlertMessage
        Accessible.name: app.t.call_reconnecting
    }

    // ---- who is in the call ----------------------------------------------------------------------------------
    Rectangle {
        id: peoplePanel
        visible: stage.peopleOpen && !stage.preview
        anchors.right: parent.right; anchors.rightMargin: 14
        y: 70
        width: Math.min(300, stage.width - 28)
        height: Math.min(peopleList.contentHeight + 64, bar.y - y - 14)
        radius: 18
        color: stage.glass
        border.width: 1; border.color: stage.glassLine
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 12
            spacing: 6
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 6
                Text {
                    Layout.fillWidth: true
                    text: app.plural("in_call_count", stage.callPeople.length)
                    font.pixelSize: 14; font.weight: Font.DemiBold; color: stage.ink
                }
                AbstractButton {
                    implicitWidth: 28; implicitHeight: 28
                    hoverEnabled: true
                    Accessible.name: app.t.close
                    onClicked: stage.peopleOpen = false
                    background: Rectangle { radius: 14; color: parent.hovered ? Qt.rgba(1, 1, 1, 0.1) : "transparent" }
                    contentItem: Item { Icon { anchors.centerIn: parent; name: "close"; size: 14; color: stage.inkMuted } }
                }
            }
            ListView {
                id: peopleList
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: stage.callPeople
                spacing: 2
                delegate: AbstractButton {
                    id: person
                    required property var modelData
                    width: ListView.view.width
                    implicitHeight: 44
                    hoverEnabled: true
                    Accessible.name: modelData.name + (modelData.hand ? ", " + app.t.stage_hand : "") + (modelData.audio ? "" : ", " + app.t.mic_is_off)
                    onClicked: tileMenu.show({ key: modelData.key, session: modelData.self ? "" : modelData.session, self: modelData.self,
                                               name: modelData.name, userId: modelData.userId || "", audio: modelData.audio,
                                               item: person })
                    background: Rectangle { radius: 10; color: person.hovered ? Qt.rgba(1, 1, 1, 0.07) : "transparent" }
                    contentItem: RowLayout {
                        spacing: 10
                        Rectangle {
                            Layout.leftMargin: 6
                            implicitWidth: 32; implicitHeight: 32; radius: 16
                            color: "transparent"
                            border.width: person.modelData.speaking ? 2 : 0; border.color: "#5FC2AC"
                            RoomAvatar { anchors.centerIn: parent; size: 28; name: person.modelData.name
                                         source: person.modelData.userId ? "image://meet/user/" + encodeURIComponent(person.modelData.userId) : "" }
                        }
                        Text { textFormat: Text.PlainText
                            Layout.fillWidth: true
                            text: person.modelData.name + (person.modelData.self ? " (" + app.t.you + ")" : "")
                            elide: Text.ElideRight
                            font.pixelSize: 13; color: stage.ink
                        }
                        Icon { visible: person.modelData.hand; name: "hand"; size: 16; color: "#F0A202" }
                        Icon { visible: person.modelData.screen; name: "screen"; size: 16; color: stage.inkMuted }
                        Icon { Layout.rightMargin: 6; name: person.modelData.audio ? "mic" : "micOff"; size: 16
                               color: person.modelData.audio ? stage.inkMuted : "#FF8A70" }
                    }
                }
            }
        }
    }

    // the menu of one person (a tile's right click, or their row above)
    MeetMenu {
        id: tileMenu
        property var who: ({})
        implicitWidth: 260
        function show(e) {
            who = e
            if (e.item) popupAt(e.item, true)
            else { x = Math.max(8, Math.min(e.x, stage.width - implicitWidth - 8)); y = Math.max(8, Math.min(e.y, stage.height - implicitHeight - 8)); open() }
        }
        OMenuItem {
            width: tileMenu.implicitWidth - 12
            readonly property bool pinned: tileMenu.who.pinned !== undefined ? !!tileMenu.who.pinned : stage.pinnedKey === tileMenu.who.key
            text: pinned ? app.t.unpin_tile : app.t.pin_tile
            iconName: "pushpin"
            onTriggered: {
                if (!pinned && app.prefs.layout !== "speaker") calls.send("layout", "speaker")
                stage.pinnedKey = pinned ? "" : (tileMenu.who.key || "")
                calls.send("pin", tileMenu.who.key || "")
            }
        }
        OMenuItem {
            width: tileMenu.implicitWidth - 12
            visible: !tileMenu.who.self && !!meet.room.moderator && !!tileMenu.who.audio && !!tileMenu.who.session
            height: visible ? implicitHeight : 0
            text: app.t.mute_person
            iconName: "micOff"
            onTriggered: calls.send("muteOther", tileMenu.who.session)
        }
        OMenuItem {
            width: tileMenu.implicitWidth - 12
            visible: !tileMenu.who.self && !!tileMenu.who.userId && meet.room.type !== 1
            height: visible ? implicitHeight : 0
            text: app.t.write_privately
            iconName: "chat"
            onTriggered: stage.writeWanted(tileMenu.who.userId)
        }
    }

    MeetMenu {
        id: reactions
        implicitWidth: 300
        Row {
            x: 4
            spacing: 2
            Repeater {
                model: meet.quickReactions
                AbstractButton {
                    required property string modelData
                    width: 34; height: 38
                    hoverEnabled: true
                    onClicked: { calls.send("reaction", modelData); reactions.close() }
                    background: Rectangle { radius: 8; color: parent.hovered ? stage.c.hover : "transparent" }
                    contentItem: Text { textFormat: Text.PlainText; text: parent.modelData; font.pixelSize: 22; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                }
            }
        }
    }

    MeetMenu {
        id: devices
        heading: app.t.call_settings
        implicitWidth: 320
        OMenuItem {
            width: devices.implicitWidth - 12
            text: stage.s.blur ? app.t.blur_off : app.t.blur_on
            iconName: "sparkle"
            enabled: stage.s.hasVideo !== false && !calls.blurLoading
            onTriggered: calls.setBlur(!stage.s.blur)
        }
        OMenuItem {
            width: devices.implicitWidth - 12
            visible: !!meet.room.moderator && meet.room.type !== 1 || (meet.room.breakoutMode || 0) > 0 || !!meet.room.breakout
            text: app.t.breakout_rooms
            iconName: "grid"
            onTriggered: breakout.open()
        }
        Repeater {
            model: [["audioinput", app.t.microphone, "mic"], ["videoinput", app.t.camera, "camera"], ["audiooutput", app.t.speakers, "speaker"]]
            Column {
                id: kind
                required property var modelData
                width: devices.implicitWidth - 12
                Text { textFormat: Text.PlainText; leftPadding: 10; topPadding: 6; bottomPadding: 2; text: kind.modelData[1]; font.pixelSize: 12; font.weight: Font.DemiBold; color: stage.c.muted }
                Repeater {
                    model: calls.devices.filter(d => d.kind === kind.modelData[0] && d.id !== "default" && d.id !== "communications")
                    OMenuItem {
                        required property var modelData
                        width: kind.width
                        text: modelData.label || app.t.device_unnamed
                        iconName: (app.prefs[kind.modelData[2]] || "") === modelData.id ? "check" : ""
                        onTriggered: calls.send(kind.modelData[2], modelData.id)
                    }
                }
            }
        }
    }

    MeetMenu {
        id: endMenu
        OMenuItem { text: app.t.leave_call; iconName: "hangup"; onTriggered: calls.hangup(false) }
        OMenuItem { text: app.t.end_for_all; iconName: "close"; danger: true; onTriggered: calls.hangup(true) }
    }

    BreakoutDialog { id: breakout }

    // the screen or window to share (Chromium asks; on Wayland, the portal of Plasma asks itself)
    ODialog {
        id: screenPicker
        title: app.t.share_screen
        property var request: null
        property var options: []
        function ask(req) {
            const list = []
            for (let i = 0; i < req.screensModel.rowCount(); i++)
                list.push({ kind: "screen", index: req.screensModel.index(i, 0), name: req.screensModel.data(req.screensModel.index(i, 0)) || (app.t.screen + " " + (i + 1)) })
            for (let i = 0; i < req.windowsModel.rowCount(); i++)
                list.push({ kind: "window", index: req.windowsModel.index(i, 0), name: req.windowsModel.data(req.windowsModel.index(i, 0)) })
            if (list.length === 1) { req.selectScreen(list[0].index); return }
            if (!list.length) { req.cancel(); return }
            request = req
            options = list
            open()
        }
        onClosed: if (request) { request.cancel(); request = null }
        ListView {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(320, contentHeight)
            clip: true
            model: screenPicker.options
            delegate: OMenuItem {
                required property var modelData
                width: ListView.view.width
                text: modelData.name
                iconName: modelData.kind === "screen" ? "screen" : "apps"
                onTriggered: {
                    const req = screenPicker.request
                    screenPicker.request = null
                    if (modelData.kind === "screen") req.selectScreen(modelData.index); else req.selectWindow(modelData.index)
                    screenPicker.close()
                }
            }
        }
        footer: [OButton { text: app.t.cancel; onClicked: screenPicker.close() }]
    }
}
