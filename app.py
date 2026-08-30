from flask import Flask, request, redirect, url_for, render_template_string, send_from_directory, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps
from uuid import uuid4
import os

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///tegridy_v4.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "Rick44")
CATEGORIES = ["Streaming", "Music", "Gaming", "Software", "Other"]
ALLOWED = {"png", "jpg", "jpeg", "gif", "webp"}

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    is_verified = db.Column(db.Boolean, default=False)
    is_eligible = db.Column(db.Boolean, default=False)
    bio = db.Column(db.String(300), default="")
    profile_picture = db.Column(db.String(255), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    service = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), default="Other")
    contact = db.Column(db.String(120), nullable=False)
    expiry_date = db.Column(db.String(20), default="")
    description = db.Column(db.String(300), default="")
    status = db.Column(db.String(20), default="Available")
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author = db.relationship("User", backref=db.backref("posts", lazy=True))

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def admin():
    return current_user.is_authenticated and current_user.username.lower() == ADMIN_USERNAME.lower()

def admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not admin():
            flash("Developer access only.", "error")
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return wrapped

def badges(user):
    result = ""
    if user.username.lower() == ADMIN_USERNAME.lower():
        result += '<span class="dev">DEV</span>'
    if user.is_verified:
        result += '<span class="verified">✓</span>'
    if user.is_eligible:
        result += '<span class="eligible">✦</span>'
    return result

def avatar(user, big=False):
    cls = "avatar big" if big else "avatar"
    if user.profile_picture:
        return f'<img class="{cls}" src="{url_for("uploaded_file", filename=user.profile_picture)}">'
    return f'<div class="{cls} placeholder">{user.username[:1].upper()}</div>'

STYLE = """
<style>
:root{--g:#00ff88;--b:#2997ff;--bg:#070907;--p:#101510;--t:#f1fff5;--m:#9db0a2;--d:#ff5c5c;--bd:#273b2c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--t);font-family:Arial,sans-serif}.container{width:min(1100px,92%);margin:auto}nav{background:#0b100c;border-bottom:1px solid var(--bd);position:sticky;top:0}.nav{min-height:68px;display:flex;align-items:center;justify-content:space-between;gap:10px}.actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.logo{color:var(--g);font-weight:900}.card{background:var(--p);border:1px solid var(--bd);border-radius:18px;padding:20px;margin:15px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:15px}.btn{display:inline-block;border:0;border-radius:10px;padding:11px 15px;background:var(--g);color:#031108;font-weight:800;cursor:pointer}.secondary{background:#202a21;color:var(--t)}.blue{background:var(--b);color:white}.danger{background:var(--d);color:white}.muted{color:var(--m)}input,select,textarea{width:100%;padding:12px;margin:6px 0;background:#080c08;color:white;border:1px solid var(--bd);border-radius:10px}textarea{min-height:100px}.avatar{width:44px;height:44px;border-radius:50%;border:2px solid var(--g);object-fit:cover}.big{width:120px;height:120px;border-width:4px}.placeholder{display:flex;align-items:center;justify-content:center;background:#193020;color:var(--g);font-weight:bold}.profile{display:flex;gap:20px;align-items:center}.verified,.eligible{display:inline-flex;width:19px;height:19px;justify-content:center;align-items:center;font-weight:bold;margin-left:4px}.verified{background:var(--b);border-radius:50%}.eligible{background:var(--g);color:#031108;border-radius:7px}.dev{background:#342711;color:#ffd36b;padding:4px 8px;border-radius:99px;font-size:.75rem;margin-left:4px}.plus{position:fixed;right:22px;bottom:24px;width:62px;height:62px;border-radius:50%;background:var(--g);color:#031108;font-size:2rem;display:flex;align-items:center;justify-content:center}.flash{padding:12px;margin:12px 0;border-radius:10px;background:#152019}.error{color:#ff9999}
</style>
"""

def layout(title, content):
    template = "<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'><title>{{ title }}</title>" + STYLE + "</head><body><nav><div class='container nav'><a class='logo' href='/'>TEGRIDY MARKET</a><div class='actions'>{% if current_user.is_authenticated %}<a href='/profile'>{{ avatar(current_user)|safe }}</a><a class='btn secondary' href='/profile'>Profile</a>{% if admin() %}<a class='btn secondary' href='/developer'>Developer</a>{% endif %}<a class='btn danger' href='/logout'>Logout</a>{% else %}<a class='btn secondary' href='/login'>Log In</a><a class='btn' href='/signup'>Sign Up</a>{% endif %}</div></div></nav><main class='container'>{% for c,m in get_flashed_messages(with_categories=true) %}<div class='flash {{ c }}'>{{ m }}</div>{% endfor %}{{ content|safe }}</main>{% if current_user.is_authenticated %}<a class='plus' href='/post/new'>+</a>{% endif %}</body></html>"
    return render_template_string(template, title=title, content=content, avatar=avatar, admin=admin)

