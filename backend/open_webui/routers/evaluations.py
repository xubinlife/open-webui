from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel

from open_webui.models.users import Users, UserModel
from open_webui.models.feedbacks import (
    FeedbackModel,
    FeedbackResponse,
    FeedbackForm,
    FeedbackUserResponse,
    FeedbackListResponse,
    Feedbacks,
)

from open_webui.constants import ERROR_MESSAGES
from open_webui.utils.auth import get_admin_user, get_verified_user

router = APIRouter()


############################
# GetConfig
############################


# 获取当前评测相关的开关配置，只有管理员可以访问
@router.get("/config")
async def get_config(request: Request, user=Depends(get_admin_user)):
    return {
        "ENABLE_EVALUATION_ARENA_MODELS": request.app.state.config.ENABLE_EVALUATION_ARENA_MODELS,
        "EVALUATION_ARENA_MODELS": request.app.state.config.EVALUATION_ARENA_MODELS,
    }


############################
# UpdateConfig
############################


# 更新评测配置的表单，均为可选字段
class UpdateConfigForm(BaseModel):
    ENABLE_EVALUATION_ARENA_MODELS: Optional[bool] = None
    EVALUATION_ARENA_MODELS: Optional[list[dict]] = None


# 管理员更新评测配置，支持动态调整开关与模型列表
@router.post("/config")
async def update_config(
    request: Request,
    form_data: UpdateConfigForm,
    user=Depends(get_admin_user),
):
    config = request.app.state.config
    if form_data.ENABLE_EVALUATION_ARENA_MODELS is not None:
        config.ENABLE_EVALUATION_ARENA_MODELS = form_data.ENABLE_EVALUATION_ARENA_MODELS
    if form_data.EVALUATION_ARENA_MODELS is not None:
        config.EVALUATION_ARENA_MODELS = form_data.EVALUATION_ARENA_MODELS
    return {
        "ENABLE_EVALUATION_ARENA_MODELS": config.ENABLE_EVALUATION_ARENA_MODELS,
        "EVALUATION_ARENA_MODELS": config.EVALUATION_ARENA_MODELS,
    }


# 管理员获取所有用户反馈列表
@router.get("/feedbacks/all", response_model=list[FeedbackResponse])
async def get_all_feedbacks(user=Depends(get_admin_user)):
    feedbacks = Feedbacks.get_all_feedbacks()
    return feedbacks


# 管理员删除所有反馈记录
@router.delete("/feedbacks/all")
async def delete_all_feedbacks(user=Depends(get_admin_user)):
    success = Feedbacks.delete_all_feedbacks()
    return success


# 管理员导出所有反馈的完整字段，用于分析或备份
@router.get("/feedbacks/all/export", response_model=list[FeedbackModel])
async def get_all_feedbacks(user=Depends(get_admin_user)):
    feedbacks = Feedbacks.get_all_feedbacks()
    return feedbacks


# 普通用户或管理员获取自身提交的反馈列表
@router.get("/feedbacks/user", response_model=list[FeedbackUserResponse])
async def get_feedbacks(user=Depends(get_verified_user)):
    feedbacks = Feedbacks.get_feedbacks_by_user_id(user.id)
    return feedbacks


# 普通用户或管理员删除自身的反馈记录
@router.delete("/feedbacks", response_model=bool)
async def delete_feedbacks(user=Depends(get_verified_user)):
    success = Feedbacks.delete_feedbacks_by_user_id(user.id)
    return success


PAGE_ITEM_COUNT = 30


# 管理员分页获取反馈列表，支持排序与方向参数
@router.get("/feedbacks/list", response_model=FeedbackListResponse)
async def get_feedbacks(
    order_by: Optional[str] = None,
    direction: Optional[str] = None,
    page: Optional[int] = 1,
    user=Depends(get_admin_user),
):
    limit = PAGE_ITEM_COUNT

    page = max(1, page)
    skip = (page - 1) * limit

    filter = {}
    if order_by:
        filter["order_by"] = order_by
    if direction:
        filter["direction"] = direction

    result = Feedbacks.get_feedback_items(filter=filter, skip=skip, limit=limit)
    return result


# 创建新的反馈记录，校验失败时返回 400
@router.post("/feedback", response_model=FeedbackModel)
async def create_feedback(
    request: Request,
    form_data: FeedbackForm,
    user=Depends(get_verified_user),
):
    feedback = Feedbacks.insert_new_feedback(user_id=user.id, form_data=form_data)
    if not feedback:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(),
        )

    return feedback


# 根据反馈 ID 获取详情，管理员可查看所有，普通用户仅能查看自己的
@router.get("/feedback/{id}", response_model=FeedbackModel)
async def get_feedback_by_id(id: str, user=Depends(get_verified_user)):
    if user.role == "admin":
        feedback = Feedbacks.get_feedback_by_id(id=id)
    else:
        feedback = Feedbacks.get_feedback_by_id_and_user_id(id=id, user_id=user.id)

    if not feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND
        )

    return feedback


# 更新指定反馈内容，管理员无权限限制，普通用户只能更新自身记录
@router.post("/feedback/{id}", response_model=FeedbackModel)
async def update_feedback_by_id(
    id: str, form_data: FeedbackForm, user=Depends(get_verified_user)
):
    if user.role == "admin":
        feedback = Feedbacks.update_feedback_by_id(id=id, form_data=form_data)
    else:
        feedback = Feedbacks.update_feedback_by_id_and_user_id(
            id=id, user_id=user.id, form_data=form_data
        )

    if not feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND
        )

    return feedback


# 删除指定反馈，管理员可删除任意记录，普通用户仅能删除自己的
@router.delete("/feedback/{id}")
async def delete_feedback_by_id(id: str, user=Depends(get_verified_user)):
    if user.role == "admin":
        success = Feedbacks.delete_feedback_by_id(id=id)
    else:
        success = Feedbacks.delete_feedback_by_id_and_user_id(id=id, user_id=user.id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND
        )

    return success
