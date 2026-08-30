import os
from datetime import datetime

from flask import Flask, render_template_string, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, login_required,
    logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import UniqueConstraint

app = Flask(__name__)

# Use an environment variable in production:
# export SECRET_KEY="your-long-random-secret"
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-before-production")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///tegridy_v2.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = "home"


# ---------------- DATABASE ----------------

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False, index=True)
    password = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    posts = db.relationship(
        "Post", backref="author", lazy=True, cascade="all, delete-orphan"
    )
    reviews = db.relationship(
        "Review", backref="reviewer", lazy=True, cascade="all, delete-orphan"
    )


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    service = db.Column(db.String(100), nullable=False, index=True)
    category = db.Column(db.String(50), nullable=False, default="Other")
    price = db.Column(db.String(50), nullable=False)
    contact = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(300), nullable=False, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    reviews = db.relationship(
        "Review", backref="post", lazy=True, cascade="all, delete-orphan"
    )


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
    __table_args__ = (UniqueConstraint("user_id", "post_id", name="one_favorite_per_user_post"),)


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


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ---------------- HELPERS ----------------

def clean(value):
    return (value or "").strip()


def post_stats(post):
    ratings = [review.rating for review in post.reviews]
    average = round(sum(ratings) / len(ratings), 1) if ratings else 0
    return average, len(ratings)


def allowed_category(category):
    return category in {"Streaming", "Music", "Gaming", "Software", "Other"}


def make_notification(user_id, message, link=""):
    db.session.add(Notification(user_id=user_id, message=message[:250], link=link[:200]))


def trending_score(post):
    ratings = [r.rating for r in post.reviews]
    avg = sum(ratings) / len(ratings) if ratings else 0
    return (avg * 2) + len(ratings)


def current_unread_count():
    if not current_user.is_authenticated:
        return 0
    return Notification.query.filter_by(user_id=current_user.id, is_read=False).count()


# ---------------- ADMIN / DEVELOPER ----------------
# IMPORTANT: Change YOUR_ADMIN_USERNAME to your actual username.
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "Rick44")

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


# ---------------- UI ----------------

TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<title>TEGRIDY MARKETPLACE</title>

<style>
:root{
    --green:#00ff88;
    --green-dark:#00b85c;
    --bg:#070907;
    --panel:#101510;
    --panel2:#151c15;
    --text:#f1fff5;
    --muted:#9db0a2;
    --danger:#ff5c5c;
    --border:#273b2c;
}

*{box-sizing:border-box}

body{
    margin:0;
    background:radial-gradient(circle at top,#102416 0%,var(--bg) 45%);
    color:var(--text);
    font-family:Arial,sans-serif;
    min-height:100vh;
}

a{color:inherit;text-decoration:none}

.container{
    width:min(1050px,92%);
    margin:auto;
}

nav{
    border-bottom:1px solid var(--border);
    background:rgba(7,9,7,.92);
    position:sticky;
    top:0;
    z-index:10;
    backdrop-filter:blur(10px);
}

.nav-inner{
    min-height:68px;
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:15px;
}

.logo{
    font-weight:900;
    letter-spacing:1px;
    color:var(--green);
    font-size:1.15rem;
}

.nav-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}

.hero{
    padding:45px 0 25px;
    text-align:center;
}

.hero h1{
    margin:0;
    font-size:clamp(2rem,7vw,4.5rem);
    letter-spacing:2px;
    text-shadow:0 0 30px rgba(0,255,136,.28);
}

.hero p{color:var(--muted);max-width:650px;margin:12px auto}

.card{
    background:linear-gradient(145deg,var(--panel),var(--panel2));
    border:1px solid var(--border);
    border-radius:16px;
    padding:20px;
    margin:15px 0;
    box-shadow:0 10px 30px rgba(0,0,0,.18);
}

.grid{
    display:grid;
    grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
    gap:15px;
}

input,select,textarea{
    width:100%;
    padding:12px;
    margin:6px 0;
    background:#080c08;
    color:var(--text);
    border:1px solid var(--border);
    border-radius:10px;
    font:inherit;
}

textarea{min-height:90px;resize:vertical}

