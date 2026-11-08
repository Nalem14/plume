// Météo, place: saved in the cloud (weather_status), so the dashboard of the cloud shows the same weather.
import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "strings.js" as S

Kirigami.FormLayout {
    id: root
    Bridge {
        id: bridge
        command: "/usr/libexec/orneos-widget weather"
        interval: 600000
        onActionFinished: ok => { saved.visible = ok; failed.visible = !ok; }
    }
    QQC2.TextField {
        id: place
        Kirigami.FormData.label: S.tr("place")
        placeholderText: bridge.result.place || "Lyon"
        onAccepted: use.clicked()
    }
    QQC2.Button {
        id: use
        text: S.tr("usePlace")
        icon.name: "mark-location"
        enabled: place.text.trim().length >= 2 && !bridge.actionBusy
        onClicked: bridge.run("/usr/libexec/orneos-widget weather-place --address=" + bridge.quote(place.text.trim()))
    }
    QQC2.Label { text: S.tr("placeHint"); wrapMode: Text.WordWrap; Layout.maximumWidth: Kirigami.Units.gridUnit * 22 }
    Kirigami.InlineMessage { id: saved; type: Kirigami.MessageType.Positive; text: S.tr("placeSaved"); visible: false; Layout.fillWidth: true }
    Kirigami.InlineMessage { id: failed; type: Kirigami.MessageType.Error; text: S.tr("actionError"); visible: false; Layout.fillWidth: true }
}
