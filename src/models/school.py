from sqlalchemy import ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.extensions import db
from src.models.enums import RoomType


class School(db.Model):
    __tablename__ = 'schools'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)
    teachers = relationship('Teacher', back_populates='school')
    rooms = relationship('Room', back_populates='school')

    def __str__(self): return self.name


class Teacher(db.Model):
    __tablename__ = 'teachers'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)
    school_id: Mapped[int] = mapped_column(ForeignKey('schools.id'), nullable=False)
    school = relationship('School', back_populates='teachers')
    constraints: Mapped[dict] = mapped_column(db.JSON, nullable=True)

    def __str__(self): return self.name


class Room(db.Model):
    __tablename__ = 'rooms'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)
    capacity: Mapped[int] = mapped_column(default=30)

    # НОВОЕ ПОЛЕ: Корпус (например, "A", "B", "Main", "Sport")
    # По умолчанию пустая строка, если корпусов нет
    building: Mapped[str] = mapped_column(nullable=True, default="")

    room_type: Mapped[RoomType] = mapped_column(Enum(RoomType), default=RoomType.STANDARD)

    school_id: Mapped[int] = mapped_column(ForeignKey('schools.id'), nullable=False)
    school = relationship('School', back_populates='rooms')

    def __str__(self):
        return f"{self.name} [{self.room_type.value}]"


class Subject(db.Model):
    __tablename__ = 'subjects'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)
    school_id: Mapped[int] = mapped_column(ForeignKey('schools.id'), nullable=False)

    def __str__(self): return self.name