.btn{
    display:inline-block;
    border:0;
    border-radius:10px;
    padding:11px 16px;
    cursor:pointer;
    background:var(--green);
    color:#031108;
    font-weight:800;
}

.btn:hover{filter:brightness(1.1)}

.btn.secondary{
    background:#202a21;
    color:var(--text);
    border:1px solid var(--border);
}

.btn.danger{background:var(--danger);color:white}

.inline-form{display:inline}

.muted{color:var(--muted)}
.small{font-size:.88rem}
.error{color:#ff8b8b}

.flash{
    padding:12px 15px;
    border-radius:10px;
    margin:12px 0;
    border:1px solid var(--border);
    background:#152019;
}

.post-top{
    display:flex;
    justify-content:space-between;
    align-items:flex-start;
    gap:10px;
}

.badge{
    display:inline-block;
    padding:5px 9px;
    border-radius:99px;
    background:#1b2b1e;
    color:var(--green);
    font-size:.78rem;
    font-weight:bold;
}

.price{
    font-size:1.15rem;
    color:var(--green);
    font-weight:bold;
}

.rating{color:#ffb84d;font-size:1rem}

.post-actions{
    display:flex;
    gap:8px;
    margin-top:15px;
    flex-wrap:wrap;
}

.review{
    padding:10px 0;
    border-top:1px solid var(--border);
}

.search-bar{
    display:grid;
    grid-template-columns:1fr 170px auto;
    gap:8px;
}

.empty{
    text-align:center;
    padding:45px 20px;
    color:var(--muted);
}

@media(max-width:650px){
    .search-bar{grid-template-columns:1fr}
    .nav-inner{padding:10px 0}
    .post-top{flex-direction:column}
}
</style>
</head>

<body>

<nav>
<div class="container nav-inner">
    <a class="logo" href="{{ url_for('home') }}">🔥 TEGRIDY MARKET</a>

    <div class="nav-actions">
    {% if current_user.is_authenticated %}
        <span class="muted small">👋 {{ current_user.username }}</span>
        <a class="btn secondary" href="#post-form">Post Spot</a>
        <a class="btn secondary" href="{{ url_for('favorites') }}">♥ Favorites</a>
        <a class="btn secondary" href="{{ url_for('notifications') }}">🔔 {% if unread_count %}{{ unread_count }}{% endif %}</a>
        <a class="btn secondary" href="{{ url_for('profile', username=current_user.username) }}">Profile</a>
        {% if current_user.username.lower() == admin_username.lower() %}
        <a class="btn secondary" href="{{ url_for('developer') }}">Developer</a>
        {% endif %}
        <a class="btn danger" href="{{ url_for('logout') }}">Logout</a>
    {% else %}
        <a class="btn secondary" href="#auth">Login / Sign Up</a>
    {% endif %}
    </div>
</div>
</nav>

<main class="container">

<section class="hero">
    <h1>TEGRIDY FAMILY 🔥</h1>
    <p>Find, share and review digital service spots in one community marketplace.</p>
</section>

{% with messages = get_flashed_messages(with_categories=true) %}
{% for category, message in messages %}
<div class="flash {% if category == 'error' %}error{% endif %}">{{ message }}</div>
{% endfor %}
{% endwith %}

{% if current_user.is_authenticated %}
<div class="card" id="post-form">
    <h2>🚀 Post a Spot</h2>
    <form method="post" action="{{ url_for('create_post') }}">
        <div class="grid">
            <input name="service" maxlength="100" placeholder="Service name (Netflix, Spotify...)" required>
            <select name="category" required>
                <option value="Streaming">Streaming</option>
                <option value="Music">Music</option>
                <option value="Gaming">Gaming</option>
                <option value="Software">Software</option>
                <option value="Other">Other</option>
            </select>
        </div>
        <div class="grid">
            <input name="price" maxlength="50" placeholder="Price (example: $3/month)" required>
            <input name="contact" maxlength="100" placeholder="Contact details" required>
        </div>
        <textarea name="description" maxlength="300" placeholder="Describe what you are offering..."></textarea>
        <button class="btn" type="submit">POST SPOT 🔥</button>
    </form>
</div>
{% else %}
<div class="grid" id="auth">
    <div class="card">
        <h2>Login</h2>
        <form method="post" action="{{ url_for('login') }}">
            <input name="username" maxlength="30" placeholder="Username" required>
            <input name="password" type="password" placeholder="Password" required>
            <button class="btn">Login</button>
        </form>
    </div>

    <div class="card">
        <h2>Create Account</h2>
        <form method="post" action="{{ url_for('signup') }}">
            <input name="username" maxlength="30" placeholder="Username" required>
            <input name="password" type="password" minlength="6" placeholder="Password (minimum 6 characters)" required>
            <button class="btn">Sign Up</button>
        </form>
    </div>
</div>
{% endif %}

<div class="card">
    <h2>🔎 Find a Spot</h2>
    <form class="search-bar" method="get">
        <input name="q" value="{{ q }}" placeholder="Search Netflix, Spotify, gaming...">
        <select name="category">
            <option value="">All categories</option>
            {% for item in categories %}
            <option value="{{ item }}" {% if category == item %}selected{% endif %}>{{ item }}</option>
            {% endfor %}
        </select>
        <button class="btn">Search</button>
    </form>
</div>

{% if trending_posts %}
<h2>🔥 Trending Spots</h2>
<div class="grid">
{% for post in trending_posts %}
<div class="card">
<span class="badge">🔥 Trending</span>
<h2>{{ post.service }}</h2>
<p class="price">{{ post.price }}</p>
<p class="muted">by @{{ post.author.username }}</p>
<a class="btn secondary" href="{{ url_for('post_detail', post_id=post.id) }}">View Spot</a>
</div>
{% endfor %}
</div>
{% endif %}

<h2>Available Spots <span class="muted small">({{ posts|length }})</span></h2>

{% if posts %}
<div class="grid">
{% for post in posts %}
<div class="card">

    <div class="post-top">
        <div>
            <span class="badge">{{ post.category }}</span>
            <h2>{{ post.service }}</h2>
        </div>
        <div class="price">{{ post.price }}</div>
    </div>

    {% if post.description %}
        <p>{{ post.description }}</p>
    {% endif %}

    <p><b>Contact:</b> {{ post.contact }}</p>
    <p class="muted small">Posted by <a href="{{ url_for('profile', username=post.author.username) }}">@{{ post.author.username }}</a></p>
    <div class="post-actions">
        <a class="btn secondary" href="{{ url_for('post_detail', post_id=post.id) }}">View Details</a>
        {% if current_user.is_authenticated %}
        <form class="inline-form" method="post" action="{{ url_for('toggle_favorite', post_id=post.id) }}">
            <button class="btn secondary">{% if post.id in favorite_ids %}♥ Saved{% else %}♡ Save{% endif %}</button>
        </form>
        {% if current_user.id != post.user_id %}
        <a class="btn secondary" href="{{ url_for('report_post', post_id=post.id) }}">🚩 Report</a>
        {% endif %}
        {% endif %}
    </div>

    <p class="rating">
        🔥 {{ stats[post.id]["average"] }}/6
        <span class="muted">({{ stats[post.id]["count"] }} review{{ '' if stats[post.id]["count"] == 1 else 's' }})</span>
    </p>

    {% if current_user.is_authenticated and current_user.id == post.user_id %}
    <div class="post-actions">
        <a class="btn secondary" href="{{ url_for('edit_post', post_id=post.id) }}">Edit</a>
        <form class="inline-form" method="post" action="{{ url_for('delete_post', post_id=post.id) }}" onsubmit="return confirm('Delete this post?')">
            <button class="btn danger">Delete</button>
        </form>
    </div>
    {% endif %}

    <h3>Reviews</h3>

    {% if post.reviews %}
        {% for review in post.reviews|sort(attribute='created_at', reverse=true) %}
        <div class="review">
            <div class="rating">🔥 {{ review.rating }}/6</div>
            {% if review.comment %}<div>{{ review.comment }}</div>{% endif %}
            <div class="muted small">by @{{ review.reviewer.username }}</div>

            {% if current_user.is_authenticated and current_user.id == review.user_id %}
            <form class="inline-form" method="post" action="{{ url_for('delete_review', review_id=review.id) }}">
                <button class="btn secondary small">Delete review</button>
            </form>
            {% endif %}
        </div>
        {% endfor %}
    {% else %}
        <p class="muted small">No reviews yet. Be the first.</p>
    {% endif %}

    {% if current_user.is_authenticated and current_user.id != post.user_id %}
    <form method="post" action="{{ url_for('review_post', post_id=post.id) }}">
        <select name="rating" required>
            <option value="1">🔥 1 Fire</option>
            <option value="2">🔥🔥 2 Fire</option>
            <option value="3">🔥🔥🔥 3 Fire</option>
            <option value="4">🔥🔥🔥🔥 4 Fire</option>
            <option value="5">🔥🔥🔥🔥🔥 5 Fire</option>
            <option value="6">🔥🔥🔥🔥🔥🔥 6 Fire</option>
        </select>
        <input name="comment" maxlength="200" placeholder="Write a review...">
        <button class="btn">Save Review</button>
    </form>
    {% endif %}

</div>
{% endfor %}
</div>

{% else %}
<div class="card empty">
    <h2>Nothing found 🔍</h2>
    <p>Try another search or category, or be the first to post a spot.</p>
</div>
{% endif %}

</main>
</body>
</html>
"""


EDIT_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Edit Spot - TEGRIDY</title>
<style>
body{background:#070907;color:#f1fff5;font-family:Arial;margin:0}
.container{width:min(700px,92%);margin:40px auto}
.card{background:#101510;border:1px solid #273b2c;border-radius:16px;padding:20px}
input,select,textarea{width:100%;box-sizing:border-box;padding:12px;margin:6px 0;background:#080c08;color:white;border:1px solid #273b2c;border-radius:10px}
textarea{min-height:100px}
.btn{padding:11px 16px;border:0;border-radius:10px;background:#00ff88;color:#031108;font-weight:bold;cursor:pointer}
.btn.secondary{background:#202a21;color:white}
</style>
</head>
<body>
<div class="container">
<div class="card">
<h1>Edit Spot</h1>
<form method="post">
<input name="service" maxlength="100" value="{{ post.service }}" required>
<select name="category">
{% for item in categories %}
<option value="{{ item }}" {% if post.category == item %}selected{% endif %}>{{ item }}</option>
{% endfor %}
</select>
<input name="price" maxlength="50" value="{{ post.price }}" required>
<input name="contact" maxlength="100" value="{{ post.contact }}" required>
<textarea name="description" maxlength="300">{{ post.description }}</textarea>
<button class="btn">Save Changes</button>
<a class="btn secondary" href="{{ url_for('home') }}">Cancel</a>
</form>
</div>
</div>
</body>
</html>
"""



DEVELOPER_TEMPLATE = r"""
<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Developer Panel</title>
<style>
body{margin:0;background:#070907;color:#f1fff5;font-family:Arial}.container{width:min(1100px,94%);margin:30px auto}.top{display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap}.card{background:#101510;border:1px solid #273b2c;border-radius:15px;padding:18px;margin:15px 0}.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}.stat{background:#151c15;border:1px solid #273b2c;border-radius:12px;padding:16px}.number{font-size:2rem;color:#00ff88;font-weight:bold}.muted{color:#9db0a2}.btn{display:inline-block;padding:9px 13px;border:0;border-radius:9px;background:#00ff88;color:#031108;font-weight:bold;cursor:pointer;text-decoration:none}.danger{background:#ff5c5c;color:white}.secondary{background:#202a21;color:white;border:1px solid #273b2c}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:11px;border-bottom:1px solid #273b2c;vertical-align:top}@media(max-width:650px){table{font-size:.8rem}}
</style></head><body><div class="container">
<div class="top"><div><h1>🛠️ TEGRIDY DEVELOPER PANEL</h1><p class="muted">Signed in as @{{ current_user.username }}</p></div><a class="btn secondary" href="{{ url_for('home') }}">← Back</a></div>
<div class="stats"><div class="stat"><div class="muted">Registered Users</div><div class="number">{{ user_count }}</div></div><div class="stat"><div class="muted">Total Posts</div><div class="number">{{ post_count }}</div></div><div class="stat"><div class="muted">Total Reviews</div><div class="number">{{ review_count }}</div></div></div>
<div class="card"><h2>👥 Registered People</h2><p class="muted">These are registered accounts. Tracking who is online right now needs an extra activity system.</p><table><tr><th>ID</th><th>Username</th><th>Joined</th><th>Posts</th></tr>{% for user in users %}<tr><td>{{ user.id }}</td><td>@{{ user.username }}</td><td>{{ user.created_at.strftime("%Y-%m-%d") }}</td><td>{{ user.posts|length }}</td></tr>{% endfor %}</table></div>
<div class="card"><h2>🚩 Open Reports ({{ report_count }})</h2>
{% for report in reports %}
<div style="padding:10px;border-bottom:1px solid #273b2c">
<b>{{ report.reason }}</b> — Spot: {{ report.reported_post.service }} by @{{ report.reported_post.author.username }}<br>
<span class="muted">{{ report.details or "No extra details" }}</span><br>
<form method="post" action="{{ url_for('developer_close_report', report_id=report.id) }}"><button class="btn secondary">Mark Resolved</button></form>
</div>
{% else %}<p class="muted">No open reports.</p>{% endfor %}
</div>

<div class="card"><h2>📋 Moderate Posts</h2><table><tr><th>ID</th><th>Service</th><th>User</th><th>Action</th></tr>{% for post in posts %}<tr><td>{{ post.id }}</td><td><b>{{ post.service }}</b><br><span class="muted">{{ post.category }} · {{ post.price }}</span></td><td>@{{ post.author.username }}</td><td><form method="post" action="{{ url_for('developer_delete_post', post_id=post.id) }}" onsubmit="return confirm('Delete this post permanently?')"><button class="btn danger">Delete</button></form></td></tr>{% endfor %}</table></div>
</div></body></html>
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
            Post.description.ilike(f"%{q}%") |
            Post.price.ilike(f"%{q}%")
        )

    if category and allowed_category(category):
        query = query.filter_by(category=category)

    posts = query.order_by(Post.created_at.desc()).all()

    stats = {}
    for post in posts:
        average, count = post_stats(post)
        stats[post.id] = {"average": average, "count": count}

    categories = ["Streaming", "Music", "Gaming", "Software", "Other"]

    return render_template_string(
        TEMPLATE,
        posts=posts,
        stats=stats,
        q=q,
        category=category,
        categories=categories,
        admin_username=ADMIN_USERNAME,
        favorite_ids=({f.post_id for f in Favorite.query.filter_by(user_id=current_user.id).all()} if current_user.is_authenticated else set()),
        unread_count=current_unread_count(),
        trending_posts=sorted(posts, key=trending_score, reverse=True)[:3]
    )


@app.route("/signup", methods=["POST"])
def signup():
    username = clean(request.form.get("username"))
    password = request.form.get("password") or ""

    if len(username) < 3 or len(username) > 30:
        flash("Username must be between 3 and 30 characters.", "error")
        return redirect(url_for("home"))

    if len(password) < 6:
        flash("Password must be at least 6 characters.", "error")
        return redirect(url_for("home"))

    if User.query.filter_by(username=username).first():
        flash("That username is already taken.", "error")
        return redirect(url_for("home"))

    user = User(
        username=username,
        password=generate_password_hash(password)
    )
    db.session.add(user)
    db.session.commit()

    login_user(user)
    flash("Account created successfully! Welcome to TEGRIDY 🔥")
    return redirect(url_for("home"))


@app.route("/login", methods=["POST"])
def login():
    username = clean(request.form.get("username"))
    password = request.form.get("password") or ""

    user = User.query.filter_by(username=username).first()

    if user and check_password_hash(user.password, password):
        login_user(user)
        flash("Welcome back! 🔥")
        return redirect(url_for("home"))

    flash("Incorrect username or password.", "error")
    return redirect(url_for("home"))


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.")
    return redirect(url_for("home"))


@app.route("/post", methods=["POST"])
@login_required
def create_post():
    service = clean(request.form.get("service"))
    category = clean(request.form.get("category"))
    price = clean(request.form.get("price"))
    contact = clean(request.form.get("contact"))
    description = clean(request.form.get("description"))

    if not all([service, price, contact]):
        flash("Service, price and contact are required.", "error")
        return redirect(url_for("home"))

    if not allowed_category(category):
        category = "Other"

    post = Post(
        service=service[:100],
        category=category,
        price=price[:50],
        contact=contact[:100],
        description=description[:300],
        user_id=current_user.id
    )

    db.session.add(post)
    db.session.commit()

    flash("Your spot has been posted! 🔥")
    return redirect(url_for("home"))


@app.route("/post/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def edit_post(post_id):
    post = db.get_or_404(Post, post_id)

    if post.user_id != current_user.id:
        flash("You can only edit your own posts.", "error")
        return redirect(url_for("home"))

    categories = ["Streaming", "Music", "Gaming", "Software", "Other"]

    if request.method == "POST":
        service = clean(request.form.get("service"))
        category = clean(request.form.get("category"))
        price = clean(request.form.get("price"))
        contact = clean(request.form.get("contact"))
        description = clean(request.form.get("description"))

        if not all([service, price, contact]):
            flash("Service, price and contact are required.", "error")
            return redirect(url_for("edit_post", post_id=post.id))

        post.service = service[:100]
        post.category = category if allowed_category(category) else "Other"
        post.price = price[:50]
        post.contact = contact[:100]
        post.description = description[:300]

        db.session.commit()
        flash("Post updated successfully!")
        return redirect(url_for("home"))

    return render_template_string(
        EDIT_TEMPLATE,
        post=post,
        categories=categories
    )


@app.route("/post/<int:post_id>/delete", methods=["POST"])
@login_required
def delete_post(post_id):
    post = db.get_or_404(Post, post_id)

    if post.user_id != current_user.id:
        flash("You can only delete your own posts.", "error")
        return redirect(url_for("home"))

    db.session.delete(post)
    db.session.commit()

    flash("Post deleted.")
    return redirect(url_for("home"))


@app.route("/review/<int:post_id>", methods=["POST"])
@login_required
def review_post(post_id):
    post = db.get_or_404(Post, post_id)

    if post.user_id == current_user.id:
        flash("You cannot review your own post.", "error")
        return redirect(url_for("home"))

    try:
        rating = int(request.form.get("rating", 0))
    except ValueError:
        rating = 0

    comment = clean(request.form.get("comment"))

    if rating < 1 or rating > 6:
        flash("Rating must be between 1 and 6.", "error")
        return redirect(url_for("home"))

    review = Review.query.filter_by(
        post_id=post.id,
        user_id=current_user.id
    ).first()

    if review:
        review.rating = rating
        review.comment = comment[:200]
        flash("Your review was updated!")
    else:
        review = Review(
            post_id=post.id,
            user_id=current_user.id,
            rating=rating,
            comment=comment[:200]
        )
        db.session.add(review)
        flash("Review added! 🔥")

    if post.user_id != current_user.id:
        make_notification(post.user_id, f"Someone reviewed your spot '{post.service}'.")
    db.session.commit()
    return redirect(url_for("home"))


@app.route("/review/<int:review_id>/delete", methods=["POST"])
@login_required
def delete_review(review_id):
    review = db.get_or_404(Review, review_id)

    if review.user_id != current_user.id:
        flash("You can only delete your own reviews.", "error")
        return redirect(url_for("home"))

    db.session.delete(review)
    db.session.commit()

    flash("Review deleted.")
    return redirect(url_for("home"))


PROFILE_TEMPLATE = r"""
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ user.username }} - TEGRIDY</title>
<style>body{background:#070907;color:#f1fff5;font-family:Arial;margin:0}.wrap{width:min(850px,92%);margin:35px auto}.card{background:#101510;border:1px solid #273b2c;border-radius:16px;padding:20px;margin:15px 0}.btn{display:inline-block;padding:10px 14px;border-radius:9px;background:#00ff88;color:#031108;text-decoration:none;font-weight:bold}.muted{color:#9db0a2}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}</style>
</head><body><div class="wrap"><a class="btn" href="{{ url_for('home') }}">← Home</a><div class="card"><h1>👤 @{{ user.username }}</h1><p class="muted">Member since {{ user.created_at.strftime("%Y-%m-%d") }}</p><div class="grid"><div><b>{{ user.posts|length }}</b><br><span class="muted">Posts</span></div><div><b>{{ user.reviews|length }}</b><br><span class="muted">Reviews</span></div></div></div><h2>Active Spots</h2>{% for post in user.posts %}<div class="card"><h3>{{ post.service }}</h3><p>{{ post.price }}</p><a class="btn" href="{{ url_for('post_detail', post_id=post.id) }}">View</a></div>{% else %}<div class="card muted">No spots posted yet.</div>{% endfor %}</div></body></html>
"""

DETAIL_TEMPLATE = r"""
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ post.service }} - TEGRIDY</title>
<style>body{background:#070907;color:#f1fff5;font-family:Arial;margin:0}.wrap{width:min(800px,92%);margin:35px auto}.card{background:#101510;border:1px solid #273b2c;border-radius:16px;padding:22px;margin:15px 0}.btn{display:inline-block;padding:10px 14px;border-radius:9px;background:#00ff88;color:#031108;text-decoration:none;font-weight:bold;border:0}.muted{color:#9db0a2}.price{color:#00ff88;font-size:1.3rem;font-weight:bold}</style>
</head><body><div class="wrap"><a class="btn" href="{{ url_for('home') }}">← Home</a><div class="card"><h1>{{ post.service }}</h1><p class="price">{{ post.price }}</p><p>{{ post.description or 'No description provided.' }}</p><p><b>Category:</b> {{ post.category }}</p><p><b>Contact:</b> {{ post.contact }}</p><p class="muted">Posted by <a href="{{ url_for('profile', username=post.author.username) }}">@{{ post.author.username }}</a></p></div><div class="card"><h2>Reviews</h2>{% for r in post.reviews %}<p>🔥 {{ r.rating }}/6 — {{ r.comment }} <span class="muted">by @{{ r.reviewer.username }}</span></p>{% else %}<p class="muted">No reviews yet.</p>{% endfor %}</div></div></body></html>
"""

REPORT_TEMPLATE = r"""
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Report - TEGRIDY</title>
<style>body{background:#070907;color:#f1fff5;font-family:Arial}.wrap{width:min(600px,92%);margin:40px auto}.card{background:#101510;border:1px solid #273b2c;border-radius:16px;padding:20px}select,textarea{width:100%;box-sizing:border-box;padding:12px;margin:8px 0;background:#080c08;color:white;border:1px solid #273b2c;border-radius:10px}.btn{padding:11px 16px;border:0;border-radius:10px;background:#00ff88;font-weight:bold}</style></head><body><div class="wrap"><div class="card"><h1>🚩 Report {{ post.service }}</h1><form method="post"><select name="reason"><option>Spam</option><option>Fake or misleading</option><option>Wrong price</option><option>Inappropriate content</option><option>Other</option></select><textarea name="details" maxlength="300" placeholder="Optional details"></textarea><button class="btn">Send Report</button></form></div></div></body></html>
"""

FAVORITES_TEMPLATE = r"""
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Favorites - TEGRIDY</title><style>body{background:#070907;color:#f1fff5;font-family:Arial}.wrap{width:min(850px,92%);margin:35px auto}.card{background:#101510;border:1px solid #273b2c;border-radius:16px;padding:20px;margin:12px 0}.btn{display:inline-block;padding:10px 14px;border-radius:9px;background:#00ff88;color:#031108;text-decoration:none;font-weight:bold}.muted{color:#9db0a2}</style></head><body><div class="wrap"><a class="btn" href="{{ url_for('home') }}">← Home</a><h1>♥ My Favorites</h1>{% for post in posts %}<div class="card"><h2>{{ post.service }}</h2><p>{{ post.price }}</p><p class="muted">@{{ post.author.username }}</p><a class="btn" href="{{ url_for('post_detail', post_id=post.id) }}">View</a></div>{% else %}<div class="card muted">You haven't saved any spots yet.</div>{% endfor %}</div></body></html>
"""

NOTIFICATIONS_TEMPLATE = r"""
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Notifications - TEGRIDY</title><style>body{background:#070907;color:#f1fff5;font-family:Arial}.wrap{width:min(750px,92%);margin:35px auto}.card{background:#101510;border:1px solid #273b2c;border-radius:16px;padding:18px;margin:10px 0}.btn{display:inline-block;padding:10px 14px;border-radius:9px;background:#00ff88;color:#031108;text-decoration:none;font-weight:bold}.muted{color:#9db0a2}</style></head><body><div class="wrap"><a class="btn" href="{{ url_for('home') }}">← Home</a><h1>🔔 Notifications</h1>{% for n in items %}<div class="card">{{ n.message }}<br><span class="muted">{{ n.created_at.strftime("%Y-%m-%d %H:%M") }}</span></div>{% else %}<div class="card muted">No notifications yet.</div>{% endfor %}</div></body></html>
"""

@app.route("/user/<username>")
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    return render_template_string(PROFILE_TEMPLATE, user=user)

@app.route("/spot/<int:post_id>")
def post_detail(post_id):
    post = db.get_or_404(Post, post_id)
    return render_template_string(DETAIL_TEMPLATE, post=post)

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
    return render_template_string(FAVORITES_TEMPLATE, posts=posts)

@app.route("/report/<int:post_id>", methods=["GET", "POST"])
@login_required
def report_post(post_id):
    post = db.get_or_404(Post, post_id)
    if request.method == "POST":
        report = Report(
            reason=clean(request.form.get("reason"))[:100],
            details=clean(request.form.get("details"))[:300],
            user_id=current_user.id,
            post_id=post.id
        )
        db.session.add(report)
        make_notification(post.user_id, f"Your post '{post.service}' was reported and may be reviewed.")
        db.session.commit()
        flash("Report sent to the developer panel.")
        return redirect(url_for("home"))
    return render_template_string(REPORT_TEMPLATE, post=post)

@app.route("/notifications")
@login_required
def notifications():
    items = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).all()
    for item in items:
        item.is_read = True
    db.session.commit()
    return render_template_string(NOTIFICATIONS_TEMPLATE, items=items)


# ---------------- DEVELOPER PANEL ----------------

@app.route("/developer")
@login_required
@admin_required
def developer():
    users = User.query.order_by(User.created_at.desc()).all()
    posts = Post.query.order_by(Post.created_at.desc()).all()
    return render_template_string(
        DEVELOPER_TEMPLATE,
        users=users,
        posts=posts,
        user_count=User.query.count(),
        post_count=Post.query.count(),
        review_count=Review.query.count(),
        reports=Report.query.filter_by(status="open").order_by(Report.created_at.desc()).all(),
        report_count=Report.query.filter_by(status="open").count()
    )

@app.route("/developer/report/<int:report_id>/resolve", methods=["POST"])
@login_required
@admin_required
def developer_close_report(report_id):
    report = db.get_or_404(Report, report_id)
    report.status = "resolved"
    db.session.commit()
    flash("Report marked as resolved.")
    return redirect(url_for("developer"))

@app.route("/developer/post/<int:post_id>/delete", methods=["POST"])
@login_required
@admin_required
def developer_delete_post(post_id):
    post = db.get_or_404(Post, post_id)
    db.session.delete(post)
    db.session.commit()
    flash(f"Developer removed post #{post_id}.")
    return redirect(url_for("developer"))


def ensure_developer_account():
    """Create the developer account automatically on first startup."""
    admin = User.query.filter_by(username=ADMIN_USERNAME).first()

    if admin is None:
        admin = User(
            username=ADMIN_USERNAME,
            password=generate_password_hash("Madende12")
        )
        db.session.add(admin)
        db.session.commit()
        print(f"Developer account @{ADMIN_USERNAME} created.")
    else:
        print(f"Developer account @{ADMIN_USERNAME} already exists.")



# Initialize database tables when the app is imported by Gunicorn/Render.
with app.app_context():
    db.create_all()
    ensure_developer_account()

if __name__ == "__main__":
    # Local development server only.
    app.run(host="0.0.0.0", port=5000, debug=True)
