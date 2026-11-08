// The rail of Plume (Windows, macOS, Linux outside Orneos OS): quiet, in the window colour. Only the open module
// takes its family's colour (its glyph and the band on its edge, as on the widgets); the counts stay saffron.
// The brand is spent in one place: docs/REFONTE-ORNIS.md.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: rail
    readonly property var c: theme.c
    implicitWidth: 76
    color: c.chrome
    signal appsRequested()
    signal ornisRequested()             // Ornis beside the module (Ctrl+J)
    property bool ornisOpen: false
    readonly property var families: ({ mail: c.famCommunicate, contacts: c.famCommunicate, calendar: c.famOrganize,
                                        tasks: c.famOrganize, notes: c.famDocs, passwords: c.famTools, ornis: c.famCommunicate,
                                        meet: c.famCommunicate, photos: c.famMedia })
    // a module of the grid in front (the Photothèque): the Apps button holds its place, in its colour
    readonly property var gridModule: (suite.grid || []).find(g => g.key === plume.module) || null

    Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: rail.c.hairline }

    component RailButton: AbstractButton {
        id: rb
        property string module
        property string iconName
        property int badge: 0
        property bool live: false        // Meet: a call goes on (a green dot that breathes)
        readonly property bool active: plume.module === module
        readonly property color tint: rail.families[module] || rail.c.action
        width: 62; height: 58
        anchors.horizontalCenter: parent.horizontalCenter
        hoverEnabled: true
        focusPolicy: Qt.StrongFocus
        Accessible.name: text
        onClicked: plume.setModule(module)
        background: Rectangle {
            radius: 9
            color: rb.active ? rail.c.card : rb.hovered ? rail.c.hover : "transparent"
            Behavior on color { ColorAnimation { duration: 120 } }
            Band {
                visible: rb.active
                x: -7
                anchors { top: parent.top; bottom: parent.bottom; topMargin: 12; bottomMargin: 12 }
                radius: 1.5
                color: rb.tint
            }
        }
        contentItem: Item {
            Icon {
                id: glyph
                anchors.horizontalCenter: parent.horizontalCenter
                y: 9
                name: rb.iconName
                size: 22
                hovered: rb.hovered
                color: rb.active ? rb.tint : rail.c.muted
            }
            Rectangle {                  // a call goes on: green, it breathes (the count waits)
                visible: rb.live
                x: glyph.x + 17; y: glyph.y - 4
                width: 11; height: 11; radius: 5.5
                color: "#2F9E7E"
                border.width: 2; border.color: rail.c.chrome
                SequentialAnimation on opacity { running: rb.live; loops: Animation.Infinite
                    NumberAnimation { to: 0.4; duration: 900 } NumberAnimation { to: 1; duration: 900 } }
            }
            Rectangle {                  // saffron count, like the dock
                visible: rb.badge > 0 && !rb.live
                x: glyph.x + 15; y: glyph.y - 7
                height: 18; radius: 9
                width: Math.max(18, count.implicitWidth + 9)
                color: rail.c.saffron
                Text {
                    id: count
                    anchors.centerIn: parent
                    text: rb.badge > 99 ? "99+" : rb.badge
                    font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium
                    color: rail.c.saffronText
                }
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                y: 35
                width: rb.width - 4
                horizontalAlignment: Text.AlignHCenter
                fontSizeMode: Text.HorizontalFit      // a long name (German) shrinks rather than spill out
                minimumPixelSize: 10
                text: rb.text
                font.family: "Schibsted Grotesk"; font.pixelSize: 11
                font.weight: rb.active ? Font.DemiBold : Font.Medium
                color: rb.active ? rail.c.text : rail.c.muted
            }
            Rectangle {
                anchors.fill: parent; anchors.margins: -2
                radius: 9; color: "transparent"
                border.width: 2; border.color: rail.c.saffron
                visible: rb.visualFocus
            }
        }
    }

    Column {
        anchors.top: parent.top
        anchors.topMargin: 14
        width: parent.width
        spacing: 6

        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            width: 38; height: 38; radius: 10
            color: rail.c.famCommunicate
            Icon { anchors.centerIn: parent; name: "plume"; size: 22; color: "#FFFFFF" }
        }
        Item { width: 1; height: 12 }
        RailButton { module: "mail"; iconName: "mail"; text: plume.t.mail; badge: mail.state === "ready" ? mail.inboxUnseen : plume.unread }
        RailButton { module: "calendar"; iconName: "calendar"; text: plume.t.calendar; badge: agenda.pending }
        RailButton { module: "contacts"; iconName: "contacts"; text: plume.t.contacts }
        RailButton { visible: plume.modules.indexOf(module) >= 0; module: "meet"; iconName: "video"; text: plume.t.meet; badge: suite.badges.meet || 0
                     live: !!suite.call.active
                     ToolTip.visible: live && hovered; ToolTip.delay: 300
                     ToolTip.text: (suite.call.label + " · " + suite.call.name).replace(/&/g, "&amp;").replace(/</g, "&lt;")
                     Accessible.description: live ? suite.call.label + " · " + suite.call.name : "" }
        RailButton { visible: plume.modules.indexOf(module) >= 0; module: "notes"; iconName: "note"; text: plume.t.notes }
        RailButton { visible: plume.modules.indexOf(module) >= 0; module: "tasks"; iconName: "checklist"; text: plume.t.tasks; badge: suite.badges.tasks || 0 }
        RailButton { visible: plume.modules.indexOf(module) >= 0; module: "passwords"; iconName: "key"; text: plume.t.passwords_rail; Accessible.name: plume.t.passwords }
        RailButton { visible: plume.modules.indexOf(module) >= 0; module: "ornis"; iconName: "ornis"; text: plume.t.ornis; badge: suite.badges.ornis || 0 }
    }

    // Ornis beside the module shown (Ctrl+J): the agent with what is open (a message, an event, a contact)
    AbstractButton {
        id: ornisButton
        visible: suite.ornisPanel && plume.module !== "ornis"
        anchors.bottom: appsButton.top
        anchors.bottomMargin: 4
        anchors.horizontalCenter: parent.horizontalCenter
        width: 48; height: 48
        hoverEnabled: true
        focusPolicy: Qt.StrongFocus
        Accessible.name: plume.t.ornis_beside
        Accessible.checkable: true
        Accessible.checked: rail.ornisOpen
        ToolTip.visible: hovered
        ToolTip.delay: 600
        ToolTip.text: plume.t.ornis_beside + "  (Ctrl+J)"
        onClicked: rail.ornisRequested()
        background: Rectangle {
            radius: 9
            color: rail.ornisOpen ? rail.c.tint : ornisButton.hovered ? rail.c.hover : "transparent"
            border.width: ornisButton.visualFocus ? 2 : 0
            border.color: rail.c.saffron
        }
        contentItem: Item {
            Icon { anchors.centerIn: parent; name: "ornis"; size: 22
                   color: rail.ornisOpen ? rail.c.tintText : ornisButton.hovered ? rail.c.text : rail.c.muted }
        }
    }

    // the other apps of the cloud, in the browser (signed in)
    AbstractButton {
        id: appsButton
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 14
        anchors.horizontalCenter: parent.horizontalCenter
        width: 48; height: 48
        hoverEnabled: true
        focusPolicy: Qt.StrongFocus
        Accessible.name: rail.gridModule ? plume.t.apps + " · " + rail.gridModule.name : plume.t.apps
        ToolTip.visible: hovered
        ToolTip.delay: 600
        ToolTip.text: rail.gridModule ? plume.t.apps + " · " + rail.gridModule.name : plume.t.apps
        onClicked: rail.appsRequested()
        background: Rectangle {
            radius: 9
            color: rail.gridModule ? rail.c.card : appsButton.hovered ? rail.c.hover : "transparent"
            border.width: appsButton.visualFocus ? 2 : 0
            border.color: rail.c.saffron
            Band {
                visible: !!rail.gridModule
                x: -14
                anchors { top: parent.top; bottom: parent.bottom; topMargin: 10; bottomMargin: 10 }
                radius: 1.5
                color: rail.families[plume.module] || rail.c.action
            }
        }
        contentItem: Item {
            Icon { anchors.centerIn: parent; name: rail.gridModule ? rail.gridModule.glyph : "apps"; size: 22
                   color: rail.gridModule ? (rail.families[plume.module] || rail.c.action) : appsButton.hovered ? rail.c.text : rail.c.muted }
        }
    }
}
