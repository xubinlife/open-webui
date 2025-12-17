from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request

from open_webui.models.prompts import (
    PromptForm,
    PromptUserResponse,
    PromptModel,
    Prompts,
)
from open_webui.constants import ERROR_MESSAGES
from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.utils.access_control import has_access, has_permission
from open_webui.config import BYPASS_ADMIN_ACCESS_CONTROL

router = APIRouter()

############################
# GetPrompts
############################


# 获取当前用户可见的提示集合，管理员可绕过权限过滤
@router.get("/", response_model=list[PromptModel])
async def get_prompts(user=Depends(get_verified_user)):
    if user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL:
        prompts = Prompts.get_prompts()
    else:
        prompts = Prompts.get_prompts_by_user_id(user.id, "read")

    return prompts


# 获取具备写权限的提示列表，用于用户侧编辑或选择
@router.get("/list", response_model=list[PromptUserResponse])
async def get_prompt_list(user=Depends(get_verified_user)):
    if user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL:
        prompts = Prompts.get_prompts()
    else:
        prompts = Prompts.get_prompts_by_user_id(user.id, "write")

    return prompts


############################
# CreateNewPrompt
############################


# 创建新的提示记录，并校验用户是否具备导入或管理权限
@router.post("/create", response_model=Optional[PromptModel])
async def create_new_prompt(
    request: Request, form_data: PromptForm, user=Depends(get_verified_user)
):
    if user.role != "admin" and not (
        has_permission(
            user.id, "workspace.prompts", request.app.state.config.USER_PERMISSIONS
        )
        or has_permission(
            user.id,
            "workspace.prompts_import",
            request.app.state.config.USER_PERMISSIONS,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.UNAUTHORIZED,
        )

    prompt = Prompts.get_prompt_by_command(form_data.command)
    if prompt is None:
        prompt = Prompts.insert_new_prompt(user.id, form_data)

        if prompt:
            return prompt
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(),
        )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=ERROR_MESSAGES.COMMAND_TAKEN,
    )


############################
# GetPromptByCommand
############################


# 根据命令标识获取提示详情，保证调用者拥有读取权限
@router.get("/command/{command}", response_model=Optional[PromptModel])
async def get_prompt_by_command(command: str, user=Depends(get_verified_user)):
    prompt = Prompts.get_prompt_by_command(f"/{command}")

    if prompt:
        if (
            user.role == "admin"
            or prompt.user_id == user.id
            or has_access(user.id, "read", prompt.access_control)
        ):
            return prompt
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# UpdatePromptByCommand
############################


# 更新指定命令的提示内容，需验证写入权限
@router.post("/command/{command}/update", response_model=Optional[PromptModel])
async def update_prompt_by_command(
    command: str,
    form_data: PromptForm,
    user=Depends(get_verified_user),
):
    prompt = Prompts.get_prompt_by_command(f"/{command}")
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    # Is the user the original creator, in a group with write access, or an admin
    if (
        prompt.user_id != user.id
        and not has_access(user.id, "write", prompt.access_control)
        and user.role != "admin"
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    prompt = Prompts.update_prompt_by_command(f"/{command}", form_data)
    if prompt:
        return prompt
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )


############################
# DeletePromptByCommand
############################


# 删除指定命令对应的提示，权限不足时返回未授权
@router.delete("/command/{command}/delete", response_model=bool)
async def delete_prompt_by_command(command: str, user=Depends(get_verified_user)):
    prompt = Prompts.get_prompt_by_command(f"/{command}")
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if (
        prompt.user_id != user.id
        and not has_access(user.id, "write", prompt.access_control)
        and user.role != "admin"
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    result = Prompts.delete_prompt_by_command(f"/{command}")
    return result
