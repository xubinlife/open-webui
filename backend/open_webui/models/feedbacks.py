import logging
import time
import uuid
from typing import Optional

from open_webui.internal.db import Base, get_db
from open_webui.models.users import User

from open_webui.env import SRC_LOG_LEVELS
from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Column, Text, JSON, Boolean

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])


####################
# Feedback DB Schema
####################


# 反馈表结构，记录用户上报的评分与意见
class Feedback(Base):
    __tablename__ = "feedback"
    id = Column(Text, primary_key=True, unique=True)
    user_id = Column(Text)
    version = Column(BigInteger, default=0)
    type = Column(Text)
    data = Column(JSON, nullable=True)
    meta = Column(JSON, nullable=True)
    snapshot = Column(JSON, nullable=True)
    created_at = Column(BigInteger)
    updated_at = Column(BigInteger)


# 反馈数据模型，用于序列化数据库记录
class FeedbackModel(BaseModel):
    id: str
    user_id: str
    version: int
    type: str
    data: Optional[dict] = None
    meta: Optional[dict] = None
    snapshot: Optional[dict] = None
    created_at: int
    updated_at: int

    model_config = ConfigDict(from_attributes=True)


####################
# Forms
####################


# 反馈响应体，面向接口返回基础字段
class FeedbackResponse(BaseModel):
    id: str
    user_id: str
    version: int
    type: str
    data: Optional[dict] = None
    meta: Optional[dict] = None
    created_at: int
    updated_at: int


# 评分信息载体，允许附加模型编号与理由
class RatingData(BaseModel):
    rating: Optional[str | int] = None
    model_id: Optional[str] = None
    sibling_model_ids: Optional[list[str]] = None
    reason: Optional[str] = None
    comment: Optional[str] = None
    model_config = ConfigDict(extra="allow", protected_namespaces=())


# 元数据载体，例如是否为竞技模式等
class MetaData(BaseModel):
    arena: Optional[bool] = None
    chat_id: Optional[str] = None
    message_id: Optional[str] = None
    tags: Optional[list[str]] = None
    model_config = ConfigDict(extra="allow")


# 快照数据，保存聊天上下文
class SnapshotData(BaseModel):
    chat: Optional[dict] = None
    model_config = ConfigDict(extra="allow")


# 创建反馈时提交的表单
class FeedbackForm(BaseModel):
    type: str
    data: Optional[RatingData] = None
    meta: Optional[dict] = None
    snapshot: Optional[SnapshotData] = None
    model_config = ConfigDict(extra="allow")


# 反馈关联的用户响应
class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str = "pending"

    last_active_at: int  # timestamp in epoch
    updated_at: int  # timestamp in epoch
    created_at: int  # timestamp in epoch

    model_config = ConfigDict(from_attributes=True)


# 带用户信息的反馈响应
class FeedbackUserResponse(FeedbackResponse):
    user: Optional[UserResponse] = None


# 反馈列表响应，封装分页结果
class FeedbackListResponse(BaseModel):
    items: list[FeedbackUserResponse]
    total: int


