import click
from flask.cli import with_appcontext
from src.extensions import db
from src.models.school import School, Teacher, Room, Subject
from src.models.schedule import StudentGroup, Workload, TimeSlot


@click.command('seed_db')
@with_appcontext
def seed_db_command():
    """Заполняет базу тестовыми данными."""
    print("🌱 Начинаем посев данных (Seeding)...")

    # Проверка на наличие данных, чтобы не дублировать
    if School.query.first():
        print("⚠️ Данные уже существуют. Пропуск.")
        return

    # 1. Создаем Школу
    school = School(name="Lyceum #1")
    db.session.add(school)
    db.session.commit()  # Коммит, чтобы получить ID школы

    # 2. Создаем Кабинеты
    rooms = [
        Room(name="101 (Math)", capacity=30, school_id=school.id),
        Room(name="102 (History)", capacity=30, school_id=school.id),
        Room(name="201 (Physics Lab)", is_lab=True, capacity=20, school_id=school.id),
        Room(name="202 (Bio Lab)", is_lab=True, capacity=20, school_id=school.id),
        Room(name="Gym", capacity=50, school_id=school.id),
    ]
    db.session.add_all(rooms)

    # 3. Создаем Учителей
    teachers = [
        Teacher(name="Mr. Anderson (Math)", school_id=school.id),
        Teacher(name="Mrs. Smith (History)", school_id=school.id),
        Teacher(name="Dr. House (Biology)", school_id=school.id),
        Teacher(name="Mr. White (Chemistry)", school_id=school.id),
        Teacher(name="Coach Carter (PE)", school_id=school.id),
    ]
    db.session.add_all(teachers)
    db.session.commit()

    # 4. Предметы
    subjects = [
        Subject(name="Mathematics", school_id=school.id),
        Subject(name="History", school_id=school.id),
        Subject(name="Biology", school_id=school.id),
        Subject(name="Chemistry", school_id=school.id),
        Subject(name="PE", school_id=school.id),
    ]
    db.session.add_all(subjects)
    db.session.commit()

    # 5. Классы
    groups = [
        StudentGroup(name="10-A", school_id=school.id),
        StudentGroup(name="10-B", school_id=school.id),
    ]
    db.session.add_all(groups)
    db.session.commit()

    # 6. Временные слоты (Пн-Пт, по 5 уроков)
    slots = []
    for day in range(1, 6):  # 1=Monday
        for period in range(1, 6):  # 1=First lesson
            slots.append(TimeSlot(day_of_week=day, period_number=period, school_id=school.id))
    db.session.add_all(slots)
    db.session.commit()

    # 7. Нагрузка (Кто что ведет)
    # Нужно получить объекты из базы, чтобы взять их ID
    math_subj = subjects[0]
    hist_subj = subjects[1]
    math_teacher = teachers[0]
    hist_teacher = teachers[1]
    group_a = groups[0]
    group_b = groups[1]

    workloads = [
        # 10-A Учит Математику (Mr. Anderson) - 5 часов
        Workload(group_id=group_a.id, subject_id=math_subj.id, teacher_id=math_teacher.id, hours_per_week=5,
                 school_id=school.id),
        # 10-A Учит Историю - 3 часа
        Workload(group_id=group_a.id, subject_id=hist_subj.id, teacher_id=hist_teacher.id, hours_per_week=3,
                 school_id=school.id),
        # 10-B Учит Математику (Тот же учитель!) - 5 часов
        Workload(group_id=group_b.id, subject_id=math_subj.id, teacher_id=math_teacher.id, hours_per_week=5,
                 school_id=school.id)
    ]

    db.session.add_all(workloads)
    db.session.commit()

    print(f"✅ Успешно создана школа '{school.name}' и тестовые данные.")


def register_commands(app):
    """Регистрирует команды в приложении."""
    app.cli.add_command(seed_db_command)