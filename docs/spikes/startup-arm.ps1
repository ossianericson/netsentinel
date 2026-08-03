# Measure one arm of app.py startup: time-to-window and RSS.
# Usage: powershell -File startup_arm.ps1 -Label after
param([string]$Label = "arm", [int]$SettleSeconds = 60)

Add-Type @"
using System;using System.Runtime.InteropServices;using System.Text;using System.Collections.Generic;
public class WEnum {
 public delegate bool Proc(IntPtr h, IntPtr l);
 [DllImport("user32.dll")] public static extern bool EnumWindows(Proc p, IntPtr l);
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
 [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
 [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int m);
 [DllImport("user32.dll")] public static extern bool IsHungAppWindow(IntPtr h);
 public static IntPtr FindDash(uint target) {
   IntPtr found = IntPtr.Zero;
   EnumWindows((h,l)=>{ uint pid; GetWindowThreadProcessId(h, out pid);
     if(pid==target && IsWindowVisible(h)){ var t=new StringBuilder(200); GetWindowText(h,t,200);
       if(t.ToString().Contains("Dashboard")){ found=h; return false; } }
     return true; }, IntPtr.Zero);
   return found; }
}
"@ -ErrorAction SilentlyContinue

Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

$sw = [Diagnostics.Stopwatch]::StartNew()
$p  = Start-Process -FilePath "python" -ArgumentList "app.py" -WorkingDirectory "C:\Code\netsentinel" -PassThru
$hwnd = [IntPtr]::Zero
while ($sw.Elapsed.TotalSeconds -lt 300) {
    $hwnd = [WEnum]::FindDash($p.Id)
    if ($hwnd -ne [IntPtr]::Zero) { break }
    Start-Sleep -Milliseconds 500
}
$appear = $sw.Elapsed.TotalSeconds
$p.Refresh()
$rssAppear = [math]::Round($p.WorkingSet64/1MB,1)
$cpuAppear = $p.CPU

Start-Sleep -Seconds $SettleSeconds
$p.Refresh()
$rssSettle = [math]::Round($p.WorkingSet64/1MB,1)
$cpuSettle = $p.CPU
$hung = if ($hwnd -ne [IntPtr]::Zero) { [WEnum]::IsHungAppWindow($hwnd) } else { "n/a" }

"=================================================="
"ARM              : $Label"
"dashboard window : $(if($hwnd -ne [IntPtr]::Zero){'appeared'}else{'NEVER APPEARED (timeout 300s)'})"
"time to window   : $([math]::Round($appear,1)) s"
"RSS at window    : $rssAppear MB   (CPU $([math]::Round($cpuAppear,1)) s)"
"RSS +${SettleSeconds}s        : $rssSettle MB   (CPU $([math]::Round($cpuSettle,1)) s)"
"CPU during settle: $([math]::Round($cpuSettle-$cpuAppear,1)) s over $SettleSeconds s"
"hung             : $hung"
"=================================================="

Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
