# -*- coding: utf-8 -*-
"""Secure LAN companion for Shopee Affiliate AutoPilot (stdlib only)."""
from __future__ import annotations
import hashlib, hmac, json, mimetypes, os, secrets, socket, sqlite3, sys, threading, time, urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DB=ROOT/"affiliate_autopilot.db"
MEDIA=ROOT/"media"
CONFIG_FILE=ROOT/"mobile_hub_config.json"
HOST="0.0.0.0"
PORT=int(os.environ.get("SHOPEE_HUB_PORT","8765"))
MAX_UPLOAD=int(os.environ.get("SHOPEE_HUB_MAX_UPLOAD",str(500*1024*1024)))
TTL=12*60*60
SESSIONS={}
LOGIN_ATTEMPTS={}
LOCK=threading.Lock()
SCHEMA="""
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS products (
 id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,category TEXT,product_url TEXT,
 affiliate_url TEXT NOT NULL,extra_comm_proof TEXT NOT NULL,commission_note TEXT NOT NULL,
 price TEXT,key_features TEXT,source TEXT,checked_date TEXT,created_at TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS jobs (
 id INTEGER PRIMARY KEY AUTOINCREMENT,product_id INTEGER NOT NULL,work_date TEXT NOT NULL,
 style TEXT NOT NULL,script TEXT NOT NULL,caption TEXT NOT NULL,hashtags TEXT NOT NULL,
 meta_prompt TEXT NOT NULL,video_path TEXT,status TEXT NOT NULL DEFAULT 'รอสร้างวิดีโอ',
 publish_url TEXT,posted_at TEXT,notes TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
 FOREIGN KEY(product_id) REFERENCES products(id));
CREATE INDEX IF NOT EXISTS idx_jobs_date ON jobs(work_date);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
"""
def now(): return datetime.now().isoformat(timespec="seconds")
def connect():
 c=sqlite3.connect(DB,timeout=20); c.row_factory=sqlite3.Row
 c.execute("PRAGMA foreign_keys=ON"); c.execute("PRAGMA busy_timeout=20000"); c.executescript(SCHEMA); return c
def init_config():
 MEDIA.mkdir(exist_ok=True)
 if CONFIG_FILE.exists():
  x=json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
  if not isinstance(x,dict) or not x.get("salt") or not x.get("hash"): raise RuntimeError("mobile_hub_config.json ไม่ถูกต้อง")
  return x,None
 pin=f"{secrets.randbelow(100000000):08d}"; salt=secrets.token_bytes(16)
 digest=hashlib.pbkdf2_hmac("sha256",pin.encode(),salt,240000)
 x={"salt":salt.hex(),"hash":digest.hex(),"created_at":now()}
 tmp=CONFIG_FILE.with_suffix(".tmp"); tmp.write_text(json.dumps(x,indent=2),encoding="utf-8"); os.replace(tmp,CONFIG_FILE)
 try: os.chmod(CONFIG_FILE,0o600)
 except OSError: pass
 return x,pin
CONFIG,FIRST_PIN=init_config()
def verify(pin):
 try:
  d=hashlib.pbkdf2_hmac("sha256",pin.encode(),bytes.fromhex(CONFIG["salt"]),240000)
  return hmac.compare_digest(d,bytes.fromhex(CONFIG["hash"]))
 except Exception: return False
def media_path(v):
 try:
  p=Path(v).resolve(); root=MEDIA.resolve()
  return p if root in p.parents and p.is_file() else None
 except Exception: return None

