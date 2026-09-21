"""Validated API inputs, shared by all write endpoints."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, AfterValidator, BeforeValidator, model_validator

from backend.config import KST
from backend.utils.todos import normalize_repeat


def password_bytes(value: str) -> str:
    if len(value.encode('utf-8')) > 72:
        raise ValueError('비밀번호는 UTF-8 기준 72바이트 이하여야 합니다.')
    return value


def new_password(value: str) -> str:
    if len(value) < 8 or not value.strip():
        raise ValueError('새 비밀번호는 공백만 사용할 수 없으며 8자 이상이어야 합니다.')
    return value


def nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError('내용을 입력해주세요.')
    return value.strip()


def email_address(value: str) -> str:
    # Preserve existing account spelling; do not silently change identity.
    if value.count('@') != 1 or any(c.isspace() for c in value):
        raise ValueError('올바른 이메일을 입력해주세요.')
    local, domain = value.split('@')
    if not local or '.' not in domain or domain.startswith('.') or domain.endswith('.'):
        raise ValueError('올바른 이메일을 입력해주세요.')
    return value


Password = Annotated[str, Field(strict=True, min_length=1), AfterValidator(password_bytes)]
NewPassword = Annotated[Password, AfterValidator(new_password)]
Content = Annotated[str, Field(strict=True, max_length=10000), AfterValidator(nonblank)]
Username = Annotated[str, Field(strict=True, min_length=1, max_length=50), AfterValidator(nonblank)]
Email = Annotated[str, Field(strict=True, max_length=100), AfterValidator(email_address)]
Code = Annotated[str, Field(strict=True, pattern=r'^\d{6}$')]


def deadline_input(value):
    if value == '':
        return None
    if value is not None and not isinstance(value, (str, datetime)):
        raise ValueError('마감일은 날짜와 시간 문자열이어야 합니다.')
    return value


def local_deadline(value):
    if value is not None and value.tzinfo is not None:
        return value.astimezone(KST).replace(tzinfo=None)
    return value


Deadline = Annotated[datetime | None, BeforeValidator(deadline_input), AfterValidator(local_deadline)]


class InputModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class EmailRequest(InputModel):
    email: Email


class LoginRequest(InputModel):
    username: Username
    password: Password


class SignupRequest(EmailRequest):
    username: Username
    password: NewPassword
    code: Code


class ResetPasswordRequest(EmailRequest):
    code: Code
    new_password: NewPassword


class ChangePasswordRequest(InputModel):
    current_password: Password
    new_password: NewPassword


class DeleteAccountRequest(InputModel):
    password: Password


class TodoCreate(InputModel):
    content: Content
    deadline: Deadline = None
    category: Annotated[str, Field(strict=True, max_length=50)] | None = None
    repeat: Annotated[dict | str | None, AfterValidator(normalize_repeat)] = None
    priority: Annotated[int, Field(strict=True, ge=0, le=2)] = 1
    detail: Annotated[str, Field(strict=True, max_length=50000)] | None = None


class TodoUpdate(InputModel):
    content: Content = None
    category: Annotated[str, Field(strict=True, max_length=50)] | None = None
    repeat: Annotated[dict | str | None, AfterValidator(normalize_repeat)] = None
    priority: Annotated[int, Field(strict=True, ge=0, le=2)] = None
    detail: Annotated[str, Field(strict=True, max_length=50000)] | None = None


class DeadlineRequest(InputModel):
    deadline: Deadline


class ReorderRequest(InputModel):
    order: list[Annotated[int, Field(strict=True, gt=0)]] = Field(max_length=10000)

    @model_validator(mode='after')
    def unique_ids(self):
        if len(set(self.order)) != len(self.order):
            raise ValueError('순서에 중복된 항목이 있습니다.')
        return self


class SubtaskCreate(InputModel):
    content: Content


class SubtaskUpdate(InputModel):
    content: Content = None
    completed: Annotated[bool, Field(strict=True)] = None