@app.route("/")
def home():
    q = (request.args.get("q") or "").strip()
    query = Post.query.order_by(Post.created_at.desc())
    if q:
        query = query.filter(Post.service.ilike(f"%{q}%"))
    cards = ""
    for post in query.all():
        cards += f"<div class='card'><span class='muted'>{post.category}</span><h2>{post.service}</h2><p>{post.description}</p><p><b>{post.status}</b></p><p class='muted'>by <a href='/profile/{post.author.username}'>@{post.author.username}</a>{badges(post.author)}</p><a class='btn secondary' href='/post/{post.id}'>View</a></div>"
    content = f"<section style='text-align:center;padding:55px 0 25px'><h1>TEGRIDY FAMILY</h1><p class='muted'>Responsible family-plan sharing community.</p></section><div class='card'><form><input name='q' value='{q}' placeholder='Search a platform'><button class='btn'>Search</button></form></div><div class='grid'>{cards or '<div class=card>No posts yet.</div>'}</div>"
    return layout("TEGRIDY MARKET", content)

@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        if len(username) < 3 or len(password) < 6 or "@" not in email:
            flash("Enter a valid username, email and password.", "error")
        elif User.query.filter((User.username.ilike(username)) | (User.email == email)).first():
            flash("Username or email already exists.", "error")
        else:
            user = User(username=username, email=email, password=generate_password_hash(password), is_verified=username.lower()==ADMIN_USERNAME.lower())
            db.session.add(user); db.session.commit(); login_user(user)
            return redirect(url_for("home"))
    return layout("Sign Up", "<div class='card'><h1>Create Account</h1><form method='post'><input name='username' placeholder='Username' required><input name='email' type='email' placeholder='Email' required><input name='password' type='password' placeholder='Password' required><button class='btn'>Sign Up</button></form></div>")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        identity = (request.form.get("identity") or "").strip()
        password = request.form.get("password") or ""
        user = User.query.filter((User.username.ilike(identity)) | (User.email.ilike(identity))).first()
        if user and check_password_hash(user.password, password):
            login_user(user); return redirect(url_for("home"))
        flash("Incorrect login details.", "error")
    return layout("Log In", "<div class='card'><h1>Log In</h1><form method='post'><input name='identity' placeholder='Username or email' required><input name='password' type='password' placeholder='Password' required><button class='btn'>Log In</button></form></div>")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))

@app.route("/profile")
@login_required
def my_profile():
    return redirect(url_for("profile", username=current_user.username))

@app.route("/profile/<username>")
def profile(username):
    user = User.query.filter(User.username.ilike(username)).first_or_404()
    posts = "".join(f"<div class='card'><h3>{p.service}</h3><p class='muted'>{p.category} · {p.status}</p><a class='btn secondary' href='/post/{p.id}'>View</a></div>" for p in user.posts)
    edit = "<a class='btn secondary' href='/profile/edit'>Edit Profile</a>" if current_user.is_authenticated and current_user.id == user.id else ""
    content = f"<div class='card'><div class='profile'>{avatar(user, True)}<div><h1>@{user.username}{badges(user)}</h1><p>{user.bio or '<span class=muted>No bio yet.</span>'}</p><p class='muted'>Member since {user.created_at.strftime('%d %B %Y')}</p><p><b>{len(user.posts)}</b> Posts</p>{edit}</div></div></div><h2>Platforms</h2>{posts or '<div class=card>No posts yet.</div>'}"
    return layout(user.username, content)

