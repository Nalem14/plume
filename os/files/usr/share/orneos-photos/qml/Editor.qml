// Editing a photo: crop (free or to a ratio), quarter turns and mirror, light, contrast, saturation and warmth,
// black and white or sepia. Everything shows at once on the large preview; « Enregistrer » has the cloud apply
// the same edit to the original (Files keeps the previous one: « Revenir à l'original »), or saves a copy.
import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Layouts
import "components"

Item {
    id: editor
    readonly property var c: theme.c
    property bool opened: false
    property int fileid: 0
    property var photo: ({})
    property string tool: "adjust"           // "crop" | "adjust" | "filters"
    // the edit, as edit.py reads it
    property int rotate: 0
    property bool flipH: false
    property bool flipV: false
    property rect crop: Qt.rect(0, 0, 1, 1)
    property real ratio: 0                   // 0: free
    property real brightness: 0
    property real contrast: 0
    property real saturation: 0
    property real warmth: 0
    property string filter: ""
    readonly property bool changed: rotate % 360 !== 0 || flipH || flipV || filter !== "" || brightness !== 0 || contrast !== 0
                                    || saturation !== 0 || warmth !== 0 || crop.x > 0.001 || crop.y > 0.001
                                    || crop.width < 0.999 || crop.height < 0.999
    signal saved(int fileid, int shownId)

    function open(id) {
        photo = photos.photo(id)
        if (!photo.fileid || photo.video) return
        fileid = id
        reset()
        tool = "adjust"
        opened = true
        forceActiveFocus()
    }
    function reset() {
        rotate = 0; flipH = false; flipV = false; crop = Qt.rect(0, 0, 1, 1); ratio = 0
        brightness = 0; contrast = 0; saturation = 0; warmth = 0; filter = ""
    }
    function close() { opened = false; win.forceActiveFocus() }
    function save(copy) {
        photos.saveEdit(fileid, { rotate: rotate, flipH: flipH, flipV: flipV,
                                  crop: { x: crop.x, y: crop.y, w: crop.width, h: crop.height },
                                  brightness: brightness, contrast: contrast, saturation: saturation, warmth: warmth,
                                  filter: filter }, copy)
        close()
    }
    function turn(delta) {
        rotate = (rotate + delta + 360) % 360
        // the crop keeps its place on the photo: turned with it
        const r = crop
        crop = delta > 0 ? Qt.rect(1 - r.y - r.height, r.x, r.height, r.width) : Qt.rect(r.y, 1 - r.x - r.width, r.height, r.width)
        if (ratio > 0) setRatio(1 / ratio)
    }
    // a ratio of the shown photo (width / height), centred in the current crop
    function setRatio(value) {
        ratio = value
        if (value <= 0) return
        const sw = frame.shownW, sh = frame.shownH
        let w = crop.width, h = crop.width * sw / value / sh
        if (h > crop.height) { h = crop.height; w = crop.height * sh * value / sw }
        crop = Qt.rect(crop.x + (crop.width - w) / 2, crop.y + (crop.height - h) / 2, w, h)
    }

    visible: opened
    z: 12
    Keys.onPressed: event => {
        if (event.key === Qt.Key_Escape) { editor.close(); event.accepted = true }
        else if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && editor.changed) { editor.save(false); event.accepted = true }
    }

    Rectangle { anchors.fill: parent; color: "#070B12" }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 60
            Layout.leftMargin: 16; Layout.rightMargin: 16
            spacing: 10
            OButton { text: app.t.cancel; onClicked: editor.close() }
            Item { Layout.fillWidth: true }
            Text {
                text: app.t.edit_title
                font.family: "Schibsted Grotesk"; font.pixelSize: 16; font.weight: Font.DemiBold
                color: "white"
            }
            Item { Layout.fillWidth: true }
            OButton { kind: "quiet"; text: app.t.edit_reset; enabled: editor.changed; onClicked: editor.reset() }
            OButton {
                id: saveMore
                kind: "quiet"; implicitWidth: 34; iconName: "more"; tip: app.t.more
                onClicked: saveMenu.open()
                OMenu {
                    id: saveMenu
                    y: parent.height + 6
                    x: parent.width - width
                    OMenuItem { text: app.t.edit_save_copy; iconName: "duplicate"; enabled: editor.changed; onTriggered: editor.save(true) }
                    OMenuItem { text: app.t.edit_revert; iconName: "restore"; onTriggered: { photos.revertEdit(editor.fileid); editor.close() } }
                }
            }
            OButton { kind: "primary"; text: app.t.save; enabled: editor.changed; onClicked: editor.save(false) }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // the preview
            Item {
                id: area
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.margins: 28
                readonly property bool turned: editor.rotate % 180 !== 0
                readonly property real srcW: Math.max(1, editor.photo.w || 1)
                readonly property real srcH: Math.max(1, editor.photo.h || 1)

                // the photo as it will be, turned and mirrored; the whole of it while cropping, else only the crop
                Item {
                    id: viewport
                    width: frame.width * frame.visW
                    height: frame.height * frame.visH
                    x: (area.width - width) / 2
                    y: (area.height - height) / 2
                    clip: !frame.cropping
                    Item {
                        id: frame
                        readonly property real shownW: area.turned ? area.srcH : area.srcW
                        readonly property real shownH: area.turned ? area.srcW : area.srcH
                        readonly property bool cropping: editor.tool === "crop"
                        readonly property real visW: cropping ? 1 : editor.crop.width
                        readonly property real visH: cropping ? 1 : editor.crop.height
                        readonly property real fit: Math.min(area.width / (shownW * visW), area.height / (shownH * visH))
                        width: shownW * fit; height: shownH * fit
                        x: cropping ? 0 : -editor.crop.x * width
                        y: cropping ? 0 : -editor.crop.y * height

                        Item {
                            id: canvas
                            anchors.fill: parent
                            layer.enabled: true
                            // drawn too: without a GPU the effect below cannot draw, the photo still shows
                            // mirrored in the photo's own frame, then turned: as the cloud applies it
                            Thumb {
                                anchors.centerIn: parent
                                width: area.turned ? parent.height : parent.width
                                height: area.turned ? parent.width : parent.height
                                rotation: editor.rotate
                                mirror: editor.flipH
                                mirrorVertically: editor.flipV
                                address: editor.fileid ? "p/2048/" + editor.fileid + "/" + (editor.photo.etag || "") : ""
                                sourceSize: Qt.size(2048, 2048)
                                fillMode: Image.Stretch
                                asynchronous: true
                            }
                        }
                        MultiEffect {
                            id: look
                            source: canvas
                            anchors.fill: parent
                            brightness: editor.brightness * 0.3
                            contrast: editor.contrast * 0.45
                            saturation: editor.filter === "bw" || editor.filter === "sepia" ? -1 : editor.saturation * 0.8
                            colorization: editor.filter === "sepia" ? 0.45 : editor.warmth * 0.22
                            colorizationColor: editor.filter === "sepia" ? "#A06B33" : "#FF9A3C"
                        }
                    }
                }
                // outside the crop, while cropping: darker
                Item {
                    anchors.fill: parent
                    visible: frame.cropping
                    Rectangle { x: viewport.x; y: viewport.y; width: frame.width; height: editor.crop.y * frame.height; color: Qt.rgba(0, 0, 0, 0.55) }
                    Rectangle { x: viewport.x; y: viewport.y + (editor.crop.y + editor.crop.height) * frame.height; width: frame.width; height: (1 - editor.crop.y - editor.crop.height) * frame.height; color: Qt.rgba(0, 0, 0, 0.55) }
                    Rectangle { x: viewport.x; y: viewport.y + editor.crop.y * frame.height; width: editor.crop.x * frame.width; height: editor.crop.height * frame.height; color: Qt.rgba(0, 0, 0, 0.55) }
                    Rectangle { x: viewport.x + (editor.crop.x + editor.crop.width) * frame.width; y: viewport.y + editor.crop.y * frame.height; width: (1 - editor.crop.x - editor.crop.width) * frame.width; height: editor.crop.height * frame.height; color: Qt.rgba(0, 0, 0, 0.55) }
                    // the crop: moved by its inside, sized by its corners
                    Rectangle {
                        id: cropBox
                        x: viewport.x + editor.crop.x * frame.width
                        y: viewport.y + editor.crop.y * frame.height
                        width: editor.crop.width * frame.width
                        height: editor.crop.height * frame.height
                        color: "transparent"
                        border.width: 2; border.color: "white"
                        // thirds
                        Repeater {
                            model: 2
                            Rectangle { required property int index; x: cropBox.width * (index + 1) / 3; width: 1; height: cropBox.height; color: Qt.rgba(1, 1, 1, 0.35) }
                        }
                        Repeater {
                            model: 2
                            Rectangle { required property int index; y: cropBox.height * (index + 1) / 3; height: 1; width: cropBox.width; color: Qt.rgba(1, 1, 1, 0.35) }
                        }
                        DragHandler {
                            target: null
                            property rect start
                            onActiveChanged: if (active) start = editor.crop
                            onTranslationChanged: {
                                const nx = Math.max(0, Math.min(1 - start.width, start.x + translation.x / frame.width))
                                const ny = Math.max(0, Math.min(1 - start.height, start.y + translation.y / frame.height))
                                editor.crop = Qt.rect(nx, ny, start.width, start.height)
                            }
                        }
                        Repeater {
                            model: [[0, 0], [1, 0], [0, 1], [1, 1]]
                            Rectangle {
                                id: handle
                                required property var modelData
                                width: 22; height: 22; radius: 11
                                x: modelData[0] * cropBox.width - 11
                                y: modelData[1] * cropBox.height - 11
                                color: "white"
                                border.width: 2; border.color: editor.c.action
                                DragHandler {
                                    target: null
                                    property rect start
                                    onActiveChanged: if (active) start = editor.crop
                                    onTranslationChanged: {
                                        const min = 0.05
                                        let x1 = start.x, y1 = start.y, x2 = start.x + start.width, y2 = start.y + start.height
                                        const dx = translation.x / frame.width, dy = translation.y / frame.height
                                        if (handle.modelData[0] === 0) x1 = Math.max(0, Math.min(x2 - min, x1 + dx)); else x2 = Math.min(1, Math.max(x1 + min, x2 + dx))
                                        if (handle.modelData[1] === 0) y1 = Math.max(0, Math.min(y2 - min, y1 + dy)); else y2 = Math.min(1, Math.max(y1 + min, y2 + dy))
                                        if (editor.ratio > 0) {
                                            // keep the ratio: the height follows the width
                                            const h = (x2 - x1) * frame.width / editor.ratio / frame.height
                                            if (handle.modelData[1] === 0) y1 = Math.max(0, y2 - h); else y2 = Math.min(1, y1 + h)
                                        }
                                        editor.crop = Qt.rect(x1, y1, x2 - x1, y2 - y1)
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // the tools
            Rectangle {
                Layout.fillHeight: true
                Layout.preferredWidth: 300
                color: theme.dark ? editor.c.card : "#0F1828"
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 18
                    spacing: 14
                    Row {
                        Layout.fillWidth: true
                        spacing: 4
                        Repeater {
                            model: [{ id: "adjust", icon: "sun", text: app.t.edit_adjust }, { id: "crop", icon: "crop", text: app.t.edit_crop },
                                    { id: "filters", icon: "image", text: app.t.edit_filters }]
                            AbstractButton {
                                id: tab
                                required property var modelData
                                readonly property bool on: editor.tool === modelData.id
                                width: (parent.width - 8) / 3; height: 58
                                hoverEnabled: true
                                Accessible.name: modelData.text
                                onClicked: editor.tool = modelData.id
                                background: Rectangle { radius: 8; color: tab.on ? Qt.rgba(1, 1, 1, 0.12) : tab.hovered ? Qt.rgba(1, 1, 1, 0.06) : "transparent" }
                                contentItem: Column {
                                    spacing: 5
                                    Icon { anchors.horizontalCenter: parent.horizontalCenter; name: tab.modelData.icon; size: 20; color: tab.on ? "#7EB8CC" : "white" }
                                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: tab.modelData.text; font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: "white" }
                                }
                            }
                        }
                    }
                    Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Qt.rgba(1, 1, 1, 0.1) }

                    // light and colour
                    ColumnLayout {
                        visible: editor.tool === "adjust"
                        Layout.fillWidth: true
                        spacing: 16
                        Tune { label: app.t.edit_light; value: editor.brightness; onMoved: v => editor.brightness = v }
                        Tune { label: app.t.edit_contrast; value: editor.contrast; onMoved: v => editor.contrast = v }
                        Tune { label: app.t.edit_saturation; value: editor.saturation; onMoved: v => editor.saturation = v }
                        Tune { label: app.t.edit_warmth; value: editor.warmth; from: 0; onMoved: v => editor.warmth = v }
                    }
                    // crop, turn, mirror
                    ColumnLayout {
                        visible: editor.tool === "crop"
                        Layout.fillWidth: true
                        spacing: 12
                        RowLayout {
                            spacing: 6
                            OButton { iconName: "rotate"; text: app.t.edit_rotate; onClicked: editor.turn(-90) }
                            OButton { kind: "quiet"; implicitWidth: 34; iconName: "flip"; tip: app.t.edit_flip; onClicked: editor.flipH = !editor.flipH }
                        }
                        Text { text: app.t.edit_ratio; font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: Qt.rgba(1, 1, 1, 0.6) }
                        Flow {
                            Layout.fillWidth: true
                            spacing: 6
                            Repeater {
                                model: [{ t: app.t.ratio_free, v: 0 }, { t: app.t.ratio_original, v: -1 }, { t: app.t.ratio_square, v: 1 },
                                        { t: "4:3", v: 4 / 3 }, { t: "3:2", v: 3 / 2 }, { t: "16:9", v: 16 / 9 }]
                                AbstractButton {
                                    id: ratioChip
                                    required property var modelData
                                    readonly property real value: modelData.v === -1 ? frame.shownW / frame.shownH : modelData.v
                                    readonly property bool on: Math.abs(editor.ratio - value) < 0.001 && (modelData.v !== 0 || editor.ratio === 0)
                                    implicitHeight: 30; implicitWidth: ratioText.implicitWidth + 22
                                    hoverEnabled: true
                                    onClicked: {
                                        if (modelData.v === 0) { editor.ratio = 0; return }
                                        editor.crop = Qt.rect(0, 0, 1, 1)
                                        editor.setRatio(value)
                                    }
                                    background: Rectangle { radius: 15; color: ratioChip.on ? "#7EB8CC" : ratioChip.hovered ? Qt.rgba(1, 1, 1, 0.16) : Qt.rgba(1, 1, 1, 0.08) }
                                    contentItem: Text { id: ratioText; text: ratioChip.modelData.t; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: ratioChip.on ? "#0A1424" : "white" }
                                }
                            }
                        }
                    }
                    // looks
                    GridLayout {
                        visible: editor.tool === "filters"
                        Layout.fillWidth: true
                        columns: 2
                        rowSpacing: 10; columnSpacing: 10
                        Repeater {
                            model: [{ id: "", t: app.t.filter_none }, { id: "bw", t: app.t.filter_bw }, { id: "sepia", t: app.t.filter_sepia }]
                            AbstractButton {
                                id: look_
                                required property var modelData
                                readonly property bool on: editor.filter === modelData.id
                                Layout.fillWidth: true
                                implicitHeight: 120
                                hoverEnabled: true
                                Accessible.name: modelData.t
                                onClicked: editor.filter = modelData.id
                                background: Rectangle { radius: 10; color: "transparent"; border.width: look_.on ? 2 : 0; border.color: "#7EB8CC" }
                                contentItem: ColumnLayout {
                                    spacing: 6
                                    Item {
                                        Layout.fillWidth: true
                                        Layout.fillHeight: true
                                        Thumb {
                                            id: sample
                                            anchors.fill: parent
                                            anchors.margins: 4
                                            address: editor.fileid ? "t/256/" + editor.fileid + "/" + (editor.photo.etag || "") : ""
                                            fillMode: Image.PreserveAspectCrop
                                            asynchronous: true
                                        }
                                        MultiEffect {
                                            anchors.fill: sample
                                            source: sample
                                            saturation: look_.modelData.id ? -1 : 0
                                            colorization: look_.modelData.id === "sepia" ? 0.45 : 0
                                            colorizationColor: "#A06B33"
                                        }
                                    }
                                    Text { Layout.alignment: Qt.AlignHCenter; text: look_.modelData.t; font.family: "Schibsted Grotesk"; font.pixelSize: 12; color: "white" }
                                }
                            }
                        }
                    }
                    Item { Layout.fillHeight: true }
                    Text {
                        Layout.fillWidth: true
                        text: app.t.edit_note
                        wrapMode: Text.WordWrap
                        font.family: "Schibsted Grotesk"; font.pixelSize: 12
                        color: Qt.rgba(1, 1, 1, 0.55)
                    }
                }
            }
        }
    }

    component Tune: ColumnLayout {
        id: tune
        property string label
        property real value
        property real from: -1
        signal moved(real v)
        Layout.fillWidth: true
        spacing: 4
        RowLayout {
            Layout.fillWidth: true
            Text { Layout.fillWidth: true; text: tune.label; font.family: "Schibsted Grotesk"; font.pixelSize: 13; color: "white" }
            Text {
                text: (tune.value > 0 ? "+" : "") + Math.round(tune.value * 100)
                font.family: "JetBrains Mono"; font.pixelSize: 12; color: Qt.rgba(1, 1, 1, 0.65)
                TapHandler { onDoubleTapped: tune.moved(0) }
            }
        }
        Slider {
            Layout.fillWidth: true
            from: tune.from; to: 1
            value: tune.value
            stepSize: 0.01
            onMoved: tune.moved(value)
            Accessible.name: tune.label
        }
    }
}
