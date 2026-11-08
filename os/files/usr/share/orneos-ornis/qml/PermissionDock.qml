// Ornis asks to do something: the request slides in above the message box, as in Claude, for the Discussion mode
// (what Ornis wants on this computer: ornis_consent through chat.consent) and the Code mode (the agent's
// permissions: code.asking) alike. What, why, the command (changed before it runs), what it would change, what to
// know, then the choices one under the other, numbered: 1 allow, 2 always (when the rule may be kept), then refuse,
// and « Refuser et dire à Ornis quoi faire » (the message box gets the focus). Esc refuses; what touches the whole
// system or a secret has « Refuser » chosen by default, Entrée never runs it by accident. No answer in time: refused.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

FocusScope {
    id: dock
    property string iconName: "devices"
    property string title
    property string subtitle
    property string place                    // another conversation asks: its name
    property string summary
    property string reason
    property bool hasCommand
    property string command
    property bool commandEditable: true      // the Code mode's agent runs the command it asked: shown, not changed
    property string cwd
    property string preview                  // a diff: what the change would be
    property var previewLines: []            // or its lines already cut ([{t: "+"|"-"|"@"|" ", s}])
    property var warnings: []                // [{tone: danger|warn|info, text}]
    property string note                     // under the choices (the mode, why there is no « always »)
    property var options: []                 // [{id, kind: allow|always|deny|tell, label}]
    property bool careful
    property double until: 0                 // ms since epoch: refused without an answer then (0: no end)
    property bool settingsVisible
    signal chosen(string id, string command)
    signal settingsRequested()

    readonly property var c: theme.c
    property int current: 0
    property int secondsLeft: 0
    property bool showPreview: false
    readonly property bool shown: visible && title !== ""
    readonly property var lines: previewLines.length ? previewLines
        : preview ? preview.split("\n").slice(0, 400).map(l => ({ t: l.startsWith("@@") ? "@" : l.startsWith("+++") || l.startsWith("---") ? "@"
                                                                       : l.startsWith("+") ? "+" : l.startsWith("-") ? "-" : " ", s: l }))
        : []

    implicitHeight: card.implicitHeight
    // a new request: from the start, the safe choice first when it is serious
    property string shownKey: ""
    onTitleChanged: Qt.callLater(reset)
    onSummaryChanged: Qt.callLater(reset)
    onCommandChanged: Qt.callLater(reset)
    Component.onCompleted: Qt.callLater(reset)
    function reset() {
        const key = title + "\n" + summary + "\n" + command
        if (key === shownKey) return
        shownKey = key
        showPreview = lines.length > 0 && lines.length <= 16
        editor.text = command
        current = careful ? Math.max(0, options.findIndex(o => o.kind === "deny")) : 0
        if (title !== "") { enter.restart(); Qt.callLater(() => dock.forceActiveFocus()) }
    }
    function choose(i) {
        const o = options[i]
        if (o) chosen(o.id, hasCommand ? editor.text.trim() : "")
    }
    function refuse() {
        const i = options.findIndex(o => o.kind === "deny")
        if (i >= 0) choose(i)
    }

    Timer {
        interval: 1000; repeat: true; triggeredOnStart: true
        running: dock.shown && dock.until > 0
        onTriggered: dock.secondsLeft = Math.max(0, Math.round((dock.until - Date.now()) / 1000))
    }

    Keys.onPressed: event => {
        if (editor.activeFocus) {
            if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && (event.modifiers & Qt.ControlModifier)) {
                choose(0); event.accepted = true
            } else if (event.key === Qt.Key_Escape) { dock.forceActiveFocus(); event.accepted = true }
            return
        }
        const n = event.key - Qt.Key_1
        if (n >= 0 && n < options.length && !(event.modifiers & (Qt.ControlModifier | Qt.AltModifier))) { choose(n); event.accepted = true }
        else if (event.key === Qt.Key_Down || event.key === Qt.Key_Tab) { current = (current + 1) % options.length; event.accepted = true }
        else if (event.key === Qt.Key_Up || event.key === Qt.Key_Backtab) { current = (current + options.length - 1) % options.length; event.accepted = true }
        else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) { choose(current); event.accepted = true }
        else if (event.key === Qt.Key_Escape) { refuse(); event.accepted = true }
    }

    // slides in from under, as a sheet over the box
    ParallelAnimation {
        id: enter
        NumberAnimation { target: slide; property: "y"; from: 14; to: 0; duration: 220; easing.type: Easing.OutCubic }
        NumberAnimation { target: card; property: "opacity"; from: 0; to: 1; duration: 180; easing.type: Easing.OutCubic }
    }

    Rectangle {
        id: card
        width: parent.width
        implicitHeight: col.implicitHeight + 28
        transform: Translate { id: slide }
        radius: 14
        color: dock.c.card
        border.width: 1; border.color: dock.careful ? dock.c.danger : dock.c.saffron
        Accessible.role: Accessible.Dialog
        Accessible.name: dock.title

        Rectangle { x: 0; y: 14; width: 4; height: parent.height - 28; radius: 2; color: dock.careful ? dock.c.danger : dock.c.saffron }

        ColumnLayout {
            id: col
            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
            anchors.margins: 14; anchors.leftMargin: 20
            spacing: 10

            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                Rectangle {
                    implicitWidth: 30; implicitHeight: 30; radius: 8
                    Layout.alignment: Qt.AlignTop
                    color: dock.careful ? dock.c.dangerTint : dock.c.saffronTint
                    Icon { anchors.centerIn: parent; name: dock.iconName; size: 16; color: dock.careful ? dock.c.danger : dock.c.saffronInk }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 1
                    Text {
                        Layout.fillWidth: true
                        text: dock.title
                        wrapMode: Text.Wrap
                        font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.weight: Font.DemiBold
                        color: dock.c.text
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: text !== ""
                        text: dock.place ? app.t.perm_elsewhere.replace("%1", dock.place) + " · " + dock.subtitle : dock.subtitle
                        wrapMode: Text.Wrap
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13
                        color: dock.c.muted
                    }
                }
                Text {
                    visible: dock.until > 0 && dock.secondsLeft > 0 && dock.secondsLeft <= 30
                    Layout.alignment: Qt.AlignTop
                    topPadding: 6
                    text: app.t.perm_countdown.replace("%1", dock.secondsLeft)
                    font.family: "Schibsted Grotesk"; font.pixelSize: 12
                    color: dock.secondsLeft <= 10 ? dock.c.danger : dock.c.muted
                }
                OButton {
                    visible: dock.settingsVisible
                    Layout.alignment: Qt.AlignTop
                    kind: "quiet"; text: app.t.perm_settings; height_: 28
                    onClicked: dock.settingsRequested()
                }
            }

            Text {                               // what (a command says it in its box)
                Layout.fillWidth: true
                visible: dock.summary !== "" && !dock.hasCommand
                text: dock.summary
                wrapMode: Text.Wrap
                textFormat: Text.PlainText
                maximumLineCount: 6; elide: Text.ElideRight
                font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.Medium
                color: dock.c.text
            }
            Text {
                Layout.fillWidth: true
                visible: dock.reason !== ""
                text: dock.hasCommand ? dock.reason : app.t.perm_why.replace("%1", dock.reason)
                wrapMode: Text.Wrap
                textFormat: Text.PlainText
                maximumLineCount: 4; elide: Text.ElideRight
                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                color: dock.hasCommand ? dock.c.text : dock.c.muted
            }

            // the command, changed before it runs if need be (Ctrl+Entrée runs it from the box)
            Rectangle {
                Layout.fillWidth: true
                visible: dock.hasCommand
                implicitHeight: Math.min(150, editor.implicitHeight + 4)
                radius: 8
                color: dock.c.bg
                border.width: editor.activeFocus ? 2 : 1
                border.color: editor.activeFocus ? dock.c.accentLine : dock.c.line
                ScrollView {
                    anchors.fill: parent
                    anchors.margins: 2
                    TextArea {
                        id: editor
                        readOnly: !dock.commandEditable
                        wrapMode: TextEdit.WrapAnywhere
                        selectByMouse: true
                        font.family: "JetBrains Mono"; font.pixelSize: 13
                        color: dock.c.text
                        selectionColor: dock.c.tint
                        padding: 8
                        background: null
                        Accessible.name: app.t.perm_edit
                    }
                }
            }
            Text {
                Layout.fillWidth: true
                visible: dock.hasCommand && dock.cwd !== ""
                text: app.t.perm_in.replace("%1", dock.cwd) + (dock.commandEditable ? " · " + app.t.perm_edit.toLowerCase() : "")
                elide: Text.ElideMiddle
                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                color: dock.c.muted
            }

            // what it would change (a diff), folded when long
            Text {
                visible: dock.lines.length > 0
                text: (dock.showPreview ? "▾ " : "▸ ") + app.t.perm_changes
                font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.underline: prevMouse.containsMouse
                color: dock.c.accent
                MouseArea { id: prevMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: dock.showPreview = !dock.showPreview }
            }
            Rectangle {
                Layout.fillWidth: true
                visible: dock.showPreview && dock.lines.length > 0
                Layout.preferredHeight: visible ? Math.min(diffCol.implicitHeight + 8, 220) : 0
                radius: 8
                color: dock.c.bg
                clip: true
                Flickable {
                    anchors.fill: parent; anchors.margins: 4
                    contentHeight: diffCol.implicitHeight
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                    Column {
                        id: diffCol
                        width: parent.width
                        Repeater {
                            model: dock.showPreview ? dock.lines : []
                            Rectangle {
                                required property var modelData
                                width: diffCol.width
                                height: diffText.implicitHeight + 2
                                color: modelData.t === "+" ? dock.c.okTint : modelData.t === "-" ? dock.c.dangerTint : "transparent"
                                Text {
                                    id: diffText
                                    x: 6; y: 1; width: parent.width - 12
                                    text: modelData.s
                                    textFormat: Text.PlainText
                                    wrapMode: Text.WrapAnywhere
                                    font.family: "JetBrains Mono"; font.pixelSize: 12
                                    color: modelData.t === "@" ? dock.c.muted : dock.c.text
                                }
                            }
                        }
                    }
                }
            }

            Repeater {                           // what to know (secrets, a script from the web, a restart…)
                model: dock.warnings
                Rectangle {
                    required property var modelData
                    Layout.fillWidth: true
                    implicitHeight: warnText.implicitHeight + 14
                    radius: 8
                    color: modelData.tone === "danger" ? dock.c.dangerTint : modelData.tone === "warn" ? dock.c.saffronTint : dock.c.tint
                    RowLayout {
                        anchors.fill: parent; anchors.margins: 7; anchors.leftMargin: 10
                        spacing: 8
                        Icon { name: modelData.tone === "info" ? "info" : "warning"; size: 14
                               color: modelData.tone === "danger" ? dock.c.danger : modelData.tone === "warn" ? dock.c.saffronInk : dock.c.tintText }
                        Text {
                            id: warnText
                            Layout.fillWidth: true
                            text: modelData.text
                            wrapMode: Text.Wrap
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13
                            color: dock.c.text
                        }
                    }
                }
            }

            // the choices, one under the other, numbered (as Claude asks)
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Repeater {
                    model: dock.options
                    AbstractButton {
                        id: opt
                        required property var modelData
                        required property int index
                        readonly property bool on: dock.current === index
                        readonly property bool go: modelData.kind === "allow" || modelData.kind === "always"
                        Layout.fillWidth: true
                        implicitHeight: 36
                        hoverEnabled: true
                        focusPolicy: Qt.NoFocus
                        onHoveredChanged: if (hovered) dock.current = index
                        onClicked: dock.choose(index)
                        Accessible.role: Accessible.Button
                        Accessible.name: modelData.label
                        background: Rectangle {
                            radius: 8
                            color: opt.on ? (opt.go && !dock.careful ? dock.c.tint : opt.go ? dock.c.dangerTint : dock.c.hover) : "transparent"
                            border.width: opt.on && dock.activeFocus ? 1 : 0
                            border.color: opt.go && !dock.careful ? dock.c.accentLine : dock.c.line
                        }
                        contentItem: RowLayout {
                            spacing: 10
                            Rectangle {
                                Layout.leftMargin: 6
                                implicitWidth: 20; implicitHeight: 20; radius: 5
                                color: "transparent"
                                border.width: 1; border.color: opt.on ? dock.c.accentLine : dock.c.line
                                Text { anchors.centerIn: parent; text: opt.index + 1; font.family: "JetBrains Mono"; font.pixelSize: 11
                                       color: opt.on ? dock.c.text : dock.c.muted }
                            }
                            Text {
                                Layout.fillWidth: true
                                text: opt.modelData.label
                                elide: Text.ElideRight
                                font.family: "Schibsted Grotesk"; font.pixelSize: 14
                                font.weight: opt.on ? Font.DemiBold : Font.Normal
                                color: opt.go && dock.careful && opt.on ? dock.c.danger : opt.go && opt.on ? dock.c.tintText : dock.c.text
                            }
                            Icon { visible: opt.on; name: "arrow"; size: 13; color: dock.c.muted; Layout.rightMargin: 8 }
                        }
                    }
                }
            }
            Text {
                Layout.fillWidth: true
                text: (dock.note ? dock.note + "\n" : "") + app.t.perm_keys.replace("%1", dock.options.length)
                wrapMode: Text.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                color: dock.c.faint
            }
        }
    }
}
