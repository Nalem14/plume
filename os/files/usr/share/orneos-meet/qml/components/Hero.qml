// The head of an app's main view, on a card tinted with the app's family: what measures the moment (a ring),
// a kicker, the large title, a line of figures in the data face, then the view's own actions.
// Offline, the same line says when the data dates from ("À jour à 13:32"), in saffron with its icon.
// backdrop: what the app lays on the card under the text (Photos: the cover, fading into the card).
import QtQuick
import QtQuick.Layouts

Surface {
    id: hero
    property color tint: c.famCommunicate
    property string kicker
    property string title
    property string meta
    property bool offline
    property string offlineText
    property real titleSize: 28
    // the ring (or any mark) before the title
    property alias leading: lead.data
    property alias backdrop: back.data
    default property alias actions: trailing.data

    implicitHeight: Math.max(row.implicitHeight + 32, 88)
    gradient: Gradient {
        orientation: Gradient.Horizontal
        GradientStop { position: 0; color: Qt.tint(hero.c.card, Qt.alpha(hero.tint, theme.dark ? 0.16 : 0.11)) }
        GradientStop { position: 0.62; color: hero.c.card }
    }

    Item {
        id: back
        anchors.fill: parent
    }

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.leftMargin: 20; anchors.rightMargin: 16
        spacing: 18
        Item {
            id: lead
            visible: implicitWidth > 0
            implicitWidth: childrenRect.width
            implicitHeight: childrenRect.height
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text { textFormat: Text.PlainText;
                visible: hero.kicker !== ""
                Layout.fillWidth: true
                text: hero.kicker
                font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                font.capitalization: Font.AllUppercase; font.letterSpacing: 0.9
                color: hero.tint
                elide: Text.ElideRight
            }
            Text { textFormat: Text.PlainText;
                Layout.fillWidth: true
                text: hero.title
                font.family: "Schibsted Grotesk"; font.pixelSize: hero.titleSize; font.weight: Font.Bold
                font.letterSpacing: -0.5
                color: hero.c.text
                elide: Text.ElideRight
                Accessible.role: Accessible.Heading
            }
            Flow {
                Layout.fillWidth: true
                Layout.topMargin: 3
                spacing: 10
                visible: hero.meta !== "" || hero.offline
                Text { textFormat: Text.PlainText;
                    visible: hero.meta !== ""
                    text: hero.meta
                    height: 20; verticalAlignment: Text.AlignVCenter
                    font.family: "JetBrains Mono"; font.pixelSize: 13
                    color: hero.c.muted
                }
                Rectangle {
                    visible: hero.offline
                    height: 20; radius: 5
                    width: offRow.implicitWidth + 12
                    color: hero.c.saffronTint
                    Row {
                        id: offRow
                        anchors.centerIn: parent
                        spacing: 5
                        Icon { anchors.verticalCenter: parent.verticalCenter; name: "offline"; size: 13; color: hero.c.saffronInk }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: hero.offlineText
                            font.family: "JetBrains Mono"; font.pixelSize: 12
                            color: hero.c.saffronInk
                        }
                    }
                }
            }
        }
        RowLayout {
            id: trailing
            spacing: 6
            Layout.alignment: Qt.AlignVCenter
        }
    }
}
