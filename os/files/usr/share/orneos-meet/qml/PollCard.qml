// A poll in the chat: its question, its options to tick (one or several), then the results once voted or
// closed. Read from the cloud when the row shows (meet.loadPoll), refreshed after each vote.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ColumnLayout {
    id: card
    readonly property var c: theme.c
    property string pollId
    property string question
    property bool mine: false
    property var poll: ({})
    property var chosen: []
    readonly property bool voted: (poll.votedSelf || []).length > 0
    readonly property bool closed: poll.status === 1
    readonly property bool showResults: voted || closed
    readonly property color ink: mine ? c.actionText : c.text
    spacing: 6

    Component.onCompleted: if (pollId) meet.loadPoll(pollId)
    Connections {
        target: meet
        function onPollChanged(id) { if (id === card.pollId) { card.poll = meet.poll(id); card.chosen = [] } }
    }

    RowLayout {
        spacing: 6
        Icon { name: "list"; size: 15; color: card.ink }
        Text { text: app.t.poll; font.pixelSize: 12; font.weight: Font.DemiBold; color: card.ink; opacity: 0.8 }
    }
    Text {
        Layout.fillWidth: true
        textFormat: Text.PlainText
        text: card.poll.question || card.question
        wrapMode: Text.Wrap
        font.pixelSize: 15; font.weight: Font.DemiBold
        color: card.ink
    }
    Repeater {
        model: card.poll.options || []
        AbstractButton {
            id: option
            required property string modelData
            required property int index
            readonly property int votes: (card.poll.votes || {})["option-" + index] || 0
            readonly property int total: card.poll.numVoters || 0
            readonly property bool picked: card.chosen.indexOf(index) >= 0 || (card.poll.votedSelf || []).indexOf(index) >= 0
            Layout.fillWidth: true
            implicitHeight: 36
            enabled: !card.showResults
            onClicked: {
                const multiple = card.poll.maxVotes === 0
                if (multiple) {
                    const list = card.chosen.slice()
                    const at = list.indexOf(index)
                    if (at >= 0) list.splice(at, 1); else list.push(index)
                    card.chosen = list
                } else {
                    meet.vote(card.pollId, [index])
                }
            }
            background: Rectangle {
                radius: 8
                color: card.mine ? Qt.alpha("white", 0.12) : card.c.bg
                border.width: option.picked ? 2 : 1
                border.color: option.picked ? (card.mine ? "white" : card.c.action) : (card.mine ? Qt.alpha("white", 0.3) : card.c.line)
                Rectangle {
                    visible: card.showResults && option.total > 0
                    width: parent.width * option.votes / Math.max(1, option.total); height: parent.height
                    radius: 8
                    color: card.mine ? Qt.alpha("white", 0.2) : card.c.tint
                }
            }
            contentItem: RowLayout {
                Text { textFormat: Text.PlainText;
                    Layout.fillWidth: true; Layout.leftMargin: 10
                    text: option.modelData
                    elide: Text.ElideRight
                    font.pixelSize: 13
                    color: card.ink
                }
                Text {
                    visible: card.showResults
                    Layout.rightMargin: 10
                    text: option.total ? Math.round(100 * option.votes / option.total) + " %" : "0 %"
                    font.family: "JetBrains Mono"; font.pixelSize: 12
                    color: card.ink
                }
            }
        }
    }
    RowLayout {
        Layout.fillWidth: true
        Text {
            Layout.fillWidth: true
            text: card.closed ? app.t.poll_closed : app.plural("voters", card.poll.numVoters || 0)
            font.pixelSize: 12
            color: card.ink; opacity: 0.75
        }
        OButton {
            visible: !card.showResults && card.poll.maxVotes === 0
            kind: card.mine ? "secondary" : "primary"
            text: app.t.vote
            enabled: card.chosen.length > 0
            onClicked: meet.vote(card.pollId, card.chosen)
        }
        OButton {
            visible: !card.closed && (card.poll.actorId === app.profile.user || meet.room.moderator) && card.poll.status !== undefined
            kind: "quiet"
            text: app.t.close_poll
            onClicked: meet.closePoll(card.pollId)
        }
    }
}
