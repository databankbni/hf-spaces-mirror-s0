from flask import Flask, flash, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from flask_cors import CORS
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
from ai_engine import (
    secure_image_digest,
    predict_bird,
    precompute_reference_embeddings,
    validate_and_compress_image,
    generate_gradcam_heatmap,
    extract_exif_metadata,
)

from models import Article, Bird, Favorite, Habitat, Park, Prediction, Review, Sighting, User, Visit, db
from dotenv import load_dotenv
import glob
import os
import uuid

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "tanzania-bird-finder-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///birdhabitat.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

CORS(app)
db.init_app(app)

DATASET_PATH = os.path.join(os.path.dirname(__file__), "dataset", "images")
BIRDS_PATH = os.path.join(os.path.dirname(__file__), "static", "birds")
PROJECT_ROOT = os.path.dirname(__file__)
UPLOAD_PATH = os.path.join(PROJECT_ROOT, "static", "uploads")
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
os.makedirs(UPLOAD_PATH, exist_ok=True)


def get_bird_image(folder_name):
    for base in (BIRDS_PATH, DATASET_PATH):
        folder = os.path.join(base, folder_name)
        if os.path.isdir(folder):
            images = sorted(glob.glob(os.path.join(folder, "*.jpg")))
            if images:
                return f"/bird-image/{folder_name}/{os.path.basename(images[0])}"
    return "/static/img/placeholder.svg"


def current_user():
    user_id = session.get("user_id")
    return User.query.get(user_id) if user_id else None


def require_admin():
    user = current_user()
    return user and user.role == "admin"


