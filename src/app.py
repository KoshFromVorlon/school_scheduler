from flask import Flask, render_template, redirect, url_for
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView

from src.config import Config
from src.extensions import db, migrate
from src.commands import register_commands
from src.api.debug import debug_bp

# Импорты всех моделей для админки и работы приложения
from src.models.schedule import Workload, TimeSlot, StudentGroup, ScheduleEntry
from src.models.school import Room, Subject, Teacher, School
from src.solver.engine import SchoolScheduler


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Инициализация расширений
    db.init_app(app)
    migrate.init_app(app, db)
    register_commands(app)
    app.register_blueprint(debug_bp)

    # --- НАСТРОЙКА АДМИНКИ (Flask-Admin) ---
    # name='School Scheduler' - заголовок в меню
    # template_mode='bootstrap4' - стиль оформления
    admin = Admin(app, name='School Scheduler', template_mode='bootstrap4')

    # Регистрация таблиц, чтобы ими можно было управлять через /admin
    admin.add_view(ModelView(School, db.session, name="Школы"))
    admin.add_view(ModelView(Teacher, db.session, name="Учителя"))
    admin.add_view(ModelView(Subject, db.session, name="Предметы"))
    admin.add_view(ModelView(Room, db.session, name="Кабинеты"))
    admin.add_view(ModelView(StudentGroup, db.session, name="Классы"))
    admin.add_view(ModelView(Workload, db.session, name="Нагрузка (План)"))
    admin.add_view(ModelView(TimeSlot, db.session, name="Слоты времени"))
    admin.add_view(ModelView(ScheduleEntry, db.session, name="Результат (Расписание)"))

    # ----------------------------------------

    @app.route('/')
    def index():
        return redirect(url_for('show_schedule'))

    @app.route('/schedule')
    def show_schedule():
        # 1. Берем ГОТОВОЕ расписание из базы
        entries = ScheduleEntry.query.all()

        # 2. Если пусто — показываем пустую таблицу
        if not entries:
            return render_template('schedule.html', schedule_grid={}, empty=True)

        # 3. Подгружаем справочники (чтобы превратить ID в Имена)
        # Оптимизация: загружаем все справочники в память словарями
        subjects = {s.id: s.name for s in Subject.query.all()}
        teachers = {t.id: t.name for t in Teacher.query.all()}
        groups = {g.id: g.name for g in StudentGroup.query.all()}
        rooms = {r.id: r.name for r in Room.query.all()}

        # Подгружаем сами нагрузки и слоты, чтобы связать данные
        workloads = {w.id: w for w in Workload.query.all()}
        slots = {s.id: s for s in TimeSlot.query.all()}

        # 4. Собираем сетку для шаблона
        schedule_grid = {}
        for entry in entries:
            w = workloads.get(entry.workload_id)
            s = slots.get(entry.timeslot_id)

            # Защита от "битых" ссылок (если удалили учителя, а расписание осталось)
            if not w or not s:
                continue

            key = (s.day_of_week, s.period_number)
            if key not in schedule_grid:
                schedule_grid[key] = []

            schedule_grid[key].append({
                "subject": subjects.get(w.subject_id, "?"),
                "teacher": teachers.get(w.teacher_id, "?"),
                "group": groups.get(w.group_id, "?"),
                "room": rooms.get(entry.room_id, "?")
            })

        return render_template('schedule.html', schedule_grid=schedule_grid, empty=False)

    @app.route('/generate', methods=['POST'])
    def generate_schedule():
        # Хардкод ID=1 пока оставляем, так как у нас одна школа
        school_id = 1
        workloads = Workload.query.filter_by(school_id=school_id).all()
        slots = TimeSlot.query.filter_by(school_id=school_id).all()
        rooms = Room.query.filter_by(school_id=school_id).all()

        if not workloads:
            return "Нет данных о нагрузке! Зайдите в /admin и добавьте записи в 'Нагрузка'.", 400

        # Запускаем решатель
        solver = SchoolScheduler(school_id)
        # Он теперь возвращает True/False, а результат пишет в БД
        success = solver.run_algorithm(workloads, slots, rooms)

        if success:
            return redirect(url_for('show_schedule'))
        else:
            return "Не удалось составить расписание (конфликт ограничений)", 400

    return app