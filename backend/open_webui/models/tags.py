import logging
import time
import uuid
from typing import Optional

from open_webui.internal.db import Base, get_db


from open_webui.env import SRC_LOG_LEVELS
from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Column, String, JSON, PrimaryKeyConstraint, Index

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])


####################
# Tag DB Schema
####################
# 标签表定义，存储用户创建的标签信息
class Tag(Base):
    __tablename__ = "tag"
    id = Column(String)
    name = Column(String)
    user_id = Column(String)
    meta = Column(JSON, nullable=True)

    __table_args__ = (
        PrimaryKeyConstraint("id", "user_id", name="pk_id_user_id"),
        Index("user_id_idx", "user_id"),
    )

    # Unique constraint ensuring (id, user_id) is unique, not just the `id` column
    __table_args__ = (PrimaryKeyConstraint("id", "user_id", name="pk_id_user_id"),)


# 标签数据的Pydantic模型，用于ORM对象的序列化
class TagModel(BaseModel):
    id: str
    name: str
    user_id: str
    meta: Optional[dict] = None
    model_config = ConfigDict(from_attributes=True)


####################
# Forms
####################


# 用于在聊天中关联标签的请求表单
class TagChatIdForm(BaseModel):
    name: str
    chat_id: str


# 标签表操作封装，提供增删查等接口
class TagTable:
    # 为指定用户创建新标签，确保名称转换后的id唯一
    def insert_new_tag(self, name: str, user_id: str) -> Optional[TagModel]:
        with get_db() as db:
            id = name.replace(" ", "_").lower()
            tag = TagModel(**{"id": id, "user_id": user_id, "name": name})
            try:
                result = Tag(**tag.model_dump())
                db.add(result)
                db.commit()
                db.refresh(result)
                if result:
                    return TagModel.model_validate(result)
                else:
                    return None
            except Exception as e:
                log.exception(f"Error inserting a new tag: {e}")
                return None

    # 按标签名称和用户ID查询单个标签
    def get_tag_by_name_and_user_id(
        self, name: str, user_id: str
    ) -> Optional[TagModel]:
        try:
            id = name.replace(" ", "_").lower()
            with get_db() as db:
                tag = db.query(Tag).filter_by(id=id, user_id=user_id).first()
                return TagModel.model_validate(tag)
        except Exception:
            return None

    # 获取用户下的全部标签列表
    def get_tags_by_user_id(self, user_id: str) -> list[TagModel]:
        with get_db() as db:
            return [
                TagModel.model_validate(tag)
                for tag in (db.query(Tag).filter_by(user_id=user_id).all())
            ]

    # 按标签ID集合和用户ID批量获取标签
    def get_tags_by_ids_and_user_id(
        self, ids: list[str], user_id: str
    ) -> list[TagModel]:
        with get_db() as db:
            return [
                TagModel.model_validate(tag)
                for tag in (
                    db.query(Tag).filter(Tag.id.in_(ids), Tag.user_id == user_id).all()
                )
            ]

    # 删除指定用户下的标签
    def delete_tag_by_name_and_user_id(self, name: str, user_id: str) -> bool:
        try:
            with get_db() as db:
                id = name.replace(" ", "_").lower()
                res = db.query(Tag).filter_by(id=id, user_id=user_id).delete()
                log.debug(f"res: {res}")
                db.commit()
                return True
        except Exception as e:
            log.error(f"delete_tag: {e}")
            return False


Tags = TagTable()
