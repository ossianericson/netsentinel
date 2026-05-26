"""
IP & Subnet Calculator Page

Interactive subnet calculator with educational reference panels.
No network calls, no workers — pure Python ipaddress math.

Covers:
  - IPv4 subnet breakdown (network, broadcast, hosts, binary visualiser)
  - CIDR quick-reference table (/1–/32)
  - IP address class reference (A/B/C/D/E, private ranges)
  - IPv4 vs IPv6 comparison
"""
from __future__ import annotations

import ipaddress

from PyQt6.QtCore import Qt
from PyQt6.QtGui  import QColor, QFont
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSizePolicy, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ui.styles import (
    ACCENT, ACCENT_DARK, AMBER, BG_ALT_ROW, BG_CARD, BG_DARK, BORDER,
    CARD_HDR_BORDER, CARD_RADIUS, GREEN, RED, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    WHITE,
)

# ── palette shortcuts ─────────────────────────────────────────────────────────
_NET_BIT_BG  = "#1A3A5C"   # blue tint for network bits
_HOST_BIT_BG = "#2D4A2D"   # green tint for host bits
_MONO = "Consolas, Courier New, monospace"


class IpCalculatorPage(QWidget):
    """Self-contained IP/subnet calculator with educational reference panels."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._build_ui()

    # ── layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # page header
        from ui.dashboard import _page_header
        outer.addWidget(_page_header(
            "IP & Subnet Calculator",
            "Calculate subnet details, visualise address bits, and learn how IPv4 addressing works",
        ))

        # scrollable body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background:transparent;")

        body = QWidget()
        body.setObjectName("contentArea")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 8, 12, 20)
        bl.setSpacing(12)

        bl.addWidget(self._build_calculator_card())
        bl.addWidget(self._build_binary_card())
        bl.addWidget(self._build_cidr_ref_card())
        bl.addWidget(self._build_classes_card())
        bl.addWidget(self._build_ipv6_card())
        bl.addStretch()

        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

    # ── card helpers ──────────────────────────────────────────────────────────

    def _card(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        """Return (card QFrame, content QVBoxLayout)."""
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet(
            f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
            f"border-radius:{CARD_RADIUS};}}"
        )
        cl = QVBoxLayout(card)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        tb = QFrame()
        tb.setFixedHeight(32)
        tb.setStyleSheet(
            f"background:{BG_CARD};border-bottom:1px solid {CARD_HDR_BORDER};"
        )
        tbl = QHBoxLayout(tb)
        tbl.setContentsMargins(12, 0, 12, 0)
        lbl = QLabel(title)
        lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY};font-weight:bold;font-size:13px;"
        )
        tbl.addWidget(lbl)
        tbl.addStretch()
        cl.addWidget(tb)
        return card, cl

    def _section_table(self, rows: list[tuple[str, str]],
                       col0_width: int = 220) -> QTableWidget:
        tbl = QTableWidget(len(rows), 2)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.horizontalHeader().setVisible(False)
        tbl.verticalHeader().setVisible(False)
        tbl.setShowGrid(False)
        tbl.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        tbl.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        tbl.setStyleSheet(
            f"QTableWidget{{background:{BG_CARD};border:none;font-size:11px;}}"
            f"QTableWidget::item{{padding:4px 8px;color:{TEXT_PRIMARY};}}"
        )
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.setColumnWidth(0, col0_width)
        tbl.verticalHeader().setDefaultSectionSize(24)
        for i, (key, val) in enumerate(rows):
            bg = BG_ALT_ROW if i % 2 else BG_CARD
            k = QTableWidgetItem(key)
            k.setFont(QFont("Consolas", 10))
            k.setForeground(QColor(ACCENT_DARK))
            k.setBackground(QColor(bg))
            v = QTableWidgetItem(val)
            v.setBackground(QColor(bg))
            tbl.setItem(i, 0, k)
            tbl.setItem(i, 1, v)
        tbl.setFixedHeight(len(rows) * 24 + 2)
        return tbl

    # ── calculator card ───────────────────────────────────────────────────────

    def _build_calculator_card(self) -> QFrame:
        card, cl = self._card("IPv4 Subnet Calculator")

        input_row = QWidget()
        input_row.setStyleSheet(f"background:{BG_CARD};")
        ir = QHBoxLayout(input_row)
        ir.setContentsMargins(12, 10, 12, 10)
        ir.setSpacing(8)

        lbl = QLabel("IP / CIDR:")
        lbl.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;")
        ir.addWidget(lbl)

        self._ip_input = QLineEdit("192.168.1.0/24")
        self._ip_input.setFixedWidth(200)
        self._ip_input.setStyleSheet(
            f"QLineEdit{{background:{BG_DARK};color:{TEXT_PRIMARY};"
            f"border:1px solid {BORDER};border-radius:3px;"
            f"padding:4px 8px;font-family:{_MONO};font-size:12px;}}"
            f"QLineEdit:focus{{border:1px solid {ACCENT};}}"
        )
        self._ip_input.returnPressed.connect(self._calculate)
        ir.addWidget(self._ip_input)

        hint = QLabel("e.g.  192.168.1.50/24  or  10.0.0.0/8  or  172.16.5.1/255.255.0.0")
        hint.setStyleSheet(f"color:{TEXT_MUTED};font-size:10px;")
        ir.addWidget(hint)
        ir.addStretch()

        btn = QPushButton("Calculate")
        btn.setFixedWidth(100)
        btn.setStyleSheet(
            f"QPushButton{{background:{ACCENT};color:{WHITE};"
            f"border:none;border-radius:3px;padding:5px 12px;"
            f"font-size:11px;font-weight:bold;}}"
            f"QPushButton:hover{{background:{ACCENT_DARK};color:{WHITE};}}"
            f"QPushButton:pressed{{background:{ACCENT_DARK};color:{WHITE};}}"
        )
        btn.clicked.connect(self._calculate)
        ir.addWidget(btn)
        cl.addWidget(input_row)

        # results grid
        self._results_widget = QWidget()
        self._results_widget.setStyleSheet(f"background:{BG_CARD};")
        self._results_layout = QGridLayout(self._results_widget)
        self._results_layout.setContentsMargins(12, 4, 12, 12)
        self._results_layout.setSpacing(4)
        self._results_widget.setVisible(False)
        cl.addWidget(self._results_widget)

        self._error_lbl = QLabel("")
        self._error_lbl.setStyleSheet(
            f"color:{RED};font-size:11px;padding:6px 12px;"
        )
        self._error_lbl.setVisible(False)
        cl.addWidget(self._error_lbl)

        # run once on load with default value
        self._calculate()
        return card

    def _calculate(self):
        raw = self._ip_input.text().strip()
        self._error_lbl.setVisible(False)
        self._results_widget.setVisible(False)

        try:
            # accept "ip/mask" where mask may be dotted-decimal
            if "/" in raw:
                ip_str, mask_str = raw.split("/", 1)
                if "." in mask_str:
                    # convert dotted-decimal mask to prefix len
                    bits = sum(bin(int(o)).count("1") for o in mask_str.split("."))
                    raw = f"{ip_str}/{bits}"
            net = ipaddress.IPv4Network(raw, strict=False)
            host_ip = ipaddress.IPv4Address(raw.split("/")[0])
        except Exception as e:
            self._error_lbl.setText(f"Invalid input: {e}")
            self._error_lbl.setVisible(True)
            return

        prefix   = net.prefixlen
        num_addr = net.num_addresses
        num_host = max(num_addr - 2, 0) if prefix < 31 else num_addr

        cls = self._ip_class(host_ip)
        is_private = host_ip.is_private
        is_loopback = host_ip.is_loopback

        rows = [
            ("Input address",      str(host_ip)),
            ("Network address",    str(net.network_address)),
            ("Broadcast address",  str(net.broadcast_address) if prefix < 31 else "N/A (point-to-point)"),
            ("First usable host",  str(net.network_address + 1) if num_host > 0 else "N/A"),
            ("Last usable host",   str(net.broadcast_address - 1) if num_host > 1 else str(net.network_address + 1) if num_host == 1 else "N/A"),
            ("Usable hosts",       f"{num_host:,}"),
            ("Total addresses",    f"{num_addr:,}"),
            ("Subnet mask",        str(net.netmask)),
            ("Wildcard mask",      str(net.hostmask)),
            ("CIDR notation",      f"/{prefix}"),
            ("IP class",           cls),
            ("Scope",              "Private" if is_private else "Loopback" if is_loopback else "Public"),
        ]

        # rebuild grid
        for i in reversed(range(self._results_layout.count())):
            self._results_layout.itemAt(i).widget().deleteLater()

        cols = 3
        for idx, (k, v) in enumerate(rows):
            row, col = divmod(idx, cols)
            cell = QWidget()
            cell.setStyleSheet(
                f"background:{'#1A2435' if (idx // cols) % 2 == 0 else BG_CARD};"
                f"border-radius:2px;"
            )
            cl2 = QVBoxLayout(cell)
            cl2.setContentsMargins(8, 4, 8, 4)
            cl2.setSpacing(1)
            kl = QLabel(k)
            kl.setStyleSheet(f"color:{TEXT_MUTED};font-size:9px;font-weight:bold;")
            vl = QLabel(v)
            vl.setStyleSheet(
                f"color:{TEXT_PRIMARY};font-size:12px;"
                f"font-family:{_MONO};"
            )
            cl2.addWidget(kl)
            cl2.addWidget(vl)
            self._results_layout.addWidget(cell, row, col)

        self._results_widget.setVisible(True)

        # update binary visualiser
        if hasattr(self, "_bin_widget"):
            self._update_binary(host_ip, net)

    @staticmethod
    def _ip_class(ip: ipaddress.IPv4Address) -> str:
        first = int(str(ip).split(".")[0])
        if first < 128:   return "A  (1–126 — large networks, 16M hosts)"
        if first < 192:   return "B  (128–191 — medium networks, 65K hosts)"
        if first < 224:   return "C  (192–223 — small networks, 254 hosts)"
        if first < 240:   return "D  (224–239 — multicast, not assignable)"
        return                    "E  (240–255 — reserved / experimental)"

    # ── binary visualiser card ────────────────────────────────────────────────

    def _build_binary_card(self) -> QFrame:
        card, cl = self._card("Binary Address Visualiser  —  network bits (blue) · host bits (green)")

        self._bin_widget = QWidget()
        self._bin_widget.setStyleSheet(f"background:{BG_CARD};")
        bv = QVBoxLayout(self._bin_widget)
        bv.setContentsMargins(12, 8, 12, 12)
        bv.setSpacing(6)

        self._bin_ip_row   = self._make_bit_row("IP address  ")
        self._bin_mask_row = self._make_bit_row("Subnet mask ")
        self._bin_net_row  = self._make_bit_row("Network     ")
        bv.addWidget(self._bin_ip_row[0])
        bv.addWidget(self._bin_mask_row[0])
        bv.addWidget(self._bin_net_row[0])

        cl.addWidget(self._bin_widget)

        # run initial visualisation
        try:
            net = ipaddress.IPv4Network("192.168.1.0/24", strict=False)
            self._update_binary(ipaddress.IPv4Address("192.168.1.0"), net)
        except Exception:
            pass
        return card

    def _make_bit_row(self, label: str) -> tuple[QWidget, list[QLabel]]:
        row_w = QWidget()
        row_w.setStyleSheet(f"background:{BG_CARD};")
        rl = QHBoxLayout(row_w)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(2)

        lbl = QLabel(label)
        lbl.setFixedWidth(90)
        lbl.setStyleSheet(f"color:{TEXT_MUTED};font-size:10px;font-family:{_MONO};")
        rl.addWidget(lbl)

        bits: list[QLabel] = []
        for i in range(32):
            if i > 0 and i % 8 == 0:
                sep = QLabel("·")
                sep.setFixedWidth(6)
                sep.setAlignment(Qt.AlignmentFlag.AlignCenter)
                sep.setStyleSheet(f"color:{TEXT_MUTED};font-size:10px;")
                rl.addWidget(sep)
            b = QLabel("0")
            b.setFixedWidth(14)
            b.setFixedHeight(18)
            b.setAlignment(Qt.AlignmentFlag.AlignCenter)
            b.setStyleSheet(
                f"color:{TEXT_PRIMARY};font-size:10px;font-family:{_MONO};"
                f"background:{BG_DARK};border-radius:1px;"
            )
            rl.addWidget(b)
            bits.append(b)

        rl.addStretch()
        return row_w, bits

    def _update_binary(self, ip: ipaddress.IPv4Address,
                       net: ipaddress.IPv4Network):
        prefix = net.prefixlen
        ip_int   = int(ip)
        mask_int = int(net.netmask)
        net_int  = int(net.network_address)

        def _fill(bits_list: list[QLabel], value: int, is_ip: bool = False):
            for i, lbl in enumerate(bits_list):
                bit = (value >> (31 - i)) & 1
                lbl.setText(str(bit))
                is_net_bit = i < prefix
                if is_net_bit:
                    bg = _NET_BIT_BG
                    fg = "#7EB8F7"
                else:
                    bg = _HOST_BIT_BG
                    fg = "#88CC88"
                lbl.setStyleSheet(
                    f"color:{fg};font-size:10px;font-family:{_MONO};"
                    f"background:{bg};border-radius:1px;"
                )

        _fill(self._bin_ip_row[1],   ip_int,   is_ip=True)
        _fill(self._bin_mask_row[1], mask_int)
        _fill(self._bin_net_row[1],  net_int)

    # ── CIDR reference card ───────────────────────────────────────────────────

    def _build_cidr_ref_card(self) -> QFrame:
        card, cl = self._card("CIDR Quick Reference  —  all prefix lengths /1 to /32")

        container = QWidget()
        container.setStyleSheet(f"background:{BG_CARD};")
        hbox = QHBoxLayout(container)
        hbox.setContentsMargins(12, 8, 12, 12)
        hbox.setSpacing(16)

        # split into 4 columns of 8 rows each
        entries = []
        for prefix in range(1, 33):
            n = ipaddress.IPv4Network(f"0.0.0.0/{prefix}", strict=False)
            hosts = max(n.num_addresses - 2, 0) if prefix < 31 else n.num_addresses
            mask  = str(n.netmask)
            entries.append((f"/{prefix}", mask, f"{hosts:,} hosts"))

        chunk = 8
        for start in range(0, 32, chunk):
            chunk_entries = entries[start:start + chunk]
            tbl = QTableWidget(len(chunk_entries), 3)
            tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            tbl.horizontalHeader().setVisible(False)
            tbl.verticalHeader().setVisible(False)
            tbl.setShowGrid(False)
            tbl.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
            tbl.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            tbl.setStyleSheet(
                f"QTableWidget{{background:{BG_CARD};border:none;font-size:10px;}}"
                f"QTableWidget::item{{padding:2px 6px;color:{TEXT_PRIMARY};}}"
            )
            tbl.setColumnWidth(0, 32)
            tbl.setColumnWidth(1, 110)
            tbl.setColumnWidth(2, 110)
            tbl.verticalHeader().setDefaultSectionSize(20)
            tbl.setFixedHeight(len(chunk_entries) * 20 + 2)

            for i, (cidr, mask, hosts) in enumerate(chunk_entries):
                bg = BG_ALT_ROW if i % 2 else BG_CARD
                prefix_num = int(cidr[1:])
                # colour by typical use
                if prefix_num <= 8:
                    fg = RED
                elif prefix_num <= 16:
                    fg = AMBER
                elif prefix_num <= 24:
                    fg = ACCENT_DARK
                else:
                    fg = GREEN

                c = QTableWidgetItem(cidr)
                c.setFont(QFont("Consolas", 10))
                c.setForeground(QColor(fg))
                c.setBackground(QColor(bg))
                m = QTableWidgetItem(mask)
                m.setBackground(QColor(bg))
                h = QTableWidgetItem(hosts)
                h.setBackground(QColor(bg))
                h.setForeground(QColor(TEXT_MUTED))
                tbl.setItem(i, 0, c)
                tbl.setItem(i, 1, m)
                tbl.setItem(i, 2, h)

            hbox.addWidget(tbl)

        cl.addWidget(container)
        return card

    # ── IP classes + private ranges card ─────────────────────────────────────

    def _build_classes_card(self) -> QFrame:
        card, cl = self._card("IP Address Classes & Private Ranges")

        content = QWidget()
        content.setStyleSheet(f"background:{BG_CARD};")
        cv = QHBoxLayout(content)
        cv.setContentsMargins(12, 8, 12, 12)
        cv.setSpacing(24)

        # classes table
        left = QWidget()
        left.setStyleSheet(f"background:{BG_CARD};")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(4)
        lh = QLabel("Address Classes")
        lh.setStyleSheet(
            f"color:{TEXT_PRIMARY};font-weight:bold;font-size:11px;"
        )
        lv.addWidget(lh)
        lv.addWidget(self._section_table([
            ("Class A  /8",   "1.0.0.0 – 126.255.255.255   (16 million hosts per network)"),
            ("Class B  /16",  "128.0.0.0 – 191.255.255.255  (65,534 hosts per network)"),
            ("Class C  /24",  "192.0.0.0 – 223.255.255.255  (254 hosts per network)"),
            ("Class D",       "224.0.0.0 – 239.255.255.255  (multicast — not assignable to hosts)"),
            ("Class E",       "240.0.0.0 – 255.255.255.255  (reserved / experimental)"),
            ("127.0.0.0/8",   "Loopback — traffic never leaves the machine (127.0.0.1 = localhost)"),
            ("0.0.0.0",       "Unspecified — means 'this host' in DHCP and routing contexts"),
        ], col0_width=130))
        cv.addWidget(left, 1)

        # private ranges
        right = QWidget()
        right.setStyleSheet(f"background:{BG_CARD};")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(4)
        rh = QLabel("Private (RFC 1918) & Special Ranges")
        rh.setStyleSheet(
            f"color:{TEXT_PRIMARY};font-weight:bold;font-size:11px;"
        )
        rv.addWidget(rh)
        rv.addWidget(self._section_table([
            ("10.0.0.0/8",        "Private Class A — 16,777,214 hosts (enterprises, VPNs)"),
            ("172.16.0.0/12",     "Private Class B — 172.16.x.x to 172.31.x.x (1,048,574 hosts)"),
            ("192.168.0.0/16",    "Private Class C — 65,534 hosts (home routers use this)"),
            ("169.254.0.0/16",    "APIPA — auto-assigned when DHCP fails (no internet access)"),
            ("100.64.0.0/10",     "Shared address space — ISP CGNAT (you can't host servers)"),
            ("198.18.0.0/15",     "Benchmarking / testing — never routed on the internet"),
            ("255.255.255.255",   "Limited broadcast — reaches all hosts on the local segment"),
        ], col0_width=150))
        cv.addWidget(right, 1)

        cl.addWidget(content)
        return card

    # ── IPv4 vs IPv6 card ─────────────────────────────────────────────────────

    def _build_ipv6_card(self) -> QFrame:
        card, cl = self._card("IPv4 vs IPv6 — Key Differences")

        txt = QLabel(
            f"<div style='margin:10px 16px 12px 16px;font-size:11px;"
            f"color:{TEXT_PRIMARY};line-height:1.75;'>"

            f"<table width='100%' cellspacing='0' cellpadding='0'>"
            f"<tr>"
            f"<td width='30%' style='color:{TEXT_MUTED};font-size:9px;"
            f"font-weight:bold;padding-bottom:6px;'>PROPERTY</td>"
            f"<td width='35%' style='color:{ACCENT_DARK};font-size:9px;"
            f"font-weight:bold;padding-bottom:6px;'>IPv4</td>"
            f"<td width='35%' style='color:{GREEN};font-size:9px;"
            f"font-weight:bold;padding-bottom:6px;'>IPv6</td>"
            f"</tr>"

            + self._ipv6_row("Address length",   "32 bits",
                             "128 bits",             True)
            + self._ipv6_row("Total addresses",  "~4.3 billion",
                             "340 undecillion (3.4 × 10³⁸)", False)
            + self._ipv6_row("Format",           "192.168.1.1  (4 decimal octets)",
                             "2001:db8::1  (8 hex groups)", True)
            + self._ipv6_row("Subnet notation",  "192.168.1.0/24",
                             "2001:db8::/32", False)
            + self._ipv6_row("Broadcast",        "Yes — 255.255.255.255",
                             "No — replaced by multicast", True)
            + self._ipv6_row("Auto-config",      "DHCP (manual or server required)",
                             "SLAAC — devices configure themselves", False)
            + self._ipv6_row("NAT required?",    "Usually — IPv4 space is exhausted",
                             "No — every device gets a global address", True)
            + self._ipv6_row("Loopback",         "127.0.0.1",
                             "::1", False)
            + self._ipv6_row("Link-local",       "169.254.0.0/16  (APIPA, failure state)",
                             "fe80::/10  (normal — every interface has one)", True)
            + self._ipv6_row("Private range",    "10.x, 172.16–31.x, 192.168.x",
                             "fc00::/7  (unique local — like RFC 1918)", False)

            + f"</table>"

            + f"<br><b>Why you see IPv6 on your LAN now:</b> Modern mesh routers, "
            f"smart speakers, and computers assign themselves an <code>fe80::</code> "
            f"link-local address automatically — this is normal and expected. "
            f"The <b>IPv6 Devices</b> tab in NetSentinel scans your link-local segment "
            f"to show all IPv6-capable hosts on the network.<br><br>"

            f"<b>IPv6 address breakdown:</b><br>"
            f"<code style='font-size:12px;'>2001:0db8:85a3:0000:0000:8a2e:0370:7334</code><br>"
            f"<span style='color:{TEXT_MUTED};font-size:10px;'>"
            f"└─ Global routing prefix (48 bits) ─┘└─ Subnet (16 bits) ─┘└─── Interface ID (64 bits) ───┘"
            f"</span>"
            f"</div>"
        )
        txt.setWordWrap(True)
        txt.setTextFormat(Qt.TextFormat.RichText)
        cl.addWidget(txt)
        return card

    @staticmethod
    def _ipv6_row(prop: str, v4: str, v6: str, alt: bool) -> str:
        bg = "#1A2435" if alt else BG_CARD
        return (
            f"<tr style='background:{bg};'>"
            f"<td style='padding:4px 8px 4px 0;color:{TEXT_MUTED};"
            f"font-size:10px;font-weight:bold;'>{prop}</td>"
            f"<td style='padding:4px 8px;font-size:10px;font-family:Consolas,monospace;'>{v4}</td>"
            f"<td style='padding:4px 8px;font-size:10px;font-family:Consolas,monospace;"
            f"color:{GREEN};'>{v6}</td>"
            f"</tr>"
        )
