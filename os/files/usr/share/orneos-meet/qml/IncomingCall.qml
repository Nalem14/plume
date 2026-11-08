// Someone calls: a card on top of the window (the desktop notification says it too, with the same answers),
// until it is answered, declined, or the call ends. answer(token, video).
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ODialog {
    id: card
    readonly property var c: theme.c
    property var call: ({})
    signal answer(string token, bool video)
    tint: c.ok
    width: 360
    closePolicy: Popup.NoAutoClose

    Connections {
        target: meet
        function onRinging(info) {
            card.call = info
            card.open()
            ringTimeout.restart()
        }
        function onRingStopped(token) { if (card.call.token === token) card.close() }
    }
    // answered (here, or another call started from the window): the card goes
    Connections { target: calls; function onChanged() { if (calls.active && calls.token === card.call.token) card.close() } }
    Timer { id: ringTimeout; interval: 45000; onTriggered: card.close() }

    ColumnLayout {
        Layout.fillWidth: true
        Layout.margins: 22
        spacing: 10
        RoomAvatar { Layout.alignment: Qt.AlignHCenter; size: 72; source: card.call.avatar || ""; name: card.call.name || "" }
        Text { textFormat: Text.PlainText;
            Layout.alignment: Qt.AlignHCenter
            text: card.call.name || ""
            font.pixelSize: 18; font.weight: Font.DemiBold; color: card.c.text
        }
        Text {
            Layout.alignment: Qt.AlignHCenter
            text: card.call.video ? app.t.incoming_video : app.t.incoming_audio
            font.pixelSize: 13; color: card.c.muted
        }
        // during another call: answering leaves it
        Text {
            visible: calls.active && calls.token !== card.call.token
            Layout.alignment: Qt.AlignHCenter
            Layout.maximumWidth: 300
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            text: app.t.answer_ends_call_long.replace("%1", calls.name)
            font.pixelSize: 12; color: card.c.saffronInk
        }
    }
    footer: [
        OButton { text: app.t.decline; danger: true; onClicked: { card.close(); meet.declineRing(card.call.token || "") } },
        OButton { kind: "secondary"; iconName: "phone"; text: app.t.answer_audio; onClicked: { card.close(); card.answer(card.call.token, false) } },
        OButton { kind: "primary"; iconName: "video"; text: app.t.answer_video; onClicked: { card.close(); card.answer(card.call.token, true) } }
    ]
}
