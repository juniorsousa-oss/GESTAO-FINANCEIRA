"""Kit AXORA: públicos somente arquivos visuais; escrita exige admin + CSRF."""
import io
from pathlib import Path
from fastapi.testclient import TestClient
from PIL import Image
from axora_v2 import db, security
from axora_v2.main import app, BRAND_KIT_SLOTS


def make_png(square=False):
    buffer=io.BytesIO()
    im=Image.new("RGBA",(180,180) if square else (180,90),(0,0,0,0))
    if square: im.paste((7,128,156,255),(9,9,171,171))
    im.save(buffer,format="PNG")
    return buffer.getvalue()


def test_kit_admin_permissions_data_persistence_and_public_assets(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY","only-ci")
    monkeypatch.setenv("SESSION_SECRET","test-secret-unique-and-long-enough-to-sign-sessions")
    monkeypatch.setenv("COOKIE_SECURE","0")
    accounts=[
      {"id":1,"display_name":"Administrador","is_admin":True,"is_active":True,"password_hash":security.hash_password("admin-brand-test-123")},
      {"id":2,"display_name":"Leitor","is_admin":False,"is_active":True,"password_hash":security.hash_password("leitor-brand-test-123")}
    ]
    assets={}
    def select(kind,*,fields="*",order=None,params=None):
      if kind=="users":
        rows=accounts
        if params and "id" in params:
          rows=[r for r in rows if str(r["id"])==str(params["id"]).removeprefix("eq.")]
      elif kind=="branding":
        rows=list(assets.values())
        if params and "key" in params:
          val=params["key"]
          if val.startswith("eq."):rows=[r for r in rows if r["key"]==val[3:]]
          elif val.startswith("in.("):
            allowed=val[4:-1].split(",")
            rows=[r for r in rows if r["key"] in allowed]
      else: rows=[]
      return [{k:v for k,v in row.items() if fields=="*" or k in fields.split(",")} for row in rows]
    def call(method,table,*,params=None,data=None,prefer=None):
      assert table=="finance_brand_assets"
      if method=="POST":
        assets[data["key"]]=dict(data)
        return [data]
      if method=="DELETE":
        assets.pop(params["key"].removeprefix("eq."),None)
        return []
      raise AssertionError(method)

    monkeypatch.setattr(db,"select",select)
    monkeypatch.setattr(db,"call",call)
    monkeypatch.setattr(security,"accounts",lambda:accounts)

    with TestClient(app) as client:
      kit=client.get("/api/brand-kit")
      assert kit.status_code==200
      assert set(kit.json())==set(BRAND_KIT_SLOTS)
      assert all(not v["configured"] for v in kit.json().values())
      assert client.get("/api/brand-kit/favicon/image").status_code==404
      assert client.get("/api/brand-kit/other/image").status_code==404
      assert client.post("/api/brand-kit/primary",files={"file":("logo.png",make_png(),"image/png")}).status_code==401
      assert client.post("/api/login",json={"password":"leitor-brand-test-123"}).status_code==200
      csrf={"X-CSRF-Token":client.get("/api/me").json()["csrf"]}
      assert client.post("/api/brand-kit/primary",headers=csrf,files={"file":("logo.png",make_png(),"image/png")}).status_code==403
      assert client.post("/api/logout",headers=csrf).status_code==200
      assert client.post("/api/login",json={"password":"admin-brand-test-123"}).status_code==200
      admin={"X-CSRF-Token":client.get("/api/me").json()["csrf"]}
      assert client.post("/api/brand-kit/primary",files={"file":("logo.png",make_png(),"image/png")}).status_code==403
      assert client.post("/api/brand-kit/other",headers=admin,files={"file":("logo.png",make_png(),"image/png")}).status_code==404
      for slot in BRAND_KIT_SLOTS:
        saved=client.post("/api/brand-kit/"+slot,headers=admin,files={"file":("logo.png",make_png(square=slot in ("icon","favicon")),"image/png")})
        assert saved.status_code==200,saved.text
        result=client.get("/api/brand-kit/"+slot+"/image")
        assert result.status_code==200
        assert result.headers["content-type"].startswith("image/webp")
        assert result.content[:4]==b"RIFF"
      assert all(v["configured"] for v in client.get("/api/brand-kit").json().values())
      assert client.get("/api/multiuser/status").json()["isolation_enabled"] is False
      assert client.delete("/api/brand-kit/favicon",headers=admin).status_code==200
      assert client.get("/api/brand-kit/favicon/image").status_code==404
      assert client.get("/api/brand-kit/icon/image").status_code==200


def test_logo_studio_frontend_and_safe_migrations():
    root=Path(__file__).resolve().parents[1]
    html=(root/"static/index.html").read_text()
    js=(root/"static/brand-kit.js").read_text()
    main=(root/"static/app.js").read_text()
    css=(root/"static/brand-kit.css").read_text()
    assert "brand-kit.js" in html and "brand-kit.css" in html
    assert html.index("app.js?") < html.index("brand-kit.js?")
    assert "brandKitPanel()" in main
    for slot in ("primary","secondary","icon","favicon"):
      assert slot+":" in js
    for action in ("save-brand-kit","export-brand-kit","reset-brand-kit"):
      assert action in js
    assert "canvas.toBlob" in js and 'image/png' in js
    assert "brand-custom" in css
    sql=(root/"migrations/20261010_multiuser_foundation.sql").read_text()
    assert "finance_workspaces" in sql
    assert "finance_workspace_members" in sql
    assert "workspace_id uuid NOT NULL" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "NÃO habilita isolamento" in sql
