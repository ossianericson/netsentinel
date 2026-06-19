#Requires -Version 5.1
<#
.SYNOPSIS
    Layer2 Ghost Hunter — Network Diagnostic Data Collector
.DESCRIPTION
    Run this script on the machine connected to the suspect network.
    It collects ARP table, DHCP info, DNS resolution, routing, and
    mDNS/NetBIOS names. Paste the full output back for analysis.
.NOTES
    Run as Administrator for best results (some commands need elevation).
    Usage: Right-click powershell -> "Run as Administrator", then:
           Set-ExecutionPolicy -Scope Process Bypass
           .\diagnose-network.ps1
#>

$divider = "=" * 60

function Section($title) {
    Write-Host "`n$divider" -ForegroundColor Cyan
    Write-Host "  $title" -ForegroundColor Yellow
    Write-Host "$divider" -ForegroundColor Cyan
}

# ── Header ────────────────────────────────────────────────────────────────────
Write-Host "`nLayer2 Ghost Hunter — Network Diagnostic Report" -ForegroundColor Green
Write-Host "Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "Hostname:  $env:COMPUTERNAME"
Write-Host "User:      $env:USERNAME"
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
Write-Host "Admin:     $isAdmin"

# ── 1. Network Adapters + IP config ──────────────────────────────────────────
Section "1. NETWORK ADAPTERS AND IP CONFIGURATION"
ipconfig /all

# ── 2. Full ARP table ─────────────────────────────────────────────────────────
Section "2. ARP TABLE (IP → MAC)"
arp -a

# ── 3. Routing table ─────────────────────────────────────────────────────────
Section "3. ROUTING TABLE"
route print

# ── 4. Ping gateway ──────────────────────────────────────────────────────────
Section "4. PING DEFAULT GATEWAY"
$gw = (Get-NetRoute -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue |
       Sort-Object RouteMetric | Select-Object -First 1).NextHop
if ($gw) {
    Write-Host "Default gateway: $gw"
    ping -n 4 $gw
} else {
    Write-Host "Could not determine default gateway." -ForegroundColor Red
}

# ── 5. Ping suspect devices ───────────────────────────────────────────────────
Section "5. PING SUSPECT IPs"
# Edit this list if your subnet is different (e.g. 192.168.0.x or 10.0.0.x)
$suspectIPs = @()

# Auto-detect local subnet and try common offender IPs
$localIP = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -notmatch "^127\." -and $_.IPAddress -notmatch "^169\.254" } |
            Select-Object -First 1).IPAddress

if ($localIP) {
    $subnet = ($localIP -split "\.")[0..2] -join "."
    Write-Host "Detected local subnet: $subnet.0/24"
    # Ping every device found in ARP table
    $arpIPs = arp -a | Select-String -Pattern "(\d+\.\d+\.\d+\.\d+)\s+([\da-fA-F-]{17})" |
              ForEach-Object { $_.Matches[0].Groups[1].Value } | Sort-Object -Unique
    foreach ($ip in $arpIPs) {
        $result = Test-Connection -ComputerName $ip -Count 1 -Quiet -ErrorAction SilentlyContinue
        Write-Host "  $ip  →  $(if ($result) { 'REACHABLE' } else { 'no response' })"
    }
} else {
    Write-Host "Could not determine local IP." -ForegroundColor Red
}

# ── 6. Reverse DNS for all ARP entries ───────────────────────────────────────
Section "6. REVERSE DNS LOOKUP (nslookup for each ARP entry)"
$arpLines = arp -a | Select-String -Pattern "(\d+\.\d+\.\d+\.\d+)\s+([\da-fA-F-]{17})"
foreach ($match in $arpLines) {
    $ip  = $match.Matches[0].Groups[1].Value
    $mac = $match.Matches[0].Groups[2].Value
    try {
        $dns = [System.Net.Dns]::GetHostEntry($ip).HostName
    } catch {
        $dns = "(no PTR record)"
    }
    Write-Host ("  {0,-18} {1,-20} {2}" -f $ip, $mac, $dns)
}

# ── 7. DHCP server check ──────────────────────────────────────────────────────
Section "7. DHCP SERVER(S) DETECTED"
ipconfig /all | Select-String -Pattern "DHCP Server" | ForEach-Object { Write-Host $_ }
# Try to find multiple DHCP servers via event log (requires admin)
if ($isAdmin) {
    $dhcpEvents = Get-WinEvent -LogName "Microsoft-Windows-Dhcp-Client/Operational" `
                    -MaxEvents 50 -ErrorAction SilentlyContinue |
                  Where-Object { $_.Message -match "DHCP server" } |
                  Select-Object -ExpandProperty Message
    if ($dhcpEvents) {
        Write-Host "`nRecent DHCP client events:"
        $dhcpEvents | Select-Object -First 10 | ForEach-Object { Write-Host "  $_" }
    } else {
        Write-Host "(No recent DHCP client events found or log not enabled)"
    }
} else {
    Write-Host "(Run as Administrator to check DHCP event log)"
}

# ── 8. NetBIOS / WINS name resolution ────────────────────────────────────────
Section "8. NETBIOS NAME TABLE"
nbtstat -n 2>$null
nbtstat -c 2>$null

# ── 9. DNS resolution test ───────────────────────────────────────────────────
Section "9. DNS RESOLUTION TEST"
$testDomains = @("google.com", "cloudflare.com", "1.1.1.1", "8.8.8.8")
foreach ($d in $testDomains) {
    try {
        $r = [System.Net.Dns]::GetHostEntry($d).AddressList[0].ToString()
        Write-Host "  $d  →  $r  [OK]" -ForegroundColor Green
    } catch {
        Write-Host "  $d  →  FAILED ($($_.Exception.Message))" -ForegroundColor Red
    }
}

# ── 10. Active TCP connections ────────────────────────────────────────────────
Section "10. ACTIVE TCP CONNECTIONS (ESTABLISHED)"
netstat -n | Select-String "ESTABLISHED"

# ── 11. Wireless networks visible ────────────────────────────────────────────
Section "11. VISIBLE WIFI NETWORKS (SSID + BSSID + SIGNAL)"
netsh wlan show networks mode=bssid 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "(No wireless adapter found or not connected)" -ForegroundColor Yellow
}

# ── 12. Current WiFi connection ──────────────────────────────────────────────
Section "12. CURRENT WIFI CONNECTION DETAILS"
netsh wlan show interfaces 2>$null

# ── 13. IPv6 neighbors ───────────────────────────────────────────────────────
Section "13. IPv6 NEIGHBOR TABLE"
netsh interface ipv6 show neighbors 2>$null

# ── Footer ────────────────────────────────────────────────────────────────────
Write-Host "`n$divider" -ForegroundColor Green
Write-Host "  Diagnostic complete. Copy ALL output above and paste it back." -ForegroundColor Green
Write-Host "$divider`n" -ForegroundColor Green
