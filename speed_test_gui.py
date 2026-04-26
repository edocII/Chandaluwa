#!/usr/bin/env python3
"""
Internet Speed Test — Figma-accurate GUI
Engine: cloudflare-speed-cli --json
"""

import tkinter as tk
from tkinter import ttk
import threading
import socket
import subprocess
import platform
import math
import json
import shutil
import os
from datetime import datetime

# ── Palette ───────────────────────────────────────────────────────────────────
C = {
    'bg':           '#F0F2F8',
    'card':         '#FFFFFF',
    'title_bar':    '#FFFFFF',
    'text':         '#1A1A2E',
    'muted':        '#8A8FA8',
    'accent_blue':  '#2563EB',
    'banner_fair_bg':  '#FFFDE6',
    'banner_fair_bd':  '#FFE082',
    'banner_fair_fg':  '#F59E0B',
    'ping_bg':      '#FFF9E6', 'ping_bd': '#FFE082', 'ping_fg': '#F59E0B',
    'dl_bg':        '#E8FAF0', 'dl_bd':   '#A7E8C2', 'dl_fg':   '#16A34A',
    'ul_bg':        '#F3EEFF', 'ul_bd':   '#C4B5FD', 'ul_fg':   '#7C3AED',
    'excellent':    '#16A34A',
    'good':         '#2563EB',
    'fair':         '#F59E0B',
    'poor':         '#DC2626',
    'stat_bg':      '#F8F9FC', 'stat_bd': '#E8EAF2',
    'net_bg':       '#F8F9FC', 'net_bd':  '#E2E6F0',
    'analysis_bg':  '#EEF3FF', 'analysis_bd': '#C7D7F8',
    'analysis_fg':  '#1D4ED8',
    'btn_start':    '#6C47FF',
    'btn_end':      '#4F8EF7',
    'close':        '#FF5F57',
    'min_':         '#FEBC2E',
    'max_':         '#28C840',
}

QUALITY_MAP = [
    (80,  'Excellent', C['excellent']),
    (40,  'Good',      C['good']),
    (15,  'Fair',      C['fair']),
    (0,   'Poor',      C['poor']),
]

def get_quality(mbps):
    for t, label, fg in QUALITY_MAP:
        if mbps >= t:
            return label, fg
    return 'Poor', C['poor']


def parse_cf_json(data: dict) -> dict:
    """
    Extract all useful fields from cloudflare-speed-cli --json output.
    Exact field paths verified from live JSON:
      data['download']['mbps']
      data['upload']['mbps']
      data['idle_latency']['mean_ms']
      data['idle_latency']['jitter_ms']
      data['meta']['city'], ['country'], ['asOrganization'], ['colo'], ['httpProtocol']
      data['dns']['dns_servers'], ['resolved_ips']
      data['interface_name'], ['is_wireless'], ['external_ipv4']
      data['tls']['protocol_version']
    """
    dl_block   = data.get('download')             or {}
    ul_block   = data.get('upload')               or {}
    idle       = data.get('idle_latency')         or {}
    meta       = data.get('meta')                 or {}
    dns_block  = data.get('dns')                  or {}
    colo       = meta.get('colo')                 or {}
    ll_dl      = data.get('loaded_latency_download') or {}

    def _f(v, fallback=0.0):
        try:
            return float(v) if v is not None else fallback
        except (TypeError, ValueError):
            return fallback

    dl     = _f(dl_block.get('mbps'))
    ul     = _f(ul_block.get('mbps'))
    ping   = _f(idle.get('mean_ms'))
    jitter = _f(idle.get('jitter_ms'))

    # Packet loss: loaded-download loss if available, else idle loss
    loss_dl   = _f(ll_dl.get('loss'))
    loss_idle = _f(idle.get('loss'))
    loss      = loss_dl if loss_dl < 100.0 else loss_idle

    dns_servers = dns_block.get('dns_servers') or []
    dns_str     = ', '.join(dns_servers) if dns_servers else '—'

    resolved  = dns_block.get('resolved_ips') or []
    remote_ip = resolved[0] if resolved else (data.get('external_ipv4') or '—')

    server_city = colo.get('city', '') or ''
    server_iata = colo.get('iata', '') or ''
    server_str  = f"{server_city} ({server_iata})" if server_city else '—'

    return {
        'dl': dl, 'ul': ul, 'ping': ping,
        'jitter': jitter, 'loss': loss,
        'isp':         data.get('as_org', '—')         or '—',
        'external_ip': data.get('external_ipv4', '—')  or '—',
        'interface':   data.get('interface_name', '—') or '—',
        'is_wireless': bool(data.get('is_wireless', False)),
        'city':        meta.get('city', '—')            or '—',
        'country':     meta.get('country', '—')         or '—',
        'server':      server_str,
        'dns':         dns_str,
        'remote_ip':   remote_ip,
        'tls':         (data.get('tls') or {}).get('protocol_version', '—') or '—',
        'http':        meta.get('httpProtocol', '—')    or '—',
        'timestamp':   data.get('timestamp_utc', '')   or '',
    }


