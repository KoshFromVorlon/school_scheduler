import pandas as pd
from src.extensions import db
from src.models.school import School, Teacher, Subject, Room
from src.models.schedule import StudentGroup, Workload
from src.models.enums import RoomType, SubgroupType


def import_data_from_file(filepath):
    """
    ИМПОРТ НАГРУЗКИ (Учителя, Предметы, Классы).
    """
    # 1. Читаем файл
    if filepath.endswith('.csv'):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)

    # Приводим заголовки к единому виду
    df.columns = [c.strip().lower() for c in df.columns]

    # Словарь соответствия колонок
    col_map = {
        'учитель': 'teacher', 'teacher': 'teacher',
        'предмет': 'subject', 'subject': 'subject',
        'класс': 'class', 'class': 'class', 'group': 'class',
        'часов': 'hours', 'hours': 'hours',
        'подгруппа': 'subgroup', 'subgroup': 'subgroup',
        'кабинет': 'roomtype', 'room_type': 'roomtype', 'roomtype': 'roomtype',
        'смена': 'shift', 'shift': 'shift'
    }

    # 2. Очистка старой нагрузки
    db.session.query(Workload).delete()

    school = School.query.first()
    if not school:
        school = School(name="My School")
        db.session.add(school)
        db.session.commit()

    # Кэши для быстрого поиска
    teachers_cache = {t.name: t for t in Teacher.query.all()}
    subjects_cache = {s.name: s for s in Subject.query.all()}
    groups_cache = {g.name: g for g in StudentGroup.query.all()}

    count = 0

    # 3. Перебор строк
    for index, row in df.iterrows():
        def get_val(rus_keys, default=None):
            for k in rus_keys:
                found_col = next((c for c in df.columns if col_map.get(c) == k), None)
                if found_col:
                    val = row[found_col]
                    return val if pd.notna(val) else default
            return default

        teacher_name = get_val(['teacher'], 'Unknown Teacher')
        subject_name = get_val(['subject'], 'General')
        class_name = str(get_val(['class'], '1-A'))
        hours = int(get_val(['hours'], 1))

        # Подгруппа
        sub_raw = str(get_val(['subgroup'], 'whole')).lower().strip()
        subgroup = SubgroupType.WHOLE_CLASS
        if '1' in sub_raw or 'first' in sub_raw:
            subgroup = SubgroupType.GROUP_1
        elif '2' in sub_raw or 'second' in sub_raw:
            subgroup = SubgroupType.GROUP_2
        elif 'boy' in sub_raw or 'м' in sub_raw:
            subgroup = SubgroupType.BOYS
        elif 'girl' in sub_raw or 'д' in sub_raw:
            subgroup = SubgroupType.GIRLS

        # Тип кабинета
        room_raw = str(get_val(['roomtype'], 'standard')).lower()
        room_type = RoomType.STANDARD
        if 'gym' in room_raw or 'спорт' in room_raw:
            room_type = RoomType.GYM
        elif 'it' in room_raw or 'инф' in room_raw:
            room_type = RoomType.IT_LAB
        elif 'chem' in room_raw or 'хим' in room_raw:
            room_type = RoomType.LAB_CHEMISTRY
        elif 'phys' in room_raw or 'физ' in room_raw and 'культ' not in subject_name.lower():
            room_type = RoomType.LAB_PHYSICS
        elif 'bio' in room_raw or 'био' in room_raw:
            room_type = RoomType.LAB_BIO

        # Смена
        shift = int(get_val(['shift'], 1))

        # Создание объектов при необходимости
        if teacher_name not in teachers_cache:
            t = Teacher(name=teacher_name, school_id=school.id)
            db.session.add(t)
            teachers_cache[teacher_name] = t
        teacher = teachers_cache[teacher_name]

        if subject_name not in subjects_cache:
            s = Subject(name=subject_name, school_id=school.id)
            db.session.add(s)
            subjects_cache[subject_name] = s
        subject = subjects_cache[subject_name]

        if class_name not in groups_cache:
            g = StudentGroup(name=class_name, shift=shift, school_id=school.id)
            db.session.add(g)
            groups_cache[class_name] = g
        group = groups_cache[class_name]

        w = Workload(
            school_id=school.id,
            teacher=teacher,
            subject=subject,
            group=group,
            hours_per_week=hours,
            subgroup=subgroup,
            required_room_type=room_type
        )
        db.session.add(w)
        count += 1

    db.session.commit()
    return count


def import_rooms_from_file(filepath):
    """
    ИМПОРТ КАБИНЕТОВ (Инфраструктура).
    Ожидаемые колонки: Name, Type, Capacity, Building
    """
    if filepath.endswith('.csv'):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)

    df.columns = [c.strip().lower() for c in df.columns]

    # Маппинг колонок
    col_map = {
        'название': 'name', 'name': 'name', 'room': 'name',
        'тип': 'type', 'type': 'type', 'roomtype': 'type',
        'вместимость': 'capacity', 'capacity': 'capacity', 'size': 'capacity',
        'корпус': 'building', 'building': 'building', 'corp': 'building'
    }

    school = School.query.first()
    if not school:
        school = School(name="Universal School")
        db.session.add(school)
        db.session.commit()

    # ВНИМАНИЕ: Удаляем старые кабинеты, чтобы обновить структуру.
    # Это каскадно удалит существующее расписание (ScheduleEntry), если оно есть.
    db.session.query(Room).delete()

    count = 0
    for index, row in df.iterrows():
        def get_val(rus_keys, default=None):
            for k in rus_keys:
                found_col = next((c for c in df.columns if col_map.get(c) == k), None)
                if found_col:
                    val = row[found_col]
                    return val if pd.notna(val) else default
            return default

        name = str(get_val(['name'], f"Room-{index}"))
        capacity = int(get_val(['capacity'], 30))
        building = str(get_val(['building'], ""))

        # Определение типа
        type_raw = str(get_val(['type'], 'standard')).lower()
        r_type = RoomType.STANDARD

        if 'gym' in type_raw or 'спорт' in type_raw:
            r_type = RoomType.GYM
        elif 'it' in type_raw or 'инф' in type_raw:
            r_type = RoomType.IT_LAB
        elif 'chem' in type_raw or 'хим' in type_raw:
            r_type = RoomType.LAB_CHEMISTRY
        elif 'phys' in type_raw or 'физ' in type_raw:
            r_type = RoomType.LAB_PHYSICS
        elif 'bio' in type_raw or 'био' in type_raw:
            r_type = RoomType.LAB_BIO

        room = Room(
            name=name,
            capacity=capacity,
            building=building,
            room_type=r_type,
            school_id=school.id
        )
        db.session.add(room)
        count += 1

    db.session.commit()
    return count