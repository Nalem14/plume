// The emojis: a search (« fete », « party », « :+1 »), the last used, then by family. picked(emoji).
// For a message's reactions (reactions: true), a right click pins an emoji beside every message (or unpins it):
// the quick reactions, 👍 👀 🎉 at first.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"
import "emoji.js" as Emoji

MeetMenu {
    id: picker
    implicitWidth: 348
    property bool reactions: false
    property string family: ""
    signal picked(string emoji)
    readonly property var quick: app.prefs.quick_reactions || []
    readonly property var recent: app.prefs.recent_emojis || []
    readonly property var shown: query.text.trim() ? Emoji.search(query.text, 64).map(e => e.emoji) : []
    readonly property real cell: Math.floor((implicitWidth - 12) / 9)
    // the recent ones (then the usual ones of work), then every family
    readonly property var sections: [{ key: "", icon: "🕘", title: app.t.emoji_recent,
                                       items: recent.concat(Emoji.POPULAR.filter(e => recent.indexOf(e) < 0)).slice(0, 18) }]
        .concat(Emoji.FAMILIES.map(f => ({ key: f.key, icon: f.icon, title: app.t["emoji_fam_" + f.key], items: f.items.map(i => i[0]) })))

    function choose(e) {
        app.setPref("recent_emojis", [e].concat(picker.recent.filter(r => r !== e)).slice(0, 16))
        picked(e)
        close()
    }
    function togglePin(e) {
        const q = picker.quick.slice()
        const at = q.indexOf(e)
        if (at >= 0) q.splice(at, 1)
        else { q.push(e); if (q.length > 6) q.shift() }
        app.setPref("quick_reactions", q)
    }
    onAboutToShow: { query.text = ""; family = ""; sectionList.positionViewAtBeginning() }
    onOpened: query.forceActiveFocus()

    ColumnLayout {
        width: picker.implicitWidth - 12
        spacing: 6
        OTextField {
            id: query
            Layout.fillWidth: true
            iconName: "search"
            placeholderText: app.t.emoji_search
            Keys.onReturnPressed: if (picker.shown.length) picker.choose(picker.shown[0])
            onTextChanged: if (text) picker.family = ""
        }
        // the families: a jump to their part of the list, the one in view lit
        Row {
            visible: !query.text
            spacing: 2
            Repeater {
                model: picker.sections
                AbstractButton {
                    required property var modelData
                    required property int index
                    width: 36; height: 32
                    hoverEnabled: true
                    onClicked: { picker.family = modelData.key; sectionList.positionViewAtIndex(index, ListView.Beginning) }
                    ToolTip.visible: hovered; ToolTip.delay: 600; ToolTip.text: modelData.title
                    background: Rectangle { radius: 8; color: picker.family === parent.modelData.key ? theme.c.tint : (parent.hovered ? theme.c.hover : "transparent") }
                    contentItem: Text { textFormat: Text.PlainText; text: parent.modelData.icon; font.pixelSize: 17; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                }
            }
        }
        // everything, one family after the other under its title (the recent ones first)
        ListView {
            id: sectionList
            visible: !query.text
            Layout.fillWidth: true
            Layout.preferredHeight: 7 * 38
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            model: picker.sections
            cacheBuffer: 4000
            onContentYChanged: if (moving || flicking || dragging) {
                const i = indexAt(0, contentY + 8)
                if (i >= 0) picker.family = picker.sections[i].key
            }
            delegate: Column {
                required property var modelData
                width: sectionList.width
                Text {
                    text: modelData.title
                    topPadding: 4; bottomPadding: 2
                    font.pixelSize: 11; font.weight: Font.DemiBold; color: theme.c.faint
                }
                Flow {
                    width: parent.width
                    Repeater { model: modelData.items; delegate: cellComponent }
                }
            }
        }
        // a search: what it finds
        GridView {
            id: grid
            visible: !!query.text
            Layout.fillWidth: true
            Layout.preferredHeight: 7 * 38
            clip: true
            cellWidth: picker.cell; cellHeight: 38
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            model: query.text ? picker.shown : []
            delegate: cellComponent
            Text {
                anchors.centerIn: parent
                visible: grid.count === 0
                text: app.t.emoji_none
                font.pixelSize: 13; color: theme.c.muted
            }
        }
        Component {
            id: cellComponent
            AbstractButton {
                id: cell
                required property string modelData
                width: picker.cell; height: 38
                hoverEnabled: true
                readonly property bool pinned: picker.reactions && picker.quick.indexOf(modelData) >= 0
                onClicked: picker.choose(modelData)
                ToolTip.visible: hovered && picker.reactions
                ToolTip.delay: 900
                ToolTip.text: pinned ? app.t.unpin_reaction : app.t.pin_reaction
                // right click (or a long press: trackpads, Ctrl+click on a Mac) pins or unpins it
                onPressAndHold: if (picker.reactions) picker.togglePin(cell.modelData); else picker.choose(cell.modelData)
                MouseArea { anchors.fill: parent; acceptedButtons: Qt.RightButton; enabled: picker.reactions; onClicked: picker.togglePin(cell.modelData) }
                background: Rectangle {
                    radius: 8
                    color: cell.hovered ? theme.c.hover : "transparent"
                    border.width: cell.pinned ? 1.5 : 0; border.color: theme.c.saffron
                }
                contentItem: Text { textFormat: Text.PlainText; text: cell.modelData; font.pixelSize: 21; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
            }
        }
        Text {
            visible: picker.reactions
            Layout.fillWidth: true
            text: app.t.pin_reaction_hint
            wrapMode: Text.Wrap
            font.pixelSize: 11; color: theme.c.faint
        }
    }
}
