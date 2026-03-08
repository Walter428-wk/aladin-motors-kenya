from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Any
import sqlite3
import json
import time
import uuid
from datetime import datetime, timedelta
import os

app = FastAPI(title="WebMonitor API", version="1.0.0")

# Allow all origins (configure for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "monitor.db"

# ─── Database Setup ───────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS pageviews (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            url TEXT,
            referrer TEXT,
            user_agent TEXT,
            screen_width INTEGER,
            screen_height INTEGER,
            timestamp INTEGER,
            country TEXT,
            ip TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            event_type TEXT,
            element TEXT,
            element_id TEXT,
            element_class TEXT,
            page_url TEXT,
            x INTEGER,
            y INTEGER,
            metadata TEXT,
            timestamp INTEGER
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS errors (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            message TEXT,
            stack TEXT,
            page_url TEXT,
            line_number INTEGER,
            column_number INTEGER,
            filename TEXT,
            timestamp INTEGER
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS performance (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            page_url TEXT,
            dns_lookup REAL,
            tcp_connect REAL,
            ttfb REAL,
            dom_load REAL,
            full_load REAL,
            fcp REAL,
            lcp REAL,
            cls REAL,
            fid REAL,
            timestamp INTEGER
        )
    """)

    conn.commit()
    conn.close()

init_db()

# ─── Models ───────────────────────────────────────────────────────────────────

class PageViewEvent(BaseModel):
    session_id: str
    url: str
    referrer: Optional[str] = ""
    user_agent: Optional[str] = ""
    screen_width: Optional[int] = 0
    screen_height: Optional[int] = 0

class ClickEvent(BaseModel):
    session_id: str
    event_type: str
    element: Optional[str] = ""
    element_id: Optional[str] = ""
    element_class: Optional[str] = ""
    page_url: str
    x: Optional[int] = 0
    y: Optional[int] = 0
    metadata: Optional[dict] = {}

class ErrorEvent(BaseModel):
    session_id: str
    message: str
    stack: Optional[str] = ""
    page_url: str
    line_number: Optional[int] = 0
    column_number: Optional[int] = 0
    filename: Optional[str] = ""

class PerformanceEvent(BaseModel):
    session_id: str
    page_url: str
    dns_lookup: Optional[float] = 0
    tcp_connect: Optional[float] = 0
    ttfb: Optional[float] = 0
    dom_load: Optional[float] = 0
    full_load: Optional[float] = 0
    fcp: Optional[float] = 0
    lcp: Optional[float] = 0
    cls: Optional[float] = 0
    fid: Optional[float] = 0

# ─── Track Endpoints ──────────────────────────────────────────────────────────

@app.post("/track/pageview")
async def track_pageview(event: PageViewEvent, request: Request):
    conn = get_db()
    ip = request.client.host
    conn.execute("""
        INSERT INTO pageviews VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (
        str(uuid.uuid4()), event.session_id, event.url, event.referrer,
        event.user_agent, event.screen_width, event.screen_height,
        int(time.time() * 1000), "", ip
    ))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.post("/track/event")
async def track_event(event: ClickEvent):
    conn = get_db()
    conn.execute("""
        INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (
        str(uuid.uuid4()), event.session_id, event.event_type,
        event.element, event.element_id, event.element_class,
        event.page_url, event.x, event.y,
        json.dumps(event.metadata), int(time.time() * 1000)
    ))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.post("/track/error")
async def track_error(event: ErrorEvent):
    conn = get_db()
    conn.execute("""
        INSERT INTO errors VALUES (?,?,?,?,?,?,?,?,?)
    """, (
        str(uuid.uuid4()), event.session_id, event.message,
        event.stack, event.page_url, event.line_number,
        event.column_number, event.filename, int(time.time() * 1000)
    ))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.post("/track/performance")
async def track_performance(event: PerformanceEvent):
    conn = get_db()
    conn.execute("""
        INSERT INTO performance VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        str(uuid.uuid4()), event.session_id, event.page_url,
        event.dns_lookup, event.tcp_connect, event.ttfb,
        event.dom_load, event.full_load, event.fcp,
        event.lcp, event.cls, event.fid, int(time.time() * 1000)
    ))
    conn.commit()
    conn.close()
    return {"ok": True}

# ─── Analytics Endpoints ──────────────────────────────────────────────────────

