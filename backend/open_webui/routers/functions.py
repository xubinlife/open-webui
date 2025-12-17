import os
import re

import logging
import aiohttp
from pathlib import Path
from typing import Optional

from open_webui.models.functions import (
    FunctionForm,
    FunctionModel,
    FunctionResponse,
    FunctionUserResponse,
    FunctionWithValvesModel,
    Functions,
)
from open_webui.utils.plugin import (
    load_function_module_by_id,
    replace_imports,
    get_function_module_from_cache,
)
from open_webui.config import CACHE_DIR
from open_webui.constants import ERROR_MESSAGES
from fastapi import APIRouter, Depends, HTTPException, Request, status
from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.env import SRC_LOG_LEVELS
from pydantic import BaseModel, HttpUrl


log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MAIN"])


router = APIRouter()

############################
# GetFunctions
############################


# 获取当前可用的函数列表（普通已验证用户即可查看）
@router.get("/", response_model=list[FunctionResponse])
async def get_functions(user=Depends(get_verified_user)):
    return Functions.get_functions()


# 管理员查看包含用户阀值配置在内的函数列表
@router.get("/list", response_model=list[FunctionUserResponse])
async def get_function_list(user=Depends(get_admin_user)):
    return Functions.get_function_list()


############################
# ExportFunctions
############################


# 导出函数定义，可选包含阀值配置，管理员限定
@router.get("/export", response_model=list[FunctionModel | FunctionWithValvesModel])
async def get_functions(include_valves: bool = False, user=Depends(get_admin_user)):
    return Functions.get_functions(include_valves=include_valves)


############################
# LoadFunctionFromLink
############################


# 用于从外部链接加载函数代码的表单
class LoadUrlForm(BaseModel):
    url: HttpUrl


# 将 GitHub 页面地址转换为原始文件下载地址
def github_url_to_raw_url(url: str) -> str:
    # 处理仓库目录链接，自动追加 main.py
    m1 = re.match(r"https://github\.com/([^/]+)/([^/]+)/tree/([^/]+)/(.*)", url)
    if m1:
        org, repo, branch, path = m1.groups()
        return f"https://raw.githubusercontent.com/{org}/{repo}/refs/heads/{branch}/{path.rstrip('/')}/main.py"

    # Handle 'blob' (file) URLs
    m2 = re.match(r"https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.*)", url)
    if m2:
        org, repo, branch, path = m2.groups()
        return (
            f"https://raw.githubusercontent.com/{org}/{repo}/refs/heads/{branch}/{path}"
        )

    # No match; return as-is
    return url