def allowed_image(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def _is_ajax():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


@app.context_processor
def inject_user():
    return {"current_user": current_user()}


@app.route("/bird-image/<folder>/<filename>")
def bird_image(folder, filename):
    for base in (BIRDS_PATH, DATASET_PATH):
        candidate = os.path.join(base, folder)
        if os.path.isdir(candidate):
            try:
                return send_from_directory(candidate, filename)
            except FileNotFoundError:
                continue
    return send_from_directory(os.path.join(app.root_path, "static", "img"), "placeholder.svg")


@app.route("/")
def index():
    return render_template(
        "index.html",
        habitats=Habitat.query.all(),
        featured_birds=Bird.query.limit(6).all(),
        featured_parks=Park.query.limit(4).all(),
        articles=Article.query.limit(3).all(),
    )


@app.route("/map")
def map_view():
    return render_template(
        "map.html",
        parks=Park.query.all(),
        habitats=Habitat.query.all(),
        birds=Bird.query.all(),
    )


@app.route("/identify", methods=["GET", "POST"])
def identify():
    result = None
    upload_url = None
    if request.method == "POST":
        upload = request.files.get("bird_image")
        if not upload or not upload.filename:
            if _is_ajax():
                return jsonify({"error": "Please choose a bird image to identify."}), 422
            flash("Please choose a bird image to identify.")
            return redirect(url_for("identify"))
        if not allowed_image(upload.filename):
            if _is_ajax():
                return jsonify({"error": "Only JPG, PNG, or WEBP images are allowed."}), 422
            flash("Only JPG, PNG, or WEBP images are allowed.")
            return redirect(url_for("identify"))

        safe_name = secure_filename(upload.filename)
        output_name = f"{uuid.uuid4().hex}-{os.path.splitext(safe_name)[0][:40]}.jpg"
        output_path = os.path.join(UPLOAD_PATH, output_name)

        upload.save(output_path)

        try:
            validate_and_compress_image(output_path, output_path=output_path)
            digest = secure_image_digest(output_path)

            birds = Bird.query.all()
            prediction = predict_bird(
                output_path,
                birds,
                PROJECT_ROOT,
                reference_embeddings=getattr(app, "reference_embeddings", None),
            )
        except ValueError as exc:
            if _is_ajax():
                return jsonify({"error": str(exc)}), 422
            flash(str(exc))
            return redirect(url_for("identify"))

        bird = prediction["bird"]
        user = current_user()
        record = Prediction(
            user_id=user.id if user else None,
            bird_id=bird.id,
            image_path=f"/static/uploads/{output_name}",
            confidence=prediction["confidence"],
            model_name=prediction["model_name"],
            status=f"completed:{digest[:12]}",
        )
        db.session.add(record)

        # --- Grad-CAM explainable AI ---
        gradcam_url = None
        ref_emb = getattr(app, "reference_embeddings", None)
        if ref_emb and bird.common_name in ref_emb:
            gradcam_name = f"gradcam-{output_name}"
            gradcam_path = os.path.join(UPLOAD_PATH, gradcam_name)
            best_ref = ref_emb[bird.common_name]
            if best_ref.ndim == 2:
                best_ref = best_ref[0]
            gradcam_result = generate_gradcam_heatmap(
                output_path, gradcam_path, reference_embedding=best_ref
            )
            if gradcam_result:
                gradcam_url = f"/static/uploads/{gradcam_name}"

        # --- EXIF metadata extraction ---
        exif_data = extract_exif_metadata(output_path)
        sighting_created = False
        if exif_data.get("gps"):
            sighting = Sighting(
                user_id=user.id if user else None,
                bird_id=bird.id,
                image_path=f"/static/uploads/{output_name}",
                latitude=exif_data["gps"]["lat"],
                longitude=exif_data["gps"]["lon"],
                confidence=prediction["confidence"],
                species_guess=bird.common_name,
            )
            db.session.add(sighting)
            sighting_created = True

        db.session.commit()

        upload_url = record.image_path
        result = {
            "record": record,
            "bird": bird,
            "confidence": prediction["confidence"],
            "alternatives": prediction["alternatives"],
            "model_name": prediction["model_name"],
            "parks": bird.parks,
            "gradcam_url": gradcam_url,
            "exif": exif_data,
            "sighting_created": sighting_created,
        }

    return render_template("identify.html", result=result, upload_url=upload_url)


@app.route("/habitats")
def habitats():
    return render_template("habitats.html", habitats=Habitat.query.all())


@app.route("/habitats/<slug>")
def habitat_detail(slug):
    habitat = Habitat.query.filter_by(slug=slug).first_or_404()
    birds = Bird.query.filter_by(habitat_id=habitat.id).all()
    parks = Park.query.filter_by(habitat_type=habitat.name).all()
    return render_template("habitat_detail.html", habitat=habitat, birds=birds, parks=parks)


@app.route("/parks")
def parks():
    all_parks = Park.query.all()
    regions = db.session.query(Park.region).distinct().all()
    habitats = db.session.query(Park.habitat_type).distinct().all()
    return render_template(
        "parks.html",
        parks=all_parks,
        regions=[r[0] for r in regions],
        habitats=[h[0] for h in habitats],
    )


@app.route("/parks/<int:park_id>", methods=["GET", "POST"])
def park_detail(park_id):
    park = Park.query.get_or_404(park_id)
    if request.method == "POST":
        user = current_user()
        if not user:
            flash("Please log in to review parks.")
            return redirect(url_for("login"))
        rating = max(1, min(5, int(request.form.get("rating", 5))))
        review = Review(user_id=user.id, park_id=park.id, rating=rating, comment=request.form.get("comment", ""))
        db.session.add(review)
        db.session.commit()
        flash("Review saved.")
        return redirect(url_for("park_detail", park_id=park.id))
    return render_template("park_detail.html", park=park)


@app.route("/species")
def species():
    birds = Bird.query.all()
    habitats = Habitat.query.all()
    statuses = db.session.query(Bird.conservation_status).distinct().all()
    return render_template(
        "species.html",
        birds=birds,
        habitats=habitats,
        statuses=[s[0] for s in statuses if s[0]],
    )


@app.route("/species/<int:bird_id>")
def species_detail(bird_id):
    bird = Bird.query.get_or_404(bird_id)
    related = Bird.query.filter_by(habitat_id=bird.habitat_id).filter(Bird.id != bird_id).limit(4).all()
    return render_template("species_detail.html", bird=bird, related=related)


@app.route("/conservation")
def conservation():
    articles = Article.query.order_by(Article.created_at.desc()).all()
    categories = db.session.query(Article.category).distinct().all()
    return render_template("conservation.html", articles=articles, categories=[c[0] for c in categories])


@app.route("/login", methods=["GET", "POST"])
def login():
    next_url = request.args.get("next") or url_for("dashboard")
    if request.method == "POST":
        user = User.query.filter_by(email=request.form.get("email", "").lower()).first()
        if user and check_password_hash(user.password_hash, request.form.get("password", "")):
            session["user_id"] = user.id
            flash("Welcome back.")
            return redirect(next_url)
        flash("Invalid email or password.")
    return render_template("auth.html", mode="login")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").lower().strip()
        if User.query.filter_by(email=email).first():
            flash("That email is already registered.")
        else:
            user = User(
                name=request.form.get("name", "Bird Explorer").strip(),
                email=email,
                password_hash=generate_password_hash(request.form.get("password", "")),
            )
            db.session.add(user)
            db.session.commit()
            session["user_id"] = user.id
            flash("Account created.")
            return redirect(url_for("dashboard"))
    return render_template("auth.html", mode="register")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.")
    return redirect(url_for("index"))


@app.route("/dashboard")
def dashboard():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    favorites = Favorite.query.filter_by(user_id=user.id).all()
    visits = Visit.query.filter_by(user_id=user.id).all()
    predictions = Prediction.query.filter_by(user_id=user.id).order_by(Prediction.created_at.desc()).limit(12).all()
    unverified_predictions = []
    unverified_count = 0
    if user.role in ("contributor", "admin"):
        unverified_predictions = (
            Prediction.query.filter(Prediction.status.like("completed:%"))
            .order_by(Prediction.created_at.desc())
            .limit(20)
            .all()
        )
        unverified_count = Prediction.query.filter(Prediction.status.like("completed:%")).count()
    return render_template(
        "dashboard.html",
        user=user,
        favorites=favorites,
        visits=visits,
        predictions=predictions,
        unverified_predictions=unverified_predictions,
        unverified_count=unverified_count,
        birds=Bird.query.all(),
        parks=Park.query.all(),
    )


@app.route("/favorite/<item_type>/<int:item_id>", methods=["POST"])
def favorite(item_type, item_id):
    user = current_user()
    if not user:
        flash("Please log in to save favorites.")
        return redirect(url_for("login", next=request.referrer or url_for("dashboard")))
    exists = Favorite.query.filter_by(user_id=user.id, item_type=item_type, item_id=item_id).first()
    if exists:
        db.session.delete(exists)
        flash("Removed from favorites.")
    else:
        db.session.add(Favorite(user_id=user.id, item_type=item_type, item_id=item_id))
        flash("Saved to favorites.")
    db.session.commit()
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/visited/<int:park_id>", methods=["POST"])
def visited(park_id):
    user = current_user()
    if not user:
        flash("Please log in to track visits.")
        return redirect(url_for("login", next=request.referrer or url_for("dashboard")))
    if not Visit.query.filter_by(user_id=user.id, park_id=park_id).first():
        db.session.add(Visit(user_id=user.id, park_id=park_id))
        db.session.commit()
    flash("Park visit tracked.")
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not require_admin():
        flash("Admin access required.")
        return redirect(url_for("login"))
    if request.method == "POST":
        content_type = request.form.get("content_type")
        if content_type == "bird":
            habitat = Habitat.query.get(int(request.form.get("habitat_id")))
            bird = Bird(
                common_name=request.form.get("common_name"),
                scientific_name=request.form.get("scientific_name"),
                habitat_id=habitat.id,
                migration_pattern=request.form.get("migration_pattern"),
                conservation_status=request.form.get("conservation_status"),
                description=request.form.get("description"),
                region=request.form.get("region"),
                image_url=request.form.get("image_url") or get_bird_image("Cape_Glossy_Starling"),
            )
            db.session.add(bird)
            for park in Park.query.filter_by(habitat_type=habitat.name).all():
                if bird not in park.birds:
                    park.birds.append(bird)
        elif content_type == "park":
            park = Park(
                name=request.form.get("name"),
                country="Tanzania",
                region=request.form.get("region"),
                description=request.form.get("description"),
                latitude=float(request.form.get("latitude")),
                longitude=float(request.form.get("longitude")),
                habitat_type=request.form.get("habitat_type"),
                best_visit_months=request.form.get("best_visit_months"),
                conservation_status=request.form.get("conservation_status"),
                area_km2=float(request.form.get("area_km2") or 0),
                image_url=request.form.get("image_url"),
            )
            park.birds = Bird.query.join(Habitat).filter(Habitat.name == park.habitat_type).limit(6).all()
            db.session.add(park)
        db.session.commit()
        flash("Content saved.")
    unlinked_birds = [bird for bird in Bird.query.all() if not bird.parks]
    low_confidence_predictions = Prediction.query.filter(Prediction.confidence < 65).order_by(Prediction.created_at.desc()).limit(10).all()
    all_predictions = Prediction.query.order_by(Prediction.created_at.desc()).limit(30).all()
    prediction_count = Prediction.query.count()
    reviewed_prediction_count = Prediction.query.filter_by(status="reviewed").count()
    avg_prediction_confidence = db.session.query(db.func.avg(Prediction.confidence)).scalar() or 0
    return render_template(
        "admin.html",
        users=User.query.all(),
        birds=Bird.query.all(),
        parks=Park.query.all(),
        habitats=Habitat.query.all(),
        predictions=all_predictions,
        prediction_count=prediction_count,
        reviewed_prediction_count=reviewed_prediction_count,
        avg_prediction_confidence=avg_prediction_confidence,
        unlinked_birds=unlinked_birds,
        low_confidence_predictions=low_confidence_predictions,
    )


@app.route("/verify/<int:prediction_id>", methods=["POST"])
def verify_prediction(prediction_id):
    user = current_user()
    if not user or user.role not in ("contributor", "admin"):
        flash("Only trusted contributors can verify identifications.")
        return redirect(url_for("login"))
    prediction = Prediction.query.get_or_404(prediction_id)
    action = request.form.get("action", "verify")
    if action == "verify":
        prediction.status = f"verified:{user.id}"
        flash("Identification verified. Thank you for contributing to research quality.")
    elif action == "flag":
        prediction.status = f"flagged:{user.id}"
        flash("Identification flagged for review. A moderator will check.")
    db.session.commit()
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/admin/predictions/<int:prediction_id>/status", methods=["POST"])
def admin_prediction_status(prediction_id):
    if not require_admin():
        flash("Admin access required.")
        return redirect(url_for("login"))
    prediction = Prediction.query.get_or_404(prediction_id)
    status = request.form.get("status", "reviewed")
    if status not in {"reviewed", "needs-review", "rejected"}:
        status = "reviewed"
    prediction.status = status
    db.session.commit()
    flash("Prediction status updated.")
    return redirect(url_for("admin"))


@app.route("/admin/predictions/<int:prediction_id>/correct", methods=["POST"])
def admin_prediction_correct(prediction_id):
    if not require_admin():
        flash("Admin access required.")
        return redirect(url_for("login"))
    prediction = Prediction.query.get_or_404(prediction_id)
    bird = Bird.query.get_or_404(int(request.form.get("bird_id")))
    prediction.bird_id = bird.id
    prediction.status = "reviewed"
    db.session.commit()
    flash("Prediction corrected and marked reviewed.")
    return redirect(url_for("admin"))


@app.route("/admin/birds/<int:bird_id>/edit", methods=["GET", "POST"])
def admin_edit_bird(bird_id):
    if not require_admin():
        flash("Admin access required.")
        return redirect(url_for("login"))
    bird = Bird.query.get_or_404(bird_id)
    if request.method == "POST":
        bird.common_name = request.form.get("common_name")
        bird.scientific_name = request.form.get("scientific_name")
        bird.habitat_id = int(request.form.get("habitat_id"))
        bird.region = request.form.get("region")
        bird.migration_pattern = request.form.get("migration_pattern")
        bird.conservation_status = request.form.get("conservation_status")
        bird.image_url = request.form.get("image_url") or bird.image_url
        bird.description = request.form.get("description")
        db.session.commit()
        flash("Bird updated.")
        return redirect(url_for("admin"))
    return render_template("admin_edit_bird.html", bird=bird, habitats=Habitat.query.all())


@app.route("/admin/parks/<int:park_id>/edit", methods=["GET", "POST"])
def admin_edit_park(park_id):
    if not require_admin():
        flash("Admin access required.")
        return redirect(url_for("login"))
    park = Park.query.get_or_404(park_id)
    if request.method == "POST":
        park.name = request.form.get("name")
        park.region = request.form.get("region")
        park.latitude = float(request.form.get("latitude"))
        park.longitude = float(request.form.get("longitude"))
        park.habitat_type = request.form.get("habitat_type")
        park.best_visit_months = request.form.get("best_visit_months")
        park.conservation_status = request.form.get("conservation_status")
        park.area_km2 = float(request.form.get("area_km2") or 0)
        park.image_url = request.form.get("image_url")
        park.description = request.form.get("description")
        db.session.commit()
        flash("Park updated.")
        return redirect(url_for("admin"))
    return render_template("admin_edit_park.html", park=park)


@app.route("/api/map-data")
def api_map_data():
    return jsonify(
        {
            "parks": [p.to_dict() for p in Park.query.all()],
            "habitats": [h.to_dict() for h in Habitat.query.all()],
            "birds": [b.to_dict() for b in Bird.query.all()],
        }
    )


@app.route("/api/parks")
def api_parks():
    region = request.args.get("region")
    habitat = request.args.get("habitat")
    bird = request.args.get("bird")
    q = Park.query
    if region:
        q = q.filter(Park.region.ilike(f"%{region}%"))
    if habitat:
        q = q.filter(Park.habitat_type.ilike(f"%{habitat}%"))
    if bird:
        q = q.join(Park.birds).filter(Bird.common_name.ilike(f"%{bird}%"))
    return jsonify([p.to_dict() for p in q.all()])


@app.route("/api/birds")
def api_birds():
    habitat = request.args.get("habitat")
    status = request.args.get("status")
    search = request.args.get("q")
    q = Bird.query
    if habitat:
        q = q.join(Habitat).filter(Habitat.slug == habitat)
    if status:
        q = q.filter(Bird.conservation_status == status)
    if search:
        q = q.filter(Bird.common_name.ilike(f"%{search}%") | Bird.scientific_name.ilike(f"%{search}%"))
    return jsonify([b.to_dict() for b in q.all()])


@app.route("/api/sightings")
def api_sightings():
    bird_id = request.args.get("bird_id", type=int)
    days = request.args.get("days", type=int)
    q = Sighting.query
    if bird_id:
        q = q.filter(Sighting.bird_id == bird_id)
    if days:
        from datetime import datetime, timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)
        q = q.filter(Sighting.created_at >= cutoff)
    sightings = q.order_by(Sighting.created_at.desc()).limit(200).all()
    return jsonify({
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [s.longitude, s.latitude]},
                "properties": {
                    "id": s.id,
                    "species": s.species_guess,
                    "confidence": s.confidence,
                    "image": s.image_path,
                    "timestamp": s.created_at.isoformat() if s.created_at else None,
                },
            }
            for s in sightings if s.latitude and s.longitude
        ],
    })


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("500.html"), 500


