"""Student account validation and lookup."""
import re

from services.errors import ValidationError


TEN_DIGITS = re.compile(r"[0-9]{10}")
NAME_PATTERN = re.compile(r"[A-Za-z][A-Za-z .'-]{1,59}")


class StudentService:
    def __init__(self, store):
        self.store = store

    def register(self, payload):
        name = payload.get("name")
        phone = payload.get("phone")
        student_id = payload.get("student_id")

        if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name.strip()):
            raise ValidationError("Enter your name using 2 to 60 letters.")
        if not isinstance(phone, str) or not TEN_DIGITS.fullmatch(phone):
            raise ValidationError("Phone number must be exactly 10 digits.")
        if not isinstance(student_id, str) or not TEN_DIGITS.fullmatch(student_id):
            raise ValidationError("College ID Card Number must be exactly 10 digits.")

        student = {"name": name.strip(), "phone": phone, "student_id": student_id}
        self.store.create_student(student)
        return student

    def authenticate(self, payload):
        name = payload.get("name")
        phone = payload.get("phone")
        if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name.strip()):
            raise ValidationError("Enter your name using 2 to 60 letters.")
        if not isinstance(phone, str) or not TEN_DIGITS.fullmatch(phone):
            raise ValidationError("Phone number must be exactly 10 digits.")
        student = self.store.get_student_by_phone(phone)
        if student and student["name"].casefold() == name.strip().casefold():
            return student
        return None