LOGIN="""<!doctype html><html lang=th><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Affiliate Hub Login</title><style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0b1220;color:#eef;font:16px system-ui;padding:20px}.box{width:min(390px,100%);background:#17243a;padding:26px;border-radius:20px}input,button{width:100%;padding:14px;margin-top:12px;border-radius:10px;font:inherit}input{background:#0c1728;color:white;border:1px solid #456;text-align:center;letter-spacing:5px}button{background:#69adff;border:0;font-weight:bold}p{color:#9aabc2;line-height:1.5}#err{color:#ff9999}</style><main class=box><h2>Shopee Affiliate Mobile Hub</h2><p>กรอก PIN 8 หลักจากหน้าต่าง Mobile Hub บนคอมพิวเตอร์</p><form id=f><input id=pin maxlength=8 inputmode=numeric placeholder='PIN 8 หลัก' required><button>เข้าสู่ระบบ</button></form><p id=err></p></main><script>f.onsubmit=async e=>{e.preventDefault();try{let r=await fetch('/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin:pin.value})});let j=await r.json();if(j.ok)location.href='/';else err.textContent=j.error}catch(x){err.textContent=x}}</script>"""
APP="""<!doctype html><html lang=th><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><meta name=theme-color content=#101827><title>Affiliate Hub</title><style>
*{box-sizing:border-box}body{margin:0;background:#0b1220;color:#edf3ff;font:15px system-ui}header{position:sticky;top:0;background:#142137;padding:14px;display:flex;justify-content:space-between;align-items:center}main{max-width:850px;margin:auto;padding:14px}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.stat,.card{background:#17263d;border:1px solid #2b405e;border-radius:13px;padding:12px}.stat b{display:block;font-size:22px}.muted{color:#9badc5;font-size:13px}.tabs,.actions{display:flex;gap:7px;flex-wrap:wrap;margin:14px 0}button,a{background:#2b405e;color:#edf3ff;border:0;border-radius:9px;padding:10px 12px;text-decoration:none;font:inherit}button.primary{background:#6ab0ff;color:#081523;font-weight:bold}.search{width:100%;padding:12px;background:#0e192a;color:white;border:1px solid #40536e;border-radius:10px;margin:10px 0}.job{background:#17263d;border:1px solid #2b405e;border-radius:13px;padding:13px;margin:9px 0}.pill{color:#b9d8ff;font-size:12px}.detail{margin-top:14px}.field{margin:12px 0}.field label{display:block;color:#aabbd2;font-size:12px}.txt{white-space:pre-wrap;overflow-wrap:anywhere;background:#0c1728;padding:10px;border-radius:8px;max-height:180px;overflow:auto}.hide{display:none}.product{padding:12px;border-bottom:1px solid #345}#toast{position:fixed;bottom:15px;left:5%;width:90%;background:#eaf3ff;color:#123;padding:12px;border-radius:10px;display:none}@media(min-width:680px){.stats{grid-template-columns:repeat(5,1fr)}#jobs{display:grid;grid-template-columns:1fr 1fr;gap:8px}.detail{grid-column:1/-1}}</style>
<header><b>SHOPEE AFFILIATE HUB</b><div><button onclick=load()>รีเฟรช</button> <button onclick=logout()>ออกจากระบบ</button></div></header><main>
<div class=stats id=stats></div><nav class=tabs><button onclick="tab('jobs')">คิวงาน</button><button onclick="tab('products')">สินค้า</button><button onclick="tab('help')">วิธีใช้</button></nav>
<section id=jobsview><input id=q class=search placeholder='ค้นหาสินค้า / สถานะ / วันที่' oninput=renderJobs()><div id=jobs></div><div id=detail class='card detail hide'></div></section>
<section id=productsview class=hide><input id=pq class=search placeholder='ค้นหาสินค้า' oninput=renderProducts()><div id=products class=card></div></section>
<section id=helpview class='card hide'><h3>วิธีใช้งาน PC ↔ Android</h3><ol><li>คอมและมือถือใช้ Wi-Fi วงเดียวกัน</li><li>เปิด START.bat บนคอม</li><li>เปิด URL ที่แสดงในหน้าต่างคอมด้วย Chrome มือถือ</li><li>กรอก PIN 8 หลัก</li><li>เลือกงานเพื่อคัดลอก Caption/Hashtag/ลิงก์ หรืออัปโหลดและดาวน์โหลดวิดีโอ</li><li>โพสต์ผ่านแอป Shopee ด้วยตนเองและเลือกสินค้าที่ตรงกัน</li></ol><p class=muted>ระบบนี้ไม่ตรวจ Extra Comm สด ไม่ scrape Shopee และไม่โพสต์แทนคุณ ใช้เฉพาะ Wi-Fi ที่เชื่อถือได้</p></section></main><div id=toast></div>
<script>
let J=[],P=[],CS='';const E=id=>document.getElementById(id);
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function note(s){E('toast').textContent=s;E('toast').style.display='block';setTimeout(()=>E('toast').style.display='none',2500)}
async function api(u,o={}){o.headers=Object.assign({},o.headers||{}, {'X-CSRF-Token':CS});let r=await fetch(u,o);if(r.status===401){location='/login-page';throw Error('หมดเวลาใช้งาน')}let j=await r.json().catch(()=>({}));if(!r.ok)throw Error(j.error||'ผิดพลาด');return j}
async function load(){try{let a=await Promise.all([api('/api/summary'),api('/api/jobs'),api('/api/products')]);CS=a[0].csrf;J=a[1].jobs;P=a[2].products;let c=a[0].counts;E('stats').innerHTML=[['สินค้า',c.products],['งานทั้งหมด',c.jobs],['รอทำ',c.pending],['มีวิดีโอ',c.videos],['โพสต์แล้ว',c.posted]].map(x=>'<div class=stat><b>'+x[1]+'</b><span class=muted>'+x[0]+'</span></div>').join('');renderJobs();renderProducts()}catch(e){note(e.message)}}
function tab(t){['jobs','products','help'].forEach(x=>{E(x+'view').classList.toggle('hide',x!==t)})}
function renderJobs(){let q=E('q').value.toLowerCase();E('jobs').innerHTML=J.filter(x=>(x.name+' '+x.status+' '+x.work_date).toLowerCase().includes(q)).map(x=>'<article class=job><div class=pill>#'+x.id+' · '+esc(x.work_date)+'</div><b>'+esc(x.name)+'</b><div class=muted>'+esc(x.style)+' · '+esc(x.status)+'</div><div class=actions><button class=primary onclick="showJob('+x.id+')">เปิดงาน</button>'+(x.has_video?'<a href=/api/video/'+x.id+'>ดาวน์โหลดวิดีโอ</a>':'')+'</div></article>').join('')||'<div class=card>ไม่พบงาน</div>'}
function renderProducts(){let q=E('pq').value.toLowerCase();E('products').innerHTML=P.filter(x=>(x.name+' '+x.category).toLowerCase().includes(q)).map(x=>'<div class=product><b>'+esc(x.name)+'</b><div class=muted>'+esc(x.category)+' · '+esc(x.commission_note)+'</div><button class=copybtn data-copy="'+esc(x.affiliate_url)+'">คัดลอก Affiliate Link</button></div>').join('')||'ไม่มีสินค้า';E('products').querySelectorAll('.copybtn').forEach(b=>b.onclick=()=>copy(b.dataset.copy))}
async function copy(s){try{if(navigator.clipboard&&window.isSecureContext){await navigator.clipboard.writeText(s);note('คัดลอกแล้ว');return}}catch(e){}let t=document.createElement('textarea');t.value=s;t.style.position='fixed';t.style.opacity='0';document.body.appendChild(t);t.select();let ok=false;try{ok=document.execCommand('copy')}catch(e){}t.remove();note(ok?'คัดลอกแล้ว':'คัดลอกไม่ได้: แตะค้างที่ข้อความแล้วเลือกคัดลอก')}
function field(label,v){return '<div class=field><label>'+label+'</label><div class=txt>'+esc(v)+'</div><button class=copybtn data-copy="'+esc(v||'')+'">คัดลอก</button></div>'}
function hideDetail(){E('detail').classList.add('hide')}
function showJob(id){let x=J.find(z=>z.id===id);if(!x)return;let d=E('detail');d.classList.remove('hide');d.innerHTML='<button onclick=hideDetail()>ปิด</button><h3>งาน #'+id+' · '+esc(x.name)+'</h3>'+field('Affiliate Link',x.affiliate_url)+field('บทรีวิว',x.script)+field('Caption',x.caption)+field('Hashtag',x.hashtags)+field('Prompt Meta AI',x.meta_prompt)+'<div class=field><label>อัปโหลดวิดีโอจากมือถือ (สูงสุด 500 MB)</label><input id=file type=file accept=.mp4,.mov,.webm,.mkv><button class=primary onclick="upload('+id+')">ส่งวิดีโอไปยังคอม</button>'+(x.has_video?' <a href=/api/video/'+id+'>ดาวน์โหลดวิดีโอ</a>':'')+'</div><div class=field><label>URL โพสต์ (ถ้ามี)</label><input id=posturl class=search value="'+esc(x.publish_url||'')+'"><button class=primary onclick="posted('+id+')">ยืนยันว่าโพสต์แล้ว</button></div>';d.querySelectorAll('.copybtn').forEach(b=>b.onclick=()=>copy(b.dataset.copy));d.scrollIntoView({behavior:'smooth'})}
async function upload(id){let f=E('file').files[0];if(!f)return note('เลือกวิดีโอก่อน');if(f.size>500*1024*1024)return note('ไฟล์ใหญ่เกิน 500 MB');if(!confirm('อัปโหลด '+f.name+' ไปยังคอม?'))return;try{await api('/api/jobs/'+id+'/video?filename='+encodeURIComponent(f.name),{method:'PUT',headers:{'Content-Type':'application/octet-stream','X-CSRF-Token':CS},body:f});note('อัปโหลดสำเร็จ');await load();showJob(id)}catch(e){note(e.message)}}
async function posted(id){if(!confirm('คุณโพสต์วิดีโอนี้ใน Shopee แล้วจริงหรือไม่?'))return;try{await api('/api/jobs/'+id+'/posted',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({publish_url:E('posturl').value})});note('บันทึกแล้ว');await load();showJob(id)}catch(e){note(e.message)}}
async function logout(){try{await api('/logout',{method:'POST'})}finally{location='/login-page'}}load();
</script>"""