@router.post("/load/url", response_model=Optional[dict])
async def load_function_from_url(
    request: Request, form_data: LoadUrlForm, user=Depends(get_admin_user)
):
    # 管理员从远端 URL 加载函数源码并返回名称与内容，仅内部可信调用

    url = str(form_data.url)
    if not url:
        raise HTTPException(status_code=400, detail="Please enter a valid URL")

    url = github_url_to_raw_url(url)
    url_parts = url.rstrip("/").split("/")

    file_name = url_parts[-1]
    function_name = (
        file_name[:-3]
        if (
            file_name.endswith(".py")
            and (not file_name.startswith(("main.py", "index.py", "__init__.py")))
        )
        else url_parts[-2] if len(url_parts) > 1 else "function"
    )

    try:
        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.get(
                url, headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status != 200:
                    raise HTTPException(
                        status_code=resp.status, detail="Failed to fetch the function"
                    )
                data = await resp.text()
                if not data:
                    raise HTTPException(
                        status_code=400, detail="No data received from the URL"
                    )
        return {
            "name": function_name,
            "content": data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error importing function: {e}")


############################
# SyncFunctions
############################


# 批量同步函数的提交表单，包含阀值信息
class SyncFunctionsForm(BaseModel):
    functions: list[FunctionWithValvesModel] = []


# 管理员批量同步函数定义并校验阀值合法性
@router.post("/sync", response_model=list[FunctionWithValvesModel])
async def sync_functions(
    request: Request, form_data: SyncFunctionsForm, user=Depends(get_admin_user)
):
    try:
        for function in form_data.functions:
            function.content = replace_imports(function.content)
            function_module, function_type, frontmatter = load_function_module_by_id(
                function.id,
                content=function.content,
            )

            if hasattr(function_module, "Valves") and function.valves:
                Valves = function_module.Valves
                try:
                    Valves(
                        **{k: v for k, v in function.valves.items() if v is not None}
                    )
                except Exception as e:
                    log.exception(
                        f"Error validating valves for function {function.id}: {e}"
                    )
                    raise e

        return Functions.sync_functions(user.id, form_data.functions)
    except Exception as e:
        log.exception(f"Failed to load a function: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(e),
        )


############################
# CreateNewFunction
############################


# 管理员创建新的函数定义，校验标识符并缓存模块
@router.post("/create", response_model=Optional[FunctionResponse])
async def create_new_function(
    request: Request, form_data: FunctionForm, user=Depends(get_admin_user)
):
    if not form_data.id.isidentifier():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only alphanumeric characters and underscores are allowed in the id",
        )

    form_data.id = form_data.id.lower()

    function = Functions.get_function_by_id(form_data.id)
    if function is None:
        try:
            form_data.content = replace_imports(form_data.content)
            function_module, function_type, frontmatter = load_function_module_by_id(
                form_data.id,
                content=form_data.content,
            )
            form_data.meta.manifest = frontmatter

            FUNCTIONS = request.app.state.FUNCTIONS
            FUNCTIONS[form_data.id] = function_module

            function = Functions.insert_new_function(user.id, function_type, form_data)

            function_cache_dir = CACHE_DIR / "functions" / form_data.id
            function_cache_dir.mkdir(parents=True, exist_ok=True)

            if function_type == "filter" and getattr(function_module, "toggle", None):
                Functions.update_function_metadata_by_id(id, {"toggle": True})

            if function:
                return function
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.DEFAULT("Error creating function"),
                )
        except Exception as e:
            log.exception(f"Failed to create a new function: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT(e),
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.ID_TAKEN,
        )


############################
# GetFunctionById
############################


# 根据函数 id 查询详细配置，仅管理员可用
@router.get("/id/{id}", response_model=Optional[FunctionModel])
async def get_function_by_id(id: str, user=Depends(get_admin_user)):
    function = Functions.get_function_by_id(id)

    if function:
        return function
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# ToggleFunctionById
############################


# 切换函数启用状态（is_active），管理员接口
@router.post("/id/{id}/toggle", response_model=Optional[FunctionModel])
async def toggle_function_by_id(id: str, user=Depends(get_admin_user)):
    function = Functions.get_function_by_id(id)
    if function:
        function = Functions.update_function_by_id(
            id, {"is_active": not function.is_active}
        )

        if function:
            return function
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("Error updating function"),
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# ToggleGlobalById
############################


# 切换函数是否全局可用（is_global），管理员接口
@router.post("/id/{id}/toggle/global", response_model=Optional[FunctionModel])
async def toggle_global_by_id(id: str, user=Depends(get_admin_user)):
    function = Functions.get_function_by_id(id)
    if function:
        function = Functions.update_function_by_id(
            id, {"is_global": not function.is_global}
        )

        if function:
            return function
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("Error updating function"),
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# UpdateFunctionById
############################


# 管理员更新已有函数的代码与元数据，重载缓存模块
@router.post("/id/{id}/update", response_model=Optional[FunctionModel])
async def update_function_by_id(
    request: Request, id: str, form_data: FunctionForm, user=Depends(get_admin_user)
):
    try:
        form_data.content = replace_imports(form_data.content)
        function_module, function_type, frontmatter = load_function_module_by_id(
            id, content=form_data.content
        )
        form_data.meta.manifest = frontmatter

        FUNCTIONS = request.app.state.FUNCTIONS
        FUNCTIONS[id] = function_module

        updated = {**form_data.model_dump(exclude={"id"}), "type": function_type}
        log.debug(updated)

        function = Functions.update_function_by_id(id, updated)

        if function_type == "filter" and getattr(function_module, "toggle", None):
            Functions.update_function_metadata_by_id(id, {"toggle": True})

        if function:
            return function
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("Error updating function"),
            )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(e),
        )


############################
# DeleteFunctionById
############################


