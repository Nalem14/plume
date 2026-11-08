// Addresses as chips, typed or picked from the contacts. Enter, Tab, comma or semicolon adds (the
// highlighted suggestion first); ↑ ↓ move in the suggestions; Backspace on an empty field removes the
// last one. Picking a suggestion with the mouse keeps the focus in the field.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

FocusScope {
    id: field
    property var addresses: []
    property string placeholder
    readonly property var c: theme.c
    property var hits: []
    property int highlighted: 0
    implicitHeight: Math.max(38, flow.implicitHeight + 8)

    function add(text) {
        const parts = String(text).split(/[,;\s]+/).map(x => x.trim().replace(/^<|>$/g, "")).filter(x => x.indexOf("@") > 0)
        if (!parts.length)
            return false
        let list = addresses.slice()
        for (const p of parts)
            if (list.map(a => a.toLowerCase()).indexOf(p.toLowerCase()) === -1)
                list.push(p)
        addresses = list
        input.text = ""
        return true
    }
    // what is typed becomes a chip only when it is an address: a name half typed stays in the field
    function commit() { if (input.text.trim()) add(input.text) }
    // what is typed but not yet an address (kept with the rest, without touching the field)
    function pending() { return input.text.trim() ? [input.text.trim()] : [] }
    function pick(index) {
        if (index >= 0 && index < hits.length)
            add(hits[index].email)
        input.forceActiveFocus()
    }
    function refresh() {
        const typed = input.text.trim()
        const taken = addresses.map(a => a.toLowerCase())
        hits = typed ? Array.from(people.suggest(typed)).filter(h => taken.indexOf(String(h.email).toLowerCase()) === -1) : []
        highlighted = 0
        if (hits.length && input.activeFocus)
            suggestions.open()
        else
            suggestions.close()
    }

    Flow {
        id: flow
        anchors.left: parent.left; anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: 6
        Repeater {
            model: field.addresses
            Rectangle {
                required property string modelData
                required property int index
                height: 28; radius: 14
                width: chipRow.implicitWidth + 14
                color: field.c.hover
                Row {
                    id: chipRow
                    anchors.centerIn: parent
                    spacing: 4
                    Text { anchors.verticalCenter: parent.verticalCenter; text: modelData; font.family: "Schibsted Grotesk"; font.pixelSize: 14; color: field.c.text }
                    OButton {
                        anchors.verticalCenter: parent.verticalCenter
                        kind: "quiet"; iconName: "close"; iconSize: 11; height_: 18; implicitWidth: 18
                        focusPolicy: Qt.NoFocus
                        tip: plume.t.remove_recipient
                        onClicked: { const l = field.addresses.slice(); l.splice(index, 1); field.addresses = l }
                    }
                }
            }
        }
        TextField {
            id: input
            focus: true
            width: Math.max(160, flow.width - 8)
            height: 30
            leftPadding: 2
            placeholderText: field.addresses.length ? "" : field.placeholder
            placeholderTextColor: field.c.muted
            color: field.c.text
            font.family: "Schibsted Grotesk"; font.pixelSize: 15
            background: null
            selectByMouse: true
            onTextChanged: field.refresh()
            onAccepted: {
                if (suggestions.opened && field.hits.length)
                    field.pick(field.highlighted)
                else
                    field.commit()
            }
            onActiveFocusChanged: {
                if (activeFocus)
                    return
                // the click on a suggestion takes the focus for a moment: let it land first
                Qt.callLater(() => {
                    if (!input.activeFocus) {
                        suggestions.close()
                        field.commit()
                    }
                })
            }
            Keys.onPressed: event => {
                if (event.key === Qt.Key_Comma || event.key === Qt.Key_Semicolon) {
                    if (suggestions.opened && field.hits.length) field.pick(field.highlighted)
                    else field.commit()
                    event.accepted = true
                } else if (event.key === Qt.Key_Tab && suggestions.opened && field.hits.length) {
                    field.pick(field.highlighted); event.accepted = true
                } else if (event.key === Qt.Key_Down && suggestions.opened) {
                    field.highlighted = Math.min(field.hits.length - 1, field.highlighted + 1); event.accepted = true
                } else if (event.key === Qt.Key_Up && suggestions.opened) {
                    field.highlighted = Math.max(0, field.highlighted - 1); event.accepted = true
                } else if (event.key === Qt.Key_Escape && suggestions.opened) {
                    suggestions.close(); event.accepted = true
                } else if (event.key === Qt.Key_Backspace && text === "" && field.addresses.length) {
                    field.addresses = field.addresses.slice(0, -1); event.accepted = true
                }
            }
            Popup {
                id: suggestions
                y: input.height + 4
                width: Math.min(380, Math.max(300, flow.width))
                padding: 4
                margins: 8
                closePolicy: Popup.NoAutoClose      // opened and closed by the field only
                focus: false
                background: Rectangle { radius: 10; color: field.c.overlay; border.width: 1; border.color: field.c.overlayLine }
                contentItem: Column {
                    Repeater {
                        model: field.hits
                        AbstractButton {
                            id: hit
                            required property var modelData
                            required property int index
                            readonly property bool current: index === field.highlighted
                            width: suggestions.availableWidth; height: 44
                            hoverEnabled: true
                            focusPolicy: Qt.NoFocus
                            Accessible.name: modelData.name + " " + modelData.email
                            onHoveredChanged: if (hovered) field.highlighted = index
                            onClicked: field.pick(index)
                            background: Rectangle { radius: 6; color: hit.current ? field.c.hover : "transparent" }
                            contentItem: RowLayout {
                                spacing: 10
                                Rectangle {
                                    Layout.leftMargin: 8
                                    implicitWidth: 28; implicitHeight: 28; radius: 14; color: field.c.tint
                                    Text { anchors.centerIn: parent; text: hit.modelData.initials; font.family: "Schibsted Grotesk"; font.pixelSize: 11; font.weight: Font.DemiBold; color: field.c.tintText }
                                }
                                Column {
                                    Layout.fillWidth: true
                                    Text { width: parent.width; text: hit.modelData.name || hit.modelData.email; elide: Text.ElideRight; font.family: "Schibsted Grotesk"; font.pixelSize: 14; color: field.c.text }
                                    Text {
                                        width: parent.width
                                        visible: !!hit.modelData.name
                                        text: hit.modelData.email
                                        elide: Text.ElideRight
                                        font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: field.c.muted
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
