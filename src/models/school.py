from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.extensions import db


# 1. Сама Школа (Лицей)
class School(db.Model):
    __tablename__ = 'schools'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)

    # Связи (чтобы можно было делать school.teachers)
    teachers = relationship('Teacher', back_populates='school')
    rooms = relationship('Room', back_populates='school')


# 2. Учитель
class Teacher(db.Model):
    __tablename__ = 'teachers'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)

    # Привязка к школе
    school_id: Mapped[int] = mapped_column(ForeignKey('schools.id'), nullable=False)
    school = relationship('School', back_populates='teachers')

    # Ограничения (например, "Не могу в Среду"). Храним как JSON.
    constraints: Mapped[dict] = mapped_column(db.JSON, nullable=True)


# 3. Кабинет
class Room(db.Model):
    __tablename__ = 'rooms'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)  # Номер кабинета
    capacity: Mapped[int] = mapped_column(default=30)  # Вместимость
    is_lab: Mapped[bool] = mapped_column(default=False)  # Это лаборатория?

    school_id: Mapped[int] = mapped_column(ForeignKey('schools.id'), nullable=False)
    school = relationship('School', back_populates='rooms')


# 4. Предмет
class Subject(db.Model):
    __tablename__ = 'subjects'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)

    school_id: Mapped[int] = mapped_column(ForeignKey('schools.id'), nullable=False)