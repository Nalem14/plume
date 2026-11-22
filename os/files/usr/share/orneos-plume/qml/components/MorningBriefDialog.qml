// Morning Brief ("Ma journée en 30 secondes"): today's events, unread priority mails, and tasks at a glance,
// each clickable to jump straight there, plus one-click Ornis synthesis.
import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Layouts

Popup {
    id: dlg
    readonly property var c: theme.c
    readonly property var loc: Qt.locale(plume.locale)
    property var data: ({ events: [], mails: [], tasks: [], prompt: "" })

    function openBrief() {
        data = plume.morningBriefData()
        open()
    }

    parent: Overlay.overlay
    x: Math.round((parent.width - width) / 2)
    y: Math.round((parent.height - height) / 2)
    width: Math.min(560, parent.width - 48)
    height: Math.min(620, Math.max(300, body.implicitHeight + 210))
    padding: 0
    modal: true
    focus: true

    Overlay.modal: Rectangle { color: dlg.c.scrim }
    enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 150; easing.type: Easing.OutCubic } }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 100 } }

    background: Item {
        RectangularShadow {
            anchors.fill: card; radius: card.radius
            blur: 36; offset.y: 14; color: dlg.c.shadow
        }
        Rectangle {
            id: card
            anchors.fill: parent
            radius: 12
            color: dlg.c.overlay
            border.width: 1; border.color: dlg.c.overlayLine
        }
    }

    contentItem: ColumnLayout {
        id: briefCol
        width: dlg.width
        spacing: 0
        // Header
        RowLayout {
            Layout.fillWidth: true
            Layout.margins: 20; Layout.bottomMargin: 14
            spacing: 12
            Rectangle {
                width: 38; height: 38; radius: 10
                color: dlg.c.tint
                Icon { anchors.centerIn: parent; name: "ornis"; size: 20; color: dlg.c.accent }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Text {
                    Layout.fillWidth: true
                    text: plume.t.brief_title
                    font.family: "Schibsted Grotesk"; font.pixelSize: 19; font.weight: Font.Bold
                    color: dlg.c.text
                }
                Text {
                    Layout.fillWidth: true
                    text: dlg.loc.toString(new Date(), "dddd d MMMM yyyy")
                    font.family: "Schibsted Grotesk"; font.pixelSize: 13
                    color: dlg.c.muted
                }
            }
            OButton { kind: "quiet"; iconName: "close"; iconSize: 14; implicitWidth: 32; onClicked: dlg.close() }
        }
        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: dlg.c.hairline }

        Flickable {
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentHeight: body.implicitHeight + 32
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            ColumnLayout {
                id: body
                x: 20; y: 16
                width: parent.width - 40
                spacing: 16

                // Events
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    Text {
                        text: plume.t.brief_events
                        font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium; font.letterSpacing: 0.8
                        color: dlg.c.famOrganize
                    }
                    Text {
                        visible: (dlg.data.events || []).length === 0
                        text: plume.t.brief_empty
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.italic: true
                        color: dlg.c.faint
                    }
                    Repeater {
                        model: dlg.data.events || []
                        delegate: AbstractButton {
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: 36
                            hoverEnabled: true
                            onClicked: { dlg.close(); plume.openItem("event", modelData.ref, "") }
                            background: Rectangle { radius: 8; color: parent.hovered ? dlg.c.hover : dlg.c.card; border.width: 1; border.color: dlg.c.hairline }
                            contentItem: RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12
                                spacing: 10
                                Text { text: modelData.time; font.family: "JetBrains Mono"; font.pixelSize: 12; font.weight: Font.Medium; color: dlg.c.famOrganize }
                                Text { Layout.fillWidth: true; text: modelData.title; elide: Text.ElideRight; font.family: "Schibsted Grotesk"; font.pixelSize: 14; color: dlg.c.text }
                            }
                        }
                    }
                }

                // Unread Mails
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    Text {
                        text: plume.t.brief_mails
                        font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium; font.letterSpacing: 0.8
                        color: dlg.c.famCommunicate
                    }
                    Text {
                        visible: (dlg.data.mails || []).length === 0
                        text: plume.t.brief_empty
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.italic: true
                        color: dlg.c.faint
                    }
                    Repeater {
                        model: dlg.data.mails || []
                        delegate: AbstractButton {
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: 38
                            hoverEnabled: true
                            onClicked: { dlg.close(); plume.openItem("mail", modelData.ref, "") }
                            background: Rectangle { radius: 8; color: parent.hovered ? dlg.c.hover : dlg.c.card; border.width: 1; border.color: dlg.c.hairline }
                            contentItem: RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12
                                spacing: 10
                                Icon { name: "mail"; size: 15; color: dlg.c.famCommunicate }
                                Text { Layout.fillWidth: true; text: modelData.title; elide: Text.ElideRight; font.family: "Schibsted Grotesk"; font.pixelSize: 14; color: dlg.c.text }
                                Text { Layout.maximumWidth: 160; text: modelData.from; elide: Text.ElideRight; font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: dlg.c.muted }
                            }
                        }
                    }
                }

                // Priority Tasks
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    Text {
                        text: plume.t.brief_tasks
                        font.family: "JetBrains Mono"; font.pixelSize: 11; font.weight: Font.Medium; font.letterSpacing: 0.8
                        color: dlg.c.accent
                    }
                    Text {
                        visible: (dlg.data.tasks || []).length === 0
                        text: plume.t.brief_empty
                        font.family: "Schibsted Grotesk"; font.pixelSize: 13; font.italic: true
                        color: dlg.c.faint
                    }
                    Repeater {
                        model: dlg.data.tasks || []
                        delegate: AbstractButton {
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: 36
                            hoverEnabled: true
                            onClicked: { dlg.close(); plume.openItem("task", modelData.uid, "orneos://task/" + modelData.uid) }
                            background: Rectangle { radius: 8; color: parent.hovered ? dlg.c.hover : dlg.c.card; border.width: 1; border.color: dlg.c.hairline }
                            contentItem: RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12
                                spacing: 10
                                Icon { name: "checklist"; size: 15; color: dlg.c.accent }
                                Text { Layout.fillWidth: true; text: (modelData.priority > 0 ? "!".repeat(modelData.priority) + " " : "") + modelData.title; elide: Text.ElideRight; font.family: "Schibsted Grotesk"; font.pixelSize: 14; color: dlg.c.text }
                            }
                        }
                    }
                }
            }
        }

        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: dlg.c.hairline }
        RowLayout {
            Layout.fillWidth: true
            Layout.margins: 16
            Item { Layout.fillWidth: true }
            OButton {
                kind: "accent"; iconName: "ornis"; text: plume.t.brief_ornis
                onClicked: {
                    const p = dlg.data.prompt || ""
                    dlg.close()
                    if (p) plume.askOrnis(p)
                }
            }
        }
    }
}
