import logging
import uuid
from typing import Optional

from open_webui.internal.db import Base, get_db
from open_webui.models.users import UserModel, UserProfileImageResponse, Users
from open_webui.env import SRC_LOG_LEVELS
from pydantic import BaseModel
from sqlalchemy import Boolean, Column, String, Text

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])

####################
# DB MODEL
####################


# 认证表模型，保存登录凭证基础信息
class Auth(Base):
    __tablename__ = "auth"

    id = Column(String, primary_key=True, unique=True)
    email = Column(String)
    password = Column(Text)
    active = Column(Boolean)


# 认证记录的Pydantic模型，用于序列化校验
class AuthModel(BaseModel):
    id: str
    email: str
    password: str
    active: bool = True


####################
# Forms
####################


# 访问令牌结构体，描述令牌及类型
class Token(BaseModel):
    token: str
    token_type: str


# API Key载体，便于统一返回
class ApiKey(BaseModel):
    api_key: Optional[str] = None


# 登录响应体，组合令牌与头像等信息
class SigninResponse(Token, UserProfileImageResponse):
    pass


# 登录表单，使用邮箱与密码校验
class SigninForm(BaseModel):
    email: str
    password: str


# LDAP 登录表单，包含用户与密码
class LdapForm(BaseModel):
    user: str
    password: str


# 更新头像的请求体
class ProfileImageUrlForm(BaseModel):
    profile_image_url: str


# 更新密码表单，包含旧密码与新密码
class UpdatePasswordForm(BaseModel):
    password: str
    new_password: str


# 注册表单，包含基础用户信息与默认头像
class SignupForm(BaseModel):
    name: str
    email: str
    password: str
    profile_image_url: Optional[str] = "/user.png"


# 管理员添加用户时的表单，附带角色信息
class AddUserForm(SignupForm):
    role: Optional[str] = "pending"


# 认证数据访问封装，提供增删改查及登录校验
class AuthsTable:
    # 创建新的认证记录并同步生成用户
    def insert_new_auth(
        self,
        email: str,
        password: str,
        name: str,
        profile_image_url: str = "/user.png",
        role: str = "pending",
        oauth: Optional[dict] = None,
    ) -> Optional[UserModel]:
        with get_db() as db:
            log.info("insert_new_auth")

            id = str(uuid.uuid4())

            auth = AuthModel(
                **{"id": id, "email": email, "password": password, "active": True}
            )
            result = Auth(**auth.model_dump())
            db.add(result)

            user = Users.insert_new_user(
                id, name, email, profile_image_url, role, oauth=oauth
            )

            db.commit()
            db.refresh(result)

            if result and user:
                return user
            else:
                return None

    # 根据邮箱验证密码并返回用户
    def authenticate_user(
        self, email: str, verify_password: callable
    ) -> Optional[UserModel]:
        log.info(f"authenticate_user: {email}")

        user = Users.get_user_by_email(email)
        if not user:
            return None

        try:
            with get_db() as db:
                auth = db.query(Auth).filter_by(id=user.id, active=True).first()
                if auth:
                    if verify_password(auth.password):
                        return user
                    else:
                        return None
                else:
                    return None
        except Exception:
            return None

    # 通过 API Key 验证并获取用户
    def authenticate_user_by_api_key(self, api_key: str) -> Optional[UserModel]:
        log.info(f"authenticate_user_by_api_key: {api_key}")
        # if no api_key, return None
        if not api_key:
            return None

        try:
            user = Users.get_user_by_api_key(api_key)
            return user if user else None
        except Exception:
            return False

    # 仅通过邮箱查找用户（无需密码校验）
    def authenticate_user_by_email(self, email: str) -> Optional[UserModel]:
        log.info(f"authenticate_user_by_email: {email}")
        try:
            with get_db() as db:
                auth = db.query(Auth).filter_by(email=email, active=True).first()
                if auth:
                    user = Users.get_user_by_id(auth.id)
                    return user
        except Exception:
            return None

    # 根据用户ID更新密码
    def update_user_password_by_id(self, id: str, new_password: str) -> bool:
        try:
            with get_db() as db:
                result = (
                    db.query(Auth).filter_by(id=id).update({"password": new_password})
                )
                db.commit()
                return True if result == 1 else False
        except Exception:
            return False

    # 根据用户ID更新邮箱
    def update_email_by_id(self, id: str, email: str) -> bool:
        try:
            with get_db() as db:
                result = db.query(Auth).filter_by(id=id).update({"email": email})
                db.commit()
                return True if result == 1 else False
        except Exception:
            return False

    # 删除认证和关联用户记录
    def delete_auth_by_id(self, id: str) -> bool:
        try:
            with get_db() as db:
                # Delete User
                result = Users.delete_user_by_id(id)

                if result:
                    db.query(Auth).filter_by(id=id).delete()
                    db.commit()

                    return True
                else:
                    return False
        except Exception:
            return False


Auths = AuthsTable()