@app.route("/api/search")
def api_search():
    q = request.args.get("q", "")
    birds = Bird.query.filter(Bird.common_name.ilike(f"%{q}%")).limit(5).all()
    parks = Park.query.filter(Park.name.ilike(f"%{q}%")).limit(5).all()
    habitats = Habitat.query.filter(Habitat.name.ilike(f"%{q}%")).limit(3).all()
    return jsonify(
        {
            "birds": [{"id": b.id, "name": b.common_name, "type": "bird", "image": b.image_url} for b in birds],
            "parks": [{"id": p.id, "name": p.name, "type": "park"} for p in parks],
            "habitats": [{"slug": h.slug, "name": h.name, "type": "habitat"} for h in habitats],
        }
    )


def seed_data():
    if Bird.query.count() > 0:
        return
    habitats_data = [
        ("Savannah", "savannah", "Open grassland and acacia woodland supporting bustards, raptors, starlings, larks, and seasonal migrants.", "Semi-arid to warm, 18-32 C", "Grassland, acacia woodland, seasonal rivers", "https://images.unsplash.com/photo-1547471080-7cc2caa01a7e?w=1200&q=85", "trees"),
        ("Wetland", "wetland", "Lakes, floodplains, papyrus edges, and marshes important for flamingos, pelicans, herons, kingfishers, and migrants.", "Humid margins, 18-30 C", "Floodplains, alkaline lakes, papyrus, reeds", "https://images.unsplash.com/photo-1559827260-dc66d52bef19?w=1200&q=85", "waves"),
        ("Montane Forest", "montane-forest", "Cool highland forest on volcanic and Eastern Arc mountains with endemic and range-restricted bird communities.", "Cool and moist, 10-24 C", "Cloud forest, canopy layers, forest streams", "https://images.unsplash.com/photo-1448375240586-882707db888b?w=1200&q=85", "leaf"),
        ("Coastal & Marine", "coastal-marine", "Mangroves, beaches, islands, estuaries, and offshore waters used by shorebirds and seabirds.", "Maritime, 23-31 C", "Mangroves, reefs, tidal flats, beaches", "https://images.unsplash.com/photo-1505118380757-91f5f5632de0?w=1200&q=85", "shell"),
        ("Alpine", "alpine", "High-elevation moorland and volcanic slopes around Kilimanjaro and Meru.", "Cold nights, 0-18 C", "Heath, moorland, cliffs, volcanic slopes", "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=1200&q=85", "mountain"),
    ]

    habitat_objs = {}
    for name, slug, desc, climate, eco, image_url, icon in habitats_data:
        habitat = Habitat.query.filter_by(slug=slug).first() or Habitat(slug=slug)
        habitat.name = name
        habitat.description = desc
        habitat.climate = climate
        habitat.ecosystem_data = eco
        habitat.image_url = image_url
        habitat.icon = icon
        db.session.add(habitat)
        habitat_objs[slug] = habitat
    db.session.flush()

    birds_data = [
        ("Grey Crowned Crane (Korongo taji)", "Balearica regulorum", "White_Pelican", "wetland", "Resident", "Endangered", "Tall, elegant crane of wetlands and grasslands. Its Tanzanian populations depend on protected marshes, floodplains, and low-disturbance nesting areas.", "Northern and western Tanzania"),
        ("Lesser Flamingo (Heroe mdogo)", "Phoeniconaias minor", "White_Pelican", "wetland", "Nomadic", "Near Threatened", "Specialist of alkaline lakes including Lake Natron, feeding on cyanobacteria and forming large pink flocks.", "Rift Valley lakes"),
        ("Pied Kingfisher (Mvumvi wa maji)", "Ceryle rudis", "Pied_Kingfisher", "wetland", "Resident", "Least Concern", "Black-and-white kingfisher often seen hovering above lakes, rivers, and ponds before diving for fish.", "Widespread near water"),
        ("Cape Glossy Starling (Kwale mng'ao)", "Lamprotornis nitens", "Cape_Glossy_Starling", "savannah", "Resident", "Least Concern", "Iridescent blue-green starling common in savannah woodland and tourist circuits across northern Tanzania.", "Savannah parks"),
        ("Secretarybird (Ndege katibu)", "Sagittarius serpentarius", "Grasshopper_Sparrow", "savannah", "Endemic movement", "Endangered", "Tall terrestrial raptor of open plains that hunts snakes and insects. Sensitive to grassland conversion and disturbance.", "Serengeti and Tarangire landscapes"),
        ("Barn Swallow (Mbayuwayu)", "Hirundo rustica", "Barn_Swallow", "savannah", "Migratory", "Least Concern", "Long-distance migrant from Eurasia that feeds over grasslands, wetlands, villages, and farms during the non-breeding season.", "Countrywide seasonal visitor"),
        ("White Pelican (Mwari mweupe)", "Pelecanus onocrotalus", "White_Pelican", "wetland", "Resident and migrant", "Least Concern", "Large waterbird using lakes, floodplains, and reservoirs; often feeds cooperatively in shallow water.", "Lakes Manyara, Natron, Rukwa"),
        ("African Fish Eagle (Tai samaki)", "Icthyophaga vocifer", "Frigatebird", "wetland", "Resident", "Least Concern", "Iconic raptor of lakes and rivers, recognized by its white head, chestnut body, and ringing call.", "Major lakes and rivers"),
        ("Superb Starling (Kwaheri)", "Lamprotornis superbus", "Cape_Glossy_Starling", "savannah", "Resident", "Least Concern", "Brightly colored starling common in dry savannah and visitor areas of northern parks.", "Northern Tanzania"),
        ("Hartlaub's Turaco (Kurumbizi)", "Tauraco hartlaubi", "Green_Jay", "montane-forest", "Resident", "Least Concern", "Forest canopy bird of highland and montane forest edges, important for seed dispersal.", "Kilimanjaro and northern highlands"),
        ("Common Tern (Shakwe)", "Sterna hirundo", "Common_Tern", "coastal-marine", "Migratory", "Least Concern", "Migratory seabird using coastal waters, islands, and estuaries along the Indian Ocean.", "Tanzania coast and islands"),
        ("Scarlet-chested Sunbird", "Chalcomitra senegalensis", "Ruby_throated_Hummingbird", "savannah", "Resident", "Least Concern", "Small nectar-feeding bird found in woodland, gardens, and savannah edges.", "Countrywide"),
    ]

    bird_objs = []
    for common, sci, folder, habitat_slug, migration, status, desc, region in birds_data:
        bird = Bird.query.filter_by(common_name=common).first() or Bird(common_name=common)
        bird.scientific_name = sci
        bird.habitat_id = habitat_objs[habitat_slug].id
        bird.migration_pattern = migration
        bird.conservation_status = status
        bird.description = desc
        bird.region = region
        bird.image_url = get_bird_image(folder)
        db.session.add(bird)
        bird_objs.append(bird)
    db.session.flush()

    desired_bird_names = {row[0] for row in birds_data}
    for bird in Bird.query.filter(~Bird.common_name.in_(desired_bird_names)).all():
        db.session.delete(bird)
    db.session.flush()

    by_habitat = {}
    for bird in bird_objs:
        by_habitat.setdefault(bird.habitat.name, []).append(bird)

    parks_data = [
        ("Serengeti National Park", "Tanzania", "Mara, Arusha, Simiyu", -2.3333, 34.8333, "Savannah", "June-October for migration; November-March for calving", "TANAPA National Park", 14763, "World-famous savannah and woodland ecosystem with raptors, bustards, starlings, migrants, and wet-season waterbirds.", "https://images.unsplash.com/photo-1547471080-7cc2caa01a7e?w=1200&q=85"),
        ("Ngorongoro Conservation Area", "Tanzania", "Arusha", -3.175, 35.55, "Savannah", "Year-round; dry season June-October best for wildlife", "UNESCO World Heritage", 8292, "Volcanic caldera with concentrated wildlife including crowned cranes, secretarybirds, and flamingos on Lake Magadi.", "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=1200&q=85"),
        ("Lake Manyara National Park", "Tanzania", "Arusha", -3.5, 35.8333, "Wetland", "Dry season June-October; best for waterbirds", "TANAPA National Park", 330, "Soda lake at the base of the Rift Valley escarpment — supports huge flamingo flocks, pelicans, storks, and fish eagles.", "https://images.unsplash.com/photo-1559827260-dc66d52bef19?w=1200&q=85"),
        ("Tarangire National Park", "Tanzania", "Manyara", -4.5, 36.0, "Savannah", "Dry season June-October; November-March green season", "TANAPA National Park", 2850, "Acacia and baobab savannah along the Tarangire River — a dry-season refuge for birds including superb starlings, hornbills, and migratory raptors.", "https://images.unsplash.com/photo-1516426122078-c23e76319801?w=1200&q=85"),
        ("Arusha National Park", "Tanzania", "Arusha", -3.25, 36.8333, "Montane Forest", "Year-round; best December-March", "TANAPA National Park", 552, "Montane forest on Mount Meru with Hartlaub's turaco, sunbirds, and forest raptors. Also features the Momella Lakes.", "https://images.unsplash.com/photo-1448375240586-882707db888b?w=1200&q=85"),
        ("Lake Natron", "Tanzania", "Arusha", -2.35, 36.0, "Wetland", "Dry season June-October", "Ramsar Site", 2400, "Alkaline lake and breeding site for East Africa's entire lesser flamingo population. Remote, starkly beautiful landscape.", "https://images.unsplash.com/photo-1505118380757-91f5f5632de0?w=1200&q=85"),
        ("Mkomazi National Park", "Tanzania", "Kilimanjaro", -4.0, 38.0, "Savannah", "Dry season June-October", "TANAPA National Park", 3245, "Arid savannah important for dry-country birds, large mammals, and the recovery of black rhino and wild dog populations.", "https://images.unsplash.com/photo-1547471080-7cc2caa01a7e?w=1200&q=85"),
        ("Kilimanjaro National Park", "Tanzania", "Kilimanjaro", -3.0667, 37.35, "Alpine", "January-March and June-October", "UNESCO World Heritage", 1688, "Africa's highest peak with five distinct habitat zones from montane forest to alpine desert — unique for high-altitude bird surveys.", "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=1200&q=85"),
    ]

    for name, country, region, lat, lon, hab, months, status, area, desc, img in parks_data:
        park = Park.query.filter_by(name=name).first() or Park(name=name)
        park.country = country
        park.region = region
        park.description = desc
        park.latitude = lat
        park.longitude = lon
        park.habitat_type = hab
        park.best_visit_months = months
        park.conservation_status = status
        park.area_km2 = area
        park.image_url = img
        park.birds = by_habitat.get(hab, bird_objs[:4])[:6]
        db.session.add(park)

    desired_park_names = {row[0] for row in parks_data}
    for park in Park.query.filter(~Park.name.in_(desired_park_names)).all():
        db.session.delete(park)

    articles_data = [
        ("Why Tanzania Matters for African Bird Conservation", "tanzania-bird-conservation", "Tanzania connects Rift Valley wetlands, coastal mangroves, savannah migration corridors, Eastern Arc forests, and Africa's highest mountain. Protecting this habitat network supports tourism, research, livelihoods, and globally important bird populations.", "Conservation", 6, get_bird_image("Cape_Glossy_Starling")),
    ]

    for title, slug, content, category, read_time, image_url in articles_data:
        article = Article.query.filter_by(slug=slug).first() or Article(slug=slug)
        article.title = title
        article.content = content
        article.category = category
        article.read_time = read_time
        article.image_url = image_url
        db.session.add(article)

    desired_article_slugs = {row[1] for row in articles_data}
    for article in Article.query.filter(~Article.slug.in_(desired_article_slugs)).all():
        db.session.delete(article)

    desired_habitat_slugs = {row[1] for row in habitats_data}
    for habitat in Habitat.query.filter(~Habitat.slug.in_(desired_habitat_slugs)).all():
        db.session.delete(habitat)

    admin_email = os.getenv("ADMIN_EMAIL", "admin@birds.tz")
    admin = User.query.filter_by(email=admin_email).first()
    if not admin:
        db.session.add(
            User(
                name="System Administrator",
                email=admin_email,
                password_hash=generate_password_hash(os.getenv("ADMIN_PASSWORD", "admin123")),
                role="admin",
            )
        )
    contributor_email = os.getenv("CONTRIBUTOR_EMAIL", "contributor@birds.tz")
    if not User.query.filter_by(email=contributor_email).first():
        db.session.add(
            User(
                name="Jane Field Researcher",
                email=contributor_email,
                password_hash=generate_password_hash(os.getenv("CONTRIBUTOR_PASSWORD", "birder123")),
                role="contributor",
            )
        )

    db.session.commit()