class Handler(BaseHTTPRequestHandler):
 server_version="AffiliateHub/1.0"
 def log_message(self,fmt,*args): print("[Hub] "+fmt%args)
 def reply(self,status,data,ctype="application/json; charset=utf-8",headers=None):
  body=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode()
  self.send_response(status);self.send_header("Content-Type",ctype);self.send_header("Content-Length",str(len(body)))
  self.send_header("X-Content-Type-Options","nosniff");self.send_header("Cache-Control","no-store")
  for k,v in (headers or {}).items():self.send_header(k,v)
  self.end_headers()
  if body:self.wfile.write(body)
 def read_json(self):
  n=int(self.headers.get("Content-Length","0"))
  if n<0 or n>64000:raise ValueError("ข้อมูลไม่ถูกต้อง")
  return json.loads(self.rfile.read(n) or b"{}")
 def auth(self):
  token=""
  for p in self.headers.get("Cookie","").split(";"):
   k,sep,v=p.strip().partition("=")
   if sep and k=="affiliate_hub":token=v
  with LOCK:
   item=SESSIONS.get(token)
   if not item:return None
   exp,csrf=item
   if exp<time.time():SESSIONS.pop(token,None);return None
   return csrf
 def secure(self):
  csrf=self.auth()
  if not csrf:self.reply(401,{"error":"กรุณาเข้าสู่ระบบ"});return False
  if self.command in ("POST","PUT","DELETE"):
   origin=self.headers.get("Origin")
   if origin:
    u=urllib.parse.urlsplit(origin)
    if u.netloc.lower()!=self.headers.get("Host","").lower():self.reply(403,{"error":"Origin ไม่ถูกต้อง"});return False
   if not hmac.compare_digest(self.headers.get("X-CSRF-Token",""),csrf):self.reply(403,{"error":"CSRF token ไม่ถูกต้อง"});return False
  self.csrf=csrf;return True
 def do_GET(self):
  path=urllib.parse.urlsplit(self.path).path
  if path=="/login-page":return self.reply(200,LOGIN,"text/html; charset=utf-8")
  if path=="/":
   if not self.auth():return self.reply(302,b"","text/plain",{"Location":"/login-page"})
   return self.reply(200,APP,"text/html; charset=utf-8")
  if not self.secure():return
  if path=="/api/summary":
   with connect() as c:
    counts={"products":c.execute("select count(*) from products where active=1").fetchone()[0],"jobs":c.execute("select count(*) from jobs").fetchone()[0],"pending":c.execute("select count(*) from jobs where status not like 'โพสต์แล้ว%'").fetchone()[0],"videos":c.execute("select count(*) from jobs where video_path is not null and video_path<>''").fetchone()[0],"posted":c.execute("select count(*) from jobs where status like 'โพสต์แล้ว%'").fetchone()[0]}
   return self.reply(200,{"counts":counts,"csrf":self.csrf})
  if path=="/api/jobs":
   with connect() as c:rows=c.execute("select j.id,j.work_date,j.style,j.status,j.script,j.caption,j.hashtags,j.meta_prompt,j.publish_url,j.video_path,p.name,p.affiliate_url,p.product_url from jobs j join products p on p.id=j.product_id order by j.work_date desc,j.id desc limit 1000").fetchall()
   out=[]
   for r in rows:
    x=dict(r);x["has_video"]=bool(media_path(x.pop("video_path",None)));out.append(x)
   return self.reply(200,{"jobs":out})
  if path=="/api/products":
   with connect() as c:rows=c.execute("select id,name,category,affiliate_url,product_url,commission_note,checked_date from products where active=1 order by id desc limit 2000").fetchall()
   return self.reply(200,{"products":[dict(r) for r in rows]})
  if path.startswith("/api/video/"):
   try:jid=int(path.rsplit("/",1)[1])
   except ValueError:return self.reply(400,{"error":"ID ไม่ถูกต้อง"})
   with connect() as c:r=c.execute("select video_path from jobs where id=?",(jid,)).fetchone()
   p=media_path(r["video_path"] if r else None)
   if not p:return self.reply(404,{"error":"ไม่พบวิดีโอ"})
   self.send_response(200)
   self.send_header("Content-Type",mimetypes.guess_type(p.name)[0] or "application/octet-stream")
   self.send_header("Content-Length",str(p.stat().st_size))
   self.send_header("Content-Disposition",f'attachment; filename="{p.name}"')
   self.send_header("X-Content-Type-Options","nosniff")
   self.send_header("Cache-Control","no-store")
   self.end_headers()
   with p.open("rb") as fh:
    while True:
     chunk=fh.read(1024*1024)
     if not chunk:break
     self.wfile.write(chunk)
   return
  return self.reply(404,{"error":"ไม่พบหน้า"})
 def do_POST(self):
  path=urllib.parse.urlsplit(self.path).path
  if path=="/login":
   try:pin=str(self.read_json().get("pin",""))
   except Exception:return self.reply(400,{"ok":False,"error":"ข้อมูลไม่ถูกต้อง"})
   ip=self.client_address[0];ts=time.time()
   with LOCK:
    attempts=[t for t in LOGIN_ATTEMPTS.get(ip,[]) if ts-t<300]
    if len(attempts)>=8:return self.reply(429,{"ok":False,"error":"ลอง PIN ผิดหลายครั้ง กรุณารอ 5 นาที"})
   if len(pin)!=8 or not pin.isdigit() or not verify(pin):
    with LOCK:LOGIN_ATTEMPTS[ip]=attempts+[ts]
    time.sleep(.5);return self.reply(401,{"ok":False,"error":"PIN ไม่ถูกต้อง"})
   with LOCK:LOGIN_ATTEMPTS.pop(ip,None)
   token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(24)
   with LOCK:SESSIONS[token]=(time.time()+TTL,csrf)
   return self.reply(200,{"ok":True},headers={"Set-Cookie":f"affiliate_hub={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={TTL}"})
  if not self.secure():return
  if path=="/logout":
   token=next((p.strip().split("=",1)[1] for p in self.headers.get("Cookie","").split(";") if p.strip().startswith("affiliate_hub=")),"")
   with LOCK:SESSIONS.pop(token,None)
   return self.reply(200,{"ok":True},headers={"Set-Cookie":"affiliate_hub=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"})
  if path.startswith("/api/jobs/") and path.endswith("/posted"):
   try:
    jid=int(path.split("/")[3]);url=str(self.read_json().get("publish_url","")).strip()
    if len(url)>2000 or (url and not url.startswith("https://")):return self.reply(400,{"error":"URL ต้องเป็น HTTPS"})
    with connect() as c:
     r=c.execute("select video_path from jobs where id=?",(jid,)).fetchone()
     if not r:return self.reply(404,{"error":"ไม่พบงาน"})
     if not media_path(r["video_path"]):return self.reply(409,{"error":"ต้องแนบวิดีโอก่อน"})
     c.execute("update jobs set status=?,publish_url=?,posted_at=?,updated_at=? where id=?",("โพสต์แล้ว (ยืนยันโดยผู้ใช้)",url,now(),now(),jid))
    return self.reply(200,{"ok":True})
   except Exception as e:return self.reply(400,{"error":str(e)})
  return self.reply(404,{"error":"ไม่พบหน้า"})
 def do_PUT(self):
  if not self.secure():return
  u=urllib.parse.urlsplit(self.path)
  if not u.path.startswith("/api/jobs/") or not u.path.endswith("/video"):return self.reply(404,{"error":"ไม่พบหน้า"})
  try:jid=int(u.path.split("/")[3])
  except ValueError:return self.reply(400,{"error":"ID ไม่ถูกต้อง"})
  n=int(self.headers.get("Content-Length","-1"))
  if n<=0 or n>MAX_UPLOAD:return self.reply(413,{"error":f"ไฟล์ต้องไม่เกิน {MAX_UPLOAD//1048576} MB"})
  filename=Path(urllib.parse.parse_qs(u.query).get("filename",["video.mp4"])[0]).name
  ext=Path(filename).suffix.lower()
  if ext not in (".mp4",".mov",".webm",".mkv"):return self.reply(415,{"error":"รองรับ MP4, MOV, WEBM, MKV"})
  with connect() as c:
   if not c.execute("select 1 from jobs where id=?",(jid,)).fetchone():return self.reply(404,{"error":"ไม่พบงาน"})
  dest=MEDIA/f"job_{jid}{ext}";tmp=MEDIA/f".{jid}_{secrets.token_hex(5)}.tmp"
  try:
   remain=n
   with tmp.open("wb") as f:
    while remain:
     b=self.rfile.read(min(remain,1024*1024))
     if not b:raise IOError("อัปโหลดไม่ครบ")
     f.write(b);remain-=len(b)
    f.flush();os.fsync(f.fileno())
   if tmp.stat().st_size!=n:raise IOError("ขนาดไฟล์ไม่ตรง")
   os.replace(tmp,dest)
   with connect() as c:c.execute("update jobs set video_path=?,status=?,updated_at=? where id=?",(str(dest),"มีวิดีโอแล้ว - รอเตรียมโพสต์",now(),jid))
   return self.reply(200,{"ok":True,"bytes":n,"filename":dest.name})
  except Exception as e:
   try:tmp.unlink(missing_ok=True)
   except OSError:pass
   return self.reply(500,{"error":"บันทึกไฟล์ไม่สำเร็จ: "+str(e)})

def ips():
 out=set()
 try:
  s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(("192.0.2.1",80));out.add(s.getsockname()[0]);s.close()
 except OSError:pass
 try:
  for x in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET):
   if not x[4][0].startswith("127."):out.add(x[4][0])
 except OSError:pass
 return sorted(out)
def main():
 srv=ThreadingHTTPServer((HOST,PORT),Handler);srv.daemon_threads=True
 print("\\n"+"="*58+"\\n SHOPEE AFFILIATE MOBILE HUB\\n"+"="*58)
 for ip in ips():print(f" มือถือเปิด: http://{ip}:{PORT}")
 print(" PIN:",FIRST_PIN if FIRST_PIN else "(ใช้ PIN เดิมจากครั้งแรก)")
 if FIRST_PIN:print(" จด PIN นี้ไว้ ระบบจะไม่แสดงซ้ำ")
 print(" Ctrl+C เพื่อปิด Mobile Hub\\n"+"="*58)
 try:srv.serve_forever()
 except KeyboardInterrupt:print("ปิด Mobile Hub แล้ว")
 finally:srv.server_close()
if __name__=="__main__":
 try:main()
 except OSError as e:print("เปิด Mobile Hub ไม่สำเร็จ:",e);input("กด Enter เพื่อปิด...")
