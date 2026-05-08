from enum import StrEnum


class FieldType(StrEnum):
    text = "text"
    textarea = "textarea"
    number = "number"
    email = "email"
    phone = "phone"
    select = "select"
    multiselect = "multiselect"
    checkbox = "checkbox"
    file = "file"
    date = "date"
