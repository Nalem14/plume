// SPDX-License-Identifier: GPL-2.0-or-later
// Photos on the desktop, like the photo widget of macOS: the cloud's photos (Memories) in turn, recent ones,
// favourites, "on this day" or one album. Small: one photo at a time. Wide: the photo and the next two beside
// it. Tall or large: the photo, and a strip of the following ones. A slow zoom while a photo is shown (none
// when animations are turned off); the pointer on the widget holds the photo. A click opens it in Photos.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import QtQuick.Effects
import org.kde.kirigami as Kirigami
import org.kde.plasma.components as PC3
import "strings.js" as S
import "ornis.js" as Ornis

Frame {
    id: root
    property string source: "recent"
    property int seconds: 30
    readonly property var feed: bridge
    readonly property var items: bridge.result.items || []
    readonly property string shown: bridge.result.shown || source
    property int turn: 0
    readonly property var current: items.length ? items[turn % items.length] : null
    readonly property bool mosaic: wide && items.length > 2
    readonly property bool motion: Kirigami.Units.longDuration > 0

    family: "media"
    context: S.tr("photos") + " · " + label()
    onOpened: bridge.launch(current ? "orneos-photos --show=" + current.id : "orneos-photos")

    function label() {
        const kind = shown.split(":")[0];
        if (kind === "album") {
            const id = shown.slice(6);
            return ((bridge.result.albums || []).find(a => a.id === id) || {}).name || S.tr("album");
        }
        return S.tr({favorites: "favoritePhotos", onthisday: "onThisDay"}[kind] || "recentPhotos");
    }
    // The caption: "3 years ago" for a memory, else its date.
    function caption(item) {
        if (!item) return "";
        const [y, m, d] = item.day.split("-").map(Number);
        const date = new Date(y, m - 1, d);
        if (root.shown === "onthisday") {
            const years = new Date().getFullYear() - y;
            return years === 1 ? S.tr("oneYearAgo") : S.fmt("yearsAgo", years);
        }
        return Qt.locale().toString(date, y === new Date().getFullYear() ? "d MMMM" : "d MMMM yyyy");
    }
    function at(offset) { return items.length ? items[(turn + offset) % items.length] : null; }
    function step(delta) { if (items.length) turn = (turn + delta + items.length) % items.length; }

    Bridge {
        id: bridge
        command: "/usr/libexec/orneos-widget photos --source=" + quote(root.source)
        interval: 600000
    }
    onItemsChanged: turn = 0
    Timer {
        interval: Math.max(5, root.seconds) * 1000
        repeat: true
        running: root.items.length > 1 && !hover.hovered
        onTriggered: root.step(1)
    }
    HoverHandler { id: hover }

    Skeleton {
        visible: bridge.result.state === "loading"
        Layout.fillWidth: true
        Layout.fillHeight: true
        rows: 2
        lead: false
        tone: Qt.alpha(Kirigami.Theme.textColor, 0.1)
    }
    PC3.Label {
        visible: text !== ""
        Layout.fillWidth: true
        text: ["signed_out", "error", "missingAlbum", "emptyPhotos"].indexOf(bridge.result.state) >= 0 ? S.tr(bridge.result.state)
              : bridge.result.state === "offline" && !root.items.length ? S.tr("offline")
              : root.source === "onthisday" && root.shown !== "onthisday" && root.roomy ? S.tr("noMemoryToday") : ""
        wrapMode: Text.WordWrap
        font: Kirigami.Theme.smallFont
        opacity: 0.75
    }
    PC3.Button {
        visible: bridge.result.state === "signed_out" || bridge.result.state === "error"
        text: bridge.result.state === "signed_out" ? "Orneos Connect" : S.tr("retry")
        onClicked: bridge.result.state === "signed_out" ? bridge.launch("orneos-connect") : bridge.refresh()
    }

    // One layer of a Picture (the mask of the Picture rounds it).
    component Layer: Image {
        required property bool front
        required property var owner
        anchors.fill: parent
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        opacity: front && status === Image.Ready ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: owner.view.motion ? 900 : 0; easing.type: Easing.InOutQuad } }
        scale: owner.main && owner.view.motion && front ? 1.07 : 1
        Behavior on scale { NumberAnimation { duration: owner.view.seconds * 1000 + 900 } }
    }

    // A photo, cropped to its place, fading into the next one; the slow zoom on the main one.
    component Picture: Item {
        id: picture
        required property var view
        property var item: null
        property bool main: false
        // Two layers: the new photo loads in the hidden one, then fades in over the other.
        property bool flip: false
        // Rounded by a mask over the whole photo, so the slow zoom stays inside its corners.
        layer.enabled: true
        layer.effect: MultiEffect {
            maskEnabled: true
            maskSource: shape
            maskThresholdMin: 0.5
            maskSpreadAtMin: 1
        }
        Rectangle {
            id: shape
            anchors.fill: parent
            radius: Ornis.t.radius.card
            visible: false
            layer.enabled: true
        }
        onItemChanged: {
            const next = item ? "file://" + item.image : "";
            if ((flip ? second : first).source.toString() === next) return;
            (flip ? first : second).source = next;
            flip = !flip;
        }
        Layer { id: first; owner: picture; front: !picture.flip }
        Layer { id: second; owner: picture; front: picture.flip }
        Rectangle {
            anchors.fill: parent
            radius: Ornis.t.radius.card
            visible: !picture.item
            color: Qt.alpha(picture.view.tint, 0.1)
        }
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: picture.view.feed.launch(picture.item ? "orneos-photos --show=" + picture.item.id : "orneos-photos")
            Accessible.role: Accessible.Button
            Accessible.name: picture.item ? S.tr("photos") + " · " + picture.view.caption(picture.item) : S.tr("photos")
        }
    }

    // ── The photo (and, wide, the next two beside it) ──
    RowLayout {
        visible: root.items.length > 0
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: Kirigami.Units.smallSpacing
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Picture {
                id: hero
                view: root
                anchors.fill: parent
                item: root.current
                main: true
            }
            Rectangle {
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                height: Math.min(parent.height * 0.45, Kirigami.Units.gridUnit * 4)
                radius: Ornis.t.radius.card
                gradient: Gradient {
                    GradientStop { position: 0; color: "transparent" }
                    GradientStop { position: 1; color: Qt.rgba(0.04, 0.08, 0.14, 0.7) }
                }
            }
            RowLayout {
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: Kirigami.Units.largeSpacing }
                Kirigami.Icon {
                    visible: !!(root.current && root.current.favorite)
                    Layout.preferredWidth: Kirigami.Units.iconSizes.small
                    Layout.preferredHeight: Kirigami.Units.iconSizes.small
                    source: "emblem-favorite"
                    color: "white"
                    isMask: true
                }
                PC3.Label {
                    Layout.fillWidth: true
                    text: root.caption(root.current)
                    color: "white"
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }
                // Wide: go back or on by hand, shown with the pointer.
                PC3.ToolButton {
                    visible: root.roomy && hover.hovered && root.items.length > 1
                    icon.name: "go-previous"
                    icon.color: "white"
                    Accessible.name: S.tr("previous")
                    onClicked: root.step(-1)
                }
                PC3.ToolButton {
                    visible: root.roomy && hover.hovered && root.items.length > 1
                    icon.name: "go-next"
                    icon.color: "white"
                    Accessible.name: S.tr("next")
                    onClicked: root.step(1)
                }
            }
        }
        ColumnLayout {
            visible: root.mosaic && !root.tall
            Layout.fillHeight: true
            Layout.fillWidth: false
            Layout.preferredWidth: parent.width * 0.34
            spacing: Kirigami.Units.smallSpacing
            Picture { view: root; Layout.fillWidth: true; Layout.fillHeight: true; item: root.at(1) }
            Picture { view: root; Layout.fillWidth: true; Layout.fillHeight: true; item: root.at(2) }
        }
    }
    // ── Tall or large: the following ones in a strip ──
    RowLayout {
        visible: root.tall && root.items.length > 2
        Layout.fillWidth: true
        Layout.fillHeight: false
        Layout.preferredHeight: Math.min(Kirigami.Units.gridUnit * 4, root.height * 0.22)
        Layout.maximumHeight: Layout.preferredHeight
        spacing: Kirigami.Units.smallSpacing
        Repeater {
            model: root.wide ? 4 : 3
            delegate: Picture {
                required property int index
                view: root
                Layout.fillWidth: true
                Layout.fillHeight: true
                item: root.at(index + 1)
            }
        }
    }
}
