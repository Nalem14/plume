// An OMenu opened next to the item that asked for it (a row, a button): popupAt(item), or above it
// (popupAbove: the bar at the bottom of a call).
import QtQuick
import "components"

OMenu {
    id: menu
    function popupAt(item, below) {
        const p = item.mapToItem(menu.parent, below ? 0 : item.width - 40, item.height)
        x = Math.max(8, Math.min(p.x, (menu.parent ? menu.parent.width : 9999) - implicitWidth - 8))
        y = p.y
        open()
    }
    function popupAbove(item) {
        const p = item.mapToItem(menu.parent, item.width / 2, 0)
        x = Math.max(8, Math.min(p.x - implicitWidth / 2, (menu.parent ? menu.parent.width : 9999) - implicitWidth - 8))
        y = Math.max(8, p.y - implicitHeight - 8)
        open()
    }
}
