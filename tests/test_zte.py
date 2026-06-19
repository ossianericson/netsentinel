import requests
import hashlib
import getpass
import urllib3
import time
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class ZTEMC889:
    def __init__(self, ip="192.168.254.1"):
        self.ip = ip
        self.base_url = f"https://{ip}/goform"
        self.session = None

    def sha256_upper(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest().upper()  # lgtm[py/weak-sensitive-data-hashing] — challenge-response protocol required by ZTE MC889 firmware

    def login(self, password: str, username: str = "admin") -> bool:
        self.session = requests.Session()
        self.session.headers.update({
            "Referer": f"https://{self.ip}/index.html",
            "User-Agent": "Mozilla/5.0"
        })
        self.session.verify = False

        ts = int(time.time() * 1000)
        ld_resp = self.session.get(f"{self.base_url}/goform_get_cmd_process?isTest=false&cmd=LD&_={ts}")
        ld_value = ld_resp.json().get("LD")

        if not ld_value:
            return False

        hash1 = self.sha256_upper(password)
        final_hash = self.sha256_upper(hash1 + ld_value)

        login_url = f"{self.base_url}/goform_set_cmd_process"
        for goform_id in ["LOGIN_MULTI_USER", "LOGIN"]:
            payload = {"isTest": "false", "goformId": goform_id, "password": final_hash}
            if goform_id == "LOGIN_MULTI_USER":
                payload["user"] = username
            resp = self.session.post(login_url, data=payload)
            try:
                if resp.json().get("result") in ["0", "success"]:
                    return True
            except:
                continue
        return False

    def get_data(self):
        # Expanded parameter list
        params = ",".join([
            "Z5g_rsrp", "Z5g_SINR", "Z5g_rsrq", 
            "lte_rsrp", "lte_snr", "lte_rsrq",
            "network_type", "wan_active_band", "nr5g_action_band",
            "cell_id", "wan_ipaddr", "ppp_status", "signalbar",
            "wa_inner_version", "lte_pci", "nr5g_pci",
            "wan_active_channel", "nr5g_action_channel", 
            "rmcc", "rmnc", "endc_info"
        ])
        
        url = f"{self.base_url}/goform_get_cmd_process?isTest=false&isReadPc=1&multi_data=1&cmd={params}"
        try:
            return self.session.get(url).json()
        except:
            return None

    def signal_quality(self, rsrp):
        try:
            r = int(float(rsrp))
            if r >= -80:   return "🟢 Excellent"
            elif r >= -90: return "🟢 Good"
            elif r >= -100:return "🟡 Fair"
            else:          return "🔴 Poor"
        except:
            return "N/A"

    def print_status(self, data):
        if not data:
            print("Failed to get data")
            return

        cell_id = data.get('cell_id', '')
        enbid = ""
        if cell_id:
            try:
                cid_int = int(cell_id, 16) if any(c.isalpha() for c in str(cell_id)) else int(cell_id)
                enbid = str(cid_int >> 8)
            except (ValueError, TypeError):
                pass  # non-fatal — cell_id may not be a valid integer

        print(f"\n📡 ZTE MC889 @ {datetime.now().strftime('%H:%M:%S')}")
        print("=" * 95)
        print(f"Operator     : Telia Sweden (240-08)")
        print(f"Cell ID      : {cell_id}   (eNB/gNB: {enbid})")
        print(f"Public IP    : {data.get('wan_ipaddr', 'N/A')}")

        print(f"\n=== 5G NR ===")
        print(f"Band         : {data.get('nr5g_action_band', 'N/A')}")
        print(f"PCI          : {data.get('nr5g_pci', 'N/A')}")
        print(f"ARFCN        : {data.get('nr5g_action_channel', 'N/A')}")
        print(f"RSRP         : {data.get('Z5g_rsrp','-')} dBm  {self.signal_quality(data.get('Z5g_rsrp'))}")

        print(f"\n=== LTE Primary ===")
        print(f"Band         : {data.get('wan_active_band', 'N/A')}")
        print(f"PCI          : {data.get('lte_pci', 'N/A')}")
        print(f"EARFCN       : {data.get('wan_active_channel', 'N/A')}")
        print(f"RSRP         : {data.get('lte_rsrp','-')} dBm")

        print(f"\nSignal Details:")
        print(f"   5G  SINR : {data.get('Z5g_SINR','-')} dB")
        print(f"   LTE SNR  : {data.get('lte_snr','-')} dB")
        print(f"   Signal   : {data.get('signalbar','?')}/5 bars")


# ====================== START ======================
if __name__ == "__main__":
    modem = ZTEMC889()
    pwd = getpass.getpass("Enter Modem Password: ")
    
    if modem.login(pwd):
        print("✅ Login successful! Monitoring started...\n")
        try:
            while True:
                data = modem.get_data()
                modem.print_status(data)
                time.sleep(10)
        except KeyboardInterrupt:
            print("\n\n👋 Monitoring stopped by user.")
    else:
        print("❌ Login failed")
