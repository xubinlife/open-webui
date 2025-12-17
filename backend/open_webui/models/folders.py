import logging
import time
import uuid
from typing import Optional
import re


from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Column, Text, JSON, Boolean, func

from open_webui.internal.db import Base, get_db
from open_webui.env import SRC_LOG_LEVELS


log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])


####################
# Folder DB Schema
####################


# 文件夹表结构，保存层级关系、用户归属及自定义数据
class Folder(Base):
    __tablename__ = "folder"
    id = Column(Text, primary_key=True, unique=True)
    parent_id = Column(Text, nullable=True)
    user_id = Column(Text)
    name = Column(Text)
    items = Column(JSON, nullable=True)
    meta = Column(JSON, nullable=True)
    data = Column(JSON, nullable=True)
    is_expanded = Column(Boolean, default=False)
    created_at = Column(BigInteger)
    updated_at = Column(BigInteger)


# Folder 数据模型，用于序列化数据库记录
class FolderModel(BaseModel):
    id: str
    parent_id: Optional[str] = None
    user_id: str
    name: str
    items: Optional[dict] = None
    meta: Optional[dict] = None
    data: Optional[dict] = None
    is_expanded: bool = False
    created_at: int
    updated_at: int

    model_config = ConfigDict(from_attributes=True)


# 文件夹元数据响应，主要存储图标等展示信息
class FolderMetadataResponse(BaseModel):
    icon: Optional[str] = None


# 仅返回文件夹的基本信息供列表展示
class FolderNameIdResponse(BaseModel):
    id: str
    name: str
    meta: Optional[FolderMetadataResponse] = None
    parent_id: Optional[str] = None
    is_expanded: bool = False
    created_at: int
    updated_at: int


####################
# Forms
####################


# 创建文件夹的入参表单
class FolderForm(BaseModel):
    name: str
    data: Optional[dict] = None
    meta: Optional[dict] = None
    model_config = ConfigDict(extra="allow")


# 更新文件夹名称、数据或元信息的表单
class FolderUpdateForm(BaseModel):
    name: Optional[str] = None
    data: Optional[dict] = None
    meta: Optional[dict] = None
    model_config = ConfigDict(extra="allow")


