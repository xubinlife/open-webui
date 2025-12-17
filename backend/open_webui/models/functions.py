import logging
import time
from typing import Optional

from open_webui.internal.db import Base, JSONField, get_db
from open_webui.models.users import Users, UserModel
from open_webui.env import SRC_LOG_LEVELS
from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Boolean, Column, String, Text, Index

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])

####################
# Functions DB Schema
####################


class Function(Base):
    # 自定义函数表，存储类型、内容、阀值配置及作用域
    __tablename__ = "function"

    id = Column(String, primary_key=True, unique=True)
    user_id = Column(String)
    name = Column(Text)
    type = Column(Text)
    content = Column(Text)
    meta = Column(JSONField)
    valves = Column(JSONField)
    is_active = Column(Boolean)
    is_global = Column(Boolean)
    updated_at = Column(BigInteger)
    created_at = Column(BigInteger)

    __table_args__ = (Index("is_global_idx", "is_global"),)


class FunctionMeta(BaseModel):
    # 函数元信息，描述用途与声明文件
    description: Optional[str] = None
    manifest: Optional[dict] = {}
    model_config = ConfigDict(extra="allow")


class FunctionModel(BaseModel):
    # 函数的基础数据模型
    id: str
    user_id: str
    name: str
    type: str
    content: str
    meta: FunctionMeta
    is_active: bool = False
    is_global: bool = False
    updated_at: int  # timestamp in epoch
    created_at: int  # timestamp in epoch

    model_config = ConfigDict(from_attributes=True)


class FunctionWithValvesModel(BaseModel):
    # 带阀值配置的函数模型，用于需要传递valves字段的场景
    id: str
    user_id: str
    name: str
    type: str
    content: str
    meta: FunctionMeta
    valves: Optional[dict] = None
    is_active: bool = False
    is_global: bool = False
    updated_at: int  # timestamp in epoch
    created_at: int  # timestamp in epoch

    model_config = ConfigDict(from_attributes=True)


####################
# Forms
####################


class FunctionUserResponse(FunctionModel):
    # 携带创建者信息的函数响应
    user: Optional[UserModel] = None


class FunctionResponse(BaseModel):
    # 对外暴露的函数简化响应结构
    id: str
    user_id: str
    type: str
    name: str
    meta: FunctionMeta
    is_active: bool
    is_global: bool
    updated_at: int  # timestamp in epoch
    created_at: int  # timestamp in epoch


class FunctionForm(BaseModel):
    # 新建或更新函数的表单
    id: str
    name: str
    content: str
    meta: FunctionMeta


class FunctionValves(BaseModel):
    # 用于更新或返回阀值配置的载体
    valves: Optional[dict] = None


