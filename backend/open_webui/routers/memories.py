from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
import logging
import asyncio
from typing import Optional

from open_webui.models.memories import Memories, MemoryModel
from open_webui.retrieval.vector.factory import VECTOR_DB_CLIENT
from open_webui.utils.auth import get_verified_user
from open_webui.env import SRC_LOG_LEVELS


log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])

router = APIRouter()


# 测试接口：返回示例文本的嵌入结果
@router.get("/ef")
async def get_embeddings(request: Request):
    return {"result": await request.app.state.EMBEDDING_FUNCTION("hello world")}


############################
# GetMemories
############################


# 获取当前用户的所有记忆片段列表
@router.get("/", response_model=list[MemoryModel])
async def get_memories(user=Depends(get_verified_user)):
    return Memories.get_memories_by_user_id(user.id)


############################
# AddMemory
############################


# 新增记忆的请求体，仅包含文本内容
class AddMemoryForm(BaseModel):
    content: str


# 更新记忆时可提交的字段
class MemoryUpdateModel(BaseModel):
    content: Optional[str] = None


# 新增一条用户记忆，并写入向量数据库
@router.post("/add", response_model=Optional[MemoryModel])
async def add_memory(
    request: Request,
    form_data: AddMemoryForm,
    user=Depends(get_verified_user),
):
    memory = Memories.insert_new_memory(user.id, form_data.content)

    vector = await request.app.state.EMBEDDING_FUNCTION(memory.content, user=user)

    VECTOR_DB_CLIENT.upsert(
        collection_name=f"user-memory-{user.id}",
        items=[
            {
                "id": memory.id,
                "text": memory.content,
                "vector": vector,
                "metadata": {"created_at": memory.created_at},
            }
        ],
    )

    return memory


############################
# QueryMemory
############################


# 查询记忆使用的表单，包含查询文本与返回数量
class QueryMemoryForm(BaseModel):
    content: str
    k: Optional[int] = 1


# 基于向量相似度查询记忆，返回最相关的结果
@router.post("/query")
async def query_memory(
    request: Request, form_data: QueryMemoryForm, user=Depends(get_verified_user)
):
    memories = Memories.get_memories_by_user_id(user.id)
    if not memories:
        raise HTTPException(status_code=404, detail="No memories found for user")

    vector = await request.app.state.EMBEDDING_FUNCTION(form_data.content, user=user)

    results = VECTOR_DB_CLIENT.search(
        collection_name=f"user-memory-{user.id}",
        vectors=[vector],
        limit=form_data.k,
    )

    return results


############################
# ResetMemoryFromVectorDB
############################
# 重建当前用户的记忆向量集合（先清空后重新嵌入）
@router.post("/reset", response_model=bool)
async def reset_memory_from_vector_db(
    request: Request, user=Depends(get_verified_user)
):
    VECTOR_DB_CLIENT.delete_collection(f"user-memory-{user.id}")

    memories = Memories.get_memories_by_user_id(user.id)

    # Generate vectors in parallel
    vectors = await asyncio.gather(
        *[
            request.app.state.EMBEDDING_FUNCTION(memory.content, user=user)
            for memory in memories
        ]
    )

    VECTOR_DB_CLIENT.upsert(
        collection_name=f"user-memory-{user.id}",
        items=[
            {
                "id": memory.id,
                "text": memory.content,
                "vector": vectors[idx],
                "metadata": {
                    "created_at": memory.created_at,
                    "updated_at": memory.updated_at,
                },
            }
            for idx, memory in enumerate(memories)
        ],
    )

    return True


############################
# DeleteMemoriesByUserId
############################


# 删除当前用户的所有记忆及对应的向量集合
@router.delete("/delete/user", response_model=bool)
async def delete_memory_by_user_id(user=Depends(get_verified_user)):
    result = Memories.delete_memories_by_user_id(user.id)

    if result:
        try:
            VECTOR_DB_CLIENT.delete_collection(f"user-memory-{user.id}")
        except Exception as e:
            log.error(e)
        return True

    return False


############################
# UpdateMemoryById
############################


# 更新指定记忆内容并同步向量索引
@router.post("/{memory_id}/update", response_model=Optional[MemoryModel])
async def update_memory_by_id(
    memory_id: str,
    request: Request,
    form_data: MemoryUpdateModel,
    user=Depends(get_verified_user),
):
    memory = Memories.update_memory_by_id_and_user_id(
        memory_id, user.id, form_data.content
    )
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")

    if form_data.content is not None:
        vector = await request.app.state.EMBEDDING_FUNCTION(memory.content, user=user)

        VECTOR_DB_CLIENT.upsert(
            collection_name=f"user-memory-{user.id}",
            items=[
                {
                    "id": memory.id,
                    "text": memory.content,
                    "vector": vector,
                    "metadata": {
                        "created_at": memory.created_at,
                        "updated_at": memory.updated_at,
                    },
                }
            ],
        )

    return memory


############################
# DeleteMemoryById
############################


# 删除单条记忆并移除对应的向量
@router.delete("/{memory_id}", response_model=bool)
async def delete_memory_by_id(memory_id: str, user=Depends(get_verified_user)):
    result = Memories.delete_memory_by_id_and_user_id(memory_id, user.id)

    if result:
        VECTOR_DB_CLIENT.delete(
            collection_name=f"user-memory-{user.id}", ids=[memory_id]
        )
        return True

    return False
