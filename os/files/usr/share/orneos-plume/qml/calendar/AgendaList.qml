// Schedule view: the next weeks as a list, one heading per day that has something.
import QtQuick
import QtQuick.Controls
import "../components"
import "../components/colors.js" as Colors
import "../components/dates.js" as D

Rectangle {
    id: list
    property date start: new Date()
    property var items: []
    property bool searching: false        // search results: in the order given (next ones, then past ones)
    property string emptyText: plume.t.no_events
    signal eventClicked(var occ, Item anchorItem)
    signal moreWanted()
    readonly property var c: theme.c
    readonly property var loc: Qt.locale(plume.locale)
    color: c.card

    readonly property var rows: {
        const out = []
        let last = ""
        const sorted = searching ? items : items.slice().sort((a, b) => {
            const da = D.iso(new Date(Math.max(a.startTs * 1000, +start))), db = D.iso(new Date(Math.max(b.startTs * 1000, +start)))
            return da < db ? -1 : da > db ? 1 : (b.allDay - a.allDay) || (a.startTs - b.startTs)
        })
        for (const occ of sorted) {
            const s = new Date(occ.start)
            const day = D.iso(s < start ? start : s)
            if (day !== last) {
                out.push({ heading: true, day: day })
                last = day
            }
            out.push({ heading: false, occ: occ })
        }
        return out
    }

    ListView {
        id: view
        anchors.fill: parent
        anchors.leftMargin: 32; anchors.rightMargin: 32
        clip: true
        model: list.rows
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}
        header: Item { width: 1; height: 12 }
        onAtYEndChanged: if (atYEnd && !list.searching && contentHeight > height) list.moreWanted()
        footer: Item { width: 1; height: 24 }

        delegate: Loader {
            required property var modelData
            width: view.width
            sourceComponent: modelData.heading ? heading : row
            property var data_: modelData
        }

        Component {
            id: heading
            Item {
                height: 48
                readonly property date day: new Date(parent.data_.day + "T00:00")
                Text {
                    anchors.bottom: parent.bottom; anchors.bottomMargin: 8
                    text: D.capitalize(list.loc.toString(parent.day, parent.day.getFullYear() === new Date().getFullYear() ? "dddd d MMMM" : "dddd d MMMM yyyy"))
                    font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.weight: Font.DemiBold
                    color: D.sameDay(parent.day, new Date()) ? list.c.accent : list.c.text
                }
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: list.c.hairline }
            }
        }
        Component {
            id: row
            AbstractButton {
                id: item
                readonly property var occ: parent.data_.occ
                height: 48
                hoverEnabled: true
                onClicked: list.eventClicked(occ, item)
                background: Rectangle { radius: 6; color: item.hovered ? list.c.hover : "transparent" }
                contentItem: Row {
                    spacing: 14
                    leftPadding: 8
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        width: 110
                        text: item.occ.task ? (item.occ.time || plume.t.task_due)
                              : item.occ.allDay ? plume.t.all_day
                              : Qt.formatTime(new Date(item.occ.start), "HH:mm") + " – " + Qt.formatTime(new Date(item.occ.end), "HH:mm")
                        font.family: item.occ.allDay ? "Schibsted Grotesk" : "JetBrains Mono"
                        font.pixelSize: 13
                        color: list.c.muted
                    }
                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: 10; height: 10; radius: item.occ.task ? 3 : 5
                        color: item.occ.task ? "transparent" : Colors.display(item.occ.color, theme.dark)
                        border.width: item.occ.task ? 1.5 : 0; border.color: Colors.display(item.occ.color, theme.dark)
                    }
                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        width: item.width - 180
                        Text {
                            width: parent.width
                            text: item.occ.title || plume.t.untitled
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 15; font.weight: Font.Medium
                            font.strikeout: item.occ.myStatus === "DECLINED"
                            color: list.c.text
                        }
                        Text {
                            visible: text !== ""
                            width: parent.width
                            text: item.occ.task ? plume.t.task_in.replace("%1", item.occ.listName || plume.t.tasks_app)
                                  : item.occ.myStatus === "NEEDS-ACTION" ? plume.t["status_NEEDS-ACTION"] + (item.occ.location ? " · " + item.occ.location : "") : item.occ.location
                            elide: Text.ElideRight
                            font.family: "Schibsted Grotesk"; font.pixelSize: 13
                            color: item.occ.myStatus === "NEEDS-ACTION" ? list.c.saffronInk : list.c.muted
                        }
                    }
                }
            }
        }
    }

    Text {
        anchors.centerIn: parent
        visible: list.items.length === 0
        text: list.emptyText
        font.family: "Schibsted Grotesk"; font.pixelSize: 16
        color: list.c.muted
    }
}
