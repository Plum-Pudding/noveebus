/**
 * map.js
 * Shared map utilities for BusBook.
 */

/**
 * Initialize a Leaflet map with OSM tiles.
 * @param {string} elementId - DOM element ID
 * @param {number} lat - Center latitude
 * @param {number} lon - Center longitude
 * @param {number} zoom - Zoom level
 */
function initMap(elementId, lat, lon, zoom = 13) {
  const map = L.map(elementId).setView([lat, lon], zoom);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19
  }).addTo(map);
  return map;
}

/**
 * Add a bus stop marker to a map.
 */
function addStopMarker(map, lat, lon, name, time) {
  const icon = L.divIcon({
    className: '',
    html: `<div style="background:#ffc107;color:#000;border-radius:50%;width:24px;height:24px;display:flex;align-items:center;justify-content:center;font-size:0.7rem;font-weight:bold;border:2px solid #000;">${name[0]}</div>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12]
  });
  return L.marker([lat, lon], { icon })
    .bindPopup(`<strong>${name}</strong>${time ? '<br><small>' + time + '</small>' : ''}`)
    .addTo(map);
}

/**
 * Draw a route polyline between stops.
 */
function drawRoute(map, stops, color = '#ffc107') {
  if (stops.length < 2) return null;
  return L.polyline(stops.map(s => [s.lat, s.lon]), {
    color,
    weight: 3,
    opacity: 0.7,
    dashArray: '5, 5'
  }).addTo(map);
}

/**
 * Create a bus emoji marker.
 */
function createBusMarker(map, lat, lon) {
  const icon = L.divIcon({
    className: '',
    html: '<div style="font-size:1.8rem;filter:drop-shadow(0 2px 4px rgba(0,0,0,0.5));">🚌</div>',
    iconSize: [36, 36],
    iconAnchor: [18, 18]
  });
  return L.marker([lat, lon], { icon }).addTo(map);
}