class FolderTable:
    # 新建文件夹并挂载到指定父节点
    def insert_new_folder(
        self, user_id: str, form_data: FolderForm, parent_id: Optional[str] = None
    ) -> Optional[FolderModel]:
        with get_db() as db:
            id = str(uuid.uuid4())
            folder = FolderModel(
                **{
                    "id": id,
                    "user_id": user_id,
                    **(form_data.model_dump(exclude_unset=True) or {}),
                    "parent_id": parent_id,
                    "created_at": int(time.time()),
                    "updated_at": int(time.time()),
                }
            )
            try:
                result = Folder(**folder.model_dump())
                db.add(result)
                db.commit()
                db.refresh(result)
                if result:
                    return FolderModel.model_validate(result)
                else:
                    return None
            except Exception as e:
                log.exception(f"Error inserting a new folder: {e}")
                return None

    # 根据文件夹 ID 与用户 ID 精确查询
    def get_folder_by_id_and_user_id(
        self, id: str, user_id: str
    ) -> Optional[FolderModel]:
        try:
            with get_db() as db:
                folder = db.query(Folder).filter_by(id=id, user_id=user_id).first()

                if not folder:
                    return None

                return FolderModel.model_validate(folder)
        except Exception:
            return None

    # 递归获取指定文件夹的所有子孙节点
    def get_children_folders_by_id_and_user_id(
        self, id: str, user_id: str
    ) -> Optional[list[FolderModel]]:
        try:
            with get_db() as db:
                folders = []

                def get_children(folder):
                    children = self.get_folders_by_parent_id_and_user_id(
                        folder.id, user_id
                    )
                    for child in children:
                        get_children(child)
                        folders.append(child)

                folder = db.query(Folder).filter_by(id=id, user_id=user_id).first()
                if not folder:
                    return None

                get_children(folder)
                return folders
        except Exception:
            return None

    # 获取用户的全部文件夹
    def get_folders_by_user_id(self, user_id: str) -> list[FolderModel]:
        with get_db() as db:
            return [
                FolderModel.model_validate(folder)
                for folder in db.query(Folder).filter_by(user_id=user_id).all()
            ]

    # 在指定父级下按名称查找文件夹，忽略大小写
    def get_folder_by_parent_id_and_user_id_and_name(
        self, parent_id: Optional[str], user_id: str, name: str
    ) -> Optional[FolderModel]:
        try:
            with get_db() as db:
                # Check if folder exists
                folder = (
                    db.query(Folder)
                    .filter_by(parent_id=parent_id, user_id=user_id)
                    .filter(Folder.name.ilike(name))
                    .first()
                )

                if not folder:
                    return None

                return FolderModel.model_validate(folder)
        except Exception as e:
            log.error(f"get_folder_by_parent_id_and_user_id_and_name: {e}")
            return None

    # 获取某个父节点下的直接子文件夹
    def get_folders_by_parent_id_and_user_id(
        self, parent_id: Optional[str], user_id: str
    ) -> list[FolderModel]:
        with get_db() as db:
            return [
                FolderModel.model_validate(folder)
                for folder in db.query(Folder)
                .filter_by(parent_id=parent_id, user_id=user_id)
                .all()
            ]

    # 调整文件夹的父级，实现移动操作
    def update_folder_parent_id_by_id_and_user_id(
        self,
        id: str,
        user_id: str,
        parent_id: str,
    ) -> Optional[FolderModel]:
        try:
            with get_db() as db:
                folder = db.query(Folder).filter_by(id=id, user_id=user_id).first()

                if not folder:
                    return None

                folder.parent_id = parent_id
                folder.updated_at = int(time.time())

                db.commit()

                return FolderModel.model_validate(folder)
        except Exception as e:
            log.error(f"update_folder: {e}")
            return

    # 更新文件夹名称或附加数据，处理重名校验
    def update_folder_by_id_and_user_id(
        self, id: str, user_id: str, form_data: FolderUpdateForm
    ) -> Optional[FolderModel]:
        try:
            with get_db() as db:
                folder = db.query(Folder).filter_by(id=id, user_id=user_id).first()

                if not folder:
                    return None

                form_data = form_data.model_dump(exclude_unset=True)

                existing_folder = (
                    db.query(Folder)
                    .filter_by(
                        name=form_data.get("name"),
                        parent_id=folder.parent_id,
                        user_id=user_id,
                    )
                    .first()
                )

                if existing_folder and existing_folder.id != id:
                    return None

                folder.name = form_data.get("name", folder.name)
                if "data" in form_data:
                    folder.data = {
                        **(folder.data or {}),
                        **form_data["data"],
                    }

                if "meta" in form_data:
                    folder.meta = {
                        **(folder.meta or {}),
                        **form_data["meta"],
                    }

                folder.updated_at = int(time.time())
                db.commit()

                return FolderModel.model_validate(folder)
        except Exception as e:
            log.error(f"update_folder: {e}")
            return

    # 更新折叠状态，便于前端记忆展开情况
    def update_folder_is_expanded_by_id_and_user_id(
        self, id: str, user_id: str, is_expanded: bool
    ) -> Optional[FolderModel]:
        try:
            with get_db() as db:
                folder = db.query(Folder).filter_by(id=id, user_id=user_id).first()

                if not folder:
                    return None

                folder.is_expanded = is_expanded
                folder.updated_at = int(time.time())

                db.commit()

                return FolderModel.model_validate(folder)
        except Exception as e:
            log.error(f"update_folder: {e}")
            return

    # 删除文件夹并级联清理子节点，返回删除的 ID 列表
    def delete_folder_by_id_and_user_id(self, id: str, user_id: str) -> list[str]:
        try:
            folder_ids = []
            with get_db() as db:
                folder = db.query(Folder).filter_by(id=id, user_id=user_id).first()
                if not folder:
                    return folder_ids

                folder_ids.append(folder.id)

                # Delete all children folders
                def delete_children(folder):
                    folder_children = self.get_folders_by_parent_id_and_user_id(
                        folder.id, user_id
                    )
                    for folder_child in folder_children:

                        delete_children(folder_child)
                        folder_ids.append(folder_child.id)

                        folder = db.query(Folder).filter_by(id=folder_child.id).first()
                        db.delete(folder)
                        db.commit()

                delete_children(folder)
                db.delete(folder)
                db.commit()
                return folder_ids
        except Exception as e:
            log.error(f"delete_folder: {e}")
            return []

    # 标准化名称以便模糊匹配，去除多余空格并统一大小写
    def normalize_folder_name(self, name: str) -> str:
        # Replace _ and space with a single space, lower case, collapse multiple spaces
        name = re.sub(r"[\s_]+", " ", name)
        return name.strip().lower()

    # 按多名称精确匹配，返回命中的文件夹及其子孙
    def search_folders_by_names(
        self, user_id: str, queries: list[str]
    ) -> list[FolderModel]:
        """
        Search for folders for a user where the name matches any of the queries, treating _ and space as equivalent, case-insensitive.
        """
        normalized_queries = [self.normalize_folder_name(q) for q in queries]
        if not normalized_queries:
            return []

        results = {}
        with get_db() as db:
            folders = db.query(Folder).filter_by(user_id=user_id).all()
            for folder in folders:
                if self.normalize_folder_name(folder.name) in normalized_queries:
                    results[folder.id] = FolderModel.model_validate(folder)

                    # get children folders
                    children = self.get_children_folders_by_id_and_user_id(
                        folder.id, user_id
                    )
                    for child in children:
                        results[child.id] = child

        # Return the results as a list
        if not results:
            return []
        else:
            results = list(results.values())
            return results

    # 按包含关系模糊搜索文件夹
    def search_folders_by_name_contains(
        self, user_id: str, query: str
    ) -> list[FolderModel]:
        """
        Partial match: normalized name contains (as substring) the normalized query.
        """
        normalized_query = self.normalize_folder_name(query)
        results = []
        with get_db() as db:
            folders = db.query(Folder).filter_by(user_id=user_id).all()
            for folder in folders:
                norm_name = self.normalize_folder_name(folder.name)
                if normalized_query in norm_name:
                    results.append(FolderModel.model_validate(folder))
        return results


Folders = FolderTable()
