# -*- coding: utf-8 -*-
"""Shopee Affiliate AutoPilot - Extra Comm assisted workflow.

This application intentionally does not scrape Shopee, automate Meta AI login,
or automate Shopee Video publishing. It manages verified-by-user product data,
content drafts, video files, post kits, and publishing records locally.
"""
from __future__ import annotations

import csv
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import webbrowser
from datetime import date, datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "affiliate_autopilot.db"
MEDIA_DIR = APP_DIR / "media"
POST_KITS_DIR = APP_DIR / "post_kits"
MEDIA_DIR.mkdir(exist_ok=True)
POST_KITS_DIR.mkdir(exist_ok=True)

SHOPEE_DASHBOARD = "https://affiliate.shopee.co.th/dashboard"
META_AI_URL = "https://www.meta.ai/"
SHOPEE_VIDEO_URL = "https://shopee.co.th/"

CATEGORIES = [
    "ความงามและสกินแคร์", "แฟชั่น", "อุปกรณ์ไอที", "เครื่องใช้ไฟฟ้า",
    "ของใช้ในบ้าน", "แม่และเด็ก", "อาหารและเครื่องดื่ม", "สุขภาพ",
    "กีฬาและกิจกรรมกลางแจ้ง", "สัตว์เลี้ยง", "ยานยนต์",
    "เครื่องเขียนและสำนักงาน", "อื่น ๆ"
]
STYLES = [
    "Influencer รีวิว", "สาธิตการใช้งาน", "Cinematic Product",
    "เล่าเรื่องปัญหา-ทางออก", "เปรียบเทียบคุณสมบัติ", "How-to / เคล็ดลับ",
    "Unboxing / แกะกล่อง", "AI เลือกให้"
]
CSV_FIELDS = [
    "name", "category", "product_url", "affiliate_url", "extra_comm_proof",
    "commission_note", "price", "key_features", "source", "checked_date"
]

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS products (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 name TEXT NOT NULL, category TEXT, product_url TEXT, affiliate_url TEXT NOT NULL,
 extra_comm_proof TEXT NOT NULL, commission_note TEXT NOT NULL, price TEXT,
 key_features TEXT, source TEXT, checked_date TEXT, created_at TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS jobs (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 product_id INTEGER NOT NULL, work_date TEXT NOT NULL, style TEXT NOT NULL,
 script TEXT NOT NULL, caption TEXT NOT NULL, hashtags TEXT NOT NULL,
 meta_prompt TEXT NOT NULL, video_path TEXT, status TEXT NOT NULL DEFAULT 'รอสร้างวิดีโอ',
 publish_url TEXT, posted_at TEXT, notes TEXT, created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 FOREIGN KEY(product_id) REFERENCES products(id)
);
CREATE INDEX IF NOT EXISTS idx_jobs_date ON jobs(work_date);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
"""


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(SCHEMA)
    return con


def valid_affiliate(url: str) -> bool:
    return bool(re.fullmatch(r"https://s\.shopee\.co\.th/[A-Za-z0-9/_?=&%.-]+", (url or "").strip(), re.I))


def safe_filename(value: str) -> str:
    value = re.sub(r"[^\wก-๙-]+", "_", value, flags=re.UNICODE).strip("_")
    return (value[:60] or "product")


def build_content(product: sqlite3.Row, style: str, variant: int = 0):
    name = (product["name"] or "สินค้าชิ้นนี้").strip()
    category = (product["category"] or "สินค้า").strip()
    features = (product["key_features"] or "ตรวจสอบรายละเอียดและคุณสมบัติจากหน้าสินค้าจริง").strip()
    price = (product["price"] or "").strip()
    hooks = {
        "Influencer รีวิว": [f"วันนี้พามาดู {name}", f"ใครกำลังดู {category} อยู่ ลองดู {name}", f"มีสินค้าอีกชิ้นที่อยากพามาดู คือ {name}"],
        "สาธิตการใช้งาน": [f"มาดูวิธีใช้งาน {name} กัน", f"คลิปนี้พาดูรายละเอียดการใช้งาน {name}", f"ก่อนเลือก {name} มาดูจุดใช้งานกัน"],
        "Cinematic Product": [f"พาชมรายละเอียดของ {name} แบบใกล้ ๆ", f"เก็บรายละเอียดสินค้า {name} ในมุมต่าง ๆ", f"มาดูดีไซน์และรายละเอียดของ {name}"],
        "เล่าเรื่องปัญหา-ทางออก": [f"ถ้ากำลังมองหาสินค้าหมวด{category} ลองดู {name}", f"กำลังเปรียบเทียบสินค้า{category} อยู่หรือเปล่า? มาดู {name}", f"ก่อนตัดสินใจเลือก{category} ลองดูรายละเอียดของ {name}"],
        "เปรียบเทียบคุณสมบัติ": [f"3 จุดที่ควรเช็กก่อนเลือก {name}", f"ก่อนซื้อ {name} มีรายละเอียดอะไรที่ควรดูบ้าง", f"ลองพิจารณาคุณสมบัติของ {name} ก่อนตัดสินใจ"],
        "How-to / เคล็ดลับ": [f"วิธีเช็กรายละเอียดก่อนเลือก {name}", f"เคล็ดลับเลือกสินค้า{category}: ดู {name} เป็นตัวอย่าง", f"มีอะไรที่ควรตรวจสอบก่อนซื้อ {name} บ้าง"],
        "Unboxing / แกะกล่อง": [f"พาชมสินค้า {name} และรายละเอียดที่ควรสังเกต", f"เปิดดูรายละเอียดของ {name} ไปพร้อมกัน", f"มาดูตัวสินค้า {name} แบบใกล้ ๆ"],
        "AI เลือกให้": [f"แนะนำให้รู้จัก {name}", f"สินค้าในหมวด{category} ที่นำมาดูวันนี้คือ {name}", f"วันนี้เลือก {name} มาเล่ารายละเอียดให้ฟัง"]
    }
    hook = hooks.get(style, hooks["AI เลือกให้"])[variant % 3]
    price_line = f"ราคาอ้างอิงที่บันทึกไว้: {price} (โปรดตรวจสอบราคาปัจจุบัน)\n" if price else ""
    script = (
        f"เปิดคลิป: {hook}\n"
        f"นำเสนอ: {features}\n"
        f"{price_line}"
        "ภาพประกอบ: แสดงสินค้าจริง รายละเอียด วัสดุ ขนาด หรือวิธีใช้ เฉพาะข้อมูลที่ตรวจสอบได้\n"
        "ปิดคลิป: ดูราคา โปรโมชัน รีวิว และรายละเอียดล่าสุดจากหน้าสินค้าก่อนตัดสินใจ\n"
        "ข้อกำกับ: ห้ามแต่งผลลัพธ์ รีวิวจากประสบการณ์ที่ไม่ได้เกิดขึ้นจริง หรือคุณสมบัติที่ไม่มีหลักฐาน"
    )
    caption = (
        f"{hook}\n\n{features}\n\n"
        "ดูรายละเอียด ราคา และรีวิวล่าสุดได้ที่หน้าสินค้า\n"
        "*ราคา โปรโมชัน และสต็อกอาจเปลี่ยนแปลงได้ โปรดตรวจสอบก่อนสั่งซื้อ"
    )
    hashtags = "#ShopeeVideo #ShopeeAffiliate #ExtraComm #รีวิวสินค้า #ของดีบอกต่อ"
    prompt = (
        "Create a vertical 9:16 product video, approximately 12–15 seconds, for a Thai Shopee Video audience. "
        f"Product: {name}. Category: {category}. Creative style: {style}. "
        f"Use the supplied genuine product images as visual reference. Verified product details only: {features}. "
        "Show clear close-up product shots, natural lighting, stable realistic camera movement, clean composition, "
        "and a Thai creator-review feel. Do not invent product features, discounts, certifications, health claims, "
        "test results, customer testimonials, or personal-use experience. Do not show a fake Shopee interface, "
        "fake prices, or fake badges. Leave clean space for adding Thai captions in editing."
    )
    return script, caption, hashtags, prompt


class AutoPilot(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Shopee Affiliate AutoPilot — Extra Comm")
        self.geometry("1320x850")
        self.minsize(1080, 700)
        self.configure(bg="#101722")
        self.con = connect_db()
        self._style()
        self._build_ui()
        self.refresh_all()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background="#101722", foreground="#e8edf5", fieldbackground="#1c2838", font=("Segoe UI", 10))
        s.configure("TFrame", background="#101722")
        s.configure("Card.TFrame", background="#1c2838")
        s.configure("TLabel", background="#101722", foreground="#e8edf5")
        s.configure("Title.TLabel", font=("Segoe UI", 19, "bold"))
        s.configure("Sub.TLabel", foreground="#a9b8ca")
        s.configure("TButton", padding=7)
        s.configure("Treeview", background="#1c2838", foreground="#e8edf5", fieldbackground="#1c2838", rowheight=28)
        s.configure("Treeview.Heading", background="#304158", foreground="white", padding=6)
        s.map("Treeview", background=[("selected", "#315b83")])

    def _build_ui(self):
        header = ttk.Frame(self); header.pack(fill="x", padx=18, pady=(14, 5))
        ttk.Label(header, text="SHOPEE AFFILIATE AUTOPILOT", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="EXTRA COMM ONLY  •  PC + ANDROID  •  LAN MOBILE HUB", style="Sub.TLabel").pack(side="right")
        warning = ttk.Label(self, text="โหมด Assisted: ไม่ scrape / ไม่เก็บรหัสผ่าน / ไม่ควบคุม Meta หรือ Shopee แทนคุณ • หลักฐาน Extra Comm ต้องตรวจจาก Shopee ก่อนใช้จริง", wraplength=1260, foreground="#f3c969")
        warning.pack(fill="x", padx=20, pady=(0, 10))
        self.tabs = ttk.Notebook(self); self.tabs.pack(fill="both", expand=True, padx=16, pady=8)
        self.tab_dash = ttk.Frame(self.tabs); self.tab_products = ttk.Frame(self.tabs); self.tab_jobs = ttk.Frame(self.tabs); self.tab_guide = ttk.Frame(self.tabs)
        self.tabs.add(self.tab_dash, text="ภาพรวม")
        self.tabs.add(self.tab_products, text="สินค้า Extra Comm")
        self.tabs.add(self.tab_jobs, text="คิววิดีโอ / โพสต์")
        self.tabs.add(self.tab_guide, text="คู่มือ")
        self._build_dashboard(); self._build_products(); self._build_jobs(); self._build_guide()
        self.status_var = tk.StringVar(value="พร้อมใช้งาน")
        ttk.Label(self, textvariable=self.status_var, anchor="w", relief="sunken").pack(fill="x", side="bottom")

    def _build_dashboard(self):
        f = self.tab_dash
        cards = ttk.Frame(f); cards.pack(fill="x", padx=14, pady=14)
        self.stats = {}
        for key, label in [("products", "สินค้าที่บันทึก"), ("proof", "มีหลักฐานกรอก"), ("today", "งานวันนี้"), ("video", "มีวิดีโอแล้ว"), ("posted", "บันทึกว่าโพสต์แล้ว")]:
            c = ttk.Frame(cards, style="Card.TFrame", padding=14); c.pack(side="left", fill="both", expand=True, padx=5)
            ttk.Label(c, text=label, background="#1c2838").pack(anchor="w")
            v = ttk.Label(c, text="0", font=("Segoe UI", 23, "bold"), background="#1c2838"); v.pack(anchor="w", pady=(8, 0)); self.stats[key] = v
        actions = ttk.Frame(f); actions.pack(fill="x", padx=20, pady=8)
        ttk.Button(actions, text="เปิด Shopee Affiliate", command=lambda: webbrowser.open(SHOPEE_DASHBOARD)).pack(side="left", padx=4)
        ttk.Button(actions, text="เปิด Meta AI", command=lambda: webbrowser.open(META_AI_URL)).pack(side="left", padx=4)
        ttk.Button(actions, text="สร้างคิววันนี้ (กำหนดจำนวน)", command=self.generate_daily).pack(side="left", padx=4)
        ttk.Button(actions, text="นำเข้า CSV", command=self.import_csv).pack(side="left", padx=4)
        ttk.Button(actions, text="สำรองฐานข้อมูล", command=self.backup).pack(side="left", padx=4)
        ttk.Label(f, text="งานล่าสุด", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=20, pady=(14, 5))
        self.recent = ttk.Treeview(f, columns=("date", "product", "style", "status"), show="headings", height=13)
        for c, title, width in [("date", "วันที่", 120), ("product", "สินค้า", 430), ("style", "รูปแบบ", 220), ("status", "สถานะ", 230)]:
            self.recent.heading(c, text=title); self.recent.column(c, width=width)
        self.recent.pack(fill="both", expand=True, padx=20, pady=6)

    def _build_products(self):
        f = self.tab_products
        form = ttk.LabelFrame(f, text="เพิ่มสินค้า (ต้องมีหลักฐาน Extra Comm และ Affiliate Link จริง)", padding=10)
        form.pack(fill="x", padx=12, pady=10)
        self.pvars = {}
        fields = [
            ("name", "ชื่อสินค้า"), ("category", "หมวดหมู่"),
            ("product_url", "URL หน้าสินค้า"), ("affiliate_url", "Affiliate Link (s.shopee.co.th)"),
            ("extra_comm_proof", "หลักฐาน Extra Comm (URL/ชื่อแคมเปญ/ภาพอ้างอิง)"),
            ("commission_note", "อัตรา/รายละเอียด Extra Comm"), ("price", "ราคาอ้างอิง"),
            ("key_features", "จุดเด่นที่ตรวจสอบได้"), ("source", "แหล่งข้อมูล"), ("checked_date", "วันที่ตรวจสอบ (YYYY-MM-DD)")
        ]
        for i, (key, label) in enumerate(fields):
            r, c = divmod(i, 2); col = c * 2
            ttk.Label(form, text=label).grid(row=r, column=col, sticky="w", padx=5, pady=4)
            var = tk.StringVar(); self.pvars[key] = var
            if key == "category":
                widget = ttk.Combobox(form, textvariable=var, values=CATEGORIES, state="readonly", width=48); widget.set(CATEGORIES[0])
            else:
                widget = ttk.Entry(form, textvariable=var, width=51)
            widget.grid(row=r, column=col + 1, sticky="ew", padx=5, pady=4)
        form.columnconfigure(1, weight=1); form.columnconfigure(3, weight=1)
        buttons = ttk.Frame(form); buttons.grid(row=5, column=0, columnspan=4, sticky="w", padx=5, pady=8)
        ttk.Button(buttons, text="บันทึกสินค้า", command=self.add_product).pack(side="left", padx=3)
        ttk.Button(buttons, text="ล้างช่องกรอก", command=self.clear_product_form).pack(side="left", padx=3)
        bar = ttk.Frame(f); bar.pack(fill="x", padx=12, pady=(3, 0))
        ttk.Button(bar, text="นำเข้า CSV", command=self.import_csv).pack(side="left", padx=3)
        ttk.Button(bar, text="ส่งออก CSV", command=self.export_products).pack(side="left", padx=3)
        ttk.Button(bar, text="ลบสินค้าที่เลือก", command=self.delete_product).pack(side="left", padx=3)
        self.ptree = ttk.Treeview(f, columns=("id", "name", "category", "comm", "proof", "link"), show="headings", height=12)
        for c, title, width in [("id", "ID", 45), ("name", "สินค้า", 240), ("category", "หมวดหมู่", 130), ("comm", "Extra Comm", 150), ("proof", "หลักฐาน", 110), ("link", "Affiliate Link", 390)]:
            self.ptree.heading(c, text=title); self.ptree.column(c, width=width)
        self.ptree.pack(fill="both", expand=True, padx=12, pady=8)

    def _build_jobs(self):
        f = self.tab_jobs
        bar = ttk.Frame(f); bar.pack(fill="x", padx=12, pady=10)
        actions = [
            ("สร้างงานจากสินค้าที่เลือก", self.generate_selected), ("เปิดรายละเอียด / คัดลอก", self.show_job),
            ("เปิด Meta AI", lambda: webbrowser.open(META_AI_URL)), ("แนบวิดีโอ", self.attach_video),
            ("สร้างชุดโพสต์", self.export_post_kit), ("บันทึกว่าโพสต์แล้ว", self.mark_published),
            ("ส่งออกคิว CSV", self.export_jobs)
        ]
        for label, command in actions: ttk.Button(bar, text=label, command=command).pack(side="left", padx=2)
        self.jtree = ttk.Treeview(f, columns=("id", "date", "product", "style", "status", "video"), show="headings", height=20)
        for c, title, width in [("id", "ID", 45), ("date", "วันที่", 100), ("product", "สินค้า", 270), ("style", "รูปแบบ", 175), ("status", "สถานะ", 180), ("video", "ไฟล์วิดีโอ", 330)]:
            self.jtree.heading(c, text=title); self.jtree.column(c, width=width)
        self.jtree.pack(fill="both", expand=True, padx=12, pady=8)
        ttk.Label(f, text="หมายเหตุ: ‘ชุดโพสต์’ จะรวมวิดีโอ แคปชัน Hashtag และลิงก์ไว้ในโฟลเดอร์เดียว ไม่ได้กดเผยแพร่แทนคุณ", foreground="#f3c969").pack(anchor="w", padx=14, pady=5)

    def _build_guide(self):
        f = self.tab_guide
        text = (
            "คู่มือใช้งาน Shopee Affiliate AutoPilot — Extra Comm\n\n"
            "เริ่มต้น\n"
            "1. เปิด Shopee Affiliate Dashboard แล้วตรวจสอบสินค้าในหมวด/แคมเปญ Extra Comm\n"
            "2. สร้าง Affiliate Link ด้วยฟังก์ชันของ Shopee ที่บัญชีคุณใช้งานได้\n"
            "3. เพิ่มสินค้าในแท็บสินค้า หรือใช้ CSV template ที่ให้มา\n"
            "4. กรอกหลักฐาน Extra Comm, อัตรา/รายละเอียด, วันที่ตรวจสอบ และลิงก์ Affiliate\n"
            "5. กด ‘สร้างคิววันนี้ 30 งาน’ เพื่อสร้างร่างงาน (สินค้าอาจถูกใช้ซ้ำหากมีไม่ถึง 30 รายการ)\n"
            "6. เปิดรายละเอียดงาน คัดลอก Prompt แล้วเปิด Meta AI เพื่อสร้างวิดีโอด้วยตนเอง\n"
            "7. ดาวน์โหลดวิดีโอจาก Meta AI แล้วแนบไฟล์ในโปรแกรม\n"
            "8. กด ‘สร้างชุดโพสต์’ เพื่อรวมวิดีโอ/แคปชัน/Hashtag/ลิงก์ไว้พร้อมใช้งาน\n"
            "9. เผยแพร่ผ่าน Shopee Video ตามฟังก์ชันที่ Shopee อนุญาต เลือกสินค้าที่ตรงกับคลิป\n"
            "10. กลับมาบันทึก URL โพสต์เพื่อเก็บประวัติ\n\n"
            "สิ่งที่โปรแกรมทำได้จริง\n"
            "• เก็บสินค้าและงานใน SQLite บนเครื่อง\n"
            "• บังคับให้มีข้อมูลหลักฐาน Extra Comm และลิงก์ Affiliate ก่อนบันทึกสินค้า\n"
            "• สร้างร่างบท แคปชัน Hashtag และ Prompt แบบอัตโนมัติจากข้อมูลที่กรอก\n"
            "• สร้างคิวได้ตามจำนวนที่กำหนด ไม่จำกัด 30 งาน/วัน, แนบวิดีโอ, สร้างชุดโพสต์, ส่งออก CSV และสำรองฐานข้อมูล\n\n"
            "ข้อจำกัดที่ต้องทราบ\n"
            "• การกรอกหลักฐานในโปรแกรมไม่ใช่การตรวจสอบ Extra Comm แบบสดจาก Shopee ต้องตรวจป้าย/อัตรา/ช่วงเวลาใน Shopee ก่อนทุกครั้ง\n"
            "• โปรแกรมนี้ไม่มี Shopee Open API และไม่ scrape ข้อมูล Shopee\n"
            "• โปรแกรมไม่สามารถสั่ง Meta AI สร้างวิดีโอผ่าน API ที่ยืนยันว่าเปิดให้สมาชิกทั่วไปใช้ได้\n"
            "• โปรแกรมไม่สามารถโพสต์ Shopee Video หรือแนบสินค้าแทนผู้ใช้ได้โดยตรง\n"
            "• จำนวนคิวเป็นแผนการผลิต ไม่ใช่การรับประกันว่าจะสร้าง/โพสต์ได้ครบทุกคลิป\n"
            "• ตรวจสอบข้อความและข้อกล่าวอ้างทั้งหมดก่อนเผยแพร่\n\n"
            f"Shopee Affiliate: {SHOPEE_DASHBOARD}\nMeta AI: {META_AI_URL}\n"
        )
        box = tk.Text(f, wrap="word", bg="#1c2838", fg="#e8edf5", insertbackground="white", font=("Segoe UI", 11), relief="flat", padx=16, pady=16)
        box.pack(fill="both", expand=True, padx=14, pady=14); box.insert("1.0", text); box.configure(state="disabled")

    def add_product(self):
        d = {k: v.get().strip() for k, v in self.pvars.items()}
        if not d["name"] or not d["extra_comm_proof"] or not d["commission_note"]:
            messagebox.showerror("ข้อมูลไม่ครบ", "ต้องกรอกชื่อสินค้า หลักฐาน Extra Comm และรายละเอียดค่าตอบแทน"); return
        if not valid_affiliate(d["affiliate_url"]):
            messagebox.showerror("Affiliate Link ไม่ถูกต้อง", "ต้องเป็นลิงก์ https://s.shopee.co.th/... ที่สร้างจากบัญชี Affiliate ของคุณ"); return
        checked = d["checked_date"] or date.today().isoformat()
        try: datetime.strptime(checked, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("วันที่ไม่ถูกต้อง", "ใช้รูปแบบ YYYY-MM-DD เช่น 2026-11-26"); return
        duplicate = self.con.execute("SELECT id FROM products WHERE affiliate_url=?", (d["affiliate_url"],)).fetchone()
        if duplicate:
            messagebox.showwarning("มีลิงก์นี้แล้ว", f"Affiliate Link นี้อยู่ในระบบแล้ว (สินค้า ID {duplicate['id']})"); return
        self.con.execute(
            "INSERT INTO products(name,category,product_url,affiliate_url,extra_comm_proof,commission_note,price,key_features,source,checked_date,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (d["name"], d["category"], d["product_url"], d["affiliate_url"], d["extra_comm_proof"], d["commission_note"], d["price"], d["key_features"], d["source"], checked, now_text())
        )
        self.con.commit(); self.clear_product_form(); self.refresh_all()
        messagebox.showinfo("บันทึกแล้ว", "บันทึกสินค้าแล้ว\nโปรแกรมเก็บหลักฐานที่คุณกรอกไว้ แต่ไม่ได้ตรวจสอบสถานะ Extra Comm แบบสดจาก Shopee")

    def clear_product_form(self):
        for k, v in self.pvars.items(): v.set(CATEGORIES[0] if k == "category" else "")

    def _selected_product(self):
        sel = self.ptree.selection()
        if not sel: return None
        pid = int(self.ptree.item(sel[0])["values"][0])
        return self.con.execute("SELECT * FROM products WHERE id=? AND active=1", (pid,)).fetchone()

    def _selected_job(self):
        sel = self.jtree.selection()
        if not sel: return None
        jid = int(self.jtree.item(sel[0])["values"][0])
        return self.con.execute("SELECT jobs.*, products.name, products.category, products.affiliate_url, products.product_url, products.commission_note, products.price, products.key_features FROM jobs JOIN products ON products.id=jobs.product_id WHERE jobs.id=?", (jid,)).fetchone()

    def _create_job(self, product, work_date: str, index: int):
        style = STYLES[index % len(STYLES)]
        script, caption, tags, prompt = build_content(product, style, index // len(STYLES))
        stamp = now_text()
        self.con.execute(
            "INSERT INTO jobs(product_id,work_date,style,script,caption,hashtags,meta_prompt,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (product["id"], work_date, style, script, caption, tags, prompt, "รอสร้างวิดีโอใน Meta AI", stamp, stamp)
        )

    def generate_daily(self):
        today = date.today().isoformat()
        products = self.con.execute("SELECT * FROM products WHERE active=1 ORDER BY checked_date DESC, id DESC").fetchall()
        if not products:
            messagebox.showwarning("ยังไม่มีสินค้า", "เพิ่มหรือนำเข้าสินค้าที่มีหลักฐาน Extra Comm และ Affiliate Link ก่อน"); return
        quantity = simpledialog.askinteger("สร้างคิววันนี้", "ต้องการสร้างงานกี่รายการ?", parent=self, initialvalue=30, minvalue=1, maxvalue=1000)
        if quantity is None: return
        existing = self.con.execute("SELECT COUNT(*) n FROM jobs WHERE work_date=?", (today,)).fetchone()["n"]
        for i in range(quantity):
            product = products[(existing + i) % len(products)]
            self._create_job(product, today, existing + i)
        self.con.commit(); self.refresh_all(); self.tabs.select(self.tab_jobs)
        reused = max(0, quantity - len(products))
        msg = f"สร้างคิวเพิ่ม {quantity} งาน วันนี้มีทั้งหมด {existing + quantity} งาน"
        if reused: msg += f"\\nมีสินค้า {len(products)} รายการ จึงมีการหมุนใช้สินค้าซ้ำ โปรดปรับเนื้อหาและหลีกเลี่ยงการโพสต์ซ้ำ"
        messagebox.showinfo("สร้างคิวแล้ว", msg)

    def generate_selected(self):
        product = self._selected_product()
        if not product:
            messagebox.showwarning("เลือกสินค้า", "เลือกสินค้าในแท็บสินค้า Extra Comm ก่อน"); return
        quantity = simpledialog.askinteger("สร้างงานจากสินค้าที่เลือก", "ต้องการสร้างงานจากสินค้านี้กี่รายการ?", parent=self, initialvalue=1, minvalue=1, maxvalue=1000)
        if quantity is None: return
        today = date.today().isoformat()
        count = self.con.execute("SELECT COUNT(*) n FROM jobs WHERE work_date=?", (today,)).fetchone()["n"]
        for i in range(quantity):
            self._create_job(product, today, count + i)
        self.con.commit(); self.refresh_all(); self.tabs.select(self.tab_jobs)

    def import_csv(self):
        path = filedialog.askopenfilename(title="เลือก CSV สินค้า", filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
        if not path: return
        added, skipped, errors = 0, 0, []
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as fh:
                reader = csv.DictReader(fh)
                missing = [x for x in CSV_FIELDS if x not in (reader.fieldnames or [])]
                if missing:
                    messagebox.showerror("CSV ไม่ถูกต้อง", "ไม่พบคอลัมน์: " + ", ".join(missing)); return
                for line, row in enumerate(reader, 2):
                    d = {k: (row.get(k) or "").strip() for k in CSV_FIELDS}
                    if not d["name"] or not d["extra_comm_proof"] or not d["commission_note"] or not valid_affiliate(d["affiliate_url"]):
                        errors.append(str(line)); continue
                    if self.con.execute("SELECT 1 FROM products WHERE affiliate_url=?", (d["affiliate_url"],)).fetchone():
                        skipped += 1; continue
                    checked = d["checked_date"] or date.today().isoformat()
                    try: datetime.strptime(checked, "%Y-%m-%d")
                    except ValueError: errors.append(str(line)); continue
                    self.con.execute(
                        "INSERT INTO products(name,category,product_url,affiliate_url,extra_comm_proof,commission_note,price,key_features,source,checked_date,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (d["name"], d["category"], d["product_url"], d["affiliate_url"], d["extra_comm_proof"], d["commission_note"], d["price"], d["key_features"], d["source"], checked, now_text())
                    ); added += 1
            self.con.commit(); self.refresh_all()
            msg = f"นำเข้าสำเร็จ {added} รายการ\nข้ามรายการซ้ำ {skipped} รายการ"
            if errors: msg += "\nข้ามแถวข้อมูลไม่ครบ/ไม่ถูกต้อง: " + ", ".join(errors[:30])
            messagebox.showinfo("นำเข้า CSV", msg)
        except Exception as exc: messagebox.showerror("นำเข้าไม่สำเร็จ", str(exc))

    def export_products(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")], initialfile="affiliate_products.csv")
        if not path: return
        rows = self.con.execute("SELECT name,category,product_url,affiliate_url,extra_comm_proof,commission_note,price,key_features,source,checked_date FROM products ORDER BY id").fetchall()
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh); writer.writerow(CSV_FIELDS)
            for row in rows: writer.writerow(list(row))
        self.status_var.set(f"ส่งออกสินค้าแล้ว: {path}")

    def delete_product(self):
        product = self._selected_product()
        if not product: messagebox.showwarning("เลือกสินค้า", "เลือกสินค้าที่ต้องการลบก่อน"); return
        has_jobs = self.con.execute("SELECT COUNT(*) n FROM jobs WHERE product_id=?", (product["id"],)).fetchone()["n"]
        if has_jobs:
            messagebox.showwarning("ลบไม่ได้", f"สินค้านี้มีงานที่ผูกอยู่ {has_jobs} งาน เพื่อรักษาประวัติ กรุณาเก็บสินค้าไว้หรือจัดการงานก่อน"); return
        if messagebox.askyesno("ยืนยัน", f"ลบสินค้า {product['name']} ?"):
            self.con.execute("DELETE FROM products WHERE id=?", (product["id"],)); self.con.commit(); self.refresh_all()

    def _copy(self, text: str):
        self.clipboard_clear(); self.clipboard_append(text or ""); self.update()
        self.status_var.set("คัดลอกข้อความแล้ว")

    def show_job(self):
        job = self._selected_job()
        if not job: messagebox.showwarning("เลือกงาน", "เลือกงานในคิวก่อน"); return
        win = tk.Toplevel(self); win.title(f"งาน #{job['id']} — {job['name']}"); win.geometry("850x760"); win.configure(bg="#101722")
        ttk.Label(win, text=f"สินค้า: {job['name']}", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=14, pady=10)
        ttk.Label(win, text=f"Extra Comm ที่บันทึก: {job['commission_note']}  |  Link: {job['affiliate_url']}", wraplength=810).pack(anchor="w", padx=14)
        sections = [("บทรีวิว", job["script"]), ("แคปชัน", job["caption"]), ("Hashtag", job["hashtags"]), ("Prompt สำหรับ Meta AI", job["meta_prompt"])]
        for title, content in sections:
            row = ttk.Frame(win); row.pack(fill="x", padx=14, pady=(10, 2))
            ttk.Label(row, text=title, font=("Segoe UI", 10, "bold")).pack(side="left")
            ttk.Button(row, text="คัดลอก", command=lambda x=content: self._copy(x)).pack(side="right")
            widget = tk.Text(win, height=4 if title != "Prompt สำหรับ Meta AI" else 5, wrap="word", bg="#1c2838", fg="#e8edf5", insertbackground="white", relief="flat")
            widget.pack(fill="x", padx=14); widget.insert("1.0", content); widget.configure(state="disabled")
        footer = ttk.Frame(win); footer.pack(fill="x", padx=14, pady=12)
        ttk.Button(footer, text="คัดลอก Prompt และเปิด Meta AI", command=lambda: (self._copy(job["meta_prompt"]), webbrowser.open(META_AI_URL))).pack(side="left", padx=3)
        ttk.Button(footer, text="เปิดหน้าสินค้า", command=lambda: webbrowser.open(job["product_url"] or job["affiliate_url"])).pack(side="left", padx=3)
        ttk.Label(win, text="ข้อความเป็นร่างจากข้อมูลที่บันทึก ต้องตรวจสอบความจริงก่อนนำไปเผยแพร่", foreground="#f3c969").pack(anchor="w", padx=14, pady=5)

    def attach_video(self):
        job = self._selected_job()
        if not job: messagebox.showwarning("เลือกงาน", "เลือกงานในคิวก่อน"); return
        path = filedialog.askopenfilename(title="เลือกวิดีโอที่ดาวน์โหลดจาก Meta AI", filetypes=[("Video files", "*.mp4 *.mov *.webm *.mkv"), ("All files", "*.*")])
        if not path: return
        src = Path(path)
        if not src.is_file() or src.suffix.lower() not in {".mp4", ".mov", ".webm", ".mkv"}:
            messagebox.showerror("ไฟล์ไม่รองรับ", "เลือกไฟล์วิดีโอ MP4, MOV, WEBM หรือ MKV"); return
        dest = MEDIA_DIR / f"job_{job['id']}{src.suffix.lower()}"
        try:
            if src.resolve() != dest.resolve(): shutil.copy2(src, dest)
            self.con.execute("UPDATE jobs SET video_path=?,status='มีวิดีโอแล้ว - รอเตรียมโพสต์',updated_at=? WHERE id=?", (str(dest), now_text(), job["id"]))
            self.con.commit(); self.refresh_all(); messagebox.showinfo("แนบวิดีโอแล้ว", f"เก็บสำเนาไว้ที่\n{dest}")
        except Exception as exc: messagebox.showerror("แนบไฟล์ไม่สำเร็จ", str(exc))

    def export_post_kit(self):
        job = self._selected_job()
        if not job: messagebox.showwarning("เลือกงาน", "เลือกงานในคิวก่อน"); return
        if not job["video_path"] or not Path(job["video_path"]).is_file():
            messagebox.showwarning("ยังไม่มีวิดีโอ", "แนบวิดีโอจาก Meta AI ก่อนสร้างชุดโพสต์"); return
        folder = POST_KITS_DIR / f"job_{job['id']}_{safe_filename(job['name'])}"
        folder.mkdir(parents=True, exist_ok=True)
        video = Path(job["video_path"])
        dest_video = folder / ("video" + video.suffix.lower())
        if video.resolve() != dest_video.resolve(): shutil.copy2(video, dest_video)
        text = (
            f"สินค้า: {job['name']}\nหมวดหมู่: {job['category']}\n"
            f"Extra Comm ที่ผู้ใช้บันทึก: {job['commission_note']}\n"
            f"Affiliate Link: {job['affiliate_url']}\n\n"
            f"CAPTION\n{job['caption']}\n\nHASHTAGS\n{job['hashtags']}\n\n"
            f"SCRIPT\n{job['script']}\n\n"
            "ก่อนโพสต์: ตรวจสอบว่า Extra Comm ยังมีผล, สินค้าตรงกับคลิป, ราคา/โปรโมชันเป็นปัจจุบัน และเปิดเผยความสัมพันธ์ Affiliate ตามข้อกำหนด"
        )
        (folder / "post_text.txt").write_text(text, encoding="utf-8")
        self.status_var.set(f"สร้างชุดโพสต์แล้ว: {folder}")
        messagebox.showinfo("สร้างชุดโพสต์แล้ว", f"ไฟล์วิดีโอและข้อความอยู่ที่\n{folder}")
        self._open_path(folder)

    def _open_path(self, path: Path):
        try:
            if sys.platform == "win32": os.startfile(str(path))
            elif sys.platform == "darwin": subprocess.Popen(["open", str(path)])
            else: subprocess.Popen(["xdg-open", str(path)])
        except Exception: pass

    def mark_published(self):
        job = self._selected_job()
        if not job: messagebox.showwarning("เลือกงาน", "เลือกงานก่อน"); return
        if not job["video_path"] or not Path(job["video_path"]).is_file():
            messagebox.showwarning("ยังไม่มีวิดีโอ", "ต้องแนบวิดีโอก่อนบันทึกการโพสต์"); return
        win = tk.Toplevel(self); win.title("บันทึกการเผยแพร่"); win.geometry("620x250"); win.configure(bg="#101722")
        ttk.Label(win, text="URL โพสต์ Shopee Video (ถ้ามี)").pack(anchor="w", padx=14, pady=(14, 4))
        url_var = tk.StringVar(); ttk.Entry(win, textvariable=url_var, width=85).pack(fill="x", padx=14)
        ttk.Label(win, text="หมายเหตุ / รหัสอ้างอิง (ถ้ามี)").pack(anchor="w", padx=14, pady=(10, 4))
        note_var = tk.StringVar(); ttk.Entry(win, textvariable=note_var, width=85).pack(fill="x", padx=14)
        ttk.Label(win, text="บันทึกนี้เป็นการยืนยันโดยผู้ใช้ว่าได้โพสต์จริงแล้ว", foreground="#f3c969").pack(anchor="w", padx=14, pady=10)
        def save():
            if not messagebox.askyesno("ยืนยัน", "คุณเผยแพร่วิดีโอนี้บน Shopee Video แล้วจริงหรือไม่?", parent=win): return
            self.con.execute("UPDATE jobs SET status='โพสต์แล้ว (ยืนยันโดยผู้ใช้)',publish_url=?,posted_at=?,notes=?,updated_at=? WHERE id=?", (url_var.get().strip(), now_text(), note_var.get().strip(), now_text(), job["id"]))
            self.con.commit(); win.destroy(); self.refresh_all()
        ttk.Button(win, text="ยืนยันและบันทึก", command=save).pack(anchor="e", padx=14, pady=8)

    def export_jobs(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")], initialfile="publishing_queue.csv")
        if not path: return
        rows = self.con.execute("SELECT jobs.*,products.name,products.affiliate_url FROM jobs JOIN products ON products.id=jobs.product_id ORDER BY jobs.work_date,jobs.id").fetchall()
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh); writer.writerow(["job_id", "date", "product", "affiliate_url", "style", "script", "caption", "hashtags", "meta_prompt", "video_path", "status", "publish_url"])
            for r in rows: writer.writerow([r["id"], r["work_date"], r["name"], r["affiliate_url"], r["style"], r["script"], r["caption"], r["hashtags"], r["meta_prompt"], r["video_path"], r["status"], r["publish_url"]])
        self.status_var.set(f"ส่งออกคิวแล้ว: {path}")

    def backup(self):
        path = filedialog.asksaveasfilename(defaultextension=".db", filetypes=[("SQLite database", "*.db")], initialfile="affiliate_autopilot_backup.db")
        if not path: return
        try:
            self.con.commit(); shutil.copy2(DB_PATH, path); messagebox.showinfo("สำรองข้อมูลแล้ว", path)
        except Exception as exc: messagebox.showerror("สำรองไม่สำเร็จ", str(exc))

    def refresh_all(self):
        counts = {
            "products": self.con.execute("SELECT COUNT(*) n FROM products WHERE active=1").fetchone()["n"],
            "proof": self.con.execute("SELECT COUNT(*) n FROM products WHERE active=1 AND extra_comm_proof<>''").fetchone()["n"],
            "today": self.con.execute("SELECT COUNT(*) n FROM jobs WHERE work_date=?", (date.today().isoformat(),)).fetchone()["n"],
            "video": self.con.execute("SELECT COUNT(*) n FROM jobs WHERE video_path IS NOT NULL AND video_path<>''").fetchone()["n"],
            "posted": self.con.execute("SELECT COUNT(*) n FROM jobs WHERE status LIKE 'โพสต์แล้ว%'").fetchone()["n"]
        }
        for key, value in counts.items(): self.stats[key].configure(text=str(value))
        for tree in (self.ptree, self.jtree, self.recent):
            for item in tree.get_children(): tree.delete(item)
        for p in self.con.execute("SELECT * FROM products WHERE active=1 ORDER BY id DESC"):
            self.ptree.insert("", "end", values=(p["id"], p["name"], p["category"], p["commission_note"], "มีข้อมูล" if p["extra_comm_proof"] else "ไม่มี", p["affiliate_url"]))
        rows = self.con.execute("SELECT jobs.*,products.name FROM jobs JOIN products ON products.id=jobs.product_id ORDER BY jobs.work_date DESC,jobs.id DESC").fetchall()
        for j in rows:
            video_name = Path(j["video_path"]).name if j["video_path"] else "-"
            self.jtree.insert("", "end", values=(j["id"], j["work_date"], j["name"], j["style"], j["status"], video_name))
            if len(self.recent.get_children()) < 15:
                self.recent.insert("", "end", values=(j["work_date"], j["name"], j["style"], j["status"]))

    def on_close(self):
        try: self.con.commit(); self.con.close()
        finally: self.destroy()


def run_self_test():
    """Small non-GUI smoke test for core functions and SQLite schema."""
    import tempfile
    assert valid_affiliate("https://s.shopee.co.th/abc123")
    assert not valid_affiliate("https://shopee.co.th/product")
    assert not valid_affiliate("http://s.shopee.co.th/abc")
    with tempfile.TemporaryDirectory() as tmp:
        dbfile = Path(tmp) / "test.db"
        con = sqlite3.connect(dbfile); con.row_factory = sqlite3.Row; con.executescript(SCHEMA)
        stamp = now_text()
        con.execute("INSERT INTO products(name,affiliate_url,extra_comm_proof,commission_note,created_at) VALUES(?,?,?,?,?)", ("Test item", "https://s.shopee.co.th/test", "proof", "Extra Comm 5%", stamp))
        p = con.execute("SELECT * FROM products").fetchone()
        script, caption, tags, prompt = build_content(p, "Influencer รีวิว", 0)
        assert all(x.strip() for x in (script, caption, tags, prompt))
        con.execute("INSERT INTO jobs(product_id,work_date,style,script,caption,hashtags,meta_prompt,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (p["id"], date.today().isoformat(), "Influencer รีวิว", script, caption, tags, prompt, stamp, stamp))
        assert con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1
        con.close()
    return "PASS: affiliate URL validation, content draft generation, SQLite schema and job insert"


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        print(run_self_test())
    else:
        try: AutoPilot().mainloop()
        except Exception as exc:
            try: messagebox.showerror("Application error", str(exc))
            except Exception: print(exc)