class FunctionsTable:
    # 封装函数相关的增删改查与同步操作
    def insert_new_function(
        self, user_id: str, type: str, form_data: FunctionForm
    ) -> Optional[FunctionModel]:
        # 创建并保存新函数
        function = FunctionModel(
            **{
                **form_data.model_dump(),
                "user_id": user_id,
                "type": type,
                "updated_at": int(time.time()),
                "created_at": int(time.time()),
            }
        )

        try:
            with get_db() as db:
                result = Function(**function.model_dump())
                db.add(result)
                db.commit()
                db.refresh(result)
                if result:
                    return FunctionModel.model_validate(result)
                else:
                    return None
        except Exception as e:
            log.exception(f"Error creating a new function: {e}")
            return None

    def sync_functions(
        self, user_id: str, functions: list[FunctionWithValvesModel]
    ) -> list[FunctionWithValvesModel]:
        # 同步用户函数：更新已存在的函数，插入新函数，删除缺失的函数
        try:
            with get_db() as db:
                # Get existing functions
                existing_functions = db.query(Function).all()
                existing_ids = {func.id for func in existing_functions}

                # Prepare a set of new function IDs
                new_function_ids = {func.id for func in functions}

                # Update or insert functions
                for func in functions:
                    if func.id in existing_ids:
                        db.query(Function).filter_by(id=func.id).update(
                            {
                                **func.model_dump(),
                                "user_id": user_id,
                                "updated_at": int(time.time()),
                            }
                        )
                    else:
                        new_func = Function(
                            **{
                                **func.model_dump(),
                                "user_id": user_id,
                                "updated_at": int(time.time()),
                            }
                        )
                        db.add(new_func)

                # Remove functions that are no longer present
                for func in existing_functions:
                    if func.id not in new_function_ids:
                        db.delete(func)

                db.commit()

                return [
                    FunctionModel.model_validate(func)
                    for func in db.query(Function).all()
                ]
        except Exception as e:
            log.exception(f"Error syncing functions for user {user_id}: {e}")
            return []

    def get_function_by_id(self, id: str) -> Optional[FunctionModel]:
        # 根据ID获取函数
        try:
            with get_db() as db:
                function = db.get(Function, id)
                return FunctionModel.model_validate(function)
        except Exception:
            return None

    def get_functions(
        self, active_only=False, include_valves=False
    ) -> list[FunctionModel | FunctionWithValvesModel]:
        # 获取函数列表，支持筛选启用状态和附带阀值
        with get_db() as db:
            if active_only:
                functions = db.query(Function).filter_by(is_active=True).all()

            else:
                functions = db.query(Function).all()

            if include_valves:
                return [
                    FunctionWithValvesModel.model_validate(function)
                    for function in functions
                ]
            else:
                return [
                    FunctionModel.model_validate(function) for function in functions
                ]

    def get_function_list(self) -> list[FunctionUserResponse]:
        # 获取按更新时间排序的函数列表并附带用户信息
        with get_db() as db:
            functions = db.query(Function).order_by(Function.updated_at.desc()).all()
            user_ids = list(set(func.user_id for func in functions))

            users = Users.get_users_by_user_ids(user_ids) if user_ids else []
            users_dict = {user.id: user for user in users}

            return [
                FunctionUserResponse.model_validate(
                    {
                        **FunctionModel.model_validate(func).model_dump(),
                        "user": (
                            users_dict.get(func.user_id).model_dump()
                            if func.user_id in users_dict
                            else None
                        ),
                    }
                )
                for func in functions
            ]

    def get_functions_by_type(
        self, type: str, active_only=False
    ) -> list[FunctionModel]:
        # 按类型获取函数，可选仅返回启用的函数
        with get_db() as db:
            if active_only:
                return [
                    FunctionModel.model_validate(function)
                    for function in db.query(Function)
                    .filter_by(type=type, is_active=True)
                    .all()
                ]
            else:
                return [
                    FunctionModel.model_validate(function)
                    for function in db.query(Function).filter_by(type=type).all()
                ]

    def get_global_filter_functions(self) -> list[FunctionModel]:
        # 获取全局启用的过滤器函数
        with get_db() as db:
            return [
                FunctionModel.model_validate(function)
                for function in db.query(Function)
                .filter_by(type="filter", is_active=True, is_global=True)
                .all()
            ]

    def get_global_action_functions(self) -> list[FunctionModel]:
        # 获取全局启用的动作函数
        with get_db() as db:
            return [
                FunctionModel.model_validate(function)
                for function in db.query(Function)
                .filter_by(type="action", is_active=True, is_global=True)
                .all()
            ]

    def get_function_valves_by_id(self, id: str) -> Optional[dict]:
        # 获取函数的阀值配置
        with get_db() as db:
            try:
                function = db.get(Function, id)
                return function.valves if function.valves else {}
            except Exception as e:
                log.exception(f"Error getting function valves by id {id}: {e}")
                return None

    def update_function_valves_by_id(
        self, id: str, valves: dict
    ) -> Optional[FunctionValves]:
        # 更新函数阀值配置
        with get_db() as db:
            try:
                function = db.get(Function, id)
                function.valves = valves
                function.updated_at = int(time.time())
                db.commit()
                db.refresh(function)
                return self.get_function_by_id(id)
            except Exception:
                return None

    def update_function_metadata_by_id(
        self, id: str, metadata: dict
    ) -> Optional[FunctionModel]:
        # 更新函数的meta字段（合并原有数据）
        with get_db() as db:
            try:
                function = db.get(Function, id)

                if function:
                    if function.meta:
                        function.meta = {**function.meta, **metadata}
                    else:
                        function.meta = metadata

                    function.updated_at = int(time.time())
                    db.commit()
                    db.refresh(function)
                    return self.get_function_by_id(id)
                else:
                    return None
            except Exception as e:
                log.exception(f"Error updating function metadata by id {id}: {e}")
                return None

    def get_user_valves_by_id_and_user_id(
        self, id: str, user_id: str
    ) -> Optional[dict]:
        # 读取指定用户对某函数的个性化阀值配置
        try:
            user = Users.get_user_by_id(user_id)
            user_settings = user.settings.model_dump() if user.settings else {}

            # Check if user has "functions" and "valves" settings
            if "functions" not in user_settings:
                user_settings["functions"] = {}
            if "valves" not in user_settings["functions"]:
                user_settings["functions"]["valves"] = {}

            return user_settings["functions"]["valves"].get(id, {})
        except Exception as e:
            log.exception(f"Error getting user values by id {id} and user id {user_id}")
            return None

    def update_user_valves_by_id_and_user_id(
        self, id: str, user_id: str, valves: dict
    ) -> Optional[dict]:
        # 更新用户级的函数阀值配置并写回用户设置
        try:
            user = Users.get_user_by_id(user_id)
            user_settings = user.settings.model_dump() if user.settings else {}

            # Check if user has "functions" and "valves" settings
            if "functions" not in user_settings:
                user_settings["functions"] = {}
            if "valves" not in user_settings["functions"]:
                user_settings["functions"]["valves"] = {}

            user_settings["functions"]["valves"][id] = valves

            # Update the user settings in the database
            Users.update_user_by_id(user_id, {"settings": user_settings})

            return user_settings["functions"]["valves"][id]
        except Exception as e:
            log.exception(
                f"Error updating user valves by id {id} and user_id {user_id}: {e}"
            )
            return None

    def update_function_by_id(self, id: str, updated: dict) -> Optional[FunctionModel]:
        # 根据传入字段更新函数信息
        with get_db() as db:
            try:
                db.query(Function).filter_by(id=id).update(
                    {
                        **updated,
                        "updated_at": int(time.time()),
                    }
                )
                db.commit()
                return self.get_function_by_id(id)
            except Exception:
                return None

    def deactivate_all_functions(self) -> Optional[bool]:
        # 将所有函数标记为未启用
        with get_db() as db:
            try:
                db.query(Function).update(
                    {
                        "is_active": False,
                        "updated_at": int(time.time()),
                    }
                )
                db.commit()
                return True
            except Exception:
                return None

    def delete_function_by_id(self, id: str) -> bool:
        # 删除指定ID的函数
        with get_db() as db:
            try:
                db.query(Function).filter_by(id=id).delete()
                db.commit()

                return True
            except Exception:
                return False


Functions = FunctionsTable()
