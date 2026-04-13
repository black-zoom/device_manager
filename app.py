from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
    Response,
)
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from datetime import date, timedelta
import csv
import io

from config import Config
from models import (
    DeviceHistory,
    db,
    User,
    Device,
    DeviceType,
    Status,
    Department,
    Crew,
    DeactivationReason,
)

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

with app.app_context():
    db.create_all()
    default_statuses = [
        "Встановлений працює",
        "Встановлений не працює",
        "Обірвано/втрачено з’єднання",
    ]

    for status_name in default_statuses:
        existing_status = Status.query.filter_by(name=status_name).first()
        if not existing_status:
            new_status = Status(name=status_name)
            db.session.add(new_status)

    db.session.commit()


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "username" not in session:
            flash("Будь ласка, спочатку увійдіть.", "error")
            return redirect(url_for("login"))
        if not session.get("is_admin"):
            flash("Ви не маєте дозволу на доступ до цієї сторінки.", "error")
            return redirect(url_for("index"))
        return f(*args, **kwargs)

    return decorated_function


@app.before_request
def refresh_session():
    if "username" in session:
        session.permanent = True


@app.route("/")
def index():
    if not User.query.filter_by(username="admin").first():
        return redirect(url_for("set_admin_password"))

    username = session.get("username")
    if not username:
        return redirect(url_for("login"))

    is_archive_mode = request.args.get("show_archived", "false").lower() == "true"
    query = Device.query.filter_by(is_archived=is_archive_mode)

    for field in ["status_id", "department_id", "crew_id"]:
        val = request.args.get(field)
        if val:
            query = query.filter(getattr(Device, field) == val)

    period = request.args.get("period")
    today = date.today()

    if period == "day":
        query = query.filter(Device.install_date == today)
    elif period == "week":
        query = query.filter(Device.install_date >= today - timedelta(days=7))
    elif period == "month":
        query = query.filter(Device.install_date >= today - timedelta(days=30))
    elif period == "year":
        query = query.filter(Device.install_date >= today - timedelta(days=365))

    if request.args.get("install_date_from"):
        query = query.filter(
            Device.install_date >= date.fromisoformat(request.args["install_date_from"])
        )
    if request.args.get("install_date_to"):
        query = query.filter(
            Device.install_date <= date.fromisoformat(request.args["install_date_to"])
        )

    devices = query.order_by(Device.id.desc()).all()

    total_in_view = Device.query.filter_by(is_archived=is_archive_mode).count()
    filtered_count = len(devices)

    percentage = (
        round((filtered_count / total_in_view * 100), 1) if total_in_view > 0 else 0
    )

    dicts = {
        "device_types": DeviceType.query.filter_by(is_active=True).all(),
        "departments": Department.query.filter_by(is_active=True).all(),
        "statuses": Status.query.filter_by(is_active=True).all(),
        "crews": Crew.query.filter_by(is_active=True).all(),
        "deactivation_reasons": DeactivationReason.query.filter_by(
            is_active=True
        ).all(),
    }

    return render_template(
        "index.html",
        is_archive_mode=is_archive_mode,
        username=username,
        devices=devices,
        filtered_count=filtered_count,
        total_devices=total_in_view,
        percentage=percentage,
        current_filters=request.args,
        **dicts,
    )


@app.route("/set-admin-password", methods=["GET", "POST"])
def set_admin_password():
    existing_admin = User.query.filter_by(is_admin=True).first()
    if existing_admin:
        flash("Адміністратор уже існує.")
        return redirect(url_for("login"))
    if request.method == "POST":
        password = request.form["password"]
        hashed_password = generate_password_hash(password)

        admin = User(username="admin", password=hashed_password, is_admin=True)
        db.session.add(admin)
        db.session.commit()

        return redirect(url_for("index"))

    return render_template("set_admin_password.html")


