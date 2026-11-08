// Ornis asks the user to choose before going on (its tool ask_user, as Claude's questions): above the message box,
// one question at a time when there are several (their names in a row on top, each one reachable), each with its
// choices (round: one only; square: several), and always « Autre » at the end with a field to say more or answer
// otherwise. « Répondre » gives everything back to Ornis, which goes on; « Passer » lets it decide.
// Keys: 1…n pick, Entrée goes to the next question (sends after the last), Échap skips.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

FocusScope {
    id: dock
    property var questions: []               // [{question, header, multi, options: [{label, description}]}]
    signal answered(var answers)             // [{question, chosen: [labels], note}]
    signal skipped()

    readonly property var c: theme.c
    property int page: 0
    property var picks: []                   // per question: the chosen labels
    property var notes: []                   // per question: what the user wrote in « Autre »
    readonly property var q: questions[page] || ({ question: "", options: [], multi: false })
    readonly property bool lastPage: page >= questions.length - 1
    implicitHeight: card.implicitHeight

    property string shownKey: ""
    onQuestionsChanged: {
        const key = JSON.stringify(questions)
        if (key === shownKey) return
        shownKey = key
        page = 0
        picks = questions.map(() => [])
        notes = questions.map(() => "")
        if (questions.length) { enter.restart(); Qt.callLater(() => dock.forceActiveFocus()) }
    }
    function picked(label) { return (picks[page] || []).indexOf(label) >= 0 }
    function toggle(label) {
        const all = picks.slice()
        let mine = (all[page] || []).slice()
        if (q.multi) mine = mine.indexOf(label) >= 0 ? mine.filter(l => l !== label) : mine.concat([label])
        else mine = mine.indexOf(label) >= 0 ? [] : [label]
        all[page] = mine
        picks = all
        if (!q.multi && mine.length && !lastPage) advance.restart()     // one choice: on to the next question
    }
    function setNote(text) { const all = notes.slice(); all[page] = text; notes = all }
    function next() { if (lastPage) send(); else page += 1 }
    function send() {
        answered(questions.map((x, i) => ({ question: x.question, chosen: picks[i] || [], note: notes[i] || "" })))
    }
    Timer { id: advance; interval: 220; onTriggered: if (!dock.lastPage) dock.page += 1 }
    onPageChanged: other.text = notes[page] || ""

    Keys.onPressed: event => {
        if (other.activeFocus) return
        const n = event.key - Qt.Key_1
        if (n >= 0 && n < q.options.length && !(event.modifiers & (Qt.ControlModifier | Qt.AltModifier))) { toggle(q.options[n].label); event.accepted = true }
        else if (n === q.options.length) { other.forceActiveFocus(); event.accepted = true }
        else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) { next(); event.accepted = true }
        else if (event.key === Qt.Key_Right && !lastPage) { page += 1; event.accepted = true }
        else if (event.key === Qt.Key_Left && page > 0) { page -= 1; event.accepted = true }
        else if (event.key === Qt.Key_Escape) { skipped(); event.accepted = true }
    }

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
        border.width: 1; border.color: dock.c.accentLine
        Accessible.role: Accessible.Dialog
        Accessible.name: app.t.ask_title

        Rectangle { x: 0; y: 14; width: 4; height: parent.height - 28; radius: 2; color: dock.c.accent }

        ColumnLayout {
            id: col
            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
            anchors.margins: 14; anchors.leftMargin: 20
            spacing: 10

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Icon { name: "ornis"; size: 16; color: dock.c.accent }
                Text {
                    text: app.t.ask_title
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                    color: dock.c.accent
                }
                // several questions: their names in a row, each one reachable, the answered ones ticked
                Flow {
                    Layout.fillWidth: true
                    visible: dock.questions.length > 1
                    spacing: 4
                    Repeater {
                        model: dock.questions.length > 1 ? dock.questions : []
                        AbstractButton {
                            id: tab
                            required property var modelData
                            required property int index
                            readonly property bool on: dock.page === index
                            readonly property bool done: (dock.picks[index] || []).length > 0 || (dock.notes[index] || "") !== ""
                            implicitWidth: tabRow.implicitWidth + 16; implicitHeight: 24
                            hoverEnabled: true
                            focusPolicy: Qt.NoFocus
                            onClicked: dock.page = index
                            Accessible.name: tabText.text
                            background: Rectangle { radius: 12; color: tab.on ? dock.c.tint : tab.hovered ? dock.c.hover : "transparent"
                                                    border.width: 1; border.color: tab.on ? dock.c.accentLine : dock.c.line }
                            contentItem: Item {
                                Row {
                                    id: tabRow
                                    anchors.centerIn: parent
                                    spacing: 4
                                    Icon { visible: tab.done; name: "check"; size: 11; color: dock.c.okInk; anchors.verticalCenter: parent.verticalCenter }
                                    Text {
                                        id: tabText
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: tab.modelData.header || (tab.index + 1)
                                        font.family: "Schibsted Grotesk"; font.pixelSize: 12; font.weight: tab.on ? Font.DemiBold : Font.Normal
                                        color: tab.on ? dock.c.tintText : dock.c.text
                                    }
                                }
                            }
                        }
                    }
                }
                Item { Layout.fillWidth: true; visible: dock.questions.length <= 1 }
                OButton { kind: "quiet"; text: app.t.ask_skip; height_: 26; onClicked: dock.skipped() }
            }

            Text {
                Layout.fillWidth: true
                text: dock.q.question
                wrapMode: Text.Wrap
                textFormat: Text.PlainText
                font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.weight: Font.DemiBold
                color: dock.c.text
            }
            Text {
                text: dock.q.multi ? app.t.ask_multi : app.t.ask_one
                font.family: "Schibsted Grotesk"; font.pixelSize: 12
                color: dock.c.muted
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Repeater {
                    model: dock.q.options
                    AbstractButton {
                        id: opt
                        required property var modelData
                        required property int index
                        readonly property bool on: dock.picked(modelData.label)
                        Layout.fillWidth: true
                        implicitHeight: optRow.implicitHeight + 14
                        hoverEnabled: true
                        focusPolicy: Qt.NoFocus
                        onClicked: dock.toggle(modelData.label)
                        Accessible.role: dock.q.multi ? Accessible.CheckBox : Accessible.RadioButton
                        Accessible.checked: on
                        Accessible.name: modelData.label
                        background: Rectangle {
                            radius: 10
                            color: opt.on ? dock.c.tint : opt.hovered ? dock.c.hover : "transparent"
                            border.width: 1; border.color: opt.on ? dock.c.accentLine : dock.c.line
                        }
                        contentItem: RowLayout {
                            id: optRow
                            spacing: 10
                            Rectangle {                  // round: one choice; square: several
                                Layout.leftMargin: 10
                                Layout.alignment: Qt.AlignTop
                                Layout.topMargin: 2
                                implicitWidth: 18; implicitHeight: 18
                                radius: dock.q.multi ? 5 : 9
                                color: opt.on ? dock.c.action : "transparent"
                                border.width: opt.on ? 0 : 1.5; border.color: dock.c.muted
                                Icon { visible: opt.on && dock.q.multi; anchors.centerIn: parent; name: "check"; size: 12; color: dock.c.actionText }
                                Rectangle { visible: opt.on && !dock.q.multi; anchors.centerIn: parent; width: 7; height: 7; radius: 4; color: dock.c.actionText }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 1
                                Text {
                                    Layout.fillWidth: true
                                    text: opt.modelData.label
                                    wrapMode: Text.Wrap
                                    textFormat: Text.PlainText
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.Medium
                                    color: opt.on ? dock.c.tintText : dock.c.text
                                }
                                Text {
                                    Layout.fillWidth: true
                                    visible: text !== ""
                                    text: opt.modelData.description || ""
                                    wrapMode: Text.Wrap
                                    textFormat: Text.PlainText
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                                    color: dock.c.muted
                                }
                            }
                            Text {
                                Layout.alignment: Qt.AlignTop
                                Layout.rightMargin: 10
                                text: opt.index + 1
                                font.family: "JetBrains Mono"; font.pixelSize: 11
                                color: dock.c.faint
                            }
                        }
                    }
                }
                // always the last one: « Autre », to say more or answer otherwise
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10
                    Text {
                        Layout.leftMargin: 10
                        text: app.t.ask_other
                        font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.Medium
                        color: dock.c.text
                    }
                    OTextField {
                        id: other
                        Layout.fillWidth: true
                        placeholderText: app.t.ask_other_hint
                        maximumLength: 1000
                        font.pixelSize: 14
                        onTextEdited: dock.setNote(text)
                        Keys.onReturnPressed: dock.next()
                        Keys.onEnterPressed: dock.next()
                        Keys.onEscapePressed: dock.forceActiveFocus()
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Text {
                    Layout.fillWidth: true
                    text: (dock.questions.length > 1 ? app.t.ask_count.replace("%1", dock.page + 1).replace("%2", dock.questions.length) + " · " : "")
                          + app.t.ask_keys.replace("%1", dock.q.options.length)
                    elide: Text.ElideRight
                    font.family: "Schibsted Grotesk"; font.pixelSize: 12
                    color: dock.c.faint
                }
                OButton { visible: dock.page > 0; kind: "quiet"; text: app.t.ask_back; iconName: "chevronLeft"; height_: 30
                          onClicked: dock.page -= 1 }
                OButton { visible: !dock.lastPage; text: app.t.ask_next; height_: 30; onClicked: dock.page += 1 }
                OButton { visible: dock.lastPage; kind: "primary"; text: app.t.ask_send; iconName: "send"; height_: 30; onClicked: dock.send() }
            }
        }
    }
}
