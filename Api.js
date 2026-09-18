// Shared helpers for the Omarchy YouTube Music service and bar widget.
// Kept dependency-free (QtQuick JSON only) so both QML files can import it
// without touching the host shell's internals.

.pragma library

var defaultSettingValues = ({
  showTrackTitle: "On",
  showArtistName: "On",
  showPausedTrack: "On",
  scrollBarText: "On",
  maxBarTextWidth: "260",
  audioQuality: "Best available",
  idleShutdownMinutes: 10,
  launchTerminal: ""
})

var settingKeys = [
  "showTrackTitle",
  "showArtistName",
  "showPausedTrack",
  "scrollBarText",
  "maxBarTextWidth",
  "audioQuality",
  "idleShutdownMinutes",
  "launchTerminal"
]

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value)
}

function shallowCopy(source) {
  var out = {}
  for (var key in source) out[key] = source[key]
  return out
}

function assign(target, patch) {
  for (var key in patch) target[key] = patch[key]
  return target
}

function parseJson(text, fallback) {
  if (!text || typeof text !== "string") return fallback
  try {
    var parsed = JSON.parse(text)
    return parsed === undefined || parsed === null ? fallback : parsed
  } catch (e) {
    return fallback
  }
}

function clamp(value, min, max) {
  var n = Number(value)
  if (isNaN(n)) return min
  return Math.min(max, Math.max(min, n))
}

// Extract the video id from a URL such as
// https://music.youtube.com/watch?v=VIDEO_ID
function parseVideoId(path) {
  var text = String(path || "")
  if (!text) return ""
  var anchor = text.indexOf("v=")
  if (anchor === -1) return ""
  var start = anchor + 2
  var end = start
  while (end < text.length) {
    var c = text.charAt(end)
    if (/[A-Za-z0-9_-]/.test(c)) end++
    else break
  }
  return end > start ? text.substring(start, end) : ""
}

function watchUrl(videoId) {
  return "https://music.youtube.com/watch?v=" + String(videoId || "")
}

function thumbnailUrl(videoId) {
  var id = String(videoId || "")
  return id ? "https://i.ytimg.com/vi/" + id + "/mqdefault.jpg" : ""
}

// mpv's metadata property is a variant map whose keys differ by casing
// depending on the source. Probe a list of candidates.
function metaValue(metadata, keys) {
  if (!isPlainObject(metadata)) return ""
  for (var i = 0; i < keys.length; i++) {
    var value = metadata[keys[i]]
    if (value !== undefined && value !== null && String(value) !== "") {
      return String(value)
    }
  }
  return ""
}

function formatTime(seconds) {
  var total = Math.max(0, Math.floor(Number(seconds) || 0))
  var h = Math.floor(total / 3600)
  var m = Math.floor((total % 3600) / 60)
  var s = total % 60
  var mm = h > 0 ? String(m).padStart(2, "0") : String(m)
  var ss = String(s).padStart(2, "0")
  return h > 0 ? h + ":" + mm + ":" + ss : mm + ":" + ss
}

function ytdlFormat(quality) {
  var text = String(quality || "Best available")
  if (text.indexOf("96") === 0) return "bestaudio[abr<=96]/bestaudio/best"
  if (text.indexOf("128") === 0) return "bestaudio[abr<=128]/bestaudio/best"
  return "bestaudio/best"
}

function normalizedMaxBarTextWidth(value) {
  var n = Math.floor(Number(value))
  if (isNaN(n)) return 260
  if (n === 0) return 0
  return Math.min(560, Math.max(160, n))
}

function normalizedSettings(values) {
  var source = isPlainObject(values) ? values : {}
  var next = shallowCopy(defaultSettingValues)
  for (var i = 0; i < settingKeys.length; i++) {
    var key = settingKeys[i]
    if (source[key] !== undefined) next[key] = source[key]
  }
  var onOff = function(value, fallback) {
    var text = String(value || fallback)
    return text === "Off" ? "Off" : "On"
  }
  next.showTrackTitle = onOff(next.showTrackTitle, "On")
  next.showArtistName = onOff(next.showArtistName, "On")
  next.showPausedTrack = onOff(next.showPausedTrack, "On")
  next.scrollBarText = onOff(next.scrollBarText, "On")
  next.maxBarTextWidth = String(normalizedMaxBarTextWidth(next.maxBarTextWidth))
  if (Number(next.maxBarTextWidth) === 0) next.scrollBarText = "Off"
  var quality = String(next.audioQuality || "Best available")
  var allowed = ["Best available", "Cap at 128 kbps", "Cap at 96 kbps"]
  if (allowed.indexOf(quality) === -1) quality = "Best available"
  next.audioQuality = quality
  next.idleShutdownMinutes = Math.min(1440, Math.max(0,
    Math.floor(Number(next.idleShutdownMinutes) || 0)))
  next.launchTerminal = String(next.launchTerminal || "").trim()
  return next
}

// The TUI writes a snapshot of the queue it loaded into mpv. Resolve the
// display metadata for a playlist position from that snapshot.
function trackAt(tuiState, index) {
  var tracks = tuiState && Array.isArray(tuiState.tracks) ? tuiState.tracks : null
  var i = Math.floor(Number(index))
  if (!tracks || isNaN(i) || i < 0 || i >= tracks.length) return null
  var track = tracks[i]
  return isPlainObject(track) ? track : null
}

function trackTitle(track) {
  return track ? String(track.title || "") : ""
}

function trackArtist(track) {
  return track ? String(track.artist || "") : ""
}

// Compose the one-line bar label from the display fields.
function barTrackText(title, artist, showTrackTitle, showArtistName) {
  var parts = []
  if (showTrackTitle !== "Off" && title) parts.push(title)
  if (showArtistName !== "Off" && artist) parts.push(artist)
  return parts.join("  ·  ")
}