@app.route("/register", methods=["GET", "POST"])
@admin_required
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash("Це ім'я користувача вже зайняте.")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)

        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        return redirect(url_for("users"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session.permanent = True
            session["username"] = username
            session["is_admin"] = user.is_admin
            return redirect(url_for("index"))

        flash("Недійсні облікові дані. Будь ласка, спробуйте ще раз.", "error")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/users")
@admin_required
def users():
    search_query = request.args.get("q", "")

    if search_query:
        user_list = User.query.filter(
            ~User.is_admin, User.username.ilike(f"%{search_query}%")
        ).all()
    else:
        user_list = User.query.filter_by(is_admin=False).all()

    return render_template("users.html", users=user_list)


@app.route("/delete_user/<int:user_id>", methods=["POST"])
@admin_required
def delete_user(user_id):
    user_to_delete = User.query.get_or_404(user_id)

    if user_to_delete.is_admin:
        flash("Неможливо видалити адміністратора!", "error")
        return redirect(url_for("users"))

    db.session.delete(user_to_delete)
    db.session.commit()
    flash("Користувач успішно видалено!")

    return redirect(url_for("users"))


def generate_next_full_number(base_n):
    last_device = (
        Device.query.filter_by(base_number=base_n)
        .order_by(Device.suffix.desc())
        .first()
    )

    if not last_device:
        new_suffix = 1
    else:
        new_suffix = last_device.suffix + 1

    full_num = f"{int(base_n):03d}-{new_suffix}"
    return base_n, new_suffix, full_num


@app.route("/device/<int:id>")
def get_device(id):
    d = Device.query.get_or_404(id)
    return {
        "id": d.id,
        "full_number": d.full_number,
        "base_number": d.base_number,
        "device_type_id": d.device_type_id,
        "department_id": d.department_id,
        "status_id": d.status_id,
        "crew_id": d.crew_id,
        "location": d.location,
        "install_date": d.install_date.isoformat() if d.install_date else "",
        "manufacture_date": d.manufacture_date.isoformat()
        if d.manufacture_date
        else "",
        "comment": d.comment,
        "deactivation_date": d.deactivation_date.isoformat()
        if d.deactivation_date
        else "",
        "deactivation_reason_id": d.deactivation_reason_id,
        "is_archived": d.is_archived,
    }


@app.route("/device/create")
def create_device():
    return render_template(
        "device_form.html",
        device=None,
        device_types=DeviceType.query.all(),
        departments=Department.query.all(),
        statuses=Status.query.all(),
        crews=Crew.query.all(),
    )


@app.route("/devices/<int:id>/edit")
def edit_device(id):
    device = Device.query.get_or_404(id)

    return render_template(
        "device_form.html",
        device=device,
        device_types=DeviceType.query.all(),
        departments=Department.query.all(),
        statuses=Status.query.all(),
        crews=Crew.query.all(),
    )


@app.route("/devices/save", methods=["POST"])
def save_device():
    username = session.get("username", "Невідомий")
    device_id = request.form.get("id")

    def parse_date(d_str):
        from datetime import date

        return date.fromisoformat(d_str) if d_str else None

    def parse_int(val):
        return int(val) if val else None

    form_data = {
        "device_type_id": int(request.form.get("device_type_id")),
        "status_id": int(request.form.get("status_id")),
        "department_id": parse_int(request.form.get("department_id")),
        "crew_id": parse_int(request.form.get("crew_id")),
        "location": request.form.get("location"),
        "comment": request.form.get("comment"),
        "manufacture_date": parse_date(request.form.get("manufacture_date")),
        "install_date": parse_date(request.form.get("install_date")),
        "deactivation_date": parse_date(request.form.get("deactivation_date")),
        "deactivation_reason_id": parse_int(request.form.get("deactivation_reason_id")),
    }

    if not device_id or device_id == "" or device_id == "null":
        user_base = request.form.get("base_number", 1)
        base, suffix, full = generate_next_full_number(user_base)

        device = Device(base_number=base, suffix=suffix, full_number=full)
        db.session.add(device)

        history_action = f"Створено запис про пристрій (ID: {full})"
    else:
        device = Device.query.get_or_404(device_id)
        changes = []
        if str(device.status_id) != str(form_data["status_id"]):
            old_status = (
                Status.query.get(device.status_id) if device.status_id else None
            )
            new_status = (
                Status.query.get(form_data["status_id"])
                if form_data["status_id"]
                else None
            )

            old_name = old_status.name if old_status else "Невідомо"
            new_name = new_status.name if new_status else "Невідомо"

            changes.append(f"Змінено статус ({old_name} ➔ {new_name})")
        if str(device.crew_id or "") != str(form_data["crew_id"] or ""):
            old_crew = Crew.query.get(device.crew_id) if device.crew_id else None
            new_crew = (
                Crew.query.get(form_data["crew_id"]) if form_data["crew_id"] else None
            )

            old_name = old_crew.name if old_crew else "Немає"
            new_name = new_crew.name if new_crew else "Немає"

            changes.append(f"Змінено виконавця ({old_name} ➔ {new_name})")
        if str(device.location or "") != str(form_data["location"] or ""):
            changes.append("Оновлено локацію")
        history_action = " | ".join(changes) if changes else None

    for key, value in form_data.items():
        setattr(device, key, value)

    if not device_id:
        db.session.flush()

    if history_action:
        history = DeviceHistory(
            device_id=device.id, username=username, action=history_action
        )
        db.session.add(history)

    try:
        db.session.commit()
        flash("Дані успішно збережено!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Помилка при збереженні: {str(e)}", "error")

    return redirect(url_for("index"))


@app.route("/devices/<int:id>/delete", methods=["POST"])
def delete_device(id):
    device = Device.query.get_or_404(id)

    device.is_archived = True

    db.session.commit()
    log = DeviceHistory(
        device_id=device.id,
        username=session["username"],
        action="Пристрій переміщено в архів",
    )
    db.session.add(log)
    db.session.commit()

    flash("Пристрій архівовано!", "success")
    return redirect(url_for("index"))


@app.route("/devices/<int:id>/restore", methods=["POST"])
def restore_device(id):
    if not session.get("username"):
        return redirect(url_for("login"))

    device = Device.query.get_or_404(id)
    device.is_archived = False

    log = DeviceHistory(
        device_id=device.id, username=session["username"], action="Відновлено з архіву"
    )

    db.session.add(log)
    db.session.commit()

    return redirect(url_for("index", show_archived="true"))


@app.route("/export_csv")
def export_csv():
    show_archived = request.args.get("show_archived") == "true"
    query = Device.query.filter_by(is_archived=show_archived)

    status_id = request.args.get("status_id")
    department_id = request.args.get("department_id")
    crew_id = request.args.get("crew_id")
    install_date_from = request.args.get("install_date_from")
    install_date_to = request.args.get("install_date_to")

    if status_id:
        query = query.filter(Device.status_id == status_id)
    if department_id:
        query = query.filter(Device.department_id == department_id)
    if crew_id:
        query = query.filter(Device.crew_id == crew_id)
    if install_date_from:
        query = query.filter(
            Device.install_date >= date.fromisoformat(install_date_from)
        )
    if install_date_to:
        query = query.filter(Device.install_date <= date.fromisoformat(install_date_to))

    devices = query.order_by(Device.id.desc()).all()

    si = io.StringIO()
    si.write("\ufeff")

    writer = csv.writer(si, delimiter=",")
    writer.writerow(
        [
            "ID",
            "Номер",
            "Тип",
            "Підрозділ",
            "Статус",
            "Виконавець",
            "Локація",
            "Дата встановлення",
            "Коментар",
        ]
    )

    for d in devices:
        writer.writerow(
            [
                d.id,
                d.full_number,
                d.device_type.name if d.device_type else "-",
                d.department.name if d.department else "-",
                d.status.name if d.status else "-",
                d.crew.name if d.crew else "-",
                d.location or "-",
                d.install_date.strftime("%d.%m.%Y") if d.install_date else "-",
                d.comment or "-",
            ]
        )

    return Response(
        si.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=devices_export.csv"},
    )


@app.route("/dictionaries")
@admin_required
def dictionaries():
    username = session.get("username")

    device_types = DeviceType.query.all()
    departments = Department.query.all()
    crews = Crew.query.all()
    statuses = Status.query.all()
    deactivation_reasons = DeactivationReason.query.all()

    return render_template(
        "dictionaries.html",
        username=username,
        device_types=device_types,
        departments=departments,
        crews=crews,
        statuses=statuses,
        deactivation_reasons=deactivation_reasons,
    )


@app.route("/dict/save", methods=["POST"])
def save_dict():
    if "username" not in session:
        return redirect(url_for("login"))

    dict_type = request.form.get("type")
    action = request.form.get("action")
    item_id = request.form.get("id")
    name = request.form.get("name")

    model_map = {
        "department": Department,
        "device_type": DeviceType,
        "crew": Crew,
        "status": Status,
        "deactivation_reason": DeactivationReason,
    }

    ModelClass = model_map.get(dict_type)

    if not ModelClass:
        return "Невідомий тип довідника", 400

    if action == "toggle" and item_id:
        item = ModelClass.query.get(item_id)
        if item:
            item.is_active = not item.is_active
            db.session.commit()

    elif action == "save":
        if item_id:
            item = ModelClass.query.get(item_id)
            if item and name:
                item.name = name
                db.session.commit()
        else:
            if name:
                new_item = ModelClass(name=name, is_active=True)
                db.session.add(new_item)
                db.session.commit()

    return redirect(url_for("dictionaries"))


@app.route("/history")
def global_history():
    history_logs = DeviceHistory.query.order_by(DeviceHistory.timestamp.desc()).all()

    return render_template("history.html", history_logs=history_logs)


if __name__ == "__main__":
    app.run(debug=True)
