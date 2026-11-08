// The event's card, next to where it was clicked: when, where, Meet, guests, the answer to an
// invitation, then edit and delete.
import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Layouts
import "../components"
import "../components/colors.js" as Colors
import "../components/dates.js" as D
import "repeat.js" as R

Popup {
    id: card
    property var info: ({})
    signal editRequested(var info)
    signal deleteRequested(var info)
    signal duplicateRequested(var info)
    property bool allGuests: false
    property point anchorPoint
    property real anchorWidth
    readonly property var c: theme.c
    readonly property var loc: Qt.locale(plume.locale)

    function show(occ, anchorItem) {
        info = agenda.details(occ.eventId, occ.rid)
        if (!info.eventId)
            return
        allGuests = false
        anchorPoint = anchorItem.mapToItem(Overlay.overlay, 0, 0)
        anchorWidth = anchorItem.width
        place()
        open()
        Qt.callLater(place)
    }
    // beside what was clicked, and always whole in the window (its height is known once laid out)
    function place() {
        const overlay = Overlay.overlay
        const p = anchorPoint
        const w = width
        let x = p.x + anchorWidth + 10
        if (x + w > overlay.width - 16)
            x = p.x - w - 10
        if (x < 16)
            x = Math.min(overlay.width - w - 16, Math.max(16, p.x))
        card.x = x
        card.y = Math.max(16, Math.min(p.y, overlay.height - height - 16))
    }
    onHeightChanged: if (opened) place()
    height: Math.min(implicitHeight, Overlay.overlay ? Overlay.overlay.height - 32 : implicitHeight)
    // the links of a description: plain text with its addresses made clickable
    function linkify(text) {
        const esc = String(text || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
        return esc.replace(/(https?:\/\/[^\s<]+[^\s<.,;:!?)\]'"])/g, '<a href="$1">$1</a>').replace(/\n/g, "<br>")
    }
    function mapUrl(place) { return "https://www.openstreetmap.org/search?query=" + encodeURIComponent(place) }
    readonly property var others: (info.attendees || []).filter(a => a.email !== (plume.profile.email || "").toLowerCase())

    function when() {
        if (!info.start)
            return ""
        const s = new Date(info.start), e = new Date(info.end)
        if (info.allDay) {
            const last = D.addDays(e, -1)
            return D.sameDay(s, last) || e <= s ? D.capitalize(loc.toString(s, "dddd d MMMM"))
                   : D.capitalize(loc.toString(s, "d MMM")) + " – " + loc.toString(last, "d MMM yyyy")
        }
        if (D.sameDay(s, e))
            return D.capitalize(loc.toString(s, "dddd d MMMM")) + " · " + D.hm(s) + " – " + D.hm(e)
        return D.capitalize(loc.toString(s, "d MMM HH:mm")) + " – " + loc.toString(e, "d MMM HH:mm")
    }

    // keyboard: E or Enter edits, Suppr deletes, D duplicates (the card has the focus while it is open)
    Shortcut { enabled: card.opened && !card.info.readonly && !card.info.canRespond; sequences: ["E", "Return", "Enter"]; onActivated: { card.close(); card.editRequested(card.info) } }
    Shortcut { enabled: card.opened && !card.info.readonly; sequences: [StandardKey.Delete, "Backspace"]; onActivated: { card.close(); card.deleteRequested(card.info) } }
    Shortcut { enabled: card.opened && agenda.defaultCalendar > 0; sequence: "D"; onActivated: { card.close(); card.duplicateRequested(card.info) } }

    parent: Overlay.overlay
    width: 380
    padding: 0
    focus: true
    enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 120; easing.type: Easing.OutCubic } }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 90 } }

    background: Item {
        RectangularShadow { anchors.fill: box; radius: 10; blur: 32; offset.y: 12; color: card.c.shadow }
        Rectangle { id: box; anchors.fill: parent; radius: 10; color: card.c.overlay; border.width: 1; border.color: card.c.overlayLine }
    }

    contentItem: ColumnLayout {
        spacing: 0
        // the details scroll when the card would not fit the window (many guests, a long description)
        ScrollView {
            id: detailsScroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredHeight: details.implicitHeight + 30
            contentWidth: availableWidth
            contentHeight: details.implicitHeight + 30
            clip: true
        ColumnLayout {
            id: details
            x: 18; y: 18
            width: detailsScroll.availableWidth - 36
            spacing: 10
            RowLayout {
                spacing: 8
                Rectangle { implicitWidth: 10; implicitHeight: 10; radius: 3; color: Colors.display(card.info.color || "#002FA7", theme.dark) }
                // the calendar: another one is picked here, an invitation too (it has no editor)
                AbstractButton {
                    id: calendarPick
                    readonly property var others: card.info.readonly ? [] : agenda.calendars.filter(c => !c.readonly && c.id !== card.info.calendarId)
                    Layout.fillWidth: true
                    enabled: others.length > 0
                    hoverEnabled: true
                    Accessible.name: plume.t.event_move
                    onClicked: calendarMenu.open()
                    contentItem: RowLayout {
                        spacing: 4
                        Text {
                            Layout.maximumWidth: calendarPick.width - 20
                            text: (card.info.calendarName || "") + (card.info.readonly ? " · " + plume.t.readonly : "")
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13
                            font.underline: calendarPick.enabled && calendarPick.hovered
                            color: calendarPick.hovered ? card.c.text : card.c.muted; elide: Text.ElideRight
                        }
                        Icon { visible: calendarPick.enabled; name: "chevronDown"; size: 13; color: card.c.muted }
                        Item { Layout.fillWidth: true }
                    }
                    background: null
                    OMenu {
                        id: calendarMenu
                        y: calendarPick.height + 4
                        heading: plume.t.event_move
                        Repeater {
                            model: calendarPick.others
                            OMenuItem {
                                required property var modelData
                                text: modelData.name
                                dot: Colors.display(modelData.color, theme.dark)
                                onTriggered: { agenda.moveEvent(card.info.eventId, modelData.id); card.close() }
                            }
                        }
                    }
                }
                OButton { kind: "quiet"; iconName: "close"; iconSize: 16; height_: 28; implicitWidth: 28; Accessible.name: plume.t.close; onClicked: card.close() }
            }
            Text {
                Layout.fillWidth: true
                text: card.info.title || plume.t.untitled
                wrapMode: Text.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 19; font.weight: Font.DemiBold
                color: card.c.text
            }
            RowLayout {
                spacing: 10
                Icon { name: "clock"; size: 16; color: card.c.muted }
                Text {
                    Layout.fillWidth: true
                    text: card.when() + (card.info.recurring ? "\n" + (R.describe(card.info.repeat, new Date(card.info.start), card.loc, plume.t) || plume.t.recurring) : "")
                    wrapMode: Text.Wrap
                    font.family: "Schibsted Grotesk"; font.pixelSize: 14
                    color: card.c.text
                }
            }
            // set in another time zone: its hours there too
            Text {
                visible: !!card.info.zoneTimes
                Layout.fillWidth: true
                Layout.leftMargin: 26
                Layout.topMargin: -6
                text: plume.t.zone_times.replace("%1", (card.info.tzid || "").split("/").pop().replace(/_/g, " ")).replace("%2", card.info.zoneTimes || "")
                wrapMode: Text.Wrap
                font.family: "Schibsted Grotesk"; font.pixelSize: 13
                color: card.c.muted
            }
            RowLayout {
                visible: !!card.info.location
                spacing: 10
                Icon { name: "pin"; size: 16; color: card.c.muted }
                // a click: the address on a map (or the page, when the place is a link)
                Text {
                    id: placeText
                    Layout.fillWidth: true
                    text: card.info.location || ""
                    textFormat: Text.PlainText
                    wrapMode: Text.Wrap
                    font.family: "Schibsted Grotesk"; font.pixelSize: 14
                    font.underline: placeArea.containsMouse
                    color: card.c.text
                    MouseArea {
                        id: placeArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        Accessible.role: Accessible.Link
                        Accessible.name: plume.t.open_map
                        onClicked: {
                            const place = (card.info.location || "").trim()
                            plume.openUrl(/^https?:\/\//.test(place) ? place : card.mapUrl(place))
                        }
                    }
                    ToolTip.visible: placeArea.containsMouse
                    ToolTip.delay: 600
                    ToolTip.text: /^https?:\/\//.test(card.info.location || "") ? plume.t.open_link : plume.t.open_map
                }
            }
            OButton {
                visible: !!card.info.meet
                kind: "primary"
                iconName: "video"
                text: card.info.meetName ? plume.t.join_on.replace("%1", card.info.meetName) : plume.t.join_meet
                onClicked: { plume.openUrl(card.info.meet); card.close() }
            }
            Text {
                id: description
                property bool more: false
                visible: !!card.info.description
                Layout.fillWidth: true
                text: card.linkify(card.info.description)
                textFormat: Text.StyledText
                linkColor: card.c.accent
                wrapMode: Text.Wrap
                maximumLineCount: more ? 200 : 6
                elide: Text.ElideRight
                lineHeight: 1.25
                font.family: "Schibsted Grotesk"; font.pixelSize: 14
                color: card.c.muted
                onLinkActivated: link => plume.openUrl(link)
                HoverHandler { cursorShape: description.hoveredLink ? Qt.PointingHandCursor : Qt.ArrowCursor }
            }
            Text {
                visible: description.visible && description.truncated && !description.more
                text: plume.t.show_more
                font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                color: card.c.accent
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: description.more = true }
            }
            ColumnLayout {
                visible: (card.info.attendees || []).length > 0
                Layout.fillWidth: true
                spacing: 6
                Text {
                    visible: !!card.info.organizer
                    text: plume.t.organizer.replace("%1", card.info.organizerName || card.info.organizer || "")
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                    color: card.c.muted
                }
                Repeater {
                    model: (card.info.attendees || []).slice(0, card.allGuests ? 500 : 6)
                    RowLayout {
                        required property var modelData
                        spacing: 8
                        Icon { name: "user"; size: 15; color: card.c.muted }
                        Text {
                            Layout.fillWidth: true
                            text: (modelData.name || modelData.email) + (modelData.optional ? " · " + plume.t.guest_optional : "")
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13
                            color: card.c.text
                        }
                        Text {
                            text: plume.t["status_" + modelData.status] || ""
                            font.family: "Schibsted Grotesk"; font.pixelSize: 12
                            color: modelData.status === "ACCEPTED" ? card.c.ok : modelData.status === "DECLINED" ? card.c.danger : card.c.muted
                        }
                    }
                }
                Text {
                    visible: !card.allGuests && (card.info.attendees || []).length > 6
                    text: plume.t.more_guests.replace("%1", (card.info.attendees || []).length - 6)
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.weight: Font.DemiBold
                    color: card.c.accent
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: card.allGuests = true }
                }
            }
        }

        }

        // the answer to an invitation
        Rectangle {
            visible: !!card.info.canRespond
            Layout.fillWidth: true
            Layout.preferredHeight: rsvp.implicitHeight + 24
            color: card.info.myStatus === "NEEDS-ACTION" ? card.c.saffronTint : "transparent"
            Rectangle { width: parent.width; height: 1; color: card.c.hairline }
            ColumnLayout {
                id: rsvp
                anchors.fill: parent; anchors.leftMargin: 18; anchors.rightMargin: 18; anchors.topMargin: 12; anchors.bottomMargin: 12
                spacing: 8
                Text {
                    text: plume.t.rsvp
                    font.family: "Schibsted Grotesk"; font.pixelSize: 14; font.weight: Font.DemiBold
                    color: card.info.myStatus === "NEEDS-ACTION" ? card.c.saffronInk : card.c.text
                }
                RowLayout {
                    spacing: 6
                    Repeater {
                        model: [["ACCEPTED", plume.t.accept], ["TENTATIVE", plume.t.maybe], ["DECLINED", plume.t.decline]]
                        OButton {
                            required property var modelData
                            Layout.fillWidth: true
                            kind: card.info.myStatus === modelData[0] ? "primary" : "secondary"
                            height_: 32
                            text: modelData[1]
                            onClicked: { agenda.respond(card.info.eventId, modelData[0]); card.close() }
                        }
                    }
                }
            }
        }

        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: card.c.hairline }
        RowLayout {
            Layout.fillWidth: true
            Layout.margins: 10; Layout.leftMargin: 12
            spacing: 6
            OButton { visible: !card.info.readonly && !card.info.canRespond; kind: "secondary"; iconName: "draft"; text: plume.t.edit; onClicked: { card.close(); card.editRequested(card.info) } }
            // read-only calendar: a copy goes into mine
            OButton {
                visible: !!card.info.readonly && agenda.defaultCalendar > 0
                kind: "secondary"; iconName: "copy"; text: plume.t.copy_to_mine
                onClicked: { card.close(); card.duplicateRequested(card.info) }
            }
            Item { Layout.fillWidth: true }
            OButton { visible: !card.info.readonly; kind: "quiet"; iconName: "trash"; tip: plume.t.delete; implicitWidth: 34; onClicked: { card.close(); card.deleteRequested(card.info) } }
            OButton {
                id: moreButton
                kind: "quiet"; iconName: "more"; tip: plume.t.more_actions; implicitWidth: 34
                onClicked: moreMenu.open()
                OMenu {
                    id: moreMenu
                    y: moreButton.height + 4
                    OMenuItem {
                        visible: !card.info.readonly && !card.info.canRespond; height: visible ? implicitHeight : 0
                        text: plume.t.duplicate; iconName: "copy"
                        onTriggered: { card.close(); card.duplicateRequested(card.info) }
                    }
                    OMenuItem {
                        visible: card.others.length > 0 || (!!card.info.organizer && card.info.canRespond); height: visible ? implicitHeight : 0
                        text: plume.t.write_guests; iconName: "mail"
                        onTriggered: {
                            const to = card.others.map(a => a.email)
                            if (card.info.organizer && to.indexOf(card.info.organizer) < 0 && card.info.organizer !== (plume.profile.email || "").toLowerCase())
                                to.unshift(card.info.organizer)
                            card.close()
                            plume.compose("mailto:" + to.join(",") + "?subject=" + encodeURIComponent(card.info.title || ""))
                        }
                    }
                    OMenuItem {
                        text: plume.t.event_to_notes; iconName: "note"
                        onTriggered: { if (!agenda.toNotes(card.info.eventId, card.info.rid || "")) plume.toast(plume.t.app_missing); card.close() }
                    }
                    OMenuItem {
                        text: plume.t.event_to_tasks; iconName: "done"
                        onTriggered: { if (!agenda.toTasks(card.info.eventId, card.info.rid || "")) plume.toast(plume.t.app_missing); card.close() }
                    }
                    OMenuItem {
                        visible: !!card.info.meet; height: visible ? implicitHeight : 0
                        text: plume.t.copy_meet; iconName: "link"
                        onTriggered: { plume.copyText(card.info.meet); card.close() }
                    }
                }
            }
        }
    }
}
