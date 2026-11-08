// « Ajouter à un album »: a new album (with these photos), then the albums of one's own and those shared
// with the account, newest first.
import QtQuick
import QtQuick.Controls
import "components"

OMenu {
    id: menu
    property var ids: []
    signal newAlbum(var ids)
    heading: app.t.add_to_album
    subheading: app.plural("count_photos", ids.length)

    function openFor(list, item) {
        ids = list
        const root = parent
        const p = item.mapToItem(root, 0, item.height + 4)
        x = Math.max(8, Math.min(p.x, root.width - width - 8))
        y = Math.min(p.y, root.height - 360)
        open()
    }

    OMenuItem { text: app.t.album_new + "…"; iconName: "plus"; onTriggered: menu.newAlbum(menu.ids) }
    Repeater {
        model: (photos.lists.albums || []).concat(photos.lists.shared || [])
        OMenuItem {
            required property var modelData
            text: modelData.name
            iconName: modelData.owner === (app.profile.user || "") ? "album" : "people"
            onTriggered: photos.addToAlbum(modelData.id, menu.ids)
        }
    }
}