# Precompute + cache reference embeddings for performance.
from identify_cache import ReferenceEmbeddingCache, load_reference_cache, save_reference_cache

# Decode base64-embedded embeddings if pkl not present
from _embeddings_data import decode_embeddings
decode_embeddings(os.path.join(PROJECT_ROOT, "reference_embeddings.pkl"))

REFERENCE_EMBEDDINGS_VERSION = "v4"

with app.app_context():
    db.create_all()
    seed_data()

    cache = load_reference_cache(PROJECT_ROOT, REFERENCE_EMBEDDINGS_VERSION)
    birds_for_cache = Bird.query.all()

    if cache is None:
        embeddings_by_name, model_name_used = precompute_reference_embeddings(birds_for_cache, PROJECT_ROOT, verbose=False)
        cache = ReferenceEmbeddingCache(
            embeddings_by_bird_id=embeddings_by_name,
            model_name=model_name_used,
            version=REFERENCE_EMBEDDINGS_VERSION,
        )
        save_reference_cache(PROJECT_ROOT, cache)

    app.reference_embeddings = cache.embeddings_by_bird_id


@app.route("/ca-cert")
def ca_cert_download():
    ca_path = os.path.join(app.root_path, "static", "mkcert-ca.pem")
    if os.path.exists(ca_path):
        return send_from_directory(os.path.join(app.root_path, "static"), "mkcert-ca.pem", mimetype="application/x-pem-file")
    return "CA certificate not available", 404


