// What Ornis is about to do, waiting for a yes: each action with its details (to, subject, date…), then
// Confirm or Cancel. « Modifier » turns the details into fields: what is changed goes with the yes (chat.confirmEdited,
// applied by the agent to the call itself). Writing a new message instead still tells Ornis what to change.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Rectangle {
    id: card
    property var actions: []
    property bool editing: false
    property var edits: ({})             // "action index" → {key: text}
    signal answered(bool yes)
    signal answeredEdited(var edits)
    // the list comes again at each refresh of the conversation: only other actions end the editing
    property string shownActions: ""
    onActionsChanged: {
        const now = JSON.stringify(actions)
        if (now !== shownActions) { shownActions = now; editing = false; edits = {} }
    }
    function setEdit(index, key, text) {
        const all = Object.assign({}, edits)
        all[index] = Object.assign({}, all[index] || {})
        all[index][key] = text
        edits = all
    }
    function confirm() {
        const out = []
        for (const index in edits) {
            const args = {}
            const original = (actions[index] || {}).args || []
            for (const key in edits[index]) {
                const was = original.find(a => a.key === key)
                if (was && was.value !== edits[index][key]) args[key] = edits[index][key]
            }
            if (Object.keys(args).length) out.push({ index: Number(index), args: args })
        }
        if (out.length) answeredEdited(out); else answered(true)
    }
    readonly property var c: theme.c
    height: column.implicitHeight + 32
    radius: 12
    color: c.card
    border.width: 1; border.color: c.accentLine

    Rectangle { width: 4; height: parent.height - 24; y: 12; x: 0; radius: 2; color: card.c.saffron }

    ColumnLayout {
        id: column
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        anchors.margins: 16; anchors.leftMargin: 22
        spacing: 12

        Text {
            text: app.t.confirm_title
            font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.weight: Font.DemiBold
            color: card.c.text
        }

        Repeater {
            model: card.actions
            ColumnLayout {
                id: action
                required property var modelData
                required property int index
                property bool expanded
                Layout.fillWidth: true
                spacing: 6
                RowLayout {
                    spacing: 10
                    Rectangle {
                        implicitWidth: 28; implicitHeight: 28; radius: 7
                        color: card.c.tint
                        Icon { anchors.centerIn: parent; name: action.modelData.icon; size: 16; color: card.c.tintText }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: action.modelData.title
                        font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.weight: Font.Medium
                        color: card.c.text
                        wrapMode: Text.Wrap
                    }
                }
                GridLayout {
                    visible: !card.editing
                    Layout.fillWidth: true
                    Layout.leftMargin: 38
                    columns: 2
                    columnSpacing: 12; rowSpacing: 4
                    Repeater {
                        model: action.modelData.args.slice(0, action.expanded ? 99 : 4).reduce((out, a) => out.concat([{ t: a.label, v: false }, { t: a.value, v: true }]), [])
                        Text {
                            required property var modelData
                            Layout.fillWidth: modelData.v
                            Layout.alignment: Qt.AlignTop
                            text: modelData.t
                            wrapMode: modelData.v ? Text.Wrap : Text.NoWrap
                            maximumLineCount: modelData.v && !action.expanded ? 4 : 400
                            elide: Text.ElideRight
                            textFormat: Text.PlainText
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13
                            font.weight: modelData.v ? Font.Normal : Font.Medium
                            color: modelData.v ? card.c.body : card.c.muted
                        }
                    }
                }
                // « Modifier »: each detail in a field (several lines for a text), the others as they are
                GridLayout {
                    visible: card.editing
                    Layout.fillWidth: true
                    Layout.leftMargin: 38
                    columns: 2
                    columnSpacing: 12; rowSpacing: 6
                    Repeater {
                        model: card.editing ? action.modelData.args : []
                        Item {
                            id: field
                            required property var modelData
                            Layout.columnSpan: 2
                            Layout.fillWidth: true
                            implicitHeight: fieldRow.implicitHeight
                            RowLayout {
                                id: fieldRow
                                width: parent.width
                                spacing: 12
                                Text {
                                    Layout.preferredWidth: 72
                                    Layout.alignment: Qt.AlignTop
                                    topPadding: 8
                                    text: field.modelData.label
                                    elide: Text.ElideRight
                                    font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.Medium
                                    color: card.c.muted
                                }
                                Loader {
                                    Layout.fillWidth: true
                                    sourceComponent: !field.modelData.editable ? fixed : field.modelData.long ? area : line
                                }
                            }
                            Component {
                                id: fixed
                                Text { text: field.modelData.value; wrapMode: Text.Wrap; topPadding: 8; textFormat: Text.PlainText
                                       font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: card.c.body }
                            }
                            Component {
                                id: line
                                OTextField {
                                    text: field.modelData.value
                                    font.pixelSize: 13
                                    Accessible.name: field.modelData.label
                                    onTextEdited: card.setEdit(action.index, field.modelData.key, text)
                                }
                            }
                            Component {
                                id: area
                                OTextArea {
                                    text: field.modelData.value
                                    font.pixelSize: 13
                                    padding: 8
                                    Accessible.name: field.modelData.label
                                    onTextChanged: if (activeFocus) card.setEdit(action.index, field.modelData.key, text)
                                }
                            }
                        }
                    }
                }
                Text {
                    visible: !card.editing && !action.expanded && (action.modelData.args.length > 4 || action.modelData.args.some(a => a.value.length > 160 || a.value.split("\n").length > 3))
                    Layout.leftMargin: 38
                    text: app.t.confirm_more
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.underline: moreMouse.containsMouse
                    color: card.c.accent
                    MouseArea { id: moreMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: action.expanded = true }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 4
            spacing: 8
            Text {
                Layout.fillWidth: true
                text: card.editing ? app.t.confirm_edit_hint : app.t.confirm_hint
                wrapMode: Text.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                color: card.c.muted
            }
            OButton {
                visible: !card.editing && card.actions.some(a => a.args.some(x => x.editable))
                kind: "quiet"; text: app.t.confirm_edit; iconName: "edit"
                onClicked: card.editing = true
            }
            OButton { text: app.t.confirm_no; iconName: "close"; onClicked: card.answered(false) }
            OButton { kind: "primary"; text: app.t.confirm_yes; iconName: "check"; onClicked: card.confirm() }
        }
    }
}
