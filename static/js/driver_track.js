/**
 * driver_track.js
 * Handles GPS watchPosition and emits location via SocketIO every 5 seconds.
 */

function startLocationTracking(socket, scheduleId, map, onLocation) {
  if (!navigator.geolocation) {
    document.getElementById('tracking_status').textContent = 'Geolocation not supported.';
    return;
  }

  let lastEmit = 0;
  const EMIT_INTERVAL = 5000; // 5 seconds

  const watchId = navigator.geolocation.watchPosition(
    (position) => {
      const { latitude: lat, longitude: lon } = position.coords;
      const now = Date.now();

      // Update map
      if (map && onLocation) {
        onLocation(lat, lon);
        map.setView([lat, lon]);
      }

      // Throttle SocketIO emits
      if (now - lastEmit >= EMIT_INTERVAL) {
        socket.emit('driver_location', {
          schedule_id: scheduleId,
          lat: lat,
          lon: lon
        });
        lastEmit = now;

        const statusEl = document.getElementById('tracking_status');
        if (statusEl) {
          statusEl.innerHTML = `<i class="bi bi-broadcast text-success me-1"></i>Location shared at ${new Date().toLocaleTimeString()}`;
        }
      }
    },
    (err) => {
      console.error('Geolocation error:', err);
      const statusEl = document.getElementById('tracking_status');
      if (statusEl) {
        statusEl.innerHTML = `<i class="bi bi-exclamation-triangle text-warning me-1"></i>Location error: ${err.message}`;
      }
    },
    {
      enableHighAccuracy: true,
      timeout: 15000,
      maximumAge: 0
    }
  );

  // Store watchId for cleanup
  window._geoWatchId = watchId;

  // Clean up on page unload
  window.addEventListener('beforeunload', () => {
    if (window._geoWatchId) {
      navigator.geolocation.clearWatch(window._geoWatchId);
    }
  });

  return watchId;
}
