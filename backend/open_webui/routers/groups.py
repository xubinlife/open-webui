import os
from pathlib import Path
from typing import Optional
import logging

from open_webui.models.users import Users, UserInfoResponse
from open_webui.models.groups import (
    Groups,
    GroupForm,
    GroupUpdateForm,
    GroupResponse,
    UserIdsForm,
)

from open_webui.config import CACHE_DIR
from open_webui.constants import ERROR_MESSAGES
from fastapi import APIRouter, Depends, HTTPException, Request, status

from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.env import SRC_LOG_LEVELS


log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MAIN"])

router = APIRouter()

############################
# GetFunctions
############################


# 获取群组列表，普通用户仅能查看自身所在群组，可过滤共享状态
@router.get("/", response_model=list[GroupResponse])
async def get_groups(share: Optional[bool] = None, user=Depends(get_verified_user)):

    filter = {}
    if user.role != "admin":
        filter["member_id"] = user.id

    if share is not None:
        filter["share"] = share

    groups = Groups.get_groups(filter=filter)

    return groups


############################
# CreateNewGroup
############################


# 管理员创建新的群组并返回成员数量
@router.post("/create", response_model=Optional[GroupResponse])
async def create_new_group(form_data: GroupForm, user=Depends(get_admin_user)):
    try:
        group = Groups.insert_new_group(user.id, form_data)
        if group:
            return GroupResponse(
                **group.model_dump(),
                member_count=Groups.get_group_member_count_by_id(group.id),
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("Error creating group"),
            )
    except Exception as e:
        log.exception(f"Error creating a new group: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(e),
        )


############################
# GetGroupById
############################


# 管理员按 id 查看群组详情，附带成员统计
@router.get("/id/{id}", response_model=Optional[GroupResponse])
async def get_group_by_id(id: str, user=Depends(get_admin_user)):
    group = Groups.get_group_by_id(id)
    if group:
        return GroupResponse(
            **group.model_dump(),
            member_count=Groups.get_group_member_count_by_id(group.id),
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# ExportGroupById
############################


# 群组导出响应，包含成员用户 ID 列表
class GroupExportResponse(GroupResponse):
    user_ids: list[str] = []
    pass


# 导出指定群组的详情及成员 ID，管理员接口
@router.get("/id/{id}/export", response_model=Optional[GroupExportResponse])
async def export_group_by_id(id: str, user=Depends(get_admin_user)):
    group = Groups.get_group_by_id(id)
    if group:
        return GroupExportResponse(
            **group.model_dump(),
            member_count=Groups.get_group_member_count_by_id(group.id),
            user_ids=Groups.get_group_user_ids_by_id(group.id),
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# GetUsersInGroupById
############################


# 管理员查询指定群组下的用户列表
@router.post("/id/{id}/users", response_model=list[UserInfoResponse])
async def get_users_in_group(id: str, user=Depends(get_admin_user)):
    try:
        users = Users.get_users_by_group_id(id)
        return users
    except Exception as e:
        log.exception(f"Error adding users to group {id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(e),
        )


############################
# UpdateGroupById
############################


# 管理员修改群组信息并返回最新成员数量
@router.post("/id/{id}/update", response_model=Optional[GroupResponse])
async def update_group_by_id(
    id: str, form_data: GroupUpdateForm, user=Depends(get_admin_user)
):
    try:
        group = Groups.update_group_by_id(id, form_data)
        if group:
            return GroupResponse(
                **group.model_dump(),
                member_count=Groups.get_group_member_count_by_id(group.id),
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("Error updating group"),
            )
    except Exception as e:
        log.exception(f"Error updating group {id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(e),
        )


############################
# AddUserToGroupByUserIdAndGroupId
############################


# 管理员批量添加用户到群组，过滤无效用户 ID
@router.post("/id/{id}/users/add", response_model=Optional[GroupResponse])
async def add_user_to_group(
    id: str, form_data: UserIdsForm, user=Depends(get_admin_user)
):
    try:
        if form_data.user_ids:
            form_data.user_ids = Users.get_valid_user_ids(form_data.user_ids)

        group = Groups.add_users_to_group(id, form_data.user_ids)
        if group:
            return GroupResponse(
                **group.model_dump(),
                member_count=Groups.get_group_member_count_by_id(group.id),
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("Error adding users to group"),
            )
    except Exception as e:
        log.exception(f"Error adding users to group {id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(e),
        )


# 管理员从群组中批量移除用户
@router.post("/id/{id}/users/remove", response_model=Optional[GroupResponse])
async def remove_users_from_group(
    id: str, form_data: UserIdsForm, user=Depends(get_admin_user)
):
    try:
        group = Groups.remove_users_from_group(id, form_data.user_ids)
        if group:
            return GroupResponse(
                **group.model_dump(),
                member_count=Groups.get_group_member_count_by_id(group.id),
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("Error removing users from group"),
            )
    except Exception as e:
        log.exception(f"Error removing users from group {id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(e),
        )


############################
# DeleteGroupById
############################


# 删除群组及关联关系，管理员权限
@router.delete("/id/{id}/delete", response_model=bool)
async def delete_group_by_id(id: str, user=Depends(get_admin_user)):
    try:
        result = Groups.delete_group_by_id(id)
        if result:
            return result
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("Error deleting group"),
            )
    except Exception as e:
        log.exception(f"Error deleting group {id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(e),
        )