@app.get("/analytics/summary")
async def get_summary():
    conn = get_db()
    now = int(time.time() * 1000)
    day_ago = now - 86400000
    week_ago = now - 604800000

    total_views = conn.execute("SELECT COUNT(*) FROM pageviews").fetchone()[0]
    views_today = conn.execute("SELECT COUNT(*) FROM pageviews WHERE timestamp > ?", (day_ago,)).fetchone()[0]
    unique_sessions = conn.execute("SELECT COUNT(DISTINCT session_id) FROM pageviews").fetchone()[0]
    total_errors = conn.execute("SELECT COUNT(*) FROM errors").fetchone()[0]
    errors_today = conn.execute("SELECT COUNT(*) FROM errors WHERE timestamp > ?", (day_ago,)).fetchone()[0]
    total_events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    avg_perf = conn.execute("""
        SELECT AVG(ttfb), AVG(full_load), AVG(lcp), AVG(fcp)
        FROM performance WHERE timestamp > ?
    """, (week_ago,)).fetchone()

    conn.close()
    return {
        "total_pageviews": total_views,
        "pageviews_today": views_today,
        "unique_sessions": unique_sessions,
        "total_errors": total_errors,
        "errors_today": errors_today,
        "total_events": total_events,
        "avg_ttfb": round(avg_perf[0] or 0, 2),
        "avg_load_time": round(avg_perf[1] or 0, 2),
        "avg_lcp": round(avg_perf[2] or 0, 2),
        "avg_fcp": round(avg_perf[3] or 0, 2),
    }

@app.get("/analytics/pageviews")
async def get_pageviews(limit: int = 50, offset: int = 0):
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM pageviews ORDER BY timestamp DESC LIMIT ? OFFSET ?
    """, (limit, offset)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/analytics/pageviews/chart")
async def get_pageviews_chart(days: int = 7):
    conn = get_db()
    since = int(time.time() * 1000) - days * 86400000
    rows = conn.execute("""
        SELECT timestamp FROM pageviews WHERE timestamp > ? ORDER BY timestamp ASC
    """, (since,)).fetchall()
    conn.close()

    # Bucket by hour
    buckets = {}
    for row in rows:
        dt = datetime.fromtimestamp(row[0] / 1000)
        key = dt.strftime("%m/%d %H:00")
        buckets[key] = buckets.get(key, 0) + 1

    return [{"time": k, "views": v} for k, v in sorted(buckets.items())]

@app.get("/analytics/top-pages")
async def get_top_pages(limit: int = 10):
    conn = get_db()
    rows = conn.execute("""
        SELECT url, COUNT(*) as count FROM pageviews
        GROUP BY url ORDER BY count DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/analytics/events")
async def get_events(limit: int = 50, offset: int = 0, event_type: Optional[str] = None):
    conn = get_db()
    if event_type:
        rows = conn.execute("""
            SELECT * FROM events WHERE event_type = ? ORDER BY timestamp DESC LIMIT ? OFFSET ?
        """, (event_type, limit, offset)).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM events ORDER BY timestamp DESC LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/analytics/errors")
async def get_errors(limit: int = 50, offset: int = 0):
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM errors ORDER BY timestamp DESC LIMIT ? OFFSET ?
    """, (limit, offset)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/analytics/performance")
async def get_performance(limit: int = 50):
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM performance ORDER BY timestamp DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/analytics/browsers")
async def get_browsers():
    conn = get_db()
    rows = conn.execute("SELECT user_agent FROM pageviews").fetchall()
    conn.close()

    browsers = {}
    for row in rows:
        ua = row[0] or ""
        if "Chrome" in ua and "Edg" not in ua:
            b = "Chrome"
        elif "Firefox" in ua:
            b = "Firefox"
        elif "Safari" in ua and "Chrome" not in ua:
            b = "Safari"
        elif "Edg" in ua:
            b = "Edge"
        else:
            b = "Other"
        browsers[b] = browsers.get(b, 0) + 1

    return [{"browser": k, "count": v} for k, v in browsers.items()]

@app.delete("/analytics/clear")
async def clear_data():
    conn = get_db()
    conn.execute("DELETE FROM pageviews")
    conn.execute("DELETE FROM events")
    conn.execute("DELETE FROM errors")
    conn.execute("DELETE FROM performance")
    conn.commit()
    conn.close()
    return {"ok": True, "message": "All data cleared"}

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": int(time.time())}

# ─── Car Management ───────────────────────────────────────────────────────────

import base64
from pathlib import Path

IMAGES_DIR = Path("car_images")
IMAGES_DIR.mkdir(exist_ok=True)

def init_cars_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            year TEXT, km TEXT, engine TEXT, transmission TEXT,
            fuel TEXT, color TEXT, price TEXT, badge TEXT,
            category TEXT, description TEXT,
            available INTEGER DEFAULT 1, created_at INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS car_photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            car_id INTEGER NOT NULL,
            image_path TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            FOREIGN KEY(car_id) REFERENCES cars(id)
        )
    """)
    conn.commit()
    conn.close()

init_cars_db()