@app.route("/profile/edit", methods=["GET","POST"])
@login_required
def edit_profile():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        bio = (request.form.get("bio") or "").strip()[:300]
        other = User.query.filter(User.username.ilike(username), User.id != current_user.id).first()
        if len(username) < 3 or other:
            flash("Username is invalid or already taken.", "error")
        else:
            file = request.files.get("profile_picture")
            if file and file.filename:
                if "." not in file.filename or file.filename.rsplit(".",1)[1].lower() not in ALLOWED:
                    flash("Use PNG, JPG, JPEG, GIF or WEBP.", "error")
                    return redirect(url_for("edit_profile"))
                ext = file.filename.rsplit(".",1)[1].lower()
                filename = f"{uuid4().hex}.{ext}"
                file.save(os.path.join(UPLOAD_DIR, filename))
                current_user.profile_picture = filename
            current_user.username = username
            current_user.bio = bio
            db.session.commit()
            return redirect(url_for("my_profile"))
    return layout("Edit Profile", f"<div class='card'><h1>Edit Profile</h1><form method='post' enctype='multipart/form-data'><input name='username' value='{current_user.username}' required><textarea name='bio'>{current_user.bio}</textarea><label>Profile picture</label><input type='file' name='profile_picture' accept='.png,.jpg,.jpeg,.gif,.webp'><button class='btn'>Save Profile</button></form></div>")

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)

@app.route("/post/new", methods=["GET","POST"])
@login_required
def create_post():
    if request.method == "POST":
        service = (request.form.get("service") or "").strip()
        category = request.form.get("category") or "Other"
        contact = (request.form.get("contact") or "").strip()
        if not service or not contact:
            flash("Platform name and contact method are required.", "error")
        else:
            post = Post(service=service[:100], category=category if category in CATEGORIES else "Other", contact=contact[:120], expiry_date=(request.form.get("expiry_date") or "")[:20], description=(request.form.get("description") or "")[:300], status=request.form.get("status") if request.form.get("status") in ["Available","Full"] else "Available", user_id=current_user.id)
            db.session.add(post); db.session.commit()
            return redirect(url_for("post_detail", post_id=post.id))
    options = "".join(f"<option>{c}</option>" for c in CATEGORIES)
    return layout("Post Platform", f"<div class='card'><h1>+ Post a Platform</h1><p class='muted'>Never post passwords, payment information or verification codes.</p><form method='post'><input name='service' placeholder='Platform name' required><select name='category'>{options}</select><input name='contact' placeholder='Contact email or official invitation method' required><input name='expiry_date' type='date'><select name='status'><option>Available</option><option>Full</option></select><textarea name='description' placeholder='Describe the available spot'></textarea><button class='btn'>Post Platform</button></form></div>")

@app.route("/post/<int:post_id>")
def post_detail(post_id):
    post = db.get_or_404(Post, post_id)
    return layout(post.service, f"<div class='card'><h1>{post.service}</h1><p>{post.description or 'No description provided.'}</p><p>Category: {post.category}</p><p>Status: {post.status}</p><p>Expiry: {post.expiry_date or 'Not provided'}</p><p>Contact method: {post.contact}</p><p class='muted'>Posted by <a href='/profile/{post.author.username}'>@{post.author.username}</a>{badges(post.author)}</p></div>")

@app.route("/developer")
@login_required
@admin_required
def developer():
    rows = ""
    for user in User.query.order_by(User.created_at.desc()).all():
        rows += f"<div class='card'><div class='profile'>{avatar(user)}<div><h3>@{user.username}{badges(user)}</h3><p class='muted'>{user.email}</p><form style='display:inline' method='post' action='/developer/{user.id}/verified'><button class='btn blue'>{'Remove Verification' if user.is_verified else 'Verify User'}</button></form><form style='display:inline' method='post' action='/developer/{user.id}/eligible'><button class='btn secondary'>{'Remove Eligible' if user.is_eligible else 'Make Eligible'}</button></form></div></div></div>"
    return layout("Developer Panel", "<h1>Developer Panel</h1><p class='muted'>Manage verification and eligibility badges.</p>" + rows)

@app.route("/developer/<int:user_id>/verified", methods=["POST"])
@login_required
@admin_required
def toggle_verified(user_id):
    user = db.get_or_404(User, user_id)
    user.is_verified = not user.is_verified
    db.session.commit()
    return redirect(url_for("developer"))

@app.route("/developer/<int:user_id>/eligible", methods=["POST"])
@login_required
@admin_required
def toggle_eligible(user_id):
    user = db.get_or_404(User, user_id)
    user.is_eligible = not user.is_eligible
    db.session.commit()
    return redirect(url_for("developer"))

with app.app_context():
    db.create_all()
    developer = User.query.filter(User.username.ilike(ADMIN_USERNAME)).first()
    if developer:
        developer.is_verified = True
        db.session.commit()

if __name__ == "__main__":
    app.run(debug=True)