def build_recommendations(dl, ul, ping, jitter, loss):
    recs = []
    if dl < 5:
        recs.append('Very slow download — check for background activity or contact your ISP')
    elif dl < 25:
        recs.append('Download speed is slow — consider upgrading your internet plan')
    if ul < 5:
        recs.append('Very slow upload — may severely affect video calls and cloud uploads')
    elif ul < 10:
        recs.append('Upload speed is limited — may affect video calls and file uploads')
    if ping > 300:
        recs.append('Very high latency — try restarting your router or modem')
    elif ping > 80:
        recs.append('High latency detected — try moving closer to your router')
    if jitter > 50:
        recs.append('High jitter — connection is unstable, may cause choppy audio/video')
    if loss > 10:
        recs.append('Significant packet loss — check cables or router settings')
    if not recs:
        recs.append('Your connection looks healthy!')
    return recs


# ── App ───────────────────────────────────────────────────────────────────────
class SpeedTestApp:
    WINDOW_W = 680
    WINDOW_H = 700

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.overrideredirect(True)
        self.root.configure(bg=C['bg'])
        self.root.resizable(False, False)
        self._center()
        self._bars    = []
        self._anim_id = None
        self._drag_x  = self._drag_y = 0
        self._build_chrome()
        self.content = tk.Frame(self.root, bg=C['bg'])
        self.content.pack(fill=tk.BOTH, expand=True)
        self._show_start()

    def _center(self):
        w, h = self.WINDOW_W, self.WINDOW_H
        x = (self.root.winfo_screenwidth()  // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f'{w}x{h}+{x}+{y}')

    def _build_chrome(self):
        bar = tk.Frame(self.root, bg=C['title_bar'], height=42)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)
        bar.bind('<ButtonPress-1>', self._drag_start)
        bar.bind('<B1-Motion>',     self._drag_move)
        tk.Label(bar, text='⚡  Speed Test',
                 font=('Segoe UI', 12, 'bold'),
                 fg=C['text'], bg=C['title_bar']).place(relx=0.5, rely=0.5, anchor='center')
        ctrl = tk.Frame(bar, bg=C['title_bar'])
        ctrl.pack(side=tk.RIGHT, padx=12)
        self._make_ctrl(ctrl, C['close'], 'x', self.root.destroy)
        self._make_ctrl(ctrl, C['max_'],  '+', self._toggle_max)
        self._make_ctrl(ctrl, C['min_'],  '-', self._minimize)
        tk.Frame(self.root, bg='#E2E6F0', height=1).pack(fill=tk.X)

    def _make_ctrl(self, parent, color, symbol, cmd):
        btn = tk.Label(parent, text=symbol, width=2,
                       bg=color, fg=color,
                       font=('Segoe UI', 9, 'bold'),
                       cursor='hand2', relief=tk.FLAT)
        btn.pack(side=tk.RIGHT, padx=3, pady=10, ipady=1)
        btn.bind('<Enter>',    lambda e, b=btn: b.config(fg='#333333'))
        btn.bind('<Leave>',    lambda e, b=btn, c=color: b.config(fg=c))
        btn.bind('<Button-1>', lambda e: cmd())

    def _drag_start(self, e):
        self._drag_x = e.x_root - self.root.winfo_x()
        self._drag_y = e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        self.root.geometry(f'+{e.x_root - self._drag_x}+{e.y_root - self._drag_y}')

    def _minimize(self):
        self.root.withdraw()
        self._min_proxy = tk.Tk()
        self._min_proxy.title('Speed Test')
        self._min_proxy.geometry('1x1+0+0')
        self._min_proxy.iconify()
        self._min_proxy.bind('<Map>', self._restore_from_minimize)

    def _restore_from_minimize(self, event=None):
        try:
            self._min_proxy.destroy()
        except Exception:
            pass
        self.root.deiconify()
        self.root.lift()

    def _toggle_max(self):
        if self.root.winfo_width() < self.root.winfo_screenwidth() - 10:
            self.root.geometry(f'{self.root.winfo_screenwidth()}x'
                               f'{self.root.winfo_screenheight()}+0+0')
        else:
            self._center()

    def _clear(self):
        if self._anim_id:
            self.root.after_cancel(self._anim_id)
            self._anim_id = None
        self._bars = []
        for w in self.content.winfo_children():
            w.destroy()

    def _after(self, fn, *a, **kw):
        self.root.after(0, lambda f=fn, args=a, kwargs=kw: f(*args, **kwargs))

    def _card(self, parent, bg=None, bd_color=None, **kw):
        return tk.Frame(parent, bg=bg or C['card'],
                        highlightbackground=bd_color or '#E2E6F0',
                        highlightthickness=1, **kw)

    def _lbl(self, parent, text='', tv=None, size=12, weight='normal',
             color=None, anchor='center', **kw):
        return tk.Label(parent, text=text, textvariable=tv,
                        font=('Segoe UI', size, weight),
                        fg=color or C['text'], bg=parent.cget('bg'),
                        anchor=anchor, **kw)

    # ── START ─────────────────────────────────────────────────────────────────
    def _show_start(self):
        self._clear()
        outer = tk.Frame(self.content, bg=C['bg'])
        outer.pack(expand=True, fill=tk.BOTH)
        card = self._card(outer)
        card.place(relx=0.5, rely=0.5, anchor='center', width=520, height=420)
        self._lbl(card, 'Speed Test', size=22, weight='bold',
                  color=C['accent_blue']).pack(pady=(48, 4))
        self._lbl(card, 'Test your internet connection speed',
                  size=11, color=C['muted']).pack()
        bf = tk.Frame(card, bg=C['card'])
        bf.pack(expand=True)
        bolt = tk.Label(bf, text='⚡', font=('Segoe UI Emoji', 90),
                        fg='#F59E0B', bg=C['card'], cursor='hand2')
        bolt.pack(pady=(30, 8))
        bolt.bind('<Button-1>', lambda _: self._start_test())
        bolt.bind('<Enter>',    lambda e: bolt.config(fg='#D97706'))
        bolt.bind('<Leave>',    lambda e: bolt.config(fg='#F59E0B'))
        self._lbl(bf, 'Click to start test', size=11,
                  color=C['muted']).pack(pady=(0, 20))

    # ── TESTING ───────────────────────────────────────────────────────────────
    def _show_testing(self):
        self._clear()
        outer = tk.Frame(self.content, bg=C['bg'])
        outer.pack(expand=True, fill=tk.BOTH)
        card = self._card(outer)
        card.place(relx=0.5, rely=0.5, anchor='center', width=520, height=420)
        self._lbl(card, 'Speed Test', size=22, weight='bold',
                  color=C['accent_blue']).pack(pady=(40, 4))
        self._lbl(card, 'Test your internet connection speed',
                  size=11, color=C['muted']).pack()
        wc = tk.Canvas(card, width=200, height=64, bg=C['card'], highlightthickness=0)
        wc.pack(pady=(36, 8))
        self._bars = []
        for i, h in enumerate([18, 30, 48, 38, 26, 44, 30]):
            x = 16 + i * 26
            bid = wc.create_rectangle(x, 32 - h // 2, x + 6, 32 + h // 2,
                                      fill=C['accent_blue'], outline='')
            self._bars.append((wc, bid, h, i))
        self._phase = 0
        self._animate()
        self._status_var  = tk.StringVar(value='Initializing...')
        self._preview_var = tk.StringVar(value='')
        self._lbl(card, tv=self._status_var,  size=12, color=C['muted']).pack(pady=(0, 4))
        self._lbl(card, tv=self._preview_var, size=28, color='#CACFE0').pack()

    def _animate(self):
        if not self._bars:
            return
        try:
            self._phase += 0.18
            for canvas, bid, base_h, i in self._bars:
                scale = 0.35 + 0.65 * abs(math.sin(self._phase + i * 0.75))
                h = max(4, int(base_h * scale))
                canvas.coords(bid, 16 + i * 26, 32 - h // 2, 22 + i * 26, 32 + h // 2)
            self._anim_id = self.root.after(55, self._animate)
        except tk.TclError:
            pass

    # ── RESULTS ───────────────────────────────────────────────────────────────
    def _show_results(self, r: dict):
        self._clear()
        dl, ul, ping  = r['dl'], r['ul'], r['ping']
        jitter, loss  = r['jitter'], r['loss']

        outer  = tk.Frame(self.content, bg=C['bg'])
        outer.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(outer, bg=C['bg'], highlightthickness=0, borderwidth=0)
        sb     = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        inner  = tk.Frame(canvas, bg=C['bg'])
        wid    = canvas.create_window((0, 0), window=inner, anchor='nw')
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(wid, width=e.width))
        inner.bind('<Configure>',
                   lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind_all('<MouseWheel>',
                        lambda e: canvas.yview_scroll(-1 * (e.delta // 120), 'units'))

        pad = 60

        # header
        hdr = tk.Frame(inner, bg=C['bg'])
        hdr.pack(fill=tk.X, pady=(20, 0))
        row = tk.Frame(hdr, bg=C['bg'])
        row.pack()
        tk.Label(row, text='⚡', font=('Segoe UI Emoji', 18),
                 fg=C['accent_blue'], bg=C['bg']).pack(side=tk.LEFT, padx=(0, 6))
        tk.Label(row, text='Speed Test', font=('Segoe UI', 20, 'bold'),
                 fg=C['accent_blue'], bg=C['bg']).pack(side=tk.LEFT)
        tk.Label(hdr, text='Test your internet connection speed',
                 font=('Segoe UI', 10), fg=C['muted'], bg=C['bg']).pack()

        def section(bg=C['card'], bd=None):
            f = self._card(inner, bg=bg, bd_color=bd)
            f.pack(fill=tk.X, padx=pad - 20, pady=6)
            return f

        # quality banner
        ql, qfg = get_quality(dl)
        banner  = section(bg=C['banner_fair_bg'], bd=C['banner_fair_bd'])
        brow    = tk.Frame(banner, bg=C['banner_fair_bg'])
        brow.pack(pady=(14, 2))
        tk.Label(brow, text='Overall Connection Quality',
                 font=('Segoe UI', 13, 'bold'), fg=C['text'],
                 bg=C['banner_fair_bg']).pack(side=tk.LEFT)
        tk.Label(banner, text=f'  {ql}',
                 font=('Segoe UI', 22, 'bold'), fg=qfg,
                 bg=C['banner_fair_bg']).pack(pady=(2, 14))

        # metric cards
        mrow = tk.Frame(inner, bg=C['bg'])
        mrow.pack(fill=tk.X, padx=pad - 20, pady=4)
        for icon, label, value, bg, bd, fg in [
            ('Ping',     'Ping',     f'{ping:.0f} ms',   C['ping_bg'], C['ping_bd'], C['ping_fg']),
            ('Down',     'Download', f'{dl:.2f} Mbps',   C['dl_bg'],  C['dl_bd'],  C['dl_fg']),
            ('Up',       'Upload',   f'{ul:.2f} Mbps',   C['ul_bg'],  C['ul_bd'],  C['ul_fg']),
        ]:
            mc = self._card(mrow, bg=bg, bd_color=bd)
            mc.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=4)
            tk.Label(mc, text=label, font=('Segoe UI', 10),
                     fg=C['muted'], bg=bg).pack(pady=(14, 2))
            tk.Label(mc, text=value, font=('Segoe UI', 18, 'bold'),
                     fg=fg, bg=bg).pack(pady=4)
            ref = dl if label == 'Download' else ul if label == 'Upload' \
                  else (100 if ping < 30 else 30 if ping < 80 else 0)
            mql, _ = get_quality(ref)
            tk.Label(mc, text=mql, font=('Segoe UI', 10, 'bold'),
                     fg=C['excellent'] if mql == 'Excellent' else
                        C['poor']      if mql == 'Poor'      else C['fair'],
                     bg=bg).pack(pady=(0, 14))

        # stats row — all real values from Cloudflare JSON
        stability     = max(0.0, 100.0 - loss - min(jitter / 2, 30))
        quality_score = (min(dl / 100, 1) * 40 + min(ul / 50, 1) * 20 +
                         max(0, 1 - ping / 500) * 20 + (stability / 100) * 20)
        srow = tk.Frame(inner, bg=C['bg'])
        srow.pack(fill=tk.X, padx=pad - 20, pady=4)
        for icon, label, val in [
            ('~', 'Jitter',        f'{jitter:.1f} ms'),
            ('%', 'Packet Loss',   f'{loss:.1f}%'),
            ('@', 'Stability',     f'{stability:.1f}%'),
            ('*', 'Quality Score', f'{quality_score:.1f}%'),
        ]:
            sc = self._card(srow, bg=C['stat_bg'], bd_color=C['stat_bd'])
            sc.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=3)
            tk.Label(sc, text=label, font=('Segoe UI', 9),
                     fg=C['muted'], bg=C['stat_bg']).pack(pady=(10, 0))
            tk.Label(sc, text=val, font=('Segoe UI', 14, 'bold'),
                     fg=C['text'], bg=C['stat_bg']).pack(pady=(2, 10))

        # network details — sourced directly from Cloudflare JSON
        nd   = section(bg=C['net_bg'], bd=C['net_bd'])
        hrow = tk.Frame(nd, bg=C['net_bg'])
        hrow.pack(fill=tk.X, padx=16, pady=(14, 8))
        tk.Label(hrow, text='Network Connection Details',
                 font=('Segoe UI', 12, 'bold'), fg=C['text'],
                 bg=C['net_bg']).pack(side=tk.LEFT)
        grid = tk.Frame(nd, bg=C['net_bg'])
        grid.pack(fill=tk.X, padx=16, pady=(0, 14))
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        iface = r['interface'] + (' (Wi-Fi)' if r['is_wireless'] else '')
        fields = [
            ('ISP',          r['isp'],         'External IP',   r['external_ip']),
            ('Interface',    iface,             'Location',      f"{r['city']}, {r['country']}"),
            ('CF Server',    r['server'],       'TLS',           r['tls']),
            ('DNS Servers',  r['dns'],          'HTTP Protocol', r['http']),
            ('Ping avg',     f"{ping:.1f} ms",  'Jitter',        f"{jitter:.1f} ms"),
        ]
        for row_i, (l1, v1, l2, v2) in enumerate(fields):
            for col, (label, val) in enumerate([(l1, v1), (l2, v2)]):
                cell = tk.Frame(grid, bg=C['net_bg'])
                cell.grid(row=row_i, column=col, sticky='w', padx=8, pady=5)
                inn = tk.Frame(cell, bg=C['net_bg'])
                inn.pack(side=tk.LEFT)
                tk.Label(inn, text=label, font=('Segoe UI', 9),
                         fg=C['muted'], bg=C['net_bg'], anchor='w').pack(anchor='w')
                tk.Label(inn, text=val, font=('Segoe UI', 11, 'bold'),
                         fg=C['text'], bg=C['net_bg'], anchor='w').pack(anchor='w')

        # analysis
        an   = section(bg=C['analysis_bg'], bd=C['analysis_bd'])
        arow = tk.Frame(an, bg=C['analysis_bg'])
        arow.pack(fill=tk.X, padx=16, pady=(14, 6))
        tk.Label(arow, text='Analysis & Recommendations',
                 font=('Segoe UI', 12, 'bold'), fg=C['text'],
                 bg=C['analysis_bg']).pack(side=tk.LEFT)
        for rec in build_recommendations(dl, ul, ping, jitter, loss):
            rf = tk.Frame(an, bg=C['analysis_bg'])
            rf.pack(fill=tk.X, padx=20, pady=2)
            tk.Label(rf, text='•', font=('Segoe UI', 11),
                     fg=C['text'], bg=C['analysis_bg']).pack(side=tk.LEFT, anchor='nw', padx=(0, 6))
            tk.Label(rf, text=rec, font=('Segoe UI', 10),
                     fg=C['text'], bg=C['analysis_bg'],
                     wraplength=500, justify=tk.LEFT).pack(side=tk.LEFT, anchor='w')
        tk.Frame(an, bg=C['analysis_bg'], height=10).pack()

        # test again button
        bf = tk.Frame(inner, bg=C['bg'])
        bf.pack(pady=18)
        bc = tk.Canvas(bf, width=200, height=46, bg=C['bg'],
                       highlightthickness=0, cursor='hand2')
        bc.pack()
        bc.create_oval(0, 0, 46, 46, fill=C['btn_start'], outline='')
        bc.create_oval(154, 0, 200, 46, fill=C['btn_end'], outline='')
        bc.create_rectangle(23, 0, 177, 46, fill=C['btn_start'], outline='')
        steps = 20
        for i in range(steps):
            t = i / steps
            col = '#{:02x}{:02x}{:02x}'.format(
                int(0x6C + t * (0x4F - 0x6C)),
                int(0x47 + t * (0x8E - 0x47)),
                int(0xFF + t * (0xF7 - 0xFF)),
            )
            bc.create_rectangle(23 + int(t * 154), 0,
                                 23 + int((t + 1/steps) * 154), 46,
                                 fill=col, outline='')
        bc.create_text(100, 23, text='Test Again',
                       font=('Segoe UI', 12, 'bold'), fill='white')
        bc.bind('<Button-1>', lambda _: self._show_start())

        # timestamp
        ts = r['timestamp']
        try:
            dt     = datetime.fromisoformat(ts.replace('Z', '+00:00'))
            ts_str = dt.strftime('%Y-%m-%d  %H:%M:%S UTC')
        except Exception:
            ts_str = datetime.now().strftime('%Y-%m-%d  %H:%M:%S')
        tk.Label(inner, text=f"Last tested: {ts_str}",
                 font=('Segoe UI', 9), fg=C['muted'], bg=C['bg']).pack(pady=(0, 16))

    # ── error screen ──────────────────────────────────────────────────────────
    def _show_error(self, msg):
        self._clear()
        outer = tk.Frame(self.content, bg=C['bg'])
        outer.pack(expand=True, fill=tk.BOTH)
        card = self._card(outer)
        card.place(relx=0.5, rely=0.5, anchor='center', width=500, height=300)
        tk.Label(card, text='!', font=('Segoe UI', 48, 'bold'),
                 fg=C['poor'], bg=C['card']).pack(pady=(40, 8))
        tk.Label(card, text=msg, font=('Segoe UI', 11), fg=C['poor'],
                 bg=C['card'], wraplength=400).pack()
        tk.Button(card, text='Try Again', font=('Segoe UI', 11),
                  fg='white', bg=C['btn_start'], relief=tk.FLAT,
                  padx=24, pady=8, cursor='hand2',
                  command=self._show_start).pack(pady=24)

    # ── runner ────────────────────────────────────────────────────────────────
    def _start_test(self):
        self._show_testing()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            self._set_status('Initializing Cloudflare Test...')

            script_dir   = os.path.dirname(os.path.abspath(__file__))
            bin_name     = 'cloudflare-speed-cli.exe' if os.name == 'nt' else 'cloudflare-speed-cli'
            local_binary = os.path.join(script_dir, bin_name)
            binary       = local_binary if os.path.exists(local_binary) \
                           else shutil.which('cloudflare-speed-cli')

            if not binary:
                raise Exception(
                    'cloudflare-speed-cli not found.\n'
                    'Place the .exe next to this script or add it to your PATH.'
                )

            self._set_status('Running speed test (~30s)...')
            result = subprocess.run(
                [binary, '--json'],
                capture_output=True, text=True, check=True
            )

            self._set_status('Parsing results...')
            data = json.loads(result.stdout)
            r    = parse_cf_json(data)

            self._after(self._show_results, r)

        except subprocess.CalledProcessError as exc:
            self._after(self._show_error,
                        f'Binary error (rc={exc.returncode}):\n{exc.stderr.strip()}')
        except json.JSONDecodeError as exc:
            self._after(self._show_error, f'Could not parse JSON:\n{exc}')
        except Exception as exc:
            self._after(self._show_error, str(exc))

    def _set_status(self, msg):
        self._after(lambda m=msg: self._status_var.set(m)
                    if hasattr(self, '_status_var') else None)

    def _set_preview(self, val):
        try:
            self._preview_var.set(val)
        except Exception:
            pass


def print_results(r: dict):
    dl, ul, ping = r['dl'], r['ul'], r['ping']
    jitter, loss = r['jitter'], r['loss']
    ql, _ = get_quality(dl)
    
    print("⚡ Speed Test Results")
    print("=" * 50)
    print(f"Download: {dl:.2f} Mbps")
    print(f"Upload: {ul:.2f} Mbps")
    print(f"Ping: {ping:.0f} ms")
    print(f"Jitter: {jitter:.1f} ms")
    print(f"Packet Loss: {loss:.1f}%")
    print(f"Quality: {ql}")
    print()
    print("Network Details:")
    print(f"ISP: {r['isp']}")
    print(f"External IP: {r['external_ip']}")
    print(f"Interface: {r['interface']}{' (Wi-Fi)' if r['is_wireless'] else ''}")
    print(f"Location: {r['city']}, {r['country']}")
    print(f"Server: {r['server']}")
    print(f"DNS: {r['dns']}")
    print(f"TLS: {r['tls']}")
    print(f"HTTP: {r['http']}")
    print()
    print("Analysis & Recommendations:")
    for rec in build_recommendations(dl, ul, ping, jitter, loss):
        print(f"• {rec}")
    print()
    ts = r['timestamp']
    try:
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        ts_str = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
    except Exception:
        ts_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"Tested at: {ts_str}")


def run_headless_test():
    print("Running speed test in headless mode...")
    try:
        binary = shutil.which('cloudflare-speed-cli')
        if not binary:
            raise Exception('cloudflare-speed-cli not found in PATH.')
        
        print("Initializing Cloudflare Test...")
        result = subprocess.run(
            [binary, '--json'],
            capture_output=True, text=True, check=True
        )
        
        print("Parsing results...")
        data = json.loads(result.stdout)
        r = parse_cf_json(data)
        print_results(r)
        
    except subprocess.CalledProcessError as exc:
        print(f"Binary error (rc={exc.returncode}): {exc.stderr.strip()}")
    except json.JSONDecodeError as exc:
        print(f"Could not parse JSON: {exc}")
    except Exception as exc:
        print(f"Error: {exc}")


def main():
    try:
        root = tk.Tk()
        SpeedTestApp(root)
        root.mainloop()
    except tk.TclError as e:
        if "couldn't connect to display" in str(e).lower() or "no display name" in str(e).lower():
            print("No display available. Running in headless mode.")
            run_headless_test()
        else:
            raise


if __name__ == '__main__':
    main()