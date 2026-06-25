"""
Canonical device type label constants.

Import from this module wherever a device type string is constructed or compared
across classifiers (device_classifier, passive_observer, dhcp_fingerprint).
Using these constants prevents silent mismatches when the same concept is spelled
differently in different files.
"""

# ── Network infrastructure ─────────────────────────────────────────────────────
TYPE_ROUTER_FIREWALL        = "Router / Firewall"
TYPE_ROUTER_GATEWAY         = "Router / Gateway"
TYPE_NETWORK_SWITCH         = "Network Switch"
TYPE_WIRELESS_AP            = "Wireless Access Point"
TYPE_MESH_NODE              = "Mesh Network Node"

# ── Servers ────────────────────────────────────────────────────────────────────
TYPE_DOMAIN_CONTROLLER      = "Domain Controller"
TYPE_FILE_NAS               = "File / NAS Server"
TYPE_MAIL_SERVER            = "Mail Server"
TYPE_PRINT_SERVER           = "Print Server"
TYPE_WEB_SERVER             = "Web / App Server"

# ── Surveillance ───────────────────────────────────────────────────────────────
TYPE_IP_CAMERA              = "IP Camera"
TYPE_VIDEO_DOORBELL         = "Video Doorbell / Intercom"

# ── Smart home & IoT ──────────────────────────────────────────────────────────
TYPE_SMART_HOME_HUB         = "Smart Home Hub"
TYPE_SMART_HOME_HUB_DISPLAY = "Smart Home Hub / Display"
TYPE_IOT_DEVICE             = "IoT Device"
TYPE_SMART_PLUG             = "Smart Plug"
TYPE_SMART_BULB             = "Smart Bulb"
TYPE_SMART_THERMOSTAT       = "Smart Thermostat"
TYPE_MATTER_DEVICE          = "Matter/Thread Device"

# ── AV & entertainment ────────────────────────────────────────────────────────
# TYPE_SMART_SPEAKER is the canonical label for mixed speaker/display devices
# (Amazon Echo, Google Home, HomePod).  TYPE_SMART_SPEAKER_AUDIO is for
# audio-only devices (Sonos, Bose, Spotify Connect speakers).
TYPE_SMART_SPEAKER          = "Smart Speaker"
TYPE_SMART_SPEAKER_AUDIO    = "Smart Speaker / Audio"
TYPE_SMART_TV               = "Smart TV"
TYPE_STREAMING_STICK        = "Streaming Stick"
TYPE_GAMES_CONSOLE          = "Games Console"

# ── Desktop / laptop / mobile ─────────────────────────────────────────────────
TYPE_WINDOWS_PC             = "Windows PC"
TYPE_MACOS_DEVICE           = "macOS Device"
TYPE_LINUX_HOST             = "Linux / Unix Host"
TYPE_IPHONE_IPAD            = "iPhone / iPad"
TYPE_ANDROID_DEVICE         = "Android Device"
TYPE_TABLET                 = "Tablet"
TYPE_WEARABLE               = "Wearable"

# ── Telephony ─────────────────────────────────────────────────────────────────
TYPE_VOIP_PHONE             = "VoIP Phone / ATA"

# ── Industrial ────────────────────────────────────────────────────────────────
TYPE_INDUSTRIAL_ICS         = "Industrial / ICS Device"

# ── Compute hardware ──────────────────────────────────────────────────────────
TYPE_SBC                    = "Single Board Computer"

# ── Fallback ──────────────────────────────────────────────────────────────────
TYPE_NETWORK_DEVICE         = "Network Device"
TYPE_UNKNOWN                = "Unknown Device"