if __name__ == "__main__":
    import os, socket, sys

    host = "0.0.0.0"
    port = int(os.getenv("PORT", 5000))
    use_ssl = "--no-ssl" not in sys.argv

    local_ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    ssl_ctx = None
    if use_ssl:
        cert_file = os.path.join(os.path.dirname(__file__), "certs", "cert.pem")
        key_file = os.path.join(os.path.dirname(__file__), "certs", "key.pem")
        if os.path.exists(cert_file) and os.path.exists(key_file):
            ssl_ctx = (cert_file, key_file)
            print(f"  Using mkcert certificate (trusted on this PC)")
        else:
            print(f"  Certificate files not found at {cert_file}")
            use_ssl = False

    protocol = "https" if use_ssl else "http"
    print(f"\n{'='*60}")
    print(f"  Tanzania Bird Finder")
    print(f"  {protocol}://localhost:{port}")
    if use_ssl and local_ip not in ("127.0.0.1", "localhost"):
        print(f"  {protocol}://{local_ip}:{port}  (phone)")
        print()
        print(f"  Phone access: first install the CA cert")
        print(f"     On phone, accept the warning, then visit:")
        print(f"     {protocol}://{local_ip}:{port}/ca-cert")
        print(f"     Download and install the certificate")
        print(f"     (Android: Security > Install a certificate > CA)")
        print(f"     (iPhone: Settings > Profile, then enable in About > Cert Trust)")
    print(f"{'='*60}\n")

    debug_mode = os.getenv("FLASK_DEBUG", "1") == "1"
    app.run(host=host, port=port, debug=debug_mode, use_reloader=False, ssl_context=ssl_ctx)

