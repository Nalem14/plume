// OpenStreetMap's tiles for the maps of Photos: straight from tile.openstreetmap.org, kept in the cache (shown
// again offline); Qt's providers repository is never asked.
import QtLocation

Plugin {
    name: "osm"
    PluginParameter { name: "osm.useragent"; value: "Orneos Photos (https://orneos.eu)" }
    PluginParameter { name: "osm.mapping.providersrepository.disabled"; value: true }
    PluginParameter { name: "osm.mapping.custom.host"; value: "https://tile.openstreetmap.org/" }
    PluginParameter { name: "osm.mapping.custom.mapcopyright"; value: "<a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a>" }
    PluginParameter { name: "osm.mapping.custom.datacopyright"; value: "" }
    PluginParameter { name: "osm.mapping.cache.directory"; value: app.mapCache }
    PluginParameter { name: "osm.mapping.cache.disk.size"; value: 300 * 1024 * 1024 }
    PluginParameter { name: "osm.mapping.prefetching_style"; value: "NoPrefetching" }
}
