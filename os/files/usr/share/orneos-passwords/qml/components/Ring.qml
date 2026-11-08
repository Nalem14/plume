// The Ornis ring: the open circle of the logo used as a dial. Only where it measures something (a time, a
// progress, a quota): docs/ROADMAP.md › Anneau. Positions run from 0 (left of the opening) to 1 (right of it).
// One file for the desktop widgets and the apps: tools/design-tokens.py copies it into each app's components
// and writes the opening from design/tokens.json. Colours come from the caller (its palette).
import QtQuick

Canvas {
    id: ring
    // [{from, to, color}] along the open arc, drawn in order over the track.
    property var segments: []
    property bool drawTrack: true
    // Segments side by side (one per task): each is shortened by its round ends, so the gaps stay visible.
    property bool separated: false
    property color trackColor: "transparent"
    property real lineWidth: Math.max(4, Math.min(width, height) / 12)
    // A dot on the arc (the time of day), or -1.
    property real marker: -1
    property color markerColor: "transparent"
    property color markerOutline: "transparent"
    readonly property real openDeg: 80 // ornis-tokens: desktop.ring.open_deg

    implicitWidth: 96
    implicitHeight: 96
    antialiasing: true
    onSegmentsChanged: requestPaint()
    onTrackColorChanged: requestPaint()
    onMarkerChanged: requestPaint()
    onMarkerOutlineChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()

    function angle(f) {
        return (90 + openDeg / 2 + (360 - openDeg) * Math.max(0, Math.min(1, f))) * Math.PI / 180;
    }

    onPaint: {
        const ctx = getContext("2d");
        ctx.reset();
        const cx = width / 2, cy = height / 2;
        const r = Math.min(width, height) / 2 - lineWidth * (marker >= 0 ? 0.9 : 0.5);
        if (r <= 0)
            return;
        ctx.lineCap = "round";
        ctx.lineWidth = lineWidth;
        const arc = (a, b, color) => {
            if (b <= a)
                return;
            ctx.strokeStyle = color;
            ctx.beginPath();
            ctx.arc(cx, cy, r, angle(a), angle(b), false);
            ctx.stroke();
        };
        if (drawTrack)
            arc(0, 1, trackColor);
        const ends = separated ? (lineWidth / 2 + 1.5) / (r * (360 - openDeg) * Math.PI / 180) : 0;
        for (const s of segments)
            arc(s.from + ends, s.to - ends, s.color);
        if (marker >= 0) {
            const t = angle(marker);
            ctx.beginPath();
            ctx.arc(cx + r * Math.cos(t), cy + r * Math.sin(t), lineWidth * 0.75, 0, 2 * Math.PI);
            ctx.fillStyle = markerColor;
            ctx.fill();
            ctx.lineWidth = Math.max(1.5, lineWidth / 4);
            ctx.strokeStyle = markerOutline;
            ctx.stroke();
        }
    }
}