# 反馈表操作封装，处理新增与查询逻辑
class FeedbackTable:
    # 插入一条新反馈并返回序列化模型
    def insert_new_feedback(
        self, user_id: str, form_data: FeedbackForm
    ) -> Optional[FeedbackModel]:
        with get_db() as db:
            id = str(uuid.uuid4())
            feedback = FeedbackModel(
                **{
                    "id": id,
                    "user_id": user_id,
                    "version": 0,
                    **form_data.model_dump(),
                    "created_at": int(time.time()),
                    "updated_at": int(time.time()),
                }
            )
            try:
                result = Feedback(**feedback.model_dump())
                db.add(result)
                db.commit()
                db.refresh(result)
                if result:
                    return FeedbackModel.model_validate(result)
                else:
                    return None
            except Exception as e:
                log.exception(f"Error creating a new feedback: {e}")
                return None

    # 根据ID获取反馈详情
    def get_feedback_by_id(self, id: str) -> Optional[FeedbackModel]:
        try:
            with get_db() as db:
                feedback = db.query(Feedback).filter_by(id=id).first()
                if not feedback:
                    return None
                return FeedbackModel.model_validate(feedback)
        except Exception:
            return None

    # 按ID与用户ID限定查询反馈
    def get_feedback_by_id_and_user_id(
        self, id: str, user_id: str
    ) -> Optional[FeedbackModel]:
        try:
            with get_db() as db:
                feedback = db.query(Feedback).filter_by(id=id, user_id=user_id).first()
                if not feedback:
                    return None
                return FeedbackModel.model_validate(feedback)
        except Exception:
            return None

    # 支持过滤、排序和分页的反馈列表查询
    def get_feedback_items(
        self, filter: dict = {}, skip: int = 0, limit: int = 30
    ) -> FeedbackListResponse:
        with get_db() as db:
            query = db.query(Feedback, User).join(User, Feedback.user_id == User.id)

            if filter:
                order_by = filter.get("order_by")
                direction = filter.get("direction")

                if order_by == "username":
                    if direction == "asc":
                        query = query.order_by(User.name.asc())
                    else:
                        query = query.order_by(User.name.desc())
                elif order_by == "model_id":
                    # it's stored in feedback.data['model_id']
                    if direction == "asc":
                        query = query.order_by(
                            Feedback.data["model_id"].as_string().asc()
                        )
                    else:
                        query = query.order_by(
                            Feedback.data["model_id"].as_string().desc()
                        )
                elif order_by == "rating":
                    # it's stored in feedback.data['rating']
                    if direction == "asc":
                        query = query.order_by(
                            Feedback.data["rating"].as_string().asc()
                        )
                    else:
                        query = query.order_by(
                            Feedback.data["rating"].as_string().desc()
                        )
                elif order_by == "updated_at":
                    if direction == "asc":
                        query = query.order_by(Feedback.updated_at.asc())
                    else:
                        query = query.order_by(Feedback.updated_at.desc())

            else:
                query = query.order_by(Feedback.created_at.desc())

            # Count BEFORE pagination
            total = query.count()

            if skip:
                query = query.offset(skip)
            if limit:
                query = query.limit(limit)

            items = query.all()

            feedbacks = []
            for feedback, user in items:
                feedback_model = FeedbackModel.model_validate(feedback)
                user_model = UserResponse.model_validate(user)
                feedbacks.append(
                    FeedbackUserResponse(**feedback_model.model_dump(), user=user_model)
                )

            return FeedbackListResponse(items=feedbacks, total=total)

    # 获取所有反馈记录
    def get_all_feedbacks(self) -> list[FeedbackModel]:
        with get_db() as db:
            return [
                FeedbackModel.model_validate(feedback)
                for feedback in db.query(Feedback)
                .order_by(Feedback.updated_at.desc())
                .all()
            ]

    # 按类型筛选反馈记录
    def get_feedbacks_by_type(self, type: str) -> list[FeedbackModel]:
        with get_db() as db:
            return [
                FeedbackModel.model_validate(feedback)
                for feedback in db.query(Feedback)
                .filter_by(type=type)
                .order_by(Feedback.updated_at.desc())
                .all()
            ]

    # 查询某用户提交的所有反馈
    def get_feedbacks_by_user_id(self, user_id: str) -> list[FeedbackModel]:
        with get_db() as db:
            return [
                FeedbackModel.model_validate(feedback)
                for feedback in db.query(Feedback)
                .filter_by(user_id=user_id)
                .order_by(Feedback.updated_at.desc())
                .all()
            ]

    # 根据ID更新反馈内容
    def update_feedback_by_id(
        self, id: str, form_data: FeedbackForm
    ) -> Optional[FeedbackModel]:
        with get_db() as db:
            feedback = db.query(Feedback).filter_by(id=id).first()
            if not feedback:
                return None

            if form_data.data:
                feedback.data = form_data.data.model_dump()
            if form_data.meta:
                feedback.meta = form_data.meta
            if form_data.snapshot:
                feedback.snapshot = form_data.snapshot.model_dump()

            feedback.updated_at = int(time.time())

            db.commit()
            return FeedbackModel.model_validate(feedback)

    # 仅允许指定用户更新其反馈
    def update_feedback_by_id_and_user_id(
        self, id: str, user_id: str, form_data: FeedbackForm
    ) -> Optional[FeedbackModel]:
        with get_db() as db:
            feedback = db.query(Feedback).filter_by(id=id, user_id=user_id).first()
            if not feedback:
                return None

            if form_data.data:
                feedback.data = form_data.data.model_dump()
            if form_data.meta:
                feedback.meta = form_data.meta
            if form_data.snapshot:
                feedback.snapshot = form_data.snapshot.model_dump()

            feedback.updated_at = int(time.time())

            db.commit()
            return FeedbackModel.model_validate(feedback)

    # 按ID删除反馈记录
    def delete_feedback_by_id(self, id: str) -> bool:
        with get_db() as db:
            feedback = db.query(Feedback).filter_by(id=id).first()
            if not feedback:
                return False
            db.delete(feedback)
            db.commit()
            return True

    # 删除指定用户的目标反馈
    def delete_feedback_by_id_and_user_id(self, id: str, user_id: str) -> bool:
        with get_db() as db:
            feedback = db.query(Feedback).filter_by(id=id, user_id=user_id).first()
            if not feedback:
                return False
            db.delete(feedback)
            db.commit()
            return True

    # 删除用户的所有反馈
    def delete_feedbacks_by_user_id(self, user_id: str) -> bool:
        with get_db() as db:
            feedbacks = db.query(Feedback).filter_by(user_id=user_id).all()
            if not feedbacks:
                return False
            for feedback in feedbacks:
                db.delete(feedback)
            db.commit()
            return True

    # 清空反馈表所有记录
    def delete_all_feedbacks(self) -> bool:
        with get_db() as db:
            feedbacks = db.query(Feedback).all()
            if not feedbacks:
                return False
            for feedback in feedbacks:
                db.delete(feedback)
            db.commit()
            return True


Feedbacks = FeedbackTable()
