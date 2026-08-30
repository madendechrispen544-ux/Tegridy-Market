import os
from datetime import datetime, date

from flask import Flask, render_template_string, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import UniqueConstraint

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-before-production")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///tegridy_v3.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"


# ---------------- DATABASE ----------------

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password = db.Column(db.String(255), nullable=False)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    posts = db.relationship("Post", backref="author", lazy=True, cascade="all, delete-orphan")
    reviews = db.relationship("Review", backref="reviewer", lazy=True, cascade="all, delete-orphan")


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    service = db.Column(db.String(100), nullable=False, index=True)
    category = db.Column(db.String(50), nullable=False, default="Other")
    contact = db.Column(db.String(120), nullable=False)
    expiry_date = db.Column(db.Date, nullable=True)
    description = db.Column(db.String(300), nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="Available")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    reviews = db.relationship("Review", backref="post", lazy=True, cascade="all, delete-orphan")


class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.String(200), nullable=False, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="one_review_per_user_per_post"),
    )


class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "post_id", name="one_favorite_per_user_post"),
    )


class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reason = db.Column(db.String(100), nullable=False)
    details = db.Column(db.String(300), default="")
    status = db.Column(db.String(20), default="open", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)

    reporter = db.relationship("User", foreign_keys=[user_id])
    reported_post = db.relationship("Post", foreign_keys=[post_id], backref="reports")


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String(250), nullable=False)
    link = db.Column(db.String(200), default="")
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)


class JoinRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String(300), default="")
    status = db.Column(db.String(20), nullable=False, default="Pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    requester_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)

    requester = db.relationship("User", foreign_keys=[requester_id])
    requested_post = db.relationship("Post", foreign_keys=[post_id], backref="join_requests")

    __table_args__ = (
        UniqueConstraint("requester_id", "post_id", name="one_join_request_per_user_post"),
    )


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ---------------- HELPERS ----------------

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "Rick44")
CATEGORIES = ["Streaming", "Music", "Gaming", "Software", "Other"]
STATUSES = ["Available", "Full"]


def clean(value):
    return (value or "").strip()


def allowed_category(category):
    return category in CATEGORIES


def is_admin():
    return current_user.is_authenticated and current_user.username.lower() == ADMIN_USERNAME.lower()


def admin_required(view):
    from functools import wraps

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_admin():
            flash("Developer access only.", "error")
            return redirect(url_for("home"))
        return view(*args, **kwargs)
    return wrapped


def make_notification(user_id, message, link=""):
    db.session.add(Notification(
        user_id=user_id,
        message=message[:250],
        link=link[:200]
    ))


def unread_count():
    if not current_user.is_authenticated:
        return 0
    return Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()


def post_stats(post):
    ratings = [review.rating for review in post.reviews]
    average = round(sum(ratings) / len(ratings), 1) if ratings else 0
    return average, len(ratings)


def post_is_expired(post):
    return bool(post.expiry_date and post.expiry_date < date.today())


def display_status(post):
    if post_is_expired(post):
        return "Expired"
    return post.status


def verification_mark(user):
    return "🔵" if user.is_verified else ""


# ---------------- MAIN TEMPLATE ----------------

TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TEGRIDY MARKETPLACE</title>
<style>
:root{
 --green:#00ff88;--blue:#2997ff;--bg:#070907;--panel:#101510;--panel2:#151c15;
 --text:#f1fff5;--muted:#9db0a2;--danger:#ff5c5c;--border:#273b2c;
}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(circle at top,#102416 0%,var(--bg) 48%);color:var(--text);font-family:Arial,sans-serif;min-height:100vh}
a{text-decoration:none;color:inherit}
.container{width:min(1100px,92%);margin:auto}
nav{position:sticky;top:0;z-index:20;background:rgba(7,9,7,.94);backdrop-filter:blur(12px);border-bottom:1px solid var(--border)}
.nav-inner{min-height:68px;display:flex;align-items:center;justify-content:space-between;gap:12px}
.logo{font-size:1.1rem;font-weight:900;letter-spacing:1px;color:var(--green)}
.nav-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.hero{text-align:center;padding:58px 0 28px}
.hero h1{font-size:clamp(2.4rem,8vw,5rem);margin:12px 0;letter-spacing:2px;text-shadow:0 0 35px rgba(0,255,136,.25)}
.hero p{max-width:720px;margin:10px auto;color:var(--muted);line-height:1.6}
.card{background:linear-gradient(145deg,var(--panel),var(--panel2));border:1px solid var(--border);border-radius:18px;padding:20px;margin:15px 0;box-shadow:0 12px 32px rgba(0,0,0,.16)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:15px}
.btn{display:inline-block;border:0;border-radius:10px;padding:11px 16px;cursor:pointer;background:var(--green);color:#031108;font-weight:800}
.btn.secondary{background:#202a21;color:var(--text);border:1px solid var(--border)}
.btn.blue{background:var(--blue);color:white}
.btn.danger{background:var(--danger);color:white}
.badge{display:inline-block;padding:5px 10px;border-radius:99px;background:#1b2b1e;color:var(--green);font-size:.78rem;font-weight:bold}
.tick{color:var(--blue);font-size:.9em}
.muted{color:var(--muted)}.small{font-size:.88rem}.price{color:var(--green);font-size:1.1rem;font-weight:bold}
.search-bar{display:grid;grid-template-columns:1fr 180px auto;gap:8px}
input,select,textarea{width:100%;padding:12px;margin:6px 0;background:#080c08;color:var(--text);border:1px solid var(--border);border-radius:10px;font:inherit}
.flash{padding:12px 15px;border-radius:10px;margin:12px 0;background:#152019;border:1px solid var(--border)}
.error{color:#ff9a9a}
.post-top{display:flex;justify-content:space-between;gap:10px}
.post-actions{display:flex;gap:8px;margin-top:15px;flex-wrap:wrap}
.rating{color:#ffb84d}
.status-Available{color:var(--green)}.status-Full{color:#ffb84d}.status-Expired{color:var(--danger)}
.plus{position:fixed;right:22px;bottom:24px;width:62px;height:62px;border-radius:50%;background:var(--green);color:#031108;display:flex;align-items:center;justify-content:center;font-size:2.3rem;font-weight:300;box-shadow:0 10px 30px rgba(0,255,136,.3);z-index:30}
.plus:hover{transform:scale(1.06)}
.empty{text-align:center;padding:45px 20px;color:var(--muted)}
@media(max-width:650px){.nav-inner{padding:10px 0}.search-bar{grid-template-columns:1fr}.post-top{flex-direction:column}.nav-actions{justify-content:flex-end}}
</style>
</head>
<body>
<nav><div class="container nav-inner">
<a class="logo" href="{{ url_for('home') }}">🔥 TEGRIDY MARKET</a>
<div class="nav-actions">
{% if current_user.is_authenticated %}
<span class="muted small">@{{ current_user.username }} {% if current_user.is_verified %}<span class="tick">🔵</span>{% endif %}</span>
<a class="btn secondary" href="{{ url_for('dashboard') }}">Dashboard</a>
<a class="btn secondary" href="{{ url_for('favorites') }}">♥</a>
<a class="btn secondary" href="{{ url_for('notifications') }}">🔔{% if unread_count %} {{ unread_count }}{% endif %}</a>
{% if is_admin %}<a class="btn secondary" href="{{ url_for('developer') }}">Developer</a>{% endif %}
<a class="btn danger" href="{{ url_for('logout') }}">Logout</a>
{% else %}
<a class="btn secondary" href="{{ url_for('login') }}">Log In</a>
<a class="btn" href="{{ url_for('signup') }}">Sign Up</a>
{% endif %}
</div></div></nav>

<main class="container">
<section class="hero">
<span class="badge">👨‍👩‍👧‍👦 FAMILY SHARING COMMUNITY</span>
<h1>TEGRIDY FAMILY 🔥</h1>
<p>Discover and manage eligible digital family-plan spots in one community.</p>
<p class="small muted">Only share plans you are authorized to share and follow each platform's official terms. Never post passwords, payment information or one-time verification codes.</p>
</section>

{% with messages=get_flashed_messages(with_categories=true) %}
{% for category,message in messages %}<div class="flash {% if category=='error' %}error{% endif %}">{{ message }}</div>{% endfor %}
{% endwith %}

<section class="grid">
<div class="card"><h2>① Discover</h2><p class="muted">Find available spots by platform or category.</p></div>
<div class="card"><h2>② Request</h2><p class="muted">Send a private request instead of publishing sensitive information.</p></div>
<div class="card"><h2>③ Connect</h2><p class="muted">Use official invitations or approved access methods where available.</p></div>
</section>

<div class="card">
<h2>🔎 Find a Platform</h2>
<form class="search-bar" method="get">
<input name="q" value="{{ q }}" placeholder="Search a platform...">
<select name="category"><option value="">All categories</option>{% for item in categories %}<option value="{{ item }}" {% if category==item %}selected{% endif %}>{{ item }}</option>{% endfor %}</select>
<button class="btn">Search</button>
</form>
</div>

{% if trending_posts %}
<h2>🔥 Trending</h2><div class="grid">
{% for post in trending_posts %}
<div class="card"><span class="badge">{{ post.category }}</span><h2>{{ post.service }}</h2><p class="muted">by @{{ post.author.username }} {% if post.author.is_verified %}<span class="tick">🔵</span>{% endif %}</p><p class="status-{{ display_status(post) }}"><b>● {{ display_status(post) }}</b></p><a class="btn secondary" href="{{ url_for('post_detail',post_id=post.id) }}">View</a></div>
{% endfor %}
</div>{% endif %}

<h2>Available Platforms <span class="muted small">({{ posts|length }})</span></h2>
{% if posts %}<div class="grid">
{% for post in posts %}
<div class="card">
<div class="post-top"><div><span class="badge">{{ post.category }}</span><h2>{{ post.service }}</h2></div><div class="status-{{ display_status(post) }}"><b>● {{ display_status(post) }}</b></div></div>
{% if post.description %}<p>{{ post.description }}</p>{% endif %}
{% if post.expiry_date %}<p class="muted small">📅 Expiry: {{ post.expiry_date.strftime("%d %b %Y") }}</p>{% else %}<p class="muted small">📅 No expiry date provided</p>{% endif %}
<p class="muted small">Posted by <a href="{{ url_for('profile',username=post.author.username) }}">@{{ post.author.username }} {% if post.author.is_verified %}<span class="tick">🔵</span>{% endif %}</a></p>
<p class="rating">🔥 {{ stats[post.id]["average"] }}/6 <span class="muted">({{ stats[post.id]["count"] }} reviews)</span></p>
<div class="post-actions"><a class="btn secondary" href="{{ url_for('post_detail',post_id=post.id) }}">View Details</a>
{% if current_user.is_authenticated %}
<form method="post" action="{{ url_for('toggle_favorite',post_id=post.id) }}"><button class="btn secondary">{% if post.id in favorite_ids %}♥ Saved{% else %}♡ Save{% endif %}</button></form>
{% if current_user.id != post.user_id and display_status(post)=="Available" %}<a class="btn blue" href="{{ url_for('request_join',post_id=post.id) }}">Request Access</a>{% endif %}
{% endif %}
</div>
</div>
{% endfor %}
</div>{% else %}<div class="card empty"><h2>Nothing found 🔍</h2><p>Try another search or be the first to add a platform.</p></div>{% endif %}
</main>

{% if current_user.is_authenticated %}<a class="plus" href="{{ url_for('create_post') }}" title="Post a platform">＋</a>{% endif %}
<footer class="container" style="padding:35px 0 45px;text-align:center;color:var(--muted);font-size:.9rem">TEGRIDY MARKETPLACE · Responsible family-plan sharing community</footer>
</body></html>
"""


AUTH_TEMPLATE = r"""
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ title }} - TEGRIDY</title>
<style>body{margin:0;background:#070907;color:#f1fff5;font-family:Arial}.wrap{width:min(480px,92%);margin:60px auto}.card{background:#101510;border:1px solid #273b2c;border-radius:18px;padding:24px}input{width:100%;box-sizing:border-box;padding:13px;margin:7px 0;background:#080c08;color:white;border:1px solid #273b2c;border-radius:10px}.btn{padding:12px 16px;border:0;border-radius:10px;background:#00ff88;color:#031108;font-weight:bold}.muted{color:#9db0a2}a{color:#00ff88;text-decoration:none}.flash{padding:10px;margin:10px 0;border:1px solid #273b2c;border-radius:10px}</style></head>
<body><div class="wrap"><div class="card"><a href="{{ url_for('home') }}">← Back home</a><h1>{{ title }}</h1>
{% with messages=get_flashed_messages(with_categories=true) %}{% for c,m in messages %}<div class="flash">{{ m }}</div>{% endfor %}{% endwith %}
<form method="post">{{ fields|safe }}<button class="btn">{{ button }}</button></form><p class="muted">{{ footer|safe }}</p></div></div></body></html>
"""


POST_TEMPLATE = r"""
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Post Platform - TEGRIDY</title>
<style>body{background:#070907;color:#f1fff5;font-family:Arial;margin:0}.wrap{width:min(700px,92%);margin:40px auto}.card{background:#101510;border:1px solid #273b2c;border-radius:18px;padding:22px}input,select,textarea{width:100%;box-sizing:border-box;padding:12px;margin:7px 0;background:#080c08;color:white;border:1px solid #273b2c;border-radius:10px}textarea{min-height:110px}.btn{padding:11px 16px;border:0;border-radius:10px;background:#00ff88;color:#031108;font-weight:bold}.muted{color:#9db0a2}</style></head>
<body><div class="wrap"><div class="card"><a class="btn" href="{{ url_for('home') }}">← Home</a><h1>➕ Post a Platform</h1><p class="muted">Do not enter passwords, card details, or verification codes.</p>
<form method="post">
<input name="service" maxlength="100" placeholder="Platform name" value="{{ post.service if post else '' }}" required>
<select name="category">{% for item in categories %}<option value="{{ item }}" {% if post and post.category==item %}selected{% endif %}>{{ item }}</option>{% endfor %}</select>
<input name="contact" maxlength="120" placeholder="Contact email or invitation method" value="{{ post.contact if post else '' }}" required>
<input type="date" name="expiry_date" value="{{ post.expiry_date.isoformat() if post and post.expiry_date else '' }}">
<select name="status">{% for item in statuses %}<option value="{{ item }}" {% if post and post.status==item %}selected{% endif %}>{{ item }}</option>{% endfor %}</select>
<textarea name="description" maxlength="300" placeholder="Describe the eligible plan or available spot...">{{ post.description if post else '' }}</textarea>
<button class="btn">{{ "Save Changes" if post else "Post Platform" }}</button>
</form></div></div></body></html>
"""


PROFILE_TEMPLATE = r"""
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ user.username }} - TEGRIDY</title>
<style>body{background:#070907;color:#f1fff5;font-family:Arial}.wrap{width:min(850px,92%);margin:35px auto}.card{background:#101510;border:1px solid #273b2c;border-radius:16px;padding:20px;margin:14px 0}.btn{display:inline-block;padding:10px 14px;border-radius:9px;background:#00ff88;color:#031108;text-decoration:none;font-weight:bold}.muted{color:#9db0a2}.tick{color:#2997ff}</style></head>
<body><div class="wrap"><a class="btn" href="{{ url_for('home') }}">← Home</a><div class="card"><h1>👤 @{{ user.username }} {% if user.is_verified %}<span class="tick">🔵 Verified</span>{% endif %}</h1><p class="muted">Member since {{ user.created_at.strftime("%Y-%m-%d") }}</p><p><b>{{ user.posts|length }}</b> Posts · <b>{{ user.reviews|length }}</b> Reviews</p></div><h2>Platforms</h2>{% for post in user.posts %}<div class="card"><h3>{{ post.service }}</h3><p>{{ post.category }} · {{ display_status(post) }}</p><a class="btn" href="{{ url_for('post_detail',post_id=post.id) }}">View</a></div>{% else %}<div class="card muted">No posts yet.</div>{% endfor %}</div></body></html>
"""


DETAIL_TEMPLATE = r"""
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ post.service }} - TEGRIDY</title>
<style>body{background:#070907;color:#f1fff5;font-family:Arial}.wrap{width:min(800px,92%);margin:35px auto}.card{background:#101510;border:1px solid #273b2c;border-radius:16px;padding:22px;margin:15px 0}.btn{display:inline-block;padding:10px 14px;border-radius:9px;background:#00ff88;color:#031108;text-decoration:none;font-weight:bold;border:0}.muted{color:#9db0a2}.blue{background:#2997ff;color:white}.tick{color:#2997ff}</style></head>
<body><div class="wrap"><a class="btn" href="{{ url_for('home') }}">← Home</a><div class="card"><h1>{{ post.service }}</h1><p>{{ post.description or "No description provided." }}</p><p><b>Category:</b> {{ post.category }}</p><p><b>Status:</b> {{ display_status(post) }}</p>{% if post.expiry_date %}<p><b>Expiry:</b> {{ post.expiry_date.strftime("%d %B %Y") }}</p>{% endif %}<p class="muted">Posted by <a href="{{ url_for('profile',username=post.author.username) }}">@{{ post.author.username }} {% if post.author.is_verified %}<span class="tick">🔵</span>{% endif %}</a></p>{% if current_user.is_authenticated and current_user.id != post.user_id and display_status(post)=="Available" %}<a class="btn blue" href="{{ url_for('request_join',post_id=post.id) }}">Request Access</a>{% endif %}</div>
<div class="card"><h2>Reviews</h2>{% for r in post.reviews %}<p>🔥 {{ r.rating }}/6 — {{ r.comment }} <span class="muted">by @{{ r.reviewer.username }}</span></p>{% else %}<p class="muted">No reviews yet.</p>{% endfor %}</div></div></body></html>
"""


REQUEST_TEMPLATE = r"""
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Request Access</title><style>body{background:#070907;color:#f1fff5;font-family:Arial}.wrap{width:min(600px,92%);margin:40px auto}.card{background:#101510;border:1px solid #273b2c;border-radius:16px;padding:20px}textarea{width:100%;box-sizing:border-box;padding:12px;background:#080c08;color:white;border:1px solid #273b2c;border-radius:10px;min-height:100px}.btn{padding:11px 16px;border:0;border-radius:10px;background:#00ff88;font-weight:bold}</style></head><body><div class="wrap"><div class="card"><h1>Request access to {{ post.service }}</h1><form method="post"><textarea name="message" maxlength="300" placeholder="Optional message to the post owner"></textarea><br><button class="btn">Send Request</button></form></div></div></body></html>
"""


DASHBOARD_TEMPLATE = r"""
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Dashboard - TEGRIDY</title><style>body{background:#070907;color:#f1fff5;font-family:Arial}.wrap{width:min(1000px,92%);margin:35px auto}.card{background:#101510;border:1px solid #273b2c;border-radius:16px;padding:20px;margin:14px 0}.btn{display:inline-block;padding:10px 14px;border-radius:9px;background:#00ff88;color:#031108;text-decoration:none;font-weight:bold}.muted{color:#9db0a2}.danger{background:#ff5c5c;color:white}</style></head>
<body><div class="wrap"><a class="btn" href="{{ url_for('home') }}">← Home</a><h1>My Dashboard</h1>
<div class="card"><h2>My Platforms</h2>{% for post in my_posts %}<p><b>{{ post.service }}</b> · {{ display_status(post) }} · <a href="{{ url_for('edit_post',post_id=post.id) }}">Edit</a></p>{% else %}<p class="muted">No platforms posted yet.</p>{% endfor %}</div>
<div class="card"><h2>Incoming Requests</h2>{% for item in incoming %}<div style="border-bottom:1px solid #273b2c;padding:10px 0"><b>@{{ item.requester.username }}</b> requested {{ item.requested_post.service }} · {{ item.status }}<br><span class="muted">{{ item.message }}</span>{% if item.status=="Pending" %}<p><a class="btn" href="{{ url_for('respond_request',request_id=item.id,response='Accepted') }}">Accept</a> <a class="btn danger" href="{{ url_for('respond_request',request_id=item.id,response='Rejected') }}">Reject</a></p>{% endif %}</div>{% else %}<p class="muted">No incoming requests.</p>{% endfor %}</div>
<div class="card"><h2>My Requests</h2>{% for item in outgoing %}<p>{{ item.requested_post.service }} — <b>{{ item.status }}</b></p>{% else %}<p class="muted">No requests sent.</p>{% endfor %}</div></div></body></html>
"""


DEVELOPER_TEMPLATE = r"""
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Developer Panel</title><style>body{margin:0;background:#070907;color:#f1fff5;font-family:Arial}.wrap{width:min(1100px,94%);margin:30px auto}.card{background:#101510;border:1px solid #273b2c;border-radius:15px;padding:18px;margin:15px 0}.btn{padding:9px 13px;border:0;border-radius:9px;background:#00ff88;color:#031108;font-weight:bold;cursor:pointer;text-decoration:none}.blue{background:#2997ff;color:white}.danger{background:#ff5c5c;color:white}.muted{color:#9db0a2}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px;border-bottom:1px solid #273b2c}</style></head>
<body><div class="wrap"><a class="btn" href="{{ url_for('home') }}">← Home</a><h1>🛠️ TEGRIDY DEVELOPER PANEL</h1>
<div class="card"><h2>Users</h2><table><tr><th>User</th><th>Email</th><th>Verified</th><th>Action</th></tr>{% for user in users %}<tr><td>@{{ user.username }}</td><td>{{ user.email }}</td><td>{% if user.is_verified %}🔵 Verified{% else %}Not verified{% endif %}</td><td><form method="post" action="{{ url_for('toggle_verify_user',user_id=user.id) }}"><button class="btn {% if not user.is_verified %}blue{% endif %}">{% if user.is_verified %}Remove Tick{% else %}Verify 🔵{% endif %}</button></form></td></tr>{% endfor %}</table></div>
<div class="card"><h2>Moderate Posts</h2>{% for post in posts %}<p><b>{{ post.service }}</b> by @{{ post.author.username }} <a href="{{ url_for('developer_delete_post',post_id=post.id) }}">Delete</a></p>{% endfor %}</div></div></body></html>
"""


# ---------------- ROUTES ----------------

@app.route("/")
def home():
    q = clean(request.args.get("q"))
    category = clean(request.args.get("category"))
    query = Post.query

    if q:
        query = query.filter(
            Post.service.ilike(f"%{q}%") |
            Post.description.ilike(f"%{q}%")
        )

    if category and allowed_category(category):
        query = query.filter_by(category=category)

    posts = query.order_by(Post.created_at.desc()).all()
    stats = {}
    for post in posts:
        average, count = post_stats(post)
        stats[post.id] = {"average": average, "count": count}

    def trend(post):
        avg, count = post_stats(post)
        return avg * 2 + count

    favorite_ids = set()
    if current_user.is_authenticated:
        favorite_ids = {f.post_id for f in Favorite.query.filter_by(user_id=current_user.id).all()}

    return render_template_string(
        TEMPLATE,
        posts=posts, stats=stats, q=q, category=category,
        categories=CATEGORIES, favorite_ids=favorite_ids,
        unread_count=unread_count(), trending_posts=sorted(posts, key=trend, reverse=True)[:3],
        is_admin=is_admin(), display_status=display_status
    )


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = clean(request.form.get("username"))
        email = clean(request.form.get("email")).lower()
        password = request.form.get("password") or ""

        if len(username) < 3 or len(username) > 30:
            flash("Username must be between 3 and 30 characters.", "error")
        elif "@" not in email or len(email) > 120:
            flash("Enter a valid email address.", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif User.query.filter_by(username=username).first():
            flash("That username is already taken.", "error")
        elif User.query.filter_by(email=email).first():
            flash("That email is already registered.", "error")
        else:
            user = User(
                username=username,
                email=email,
                password=generate_password_hash(password)
            )
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Account created successfully! Welcome to TEGRIDY 🔥")
            return redirect(url_for("home"))

    fields = '<input name="username" maxlength="30" placeholder="Username" required><input name="email" type="email" maxlength="120" placeholder="Email address" required><input name="password" type="password" minlength="6" placeholder="Password (minimum 6 characters)" required>'
    return render_template_string(AUTH_TEMPLATE, title="Create Account", fields=fields, button="Sign Up", footer='Already have an account? <a href="/login">Log In</a>')


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identity = clean(request.form.get("identity"))
        password = request.form.get("password") or ""
        user = User.query.filter(
            (User.username == identity) | (User.email == identity.lower())
        ).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            flash("Welcome back! 🔥")
            return redirect(url_for("home"))

        flash("Incorrect username/email or password.", "error")

    fields = '<input name="identity" placeholder="Username or email" required><input name="password" type="password" placeholder="Password" required>'
    return render_template_string(AUTH_TEMPLATE, title="Log In", fields=fields, button="Log In", footer='New here? <a href="/signup">Create an account</a>')


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.")
    return redirect(url_for("home"))


@app.route("/post", methods=["GET", "POST"])
@login_required
def create_post():
    if request.method == "POST":
        service = clean(request.form.get("service"))
        category = clean(request.form.get("category"))
        contact = clean(request.form.get("contact"))
        expiry_raw = clean(request.form.get("expiry_date"))
        description = clean(request.form.get("description"))
        status = clean(request.form.get("status"))

        expiry_date = None
        if expiry_raw:
            try:
                expiry_date = datetime.strptime(expiry_raw, "%Y-%m-%d").date()
            except ValueError:
                flash("Invalid expiry date.", "error")
                return redirect(url_for("create_post"))

        if not service or not contact:
            flash("Platform name and contact/invitation method are required.", "error")
            return redirect(url_for("create_post"))

        post = Post(
            service=service[:100],
            category=category if allowed_category(category) else "Other",
            contact=contact[:120],
            expiry_date=expiry_date,
            description=description[:300],
            status=status if status in STATUSES else "Available",
            user_id=current_user.id
        )
        db.session.add(post)
        db.session.commit()
        flash("Platform posted successfully! 🔥")
        return redirect(url_for("home"))

    return render_template_string(POST_TEMPLATE, post=None, categories=CATEGORIES, statuses=STATUSES)


@app.route("/post/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def edit_post(post_id):
    post = db.get_or_404(Post, post_id)
    if post.user_id != current_user.id and not is_admin():
        flash("You can only edit your own posts.", "error")
        return redirect(url_for("home"))

    if request.method == "POST":
        post.service = clean(request.form.get("service"))[:100]
        category = clean(request.form.get("category"))
        post.category = category if allowed_category(category) else "Other"
        post.contact = clean(request.form.get("contact"))[:120]
        post.description = clean(request.form.get("description"))[:300]
        status = clean(request.form.get("status"))
        post.status = status if status in STATUSES else "Available"

        expiry_raw = clean(request.form.get("expiry_date"))
        if expiry_raw:
            try:
                post.expiry_date = datetime.strptime(expiry_raw, "%Y-%m-%d").date()
            except ValueError:
                flash("Invalid expiry date.", "error")
                return redirect(url_for("edit_post", post_id=post.id))
        else:
            post.expiry_date = None

        db.session.commit()
        flash("Platform updated.")
        return redirect(url_for("dashboard"))

    return render_template_string(POST_TEMPLATE, post=post, categories=CATEGORIES, statuses=STATUSES)


@app.route("/spot/<int:post_id>")
def post_detail(post_id):
    post = db.get_or_404(Post, post_id)
    return render_template_string(DETAIL_TEMPLATE, post=post, display_status=display_status)


@app.route("/join/<int:post_id>", methods=["GET", "POST"])
@login_required
def request_join(post_id):
    post = db.get_or_404(Post, post_id)

    if post.user_id == current_user.id:
        flash("You cannot request your own post.", "error")
        return redirect(url_for("post_detail", post_id=post.id))

    if display_status(post) != "Available":
        flash("This platform is not currently available.", "error")
        return redirect(url_for("post_detail", post_id=post.id))

    existing = JoinRequest.query.filter_by(
        requester_id=current_user.id,
        post_id=post.id
    ).first()

    if request.method == "POST":
        if existing:
            flash("You already requested this platform.", "error")
        else:
            item = JoinRequest(
                requester_id=current_user.id,
                post_id=post.id,
                message=clean(request.form.get("message"))[:300]
            )
            db.session.add(item)
            make_notification(post.user_id, f"@{current_user.username} requested access to {post.service}.", url_for("dashboard"))
            db.session.commit()
            flash("Your request was sent.")
        return redirect(url_for("dashboard"))

    if existing:
        flash("You already requested this platform.", "error")
        return redirect(url_for("dashboard"))

    return render_template_string(REQUEST_TEMPLATE, post=post)


@app.route("/request/<int:request_id>/<response>")
@login_required
def respond_request(request_id, response):
    item = db.get_or_404(JoinRequest, request_id)

    if item.requested_post.user_id != current_user.id:
        flash("You cannot manage this request.", "error")
        return redirect(url_for("dashboard"))

    if response not in {"Accepted", "Rejected"} or item.status != "Pending":
        return redirect(url_for("dashboard"))

    item.status = response
    make_notification(
        item.requester_id,
        f"Your request for {item.requested_post.service} was {response.lower()}.",
        url_for("dashboard")
    )
    db.session.commit()
    flash(f"Request {response.lower()}.")
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
@login_required
def dashboard():
    my_posts = Post.query.filter_by(user_id=current_user.id).order_by(Post.created_at.desc()).all()
    incoming = JoinRequest.query.join(Post).filter(Post.user_id == current_user.id).order_by(JoinRequest.created_at.desc()).all()
    outgoing = JoinRequest.query.filter_by(requester_id=current_user.id).order_by(JoinRequest.created_at.desc()).all()
    return render_template_string(
        DASHBOARD_TEMPLATE,
        my_posts=my_posts, incoming=incoming, outgoing=outgoing,
        display_status=display_status
    )


@app.route("/favorite/<int:post_id>", methods=["POST"])
@login_required
def toggle_favorite(post_id):
    db.get_or_404(Post, post_id)
    favorite = Favorite.query.filter_by(user_id=current_user.id, post_id=post_id).first()
    if favorite:
        db.session.delete(favorite)
        flash("Removed from favorites.")
    else:
        db.session.add(Favorite(user_id=current_user.id, post_id=post_id))
        flash("Saved to favorites! ♥")
    db.session.commit()
    return redirect(request.referrer or url_for("home"))


@app.route("/favorites")
@login_required
def favorites():
    saved = Favorite.query.filter_by(user_id=current_user.id).all()
    posts = [db.session.get(Post, item.post_id) for item in saved]
    posts = [p for p in posts if p]
    html = """
    <html><body style='background:#070907;color:#f1fff5;font-family:Arial'><div style='width:min(850px,92%);margin:35px auto'>
    <a href='/' style='color:#00ff88'>← Home</a><h1>♥ My Favorites</h1>
    {% for post in posts %}<div style='padding:18px;border:1px solid #273b2c;border-radius:14px;margin:12px 0'><h2>{{ post.service }}</h2><p>{{ post.category }}</p><a href='{{ url_for("post_detail",post_id=post.id) }}' style='color:#00ff88'>View</a></div>{% else %}<p>No favorites yet.</p>{% endfor %}
    </div></body></html>
    """
    return render_template_string(html, posts=posts)


@app.route("/review/<int:post_id>", methods=["POST"])
@login_required
def review_post(post_id):
    post = db.get_or_404(Post, post_id)
    if post.user_id == current_user.id:
        flash("You cannot review your own post.", "error")
        return redirect(url_for("post_detail", post_id=post.id))

    try:
        rating = int(request.form.get("rating", 0))
    except ValueError:
        rating = 0

    if rating < 1 or rating > 6:
        flash("Rating must be between 1 and 6.", "error")
        return redirect(url_for("post_detail", post_id=post.id))

    review = Review.query.filter_by(post_id=post.id, user_id=current_user.id).first()
    if review:
        review.rating = rating
        review.comment = clean(request.form.get("comment"))[:200]
    else:
        db.session.add(Review(
            post_id=post.id,
            user_id=current_user.id,
            rating=rating,
            comment=clean(request.form.get("comment"))[:200]
        ))
    db.session.commit()
    flash("Review saved.")
    return redirect(url_for("post_detail", post_id=post.id))


@app.route("/user/<username>")
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    return render_template_string(PROFILE_TEMPLATE, user=user, display_status=display_status)


@app.route("/notifications")
@login_required
def notifications():
    items = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).all()
    for item in items:
        item.is_read = True
    db.session.commit()

    html = """
    <html><body style='background:#070907;color:#f1fff5;font-family:Arial'><div style='width:min(800px,92%);margin:35px auto'><a href='/' style='color:#00ff88'>← Home</a><h1>🔔 Notifications</h1>
    {% for item in items %}<div style='padding:18px;border:1px solid #273b2c;border-radius:14px;margin:10px 0'>{{ item.message }}<br><small style='color:#9db0a2'>{{ item.created_at.strftime("%Y-%m-%d %H:%M") }}</small></div>{% else %}<p>No notifications yet.</p>{% endfor %}
    </div></body></html>
    """
    return render_template_string(html, items=items)


# ---------------- DEVELOPER PANEL ----------------

@app.route("/developer")
@login_required
@admin_required
def developer():
    users = User.query.order_by(User.created_at.desc()).all()
    posts = Post.query.order_by(Post.created_at.desc()).all()
    return render_template_string(DEVELOPER_TEMPLATE, users=users, posts=posts)


@app.route("/developer/user/<int:user_id>/verify", methods=["POST"])
@login_required
@admin_required
def toggle_verify_user(user_id):
    user = db.get_or_404(User, user_id)
    user.is_verified = not user.is_verified
    db.session.commit()
    flash(f"Verification updated for @{user.username}.")
    return redirect(url_for("developer"))


@app.route("/developer/post/<int:post_id>/delete")
@login_required
@admin_required
def developer_delete_post(post_id):
    post = db.get_or_404(Post, post_id)
    db.session.delete(post)
    db.session.commit()
    flash("Post deleted.")
    return redirect(url_for("developer"))


# ---------------- STARTUP ----------------

def migrate_legacy_database():
    """Best-effort migration for old SQLite installs."""
    if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        return
    try:
        with db.engine.connect() as conn:
            columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(user)")}
            if "email" not in columns:
                conn.exec_driver_sql("ALTER TABLE user ADD COLUMN email VARCHAR(120)")
                conn.exec_driver_sql("UPDATE user SET email = username || '@legacy.tegridy.local' WHERE email IS NULL")
            if "is_verified" not in columns:
                conn.exec_driver_sql("ALTER TABLE user ADD COLUMN is_verified BOOLEAN DEFAULT 0")
            post_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(post)")}
            if "expiry_date" not in post_columns:
                conn.exec_driver_sql("ALTER TABLE post ADD COLUMN expiry_date DATE")
            if "status" not in post_columns:
                conn.exec_driver_sql("ALTER TABLE post ADD COLUMN status VARCHAR(20) DEFAULT 'Available'")
            conn.commit()
    except Exception as exc:
        print("Legacy migration skipped:", exc)


def ensure_developer_account():
    admin = User.query.filter_by(username=ADMIN_USERNAME).first()
    admin_password = os.environ.get("ADMIN_PASSWORD")

    if admin is None and admin_password:
        admin = User(
            username=ADMIN_USERNAME,
            email=os.environ.get("ADMIN_EMAIL", f"{ADMIN_USERNAME.lower()}@tegridy.local"),
            password=generate_password_hash(admin_password),
            is_verified=True
        )
        db.session.add(admin)
        db.session.commit()
        print(f"Developer account @{ADMIN_USERNAME} created.")
    elif admin:
        admin.is_verified = True
        db.session.commit()


with app.app_context():
    db.create_all()
    migrate_legacy_database()
    db.create_all()
    ensure_developer_account()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