# 删除指定函数并清理应用缓存，管理员权限
@router.delete("/id/{id}/delete", response_model=bool)
async def delete_function_by_id(
    request: Request, id: str, user=Depends(get_admin_user)
):
    result = Functions.delete_function_by_id(id)

    if result:
        FUNCTIONS = request.app.state.FUNCTIONS
        if id in FUNCTIONS:
            del FUNCTIONS[id]

    return result


############################
# GetFunctionValves
############################


# 管理员查看函数的阀值配置
@router.get("/id/{id}/valves", response_model=Optional[dict])
async def get_function_valves_by_id(id: str, user=Depends(get_admin_user)):
    function = Functions.get_function_by_id(id)
    if function:
        try:
            valves = Functions.get_function_valves_by_id(id)
            return valves
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT(e),
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# GetFunctionValvesSpec
############################


# 获取函数阀值的 Pydantic schema 描述，便于前端生成表单
@router.get("/id/{id}/valves/spec", response_model=Optional[dict])
async def get_function_valves_spec_by_id(
    request: Request, id: str, user=Depends(get_admin_user)
):
    function = Functions.get_function_by_id(id)
    if function:
        function_module, function_type, frontmatter = get_function_module_from_cache(
            request, id
        )

        if hasattr(function_module, "Valves"):
            Valves = function_module.Valves
            return Valves.schema()
        return None
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# UpdateFunctionValves
############################


# 管理员更新函数阀值并校验数据合法性
@router.post("/id/{id}/valves/update", response_model=Optional[dict])
async def update_function_valves_by_id(
    request: Request, id: str, form_data: dict, user=Depends(get_admin_user)
):
    function = Functions.get_function_by_id(id)
    if function:
        function_module, function_type, frontmatter = get_function_module_from_cache(
            request, id
        )

        if hasattr(function_module, "Valves"):
            Valves = function_module.Valves

            try:
                form_data = {k: v for k, v in form_data.items() if v is not None}
                valves = Valves(**form_data)

                valves_dict = valves.model_dump(exclude_unset=True)
                Functions.update_function_valves_by_id(id, valves_dict)
                return valves_dict
            except Exception as e:
                log.exception(f"Error updating function values by id {id}: {e}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.DEFAULT(e),
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ERROR_MESSAGES.NOT_FOUND,
            )

    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# FunctionUserValves
############################


# 普通用户获取自己对指定函数的个性化阀值
@router.get("/id/{id}/valves/user", response_model=Optional[dict])
async def get_function_user_valves_by_id(id: str, user=Depends(get_verified_user)):
    function = Functions.get_function_by_id(id)
    if function:
        try:
            user_valves = Functions.get_user_valves_by_id_and_user_id(id, user.id)
            return user_valves
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT(e),
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


# 获取用户级阀值表单的 schema，供前端构建
@router.get("/id/{id}/valves/user/spec", response_model=Optional[dict])
async def get_function_user_valves_spec_by_id(
    request: Request, id: str, user=Depends(get_verified_user)
):
    function = Functions.get_function_by_id(id)
    if function:
        function_module, function_type, frontmatter = get_function_module_from_cache(
            request, id
        )

        if hasattr(function_module, "UserValves"):
            UserValves = function_module.UserValves
            return UserValves.schema()
        return None
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


# 普通用户更新自己的阀值配置并持久化
@router.post("/id/{id}/valves/user/update", response_model=Optional[dict])
async def update_function_user_valves_by_id(
    request: Request, id: str, form_data: dict, user=Depends(get_verified_user)
):
    function = Functions.get_function_by_id(id)

    if function:
        function_module, function_type, frontmatter = get_function_module_from_cache(
            request, id
        )

        if hasattr(function_module, "UserValves"):
            UserValves = function_module.UserValves

            try:
                form_data = {k: v for k, v in form_data.items() if v is not None}
                user_valves = UserValves(**form_data)
                user_valves_dict = user_valves.model_dump(exclude_unset=True)
                Functions.update_user_valves_by_id_and_user_id(
                    id, user.id, user_valves_dict
                )
                return user_valves_dict
            except Exception as e:
                log.exception(f"Error updating function user valves by id {id}: {e}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.DEFAULT(e),
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ERROR_MESSAGES.NOT_FOUND,
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )
