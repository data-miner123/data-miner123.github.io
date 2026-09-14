#!/usr/bin/env python3
"""Small self-hosted group website. Python 3.10+, standard library only."""
import argparse, base64, binascii, getpass, hashlib, hmac, json, mimetypes, os, re, secrets, sqlite3, subprocess, threading, time
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
MAX_FILE, MAX_LITERATURE_FILE, MAX_REQUEST, SESSION_DAYS = 5*1024*1024, 20*1024*1024, 40*1024*1024, 7
EXTENSIONS = {'.pdf','.md','.txt','.docx','.pptx','.xlsx','.png','.jpg','.jpeg'}
PUBLICATION_IMAGE_EXTENSIONS = {'.png','.jpg','.jpeg','.webp'}
USERNAME_RE = re.compile(r'^[A-Za-z0-9_.-]{3,32}$')
DB_PATH = ROOT/'data'/'vis-group.sqlite3'
PUBLICATIONS_PATH = ROOT/'publications.json'
PUBLICATION_ASSETS = ROOT/'publication-assets'
SECURE_COOKIE = os.environ.get('VIS_SECURE_COOKIE') == '1'
LOGIN_ATTEMPTS = {}
SITE_LOCK = threading.Lock()
PUBLICATION_LOCK = threading.Lock()

def now_iso(): return datetime.now(timezone.utc).isoformat()

def connect():
    db=sqlite3.connect(DB_PATH,timeout=15); db.row_factory=sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON'); return db

def hash_password(password,salt=None):
    salt=salt or secrets.token_bytes(16)
    digest=hashlib.scrypt(password.encode(),salt=salt,n=2**14,r=8,p=1,dklen=32)
    return salt.hex(),digest.hex()

def valid_password(password,salt,digest):
    try: return hmac.compare_digest(hash_password(password,bytes.fromhex(salt))[1],digest)
    except (ValueError,UnicodeError): return False

def initialize(seed=True):
    DB_PATH.parent.mkdir(parents=True,exist_ok=True); db=connect()
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY,title TEXT NOT NULL,author TEXT NOT NULL,kind TEXT NOT NULL CHECK(kind IN ('daily','weekly')),date TEXT NOT NULL,summary TEXT NOT NULL,body TEXT NOT NULL,filename TEXT NOT NULL DEFAULT '',attachment BLOB,example INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,user_id TEXT REFERENCES users(id) ON DELETE SET NULL);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,username TEXT NOT NULL COLLATE NOCASE UNIQUE,display_name TEXT NOT NULL,password_salt TEXT NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('member','admin')),status TEXT NOT NULL CHECK(status IN ('pending','active','disabled')),created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,expires_at TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS literature(id TEXT PRIMARY KEY,title TEXT NOT NULL,authors TEXT NOT NULL,source TEXT NOT NULL DEFAULT '',year TEXT NOT NULL DEFAULT '',url TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',filename TEXT NOT NULL DEFAULT '',attachment BLOB,uploader TEXT NOT NULL,uploader_id TEXT REFERENCES users(id) ON DELETE SET NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS literature_comments(id TEXT PRIMARY KEY,literature_id TEXT NOT NULL REFERENCES literature(id) ON DELETE CASCADE,author TEXT NOT NULL,author_id TEXT REFERENCES users(id) ON DELETE SET NULL,body TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS publication_files(publication_id TEXT PRIMARY KEY,filename TEXT NOT NULL,attachment BLOB NOT NULL,uploader_id TEXT REFERENCES users(id) ON DELETE SET NULL,updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_reports_date ON reports(date DESC,created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
        CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_literature_created_at ON literature(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_literature_comments_item ON literature_comments(literature_id,created_at);''')
        cols={r['name'] for r in db.execute('PRAGMA table_info(reports)')}
        if 'user_id' not in cols: db.execute('ALTER TABLE reports ADD COLUMN user_id TEXT REFERENCES users(id) ON DELETE SET NULL')
        if not db.execute("SELECT 1 FROM settings WHERE key='initialized'").fetchone():
            if seed:
                examples=[('可视分析原型：交互流程与实验进展','成员 A','daily','2026-09-08','完成筛选与联动视图，梳理下一轮实验需要验证的问题。'),('文献阅读：人机协作中的可解释性','成员 B','daily','2026-09-08','整理三篇相关工作的研究问题、方法与实验设计。'),('第 36 周研究进展与下周计划','成员 A','weekly','2026-09-06','回顾本周原型迭代、数据处理与待解决的问题。'),('数据整理与可视化方案探索','成员 C','weekly','2026-09-05','完成第一版数据清洗，比较不同视觉编码的适用场景。')]
                for title,author,kind,day,summary in examples:
                    body=f'本条为示例报告。\n\n已完成\n{summary}\n\n遇到的问题\n需要进一步检查实验数据的完整性。\n\n下一步计划\n1. 整理结果。\n2. 完善实验方案。\n3. 在组会上交流。'
                    db.execute('INSERT INTO reports(id,title,author,kind,date,summary,body,filename,attachment,example,created_at,user_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(uuid4().hex,title,author,kind,day,summary,body,'',None,1,now_iso(),None))
            db.execute("INSERT INTO settings VALUES('initialized','1')")
        db.execute('DELETE FROM sessions WHERE expires_at<=?',(now_iso(),)); db.execute('PRAGMA optimize'); db.commit()
    finally: db.close()

def create_admin(username):
    if not USERNAME_RE.fullmatch(username): raise ValueError('账号须为 3–32 位英文字母、数字、点、下划线或连字符。')
    name=input('管理员显示姓名: ').strip()
    if not name or len(name)>60: raise ValueError('显示姓名不能为空，且不能超过 60 个字符。')
    password=getpass.getpass('管理员密码（至少 10 位）: ')
    if password!=getpass.getpass('再次输入密码: '): raise ValueError('两次密码不一致。')
    if not 10<=len(password)<=200: raise ValueError('密码长度须为 10–200 位。')
    salt,digest=hash_password(password); db=connect()
    try:
        with db: db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?,?)',(uuid4().hex,username,name,salt,digest,'admin','active',now_iso()))
    except sqlite3.IntegrityError as exc: raise ValueError('该账号已存在。') from exc
    finally: db.close()

def reset_password(username):
    password=getpass.getpass('新密码（至少 10 位）: ')
    if password!=getpass.getpass('再次输入新密码: '): raise ValueError('两次密码不一致。')
    if not 10<=len(password)<=200: raise ValueError('密码长度须为 10–200 位。')
    salt,digest=hash_password(password); db=connect()
    try:
        with db:
            changed=db.execute('UPDATE users SET password_salt=?,password_hash=? WHERE username=?',(salt,digest,username)).rowcount
            if not changed: raise ValueError('找不到这个网站账号。')
            db.execute('DELETE FROM sessions WHERE user_id=(SELECT id FROM users WHERE username=?)',(username,))
    finally: db.close()

class ApiError(Exception):
    def __init__(self,status,message): self.status,self.message=status,message; super().__init__(message)

def clean(data,key,maximum,required=True):
    value=data.get(key,'')
    if not isinstance(value,str): raise ApiError(400,'字段格式不正确。')
    value=value.strip()
    if (required and not value) or len(value)>maximum: raise ApiError(400,'请完整填写表单，并检查文字长度。')
    return value

def read_site():
    return json.loads((ROOT/'site.json').read_text(encoding='utf-8'))

def public_site():
    site=read_site()
    members=site.get('members',[])
    if isinstance(members,list):
        site['members']=[{key:value for key,value in member.items() if key!='user_id'} if isinstance(member,dict) else member for member in members]
    return site

def write_site(site):
    path=ROOT/'site.json'; temporary=path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(site,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    os.replace(temporary,path)

def clean_news(data):
    item={key:clean(data,key,maximum,key!='detail') for key,maximum in {'date':10,'title':120,'tag':30,'text':300,'detail':5000}.items()}
    try:
        if date.fromisoformat(item['date']).isoformat()!=item['date']: raise ValueError
    except ValueError: raise ApiError(400,'动态日期不正确。')
    return item

def clean_profile(data):
    return {key:clean(data,key,maximum,key in {'name','role'}) for key,maximum in {'name':60,'role':80,'area':300,'initial':10}.items()}

def read_publications():
    if not PUBLICATIONS_PATH.exists(): return []
    items=json.loads(PUBLICATIONS_PATH.read_text(encoding='utf-8'))
    if not isinstance(items,list) or not all(isinstance(item,dict) for item in items): raise ApiError(500,'成果数据文件格式不正确。')
    return items

def write_publications(items):
    temporary=PUBLICATIONS_PATH.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(items,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    os.replace(temporary,PUBLICATIONS_PATH)

def publications_with_files():
    items=read_publications(); db=connect()
    try: files={row['publication_id']:row['filename'] for row in db.execute('SELECT publication_id,filename FROM publication_files')}
    finally: db.close()
    return [{**item,'filename':files.get(item.get('id'),'')} for item in items]

def clean_publication(data):
    item={key:clean(data,key,maximum,key in {'title','authors','venue','year'}) for key,maximum in {'title':250,'authors':500,'venue':200,'year':4,'summary':1500,'url':1000,'image_alt':300}.items()}
    if not re.fullmatch(r'\d{4}',item['year']): raise ApiError(400,'成果年份应为 4 位数字。')
    if item['url']:
        parsed=urlsplit(item['url'])
        if parsed.scheme not in {'http','https'} or not parsed.netloc: raise ApiError(400,'论文链接必须是完整的 HTTP 或 HTTPS 地址。')
    item['image_alt']=item['image_alt'] or f"{item['title']} 的代表图"
    return item

def decode_publication_image(data):
    image=data.get('image')
    if not image: return '',None
    if not isinstance(image,dict) or not isinstance(image.get('name'),str) or not isinstance(image.get('data'),str): raise ApiError(400,'代表图格式不正确。')
    filename=image['name'].replace('\\','/').split('/')[-1]; extension=Path(filename).suffix.lower()
    if extension not in PUBLICATION_IMAGE_EXTENSIONS: raise ApiError(400,'代表图仅支持 JPG、PNG 或 WebP。')
    try: content=base64.b64decode(image['data'],validate=True)
    except binascii.Error: raise ApiError(400,'代表图内容不正确。')
    if not content or len(content)>MAX_FILE: raise ApiError(400,'代表图不能为空，且不能超过 5 MB。')
    detected=''
    if content.startswith(b'\x89PNG\r\n\x1a\n'): detected='.png'
    elif content.startswith(b'\xff\xd8\xff'): detected='.jpg'
    elif len(content)>=12 and content[:4]==b'RIFF' and content[8:12]==b'WEBP': detected='.webp'
    allowed_extensions={'.jpg','.jpeg'} if detected=='.jpg' else {detected}
    if not detected or extension not in allowed_extensions: raise ApiError(400,'代表图扩展名与实际文件类型不一致。')
    return detected,content

def decode_publication_paper(data):
    paper=data.get('paper')
    if not paper: return '',None
    if not isinstance(paper,dict) or not isinstance(paper.get('name'),str) or not isinstance(paper.get('data'),str): raise ApiError(400,'论文文件格式不正确。')
    filename=paper['name'].replace('\\','/').split('/')[-1]
    if not filename or len(filename)>180 or any(ord(c)<32 for c in filename) or Path(filename).suffix.lower()!='.pdf': raise ApiError(400,'论文文件仅支持 PDF。')
    try: attachment=base64.b64decode(paper['data'],validate=True)
    except binascii.Error: raise ApiError(400,'论文文件内容不正确。')
    if not attachment or len(attachment)>MAX_LITERATURE_FILE: raise ApiError(400,'论文 PDF 不能为空，且不能超过 20 MB。')
    if not attachment.startswith(b'%PDF-'): raise ApiError(400,'上传的文件不是有效的 PDF。')
    return filename,attachment

def publication_changes_pending():
    result=subprocess.run(['git','-C',str(ROOT),'status','--porcelain','--','publications.json','publication-assets'],capture_output=True,text=True,timeout=10)
    return bool(result.stdout.strip())

def run_git(arguments,timeout=90):
    environment=os.environ.copy(); environment['GIT_SSH_COMMAND']='ssh -o BatchMode=yes -o ConnectTimeout=10'
    try: result=subprocess.run(['git','-C',str(ROOT),*arguments],capture_output=True,text=True,timeout=timeout,env=environment)
    except (OSError,subprocess.TimeoutExpired): raise ApiError(502,'GitHub 发布命令未能完成，请稍后重试。')
    if result.returncode:
        detail=(result.stderr or result.stdout or '').strip().splitlines()
        raise ApiError(502,'GitHub 发布失败：'+(detail[-1][:300] if detail else '未知错误'))
    return result.stdout.strip()

def decode_attachment(data,maximum):
    item=data.get('attachment')
    if not item: return '',None
    if not isinstance(item,dict) or not isinstance(item.get('name'),str) or not isinstance(item.get('data'),str): raise ApiError(400,'附件格式不正确。')
    filename=item['name'].replace('\\','/').split('/')[-1]
    if not filename or len(filename)>180 or any(ord(c)<32 for c in filename) or Path(filename).suffix.lower() not in EXTENSIONS: raise ApiError(400,'不支持该附件格式或文件名过长。')
    try: attachment=base64.b64decode(item['data'],validate=True)
    except binascii.Error: raise ApiError(400,'附件内容不正确。')
    if not attachment or len(attachment)>maximum: raise ApiError(400,f'附件不能为空，且不能超过 {maximum//1024//1024} MB。')
    return filename,attachment

class Handler(BaseHTTPRequestHandler):
    server_version='VISGroup/2.0'
    def setup(self): super().setup(); self.connection.settimeout(30)
    def respond(self,status,data,content_type='application/json; charset=utf-8',headers=None):
        if not isinstance(data,bytes): data=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Content-Type',content_type); self.send_header('Content-Length',str(len(data)))
        for k,v in {'X-Content-Type-Options':'nosniff','Cache-Control':'no-store','Referrer-Policy':'same-origin','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"}.items(): self.send_header(k,v)
        for k,v in (headers or {}).items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(data)
    def json_body(self):
        if self.headers.get('X-Requested-With')!='VISGroup' or self.headers.get_content_type()!='application/json': raise ApiError(415,'请通过本站提交数据。')
        origin=self.headers.get('Origin')
        if origin and urlsplit(origin).netloc!=self.headers.get('Host'): raise ApiError(403,'不允许跨站提交。')
        try: length=int(self.headers.get('Content-Length','0'))
        except ValueError: raise ApiError(400,'请求长度不正确。')
        if length<=0 or length>MAX_REQUEST: raise ApiError(413,'请求过大，请检查附件大小。')
        try: data=json.loads(self.rfile.read(length))
        except (json.JSONDecodeError,UnicodeError): raise ApiError(400,'提交内容格式不正确。')
        if not isinstance(data,dict): raise ApiError(400,'提交内容格式不正确。')
        return data
    def current_user(self):
        try: morsel=SimpleCookie(self.headers.get('Cookie','')).get('vis_session')
        except Exception: return None
        if not morsel: return None
        token_hash=hashlib.sha256(morsel.value.encode()).hexdigest(); db=connect()
        try: row=db.execute('SELECT users.id,users.username,users.display_name,users.role,users.status,sessions.expires_at FROM sessions JOIN users ON users.id=sessions.user_id WHERE sessions.token_hash=?',(token_hash,)).fetchone()
        finally: db.close()
        return dict(row) if row and row['expires_at']>now_iso() and row['status']=='active' else None
    def require_user(self,admin=False):
        user=self.current_user()
        if not user: raise ApiError(401,'请先登录。')
        if admin and user['role']!='admin': raise ApiError(403,'只有管理员可以执行此操作。')
        return user
    def fail(self,exc):
        if isinstance(exc,ApiError): self.respond(exc.status,{'error':exc.message})
        elif isinstance(exc,(ValueError,binascii.Error,UnicodeError)): self.respond(400,{'error':str(exc)})
        else: self.log_error('Request failed: %s',type(exc).__name__); self.respond(500,{'error':'服务器处理失败，请稍后重试。'})
    def do_GET(self):
        path=urlsplit(self.path).path
        try:
            if path=='/api/site':
                self.respond(200,public_site())
            elif path=='/api/auth/me':
                user=self.current_user(); self.respond(200,{'user':{k:user[k] for k in ('id','username','display_name','role')} if user else None})
            elif path=='/api/profile':
                self.get_profile()
            elif path=='/api/reports':
                user=self.require_user(); db=connect()
                try:
                    if user['role']=='admin':
                        rows=db.execute('SELECT id,title,author,kind,date,summary,filename,example,created_at,user_id FROM reports ORDER BY date DESC,created_at DESC').fetchall()
                    else:
                        rows=db.execute('SELECT id,title,author,kind,date,summary,filename,example,created_at,user_id FROM reports WHERE user_id=? ORDER BY date DESC,created_at DESC',(user['id'],)).fetchall()
                finally: db.close()
                self.respond(200,[dict(r) for r in rows])
            elif path=='/api/literature':
                self.require_user(); db=connect()
                try: rows=db.execute('''SELECT literature.id,title,authors,source,year,url,notes,filename,uploader,uploader_id,literature.created_at,COUNT(literature_comments.id) AS comment_count FROM literature LEFT JOIN literature_comments ON literature_comments.literature_id=literature.id GROUP BY literature.id ORDER BY literature.created_at DESC''').fetchall()
                finally: db.close()
                self.respond(200,[dict(r) for r in rows])
            elif path=='/api/publications':
                self.require_user(); self.respond(200,publications_with_files())
            elif path=='/api/admin/users':
                self.require_user(True); db=connect()
                try: rows=db.execute("SELECT id,username,display_name,role,status,created_at FROM users ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END,created_at").fetchall()
                finally: db.close()
                self.respond(200,[dict(r) for r in rows])
            elif path=='/api/admin/members':
                self.require_user(True); site=read_site(); members=site.get('members',[])
                if not isinstance(members,list): raise ApiError(500,'小组成员配置格式不正确。')
                self.respond(200,members)
            elif path=='/api/admin/publications':
                self.require_user(True); self.respond(200,{'items':publications_with_files(),'pending_changes':publication_changes_pending()})
            elif re.fullmatch(r'/api/reports/[0-9a-f]{32}(/attachment)?',path):
                user=self.require_user(); report_id=path.split('/')[3]; db=connect()
                try: row=db.execute('SELECT * FROM reports WHERE id=?',(report_id,)).fetchone()
                finally: db.close()
                if not row or (user['role']!='admin' and row['user_id']!=user['id']): raise ApiError(404,'报告不存在。')
                if path.endswith('/attachment'):
                    if row['attachment'] is None: raise ApiError(404,'这份报告没有附件。')
                    self.respond(200,row['attachment'],'application/octet-stream',{'Content-Disposition':"attachment; filename=report-attachment; filename*=UTF-8''"+quote(row['filename'],safe='')})
                else: self.respond(200,{k:row[k] for k in row.keys() if k!='attachment'})
            elif re.fullmatch(r'/api/literature/[0-9a-f]{32}(/attachment)?',path):
                self.require_user(); literature_id=path.split('/')[3]; db=connect()
                try:
                    row=db.execute('SELECT * FROM literature WHERE id=?',(literature_id,)).fetchone()
                    comments=db.execute('SELECT id,author,author_id,body,created_at FROM literature_comments WHERE literature_id=? ORDER BY created_at',(literature_id,)).fetchall() if row and not path.endswith('/attachment') else []
                finally: db.close()
                if not row: raise ApiError(404,'文献不存在。')
                if path.endswith('/attachment'):
                    if row['attachment'] is None: raise ApiError(404,'这篇文献没有附件。')
                    mime=mimetypes.guess_type(row['filename'])[0] or 'application/octet-stream'; disposition='inline' if mime=='application/pdf' else 'attachment'
                    self.respond(200,row['attachment'],mime,{'Content-Disposition':f"{disposition}; filename=literature; filename*=UTF-8''"+quote(row['filename'],safe='')})
                else:
                    item={k:row[k] for k in row.keys() if k!='attachment'}; item['comments']=[dict(comment) for comment in comments]; self.respond(200,item)
            elif re.fullmatch(r'/api/publications/[0-9a-f]{32}/attachment',path):
                self.require_user(); publication_id=path.split('/')[3]; db=connect()
                try: row=db.execute('SELECT filename,attachment FROM publication_files WHERE publication_id=?',(publication_id,)).fetchone()
                finally: db.close()
                if not row: raise ApiError(404,'这项成果尚未上传组内论文 PDF。')
                self.respond(200,row['attachment'],'application/pdf',{'Content-Disposition':"inline; filename=paper.pdf; filename*=UTF-8''"+quote(row['filename'],safe='')})
            elif re.fullmatch(r'/publication-assets/[0-9a-f]{32}\.(png|jpg|webp)',path):
                self.require_user(); file=ROOT/path.lstrip('/')
                if not file.is_file(): raise ApiError(404,'代表图不存在。')
                self.respond(200,file.read_bytes(),mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
            else:
                files={'/':'index.html','/index.html':'index.html','/styles.css':'styles.css','/app.js':'app.js','/favicon.svg':'favicon.svg'}
                if path not in files: raise ApiError(404,'页面不存在。')
                file=ROOT/'static'/files[path]; mime=mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
                self.respond(200,file.read_bytes(),mime+('; charset=utf-8' if file.suffix in {'.js','.html','.css'} else ''))
        except Exception as exc: self.fail(exc)
    def do_POST(self):
        path=urlsplit(self.path).path
        try:
            data=self.json_body()
            if path=='/api/auth/register': self.register(data)
            elif path=='/api/auth/login': self.login(data)
            elif path=='/api/auth/logout': self.logout()
            elif path=='/api/reports': self.create_report(data)
            elif path=='/api/literature': self.create_literature(data)
            elif path=='/api/profile': self.update_profile(data)
            elif path=='/api/admin/news': self.create_news(data)
            elif path=='/api/admin/publications': self.create_publication(data)
            elif path=='/api/admin/publications/publish': self.publish_publications()
            elif re.fullmatch(r'/api/admin/publications/[0-9a-f]{32}/delete',path): self.delete_publication(path)
            elif re.fullmatch(r'/api/admin/publications/[0-9a-f]{32}/move',path): self.move_publication(path,data)
            elif re.fullmatch(r'/api/admin/publications/[0-9a-f]{32}',path): self.update_publication(path,data)
            elif re.fullmatch(r'/api/admin/news/\d+/delete',path): self.delete_news(int(path.split('/')[4]))
            elif re.fullmatch(r'/api/admin/news/\d+',path): self.update_news(path,data)
            elif re.fullmatch(r'/api/admin/members/\d+/bind',path): self.bind_member(path,data)
            elif re.fullmatch(r'/api/literature/[0-9a-f]{32}/comments',path): self.create_literature_comment(path,data)
            elif re.fullmatch(r'/api/admin/users/[0-9a-f]{32}/(approve|disable|promote)',path): self.manage_user(path,data)
            else: raise ApiError(404,'接口不存在。')
        except Exception as exc: self.fail(exc)
    def do_DELETE(self):
        path=urlsplit(self.path).path
        try:
            self.json_body(); self.require_user(True); report_match=re.fullmatch(r'/api/reports/([0-9a-f]{32})',path); literature_match=re.fullmatch(r'/api/literature/([0-9a-f]{32})',path); news_match=re.fullmatch(r'/api/admin/news/(\d+)',path)
            if news_match: return self.delete_news(int(news_match.group(1)))
            if not report_match and not literature_match: raise ApiError(404,'接口不存在。')
            db=connect()
            try:
                with db:
                    if report_match: changed=db.execute('DELETE FROM reports WHERE id=?',(report_match.group(1),)).rowcount
                    else: changed=db.execute('DELETE FROM literature WHERE id=?',(literature_match.group(1),)).rowcount
            finally: db.close()
            if not changed: raise ApiError(404,'内容不存在。')
            self.respond(200,{'ok':True})
        except Exception as exc: self.fail(exc)
    def register(self,data):
        username,name,password=clean(data,'username',32),clean(data,'display_name',60),clean(data,'password',200)
        if not USERNAME_RE.fullmatch(username): raise ApiError(400,'账号须为 3–32 位英文字母、数字、点、下划线或连字符。')
        if len(password)<10: raise ApiError(400,'密码至少需要 10 位。')
        salt,digest=hash_password(password); db=connect()
        try:
            with db: db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?,?)',(uuid4().hex,username,name,salt,digest,'member','pending',now_iso()))
        except sqlite3.IntegrityError: raise ApiError(409,'该账号已经注册，请直接登录或联系管理员。')
        finally: db.close()
        self.respond(201,{'ok':True,'message':'注册申请已提交，等待管理员审核。'})
    def login(self,data):
        username,password=clean(data,'username',32),clean(data,'password',200); address=self.client_address[0]
        attempts=[t for t in LOGIN_ATTEMPTS.get(address,[]) if time.time()-t<300]
        if len(attempts)>=10: raise ApiError(429,'登录尝试过多，请 5 分钟后再试。')
        db=connect()
        try:
            row=db.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
            if not row or not valid_password(password,row['password_salt'],row['password_hash']):
                attempts.append(time.time()); LOGIN_ATTEMPTS[address]=attempts; raise ApiError(401,'账号或密码不正确。')
            if row['status']=='pending': raise ApiError(403,'账号正在等待管理员审核。')
            if row['status']!='active': raise ApiError(403,'账号已停用，请联系管理员。')
            LOGIN_ATTEMPTS.pop(address,None); token=secrets.token_urlsafe(32); expiry=(datetime.now(timezone.utc)+timedelta(days=SESSION_DAYS)).isoformat()
            with db:
                db.execute('DELETE FROM sessions WHERE user_id=? OR expires_at<=?',(row['id'],now_iso()))
                db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),row['id'],expiry,now_iso()))
        finally: db.close()
        cookie=f'vis_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_DAYS*86400}'+('; Secure' if SECURE_COOKIE else '')
        self.respond(200,{'user':{'id':row['id'],'username':row['username'],'display_name':row['display_name'],'role':row['role']}},headers={'Set-Cookie':cookie})
    def logout(self):
        morsel=SimpleCookie(self.headers.get('Cookie','')).get('vis_session')
        if morsel:
            db=connect()
            try:
                with db: db.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(morsel.value.encode()).hexdigest(),))
            finally: db.close()
        self.respond(200,{'ok':True},headers={'Set-Cookie':'vis_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0'+('; Secure' if SECURE_COOKIE else '')})
    def create_report(self,data):
        user=self.require_user(); title=clean(data,'title',120); kind,day=clean(data,'kind',10),clean(data,'date',10)
        if kind not in {'daily','weekly'}: raise ApiError(400,'报告类型不正确。')
        try:
            if date.fromisoformat(day).isoformat()!=day: raise ValueError
        except ValueError: raise ApiError(400,'报告日期不正确。')
        body,summary=clean(data,'body',50000,False),clean(data,'summary',300,False); filename,attachment=decode_attachment(data,MAX_FILE)
        if not body and attachment is None: raise ApiError(400,'请填写报告正文，或上传一份附件。')
        summary=summary or body[:120] or '附件：'+filename; report_id=uuid4().hex; db=connect()
        try:
            with db: db.execute('INSERT INTO reports(id,title,author,kind,date,summary,body,filename,attachment,example,created_at,user_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(report_id,title,user['display_name'],kind,day,summary,body,filename,attachment,0,now_iso(),user['id']))
        finally: db.close()
        self.respond(201,{'id':report_id})
    def create_literature(self,data):
        user=self.require_user(); title,authors=clean(data,'title',200),clean(data,'authors',400)
        source,year,url,notes=clean(data,'source',200,False),clean(data,'year',4,False),clean(data,'url',1000,False),clean(data,'notes',5000,False)
        if year and not re.fullmatch(r'\d{4}',year): raise ApiError(400,'年份应为 4 位数字。')
        if url:
            parsed=urlsplit(url)
            if parsed.scheme not in {'http','https'} or not parsed.netloc: raise ApiError(400,'文献链接必须是完整的 HTTP 或 HTTPS 地址。')
        filename,attachment=decode_attachment(data,MAX_LITERATURE_FILE)
        if attachment is None and not url: raise ApiError(400,'请上传文献附件，或填写文献链接。')
        literature_id=uuid4().hex; db=connect()
        try:
            with db: db.execute('INSERT INTO literature VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(literature_id,title,authors,source,year,url,notes,filename,attachment,user['display_name'],user['id'],now_iso()))
        finally: db.close()
        self.respond(201,{'id':literature_id})
    def create_literature_comment(self,path,data):
        user=self.require_user(); body=clean(data,'body',2000); literature_id=path.split('/')[3]; db=connect()
        try:
            with db:
                if not db.execute('SELECT 1 FROM literature WHERE id=?',(literature_id,)).fetchone(): raise ApiError(404,'文献不存在。')
                comment_id=uuid4().hex; db.execute('INSERT INTO literature_comments VALUES(?,?,?,?,?,?)',(comment_id,literature_id,user['display_name'],user['id'],body,now_iso()))
        finally: db.close()
        self.respond(201,{'id':comment_id})
    def get_profile(self):
        user=self.require_user(); site=read_site(); members=site.get('members',[])
        if not isinstance(members,list): raise ApiError(500,'小组成员配置格式不正确。')
        for member in members:
            if isinstance(member,dict) and member.get('user_id')==user['id']:
                return self.respond(200,{key:value for key,value in member.items() if key!='user_id'})
        raise ApiError(404,'你的账号尚未绑定小组成员，请联系管理员。')
    def update_profile(self,data):
        user=self.require_user(); profile=clean_profile(data)
        with SITE_LOCK:
            site=read_site(); members=site.get('members',[])
            if not isinstance(members,list): raise ApiError(500,'小组成员配置格式不正确。')
            for index,member in enumerate(members):
                if isinstance(member,dict) and member.get('user_id')==user['id']:
                    members[index]={**member,**profile}; write_site(site); break
            else: raise ApiError(404,'你的账号尚未绑定小组成员，请联系管理员。')
        self.respond(200,{'profile':profile,'site':public_site()})
    def bind_member(self,path,data):
        self.require_user(True); index=int(path.split('/')[4]); user_id=clean(data,'user_id',32,False)
        if user_id and not re.fullmatch(r'[0-9a-f]{32}',user_id): raise ApiError(400,'账号标识不正确。')
        if user_id:
            db=connect()
            try: exists=db.execute('SELECT 1 FROM users WHERE id=?',(user_id,)).fetchone()
            finally: db.close()
            if not exists: raise ApiError(404,'账号不存在。')
        with SITE_LOCK:
            site=read_site(); members=site.get('members',[])
            if not isinstance(members,list) or index>=len(members): raise ApiError(404,'小组成员不存在。')
            if user_id and any(i!=index and isinstance(member,dict) and member.get('user_id')==user_id for i,member in enumerate(members)): raise ApiError(409,'这个账号已经绑定了其他成员。')
            if not isinstance(members[index],dict): raise ApiError(500,'小组成员配置格式不正确。')
            if user_id: members[index]['user_id']=user_id
            else: members[index].pop('user_id',None)
            write_site(site)
        self.respond(200,{'members':members})
    def create_news(self,data):
        self.require_user(True); item=clean_news(data)
        with SITE_LOCK:
            site=read_site(); news=site.setdefault('news',[])
            if not isinstance(news,list): raise ApiError(500,'小组动态配置格式不正确。')
            if len(news)>=100: raise ApiError(400,'小组动态最多保留 100 条。')
            news.insert(0,item); write_site(site)
        self.respond(201,{'news':news})
    def update_news(self,path,data):
        self.require_user(True); index=int(path.rsplit('/',1)[1]); item=clean_news(data)
        with SITE_LOCK:
            site=read_site(); news=site.get('news',[])
            if not isinstance(news,list) or index>=len(news): raise ApiError(404,'动态不存在。')
            news[index]=item; write_site(site)
        self.respond(200,{'news':news})
    def delete_news(self,index):
        self.require_user(True)
        with SITE_LOCK:
            site=read_site(); news=site.get('news',[])
            if not isinstance(news,list) or index>=len(news): raise ApiError(404,'动态不存在。')
            news.pop(index); write_site(site)
        self.respond(200,{'news':news})
    def create_publication(self,data):
        user=self.require_user(True); item=clean_publication(data); extension,content=decode_publication_image(data); paper_name,paper=decode_publication_paper(data); publication_id=uuid4().hex
        item.update({'id':publication_id,'image':'','created_at':now_iso(),'updated_at':now_iso()})
        with PUBLICATION_LOCK:
            items=read_publications()
            if len(items)>=100: raise ApiError(400,'公开成果最多保留 100 条。')
            if content is not None:
                PUBLICATION_ASSETS.mkdir(parents=True,exist_ok=True); target=PUBLICATION_ASSETS/f'{publication_id}{extension}'; temporary=target.with_suffix(target.suffix+'.tmp'); temporary.write_bytes(content); os.replace(temporary,target); item['image']=f'publication-assets/{target.name}'
            items.insert(0,item); write_publications(items)
            if paper is not None:
                db=connect()
                try:
                    with db: db.execute('INSERT INTO publication_files(publication_id,filename,attachment,uploader_id,updated_at) VALUES(?,?,?,?,?)',(publication_id,paper_name,paper,user['id'],now_iso()))
                finally: db.close()
        self.respond(201,{'items':publications_with_files(),'pending_changes':True})
    def update_publication(self,path,data):
        user=self.require_user(True); publication_id=path.rsplit('/',1)[1]; cleaned=clean_publication(data); extension,content=decode_publication_image(data); paper_name,paper=decode_publication_paper(data); remove_image=data.get('remove_image') is True; remove_paper=data.get('remove_paper') is True
        with PUBLICATION_LOCK:
            items=read_publications(); index=next((i for i,item in enumerate(items) if item.get('id')==publication_id),None)
            if index is None: raise ApiError(404,'成果不存在。')
            previous=items[index]; old_image=previous.get('image',''); new_image=old_image
            if content is not None:
                PUBLICATION_ASSETS.mkdir(parents=True,exist_ok=True); target=PUBLICATION_ASSETS/f'{uuid4().hex}{extension}'; temporary=target.with_suffix(target.suffix+'.tmp'); temporary.write_bytes(content); os.replace(temporary,target); new_image=f'publication-assets/{target.name}'
            elif remove_image: new_image=''
            items[index]={**cleaned,'id':publication_id,'image':new_image,'created_at':previous.get('created_at',now_iso()),'updated_at':now_iso()}; write_publications(items)
            if old_image and old_image!=new_image and re.fullmatch(r'publication-assets/[0-9a-f]{32}\.(png|jpg|webp)',old_image): (ROOT/old_image).unlink(missing_ok=True)
            if paper is not None or remove_paper:
                db=connect()
                try:
                    with db:
                        if paper is not None: db.execute('INSERT INTO publication_files(publication_id,filename,attachment,uploader_id,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(publication_id) DO UPDATE SET filename=excluded.filename,attachment=excluded.attachment,uploader_id=excluded.uploader_id,updated_at=excluded.updated_at',(publication_id,paper_name,paper,user['id'],now_iso()))
                        else: db.execute('DELETE FROM publication_files WHERE publication_id=?',(publication_id,))
                finally: db.close()
        self.respond(200,{'items':publications_with_files(),'pending_changes':True})
    def delete_publication(self,path):
        self.require_user(True); publication_id=path.split('/')[4]
        with PUBLICATION_LOCK:
            items=read_publications(); index=next((i for i,item in enumerate(items) if item.get('id')==publication_id),None)
            if index is None: raise ApiError(404,'成果不存在。')
            removed=items.pop(index); write_publications(items); image=removed.get('image','')
            if image and re.fullmatch(r'publication-assets/[0-9a-f]{32}\.(png|jpg|webp)',image): (ROOT/image).unlink(missing_ok=True)
            db=connect()
            try:
                with db: db.execute('DELETE FROM publication_files WHERE publication_id=?',(publication_id,))
            finally: db.close()
        self.respond(200,{'items':publications_with_files(),'pending_changes':True})
    def move_publication(self,path,data):
        self.require_user(True); publication_id=path.split('/')[4]; direction=clean(data,'direction',4)
        if direction not in {'up','down'}: raise ApiError(400,'排序方向不正确。')
        with PUBLICATION_LOCK:
            items=read_publications(); index=next((i for i,item in enumerate(items) if item.get('id')==publication_id),None)
            if index is None: raise ApiError(404,'成果不存在。')
            target=index+(-1 if direction=='up' else 1)
            if 0<=target<len(items): items[index],items[target]=items[target],items[index]; write_publications(items)
        self.respond(200,{'items':publications_with_files(),'pending_changes':publication_changes_pending()})
    def publish_publications(self):
        self.require_user(True)
        with PUBLICATION_LOCK:
            run_git(['pull','--rebase','--autostash','origin','main'])
            run_git(['add','--','publications.json','publication-assets'])
            diff=subprocess.run(['git','-C',str(ROOT),'diff','--cached','--quiet','--','publications.json','publication-assets'],timeout=10)
            if diff.returncode==0: return self.respond(200,{'ok':True,'published':False,'message':'没有待发布的成果改动。'})
            if diff.returncode!=1: raise ApiError(502,'无法检查待发布的 GitHub 改动。')
            run_git(['commit','-m',f"Publish group achievements {datetime.now().strftime('%Y-%m-%d %H:%M')}",'--','publications.json','publication-assets'])
            run_git(['push','origin','main'])
            commit=run_git(['rev-parse','--short','HEAD'])
        self.respond(200,{'ok':True,'published':True,'commit':commit,'message':'成果已推送到 GitHub Pages，通常会在几分钟内更新。'})
    def manage_user(self,path,data):
        admin=self.require_user(True); _,_,_,_,user_id,action=path.split('/')
        if user_id==admin['id'] and action in {'disable','promote'}: raise ApiError(400,'不能停用或修改自己的管理员身份。')
        db=connect()
        try:
            with db:
                if not db.execute('SELECT 1 FROM users WHERE id=?',(user_id,)).fetchone(): raise ApiError(404,'成员不存在。')
                if action=='approve': db.execute("UPDATE users SET status='active' WHERE id=?",(user_id,))
                elif action=='disable': db.execute("UPDATE users SET status='disabled' WHERE id=?",(user_id,)); db.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
                else:
                    role=clean(data,'role',10)
                    if role not in {'member','admin'}: raise ApiError(400,'角色不正确。')
                    db.execute('UPDATE users SET role=? WHERE id=?',(role,user_id))
        finally: db.close()
        self.respond(200,{'ok':True})

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='VIS Group website; no third-party packages required.')
    parser.add_argument('--host',default='127.0.0.1'); parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--data-dir',type=Path,default=ROOT/'data'); parser.add_argument('--no-demo',action='store_true')
    parser.add_argument('--clear-demo',action='store_true'); parser.add_argument('--create-admin',metavar='USERNAME')
    parser.add_argument('--reset-password',metavar='USERNAME')
    args=parser.parse_args(); DB_PATH=args.data_dir.resolve()/'vis-group.sqlite3'; initialize(seed=not args.no_demo)
    try:
        if args.create_admin: create_admin(args.create_admin); print('管理员已创建。现在可以正常启动网站并登录。')
        elif args.reset_password: reset_password(args.reset_password); print('网站账号密码已重置，原有登录会话已退出。')
        elif args.clear_demo:
            db=connect()
            try:
                with db: db.execute('DELETE FROM reports WHERE example=1')
            finally: db.close()
            print('示例报告已移除，成员提交的报告已保留。')
        else:
            server=ThreadingHTTPServer((args.host,args.port),Handler); server.daemon_threads=True
            print(f'VIS Group: http://{args.host}:{args.port}\nData: {DB_PATH}\nStop: Ctrl+C',flush=True)
            try: server.serve_forever()
            except KeyboardInterrupt: pass
            finally: server.server_close()
    except ValueError as exc: parser.error(str(exc))