class CarModel(BaseModel):
    name: str
    year: Optional[str] = ""
    km: Optional[str] = ""
    engine: Optional[str] = ""
    transmission: Optional[str] = ""
    fuel: Optional[str] = ""
    color: Optional[str] = ""
    price: Optional[str] = ""
    badge: Optional[str] = ""
    category: Optional[str] = "all"
    description: Optional[str] = ""
    available: Optional[int] = 1
    images: Optional[list] = []
    delete_photo_ids: Optional[list] = []

def get_car_photos(conn, car_id):
    rows = conn.execute(
        "SELECT id, image_path FROM car_photos WHERE car_id=? ORDER BY sort_order ASC", (car_id,)
    ).fetchall()
    return [{"photo_id": r[0], "url": f"/cars/photo/{r[0]}"} for r in rows if Path(r[1]).exists()]

def enrich_car(conn, car_dict):
    photos = get_car_photos(conn, car_dict["id"])
    car_dict["photos"] = photos
    car_dict["image_url"] = photos[0]["url"] if photos else None
    return car_dict

def save_photos(conn, car_id, images):
    existing_count = conn.execute("SELECT COUNT(*) FROM car_photos WHERE car_id=?", (car_id,)).fetchone()[0]
    for i, img in enumerate(images):
        if not img.get("data"):
            continue
        try:
            img_bytes = base64.b64decode(img["data"])
            ext = img.get("ext", "jpg").lower()
            fname = f"car_{car_id}_{int(time.time()*1000)}_{i}.{ext}"
            fpath = str(IMAGES_DIR / fname)
            with open(fpath, "wb") as f:
                f.write(img_bytes)
            conn.execute(
                "INSERT INTO car_photos (car_id, image_path, sort_order) VALUES (?,?,?)",
                (car_id, fpath, existing_count + i)
            )
        except:
            continue

@app.get("/cars")
async def get_cars():
    conn = get_db()
    rows = conn.execute("SELECT * FROM cars ORDER BY available DESC, created_at DESC").fetchall()
    cars = [enrich_car(conn, dict(r)) for r in rows]
    conn.close()
    return cars

@app.get("/cars/all")
async def get_all_cars():
    conn = get_db()
    rows = conn.execute("SELECT * FROM cars ORDER BY created_at DESC").fetchall()
    cars = [enrich_car(conn, dict(r)) for r in rows]
    conn.close()
    return cars

@app.get("/cars/photo/{photo_id}")
async def get_car_photo(photo_id: int):
    from fastapi.responses import FileResponse
    conn = get_db()
    row = conn.execute("SELECT image_path FROM car_photos WHERE id=?", (photo_id,)).fetchone()
    conn.close()
    if not row or not Path(row[0]).exists():
        raise HTTPException(status_code=404, detail="Photo not found")
    return FileResponse(row[0])

@app.post("/cars")
async def create_car(car: CarModel):
    conn = get_db()
    cursor = conn.execute("""
        INSERT INTO cars (name,year,km,engine,transmission,fuel,color,price,badge,category,description,available,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (car.name, car.year, car.km, car.engine, car.transmission,
          car.fuel, car.color, car.price, car.badge, car.category,
          car.description, car.available, int(time.time() * 1000)))
    car_id = cursor.lastrowid
    if car.images:
        save_photos(conn, car_id, car.images)
    conn.commit()
    conn.close()
    return {"ok": True, "id": car_id}

@app.put("/cars/{car_id}")
async def update_car(car_id: int, car: CarModel):
    conn = get_db()
    if not conn.execute("SELECT id FROM cars WHERE id=?", (car_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Car not found")
    for pid in (car.delete_photo_ids or []):
        row = conn.execute("SELECT image_path FROM car_photos WHERE id=? AND car_id=?", (pid, car_id)).fetchone()
        if row and Path(row[0]).exists():
            Path(row[0]).unlink()
        conn.execute("DELETE FROM car_photos WHERE id=? AND car_id=?", (pid, car_id))
    if car.images:
        # Do not save/upload images on update (images removed)
        pass
    conn.execute("""
        UPDATE cars SET name=?,year=?,km=?,engine=?,transmission=?,fuel=?,color=?,
        price=?,badge=?,category=?,description=?,available=? WHERE id=?
    """, (car.name, car.year, car.km, car.engine, car.transmission,
          car.fuel, car.color, car.price, car.badge, car.category,
          car.description, car.available, car_id))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.delete("/cars/{car_id}")
async def delete_car(car_id: int):
    conn = get_db()
    photos = conn.execute("SELECT image_path FROM car_photos WHERE car_id=?", (car_id,)).fetchall()
    for p in photos:
        if p[0] and Path(p[0]).exists():
            Path(p[0]).unlink()
    conn.execute("DELETE FROM car_photos WHERE car_id=?", (car_id,))
    conn.execute("DELETE FROM cars WHERE id=?", (car_id,))
    conn.commit()
    conn.close()
    return {"ok": True}