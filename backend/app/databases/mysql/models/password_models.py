from typing import List, Optional

from sqlalchemy import Column, ForeignKeyConstraint, Index, Integer, JSON, String, TIMESTAMP, Text, text
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship
from sqlalchemy.orm.base import Mapped

Base = declarative_base()


class PasswordSetting(Base):
    __tablename__ = 'password_setting'

    id = mapped_column(Integer, primary_key=True)
    email_reminder = mapped_column(TINYINT)
    appcode = mapped_column(String(45))
    duration = mapped_column(Integer)
    password_limit = mapped_column(Integer)
    email_reminder_duration = mapped_column(Integer)
    min_password = mapped_column(Integer, server_default=text("'8'"))
    include_uppercase = mapped_column(TINYINT, server_default=text("'0'"))
    include_number = mapped_column(TINYINT, server_default=text("'0'"))
    include_symbol = mapped_column(TINYINT, server_default=text("'0'"))

    password_history: Mapped[List['PasswordHistory']] = relationship('PasswordHistory', uselist=True, back_populates='setting')


class PasswordHistory(Base):
    __tablename__ = 'password_history'
    __table_args__ = (
        ForeignKeyConstraint(['setting_id'], ['password_setting.id'], name='fk password_history.setting_id to password_setting.id'),
        Index('fk password_history.setting_id to password_setting.id', 'setting_id')
    )

    id = mapped_column(Integer, primary_key=True)
    update_at = mapped_column(TIMESTAMP, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    old_password_list = mapped_column(JSON)
    expired_dt = mapped_column(TIMESTAMP)
    phone_num = mapped_column(String(45))
    email = mapped_column(String(64))
    name = mapped_column(String(128))
    password = mapped_column(Text)
    setting_id = mapped_column(Integer)
    appcode = mapped_column(String(45))
    recovery_id = mapped_column(Text)
    uid = mapped_column(String(45))
    sid = mapped_column(String(45))
    app = mapped_column(String(45))
    user_type = mapped_column(String(45))
    encrypted_info = mapped_column(Text)

    setting: Mapped[Optional['PasswordSetting']] = relationship('PasswordSetting', back_populates='password_history')
