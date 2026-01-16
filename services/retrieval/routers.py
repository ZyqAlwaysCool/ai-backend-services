'''
Description: Retrieval服务HTTP路由
Author: zyq
Date: 2025-09-18 15:50:47
LastEditors: zyq
LastEditTime: 2025-12-04 18:35:55
'''

import uuid
import os
import tempfile
from pathlib import Path
from typing import List, Optional
from pydantic import Field
from fastapi import APIRouter, Request, UploadFile, File, Form, Query
from loguru import logger

from core.schemas.base_resp_model_define import BaseResponse
from core.exceptions import ValidationException, BaseBusinessException
from ..services_err_codes import (
    RETRIEVAL_SERVICE_INIT_ERROR, 
    RETRIEVAL_SERVICE_TASK_NOT_FOUND_ERROR,
    RETRIEVAL_SERVICE_PROVIDER_NOT_SUPPORTED,
    RETRIEVAL_SERVICE_PROVIDER_CALL_FAILED,
    RETRIEVAL_SERVICE_CREDENTIAL_MISSING,
    get_service_error_message
)
from .schemas import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseDocumentCreateRequest,
    KnowledgeBaseDocumentUpdateRequest,
    KnowledgeBaseSegmentCreateRequest,
    KnowledgeBaseSegmentUpdateRequest,
    KnowledgeBaseSegmentDeleteRequest,
    KnowledgeBaseMetadataAssignRequest,
    KnowledgeBaseMetadataAssignByNameRequest,
    KnowledgeBaseMetadataRenameRequest,
    KnowledgeBaseMetadataDeleteRequest,
    KBCredentialCreateRequest,
    RetrievalUploadRequest, RetrievalUploadResponse, 
    KnowledgeBaseBuildRequest, KnowledgeBaseBuildResponse, BuildTaskStatusResponse,
    RetrievalQueryRequest, KnowledgeBaseQueryResponse,
    KnowledgeBaseProviderEnum,
    KnowledgeBaseToggleBuiltInMetadataRequest,
)

# 创建retrieval服务路由
retrieval_router = APIRouter(tags=["向量检索服务"])


def _get_handlers(request: Request):
    service_registry = getattr(request.app.state, 'service_registry', None)
    service = service_registry.get_service('retrieval') if service_registry else None
    handlers = service.handlers if service else None
    if not handlers:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_INIT_ERROR,
            message=get_service_error_message(RETRIEVAL_SERVICE_INIT_ERROR)
        )
    return handlers


# 统一知识库管理接口（移除路径占位符，参数走表单/查询/JSON）
@retrieval_router.post("/kb/create", response_model=BaseResponse, summary=["创建/绑定知识库"])
async def kb_create(
    request: Request,
    payload: KnowledgeBaseCreateRequest
):
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    handlers = _get_handlers(request)
    user_ctx = handlers._build_user_ctx(request)
    provider = payload.provider or "local"
    try:
        kb_info = await handlers.create_kb(payload, provider, user_ctx)
        return BaseResponse.success(data=kb_info.dict(), trace_id=trace_id)
    except BaseBusinessException:
        raise
    except ValueError as e:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_PROVIDER_CALL_FAILED,
            message=str(e)
        )


@retrieval_router.get("/kb/list", response_model=BaseResponse, summary=["知识库列表"])
async def kb_list(
    request: Request,
    page: int = Query(1, ge=1, le=100),
    limit: int = Query(20, ge=1, le=100),
    provider: KnowledgeBaseProviderEnum = Query(KnowledgeBaseProviderEnum.LOCAL)
):
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    handlers = _get_handlers(request)
    user_ctx = handlers._build_user_ctx(request)
    kb_list = await handlers.list_kb(page=page, limit=limit, provider=provider, user_ctx=user_ctx)
    return BaseResponse.success(data=kb_list.dict(), trace_id=trace_id)


@retrieval_router.post("/kb/delete", response_model=BaseResponse, summary=["删除知识库"])
async def kb_delete(
    request: Request,
    kb_name: str = Form(...),
    provider: KnowledgeBaseProviderEnum = Form(...)
):
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    handlers = _get_handlers(request)
    user_ctx = handlers._build_user_ctx(request)
    await handlers.delete_kb(kb_name=kb_name.strip(), provider=provider, user_ctx=user_ctx)
    return BaseResponse.success(data={"deleted": True}, trace_id=trace_id)

@retrieval_router.post("/kb/documents", response_model=BaseResponse, summary=["上传文件/文本到知识库（统一接口）"])
async def kb_create_document(
    request: Request,
    kb_name: str = Form(..., description="知识库名称"),
    provider: KnowledgeBaseProviderEnum = Form(..., description="provider 标识"),
    input_type: str = Form(..., description="text|file"),
    doc_name: Optional[str] = Form(None, description="文档名称"),
    text: Optional[str] = Form(None, description="文本内容，当 input_type=text"),
    file: Optional[UploadFile] = File(None, description="文件，当 input_type=file"),
    indexing_technique: Optional[str] = Form(None, description="索引模式"),
    process_rule: Optional[str] = Form(None, description="处理规则(JSON)"),
):
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"KB create document - TraceID: {trace_id} | KB: {kb_name} | provider: {provider}")

    if not kb_name or not kb_name.strip():
        raise ValidationException("知识库名称不能为空")
    if input_type not in {"text", "file"}:
        raise ValidationException("input_type 仅支持 text 或 file")
    if input_type == "text":
        if text is None or text.strip() == "":
            raise ValidationException("文本内容不能为空")
        if not doc_name or not doc_name.strip():
            raise ValidationException("文档名称不能为空")
    elif input_type == "file":
        if not file:
            raise ValidationException("请选择要上传的文件")
        if not doc_name:
            if not file.filename:
                raise ValidationException("文件名称缺失")
            doc_name = Path(file.filename).name

    # 解析 process_rule
    import json
    pr_obj = None
    if process_rule:
        try:
            pr_obj = json.loads(process_rule)
        except json.JSONDecodeError:
            raise ValidationException("process_rule 格式错误,请使用有效的JSON格式")
    handlers = _get_handlers(request)
    user_ctx = handlers._build_user_ctx(request)

    # 处理文件保存为临时路径
    temp_path = None
    if input_type == "file" and file:
        content = await file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix or "") as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name

    req_model = KnowledgeBaseDocumentCreateRequest(
        input_type=input_type,
        doc_name=doc_name,
        text=text,
        file_path=temp_path,
        indexing_technique=indexing_technique,
        process_rule=pr_obj,
    )

    try:
        resp = await handlers.create_kb_document(
            kb_name=kb_name.strip(),
            provider=provider,
            req=req_model,
            upload_options=None,
            trace_id=trace_id,
            user_ctx=user_ctx,
        )
        return BaseResponse.success(data=resp.dict(), trace_id=trace_id)
    except NotImplementedError as e:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_PROVIDER_NOT_SUPPORTED,
            message=str(e)
        )
    except ValueError as e:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_PROVIDER_CALL_FAILED,
            message=str(e)
        )
    finally:
        if temp_path and Path(temp_path).exists():
            try:
                os.unlink(temp_path)
            except Exception:
                pass

@retrieval_router.get("/kb/documents/list", response_model=BaseResponse, summary=["知识库文档列表"])
async def kb_list_documents(
    request: Request,
    kb_name: str = Query(..., min_length=1),
    page: int = Query(1, ge=1, le=100),
    limit: int = Query(20, ge=1, le=100),
    provider: KnowledgeBaseProviderEnum = Query(KnowledgeBaseProviderEnum.LOCAL)
):
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    handlers = _get_handlers(request)
    user_ctx = handlers._build_user_ctx(request)
    docs = await handlers.list_kb_documents(kb_name, provider, page, limit, user_ctx)
    return BaseResponse.success(data=docs.dict(), trace_id=trace_id)


@retrieval_router.post("/kb/documents/delete", response_model=BaseResponse, summary=["删除文档"])
async def kb_delete_document(
    request: Request,
    kb_name: str = Form(...),
    doc_name: str = Form(...),
    provider: KnowledgeBaseProviderEnum = Form(...)
):
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    handlers = _get_handlers(request)
    user_ctx = handlers._build_user_ctx(request)
    try:
        await handlers.delete_kb_document(kb_name.strip(), doc_name, provider, user_ctx)
        return BaseResponse.success(data={"deleted": True}, trace_id=trace_id)
    except NotImplementedError as e:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_PROVIDER_NOT_SUPPORTED,
            message=str(e)
        )
    except ValueError as e:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_PROVIDER_CALL_FAILED,
            message=str(e)
        )


@retrieval_router.post("/kb/documents/update", response_model=BaseResponse, summary=["更新文档（文件/文本）"])
async def kb_update_document(
    request: Request,
    kb_name: str = Form(...),
    doc_name: Optional[str] = Form(None),
    provider: KnowledgeBaseProviderEnum = Form(..., description="provider标识"),
    input_type: str = Form(..., description="text|file"),
    text: Optional[str] = Form(None, description="文本内容，当 input_type=text"),
    file: Optional[UploadFile] = File(None, description="文件，当 input_type=file"),
    indexing_technique: Optional[str] = Form(None, description="索引模式"),
    process_rule: Optional[str] = Form(None, description="处理规则(JSON)"),
):
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    if not kb_name or not kb_name.strip():
        raise ValidationException("知识库名称不能为空")
    if input_type not in {"text", "file"}:
        raise ValidationException("input_type 仅支持 text 或 file")
    if input_type == "file" and not file:
        raise ValidationException("请选择要上传的文件")
    if input_type == "text" and (text is None or text.strip() == ""):
        raise ValidationException("文本内容不能为空")

    import json
    pr_obj = None
    if process_rule:
        try:
            pr_obj = json.loads(process_rule)
        except json.JSONDecodeError:
            raise ValidationException("process_rule 格式错误，请使用有效的JSON格式")

    handlers = _get_handlers(request)
    user_ctx = handlers._build_user_ctx(request)

    temp_path = None
    if input_type == "file" and file:
        content = await file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix or "") as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name

    req_model = KnowledgeBaseDocumentUpdateRequest(
        input_type=input_type,
        doc_name=doc_name,
        text=text,
        file_path=temp_path,
        indexing_technique=indexing_technique,
        process_rule=pr_obj,
    )

    try:
        resp = await handlers.update_kb_document(
            kb_name=kb_name.strip(),
            provider=provider,
            req=req_model,
            trace_id=trace_id,
            user_ctx=user_ctx,
        )
        return BaseResponse.success(data=resp.dict(), trace_id=trace_id)
    except NotImplementedError as e:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_PROVIDER_NOT_SUPPORTED,
            message=str(e)
        )
    except ValueError as e:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_PROVIDER_CALL_FAILED,
            message=str(e)
        )
    finally:
        if temp_path and Path(temp_path).exists():
            try:
                os.unlink(temp_path)
            except Exception:
                pass


@retrieval_router.get("/kb/documents/indexing-status", response_model=BaseResponse, summary=["查询文档索引状态"])
async def kb_index_status(
    request: Request,
    kb_name: str,
    batch_task_id: str,
    provider: KnowledgeBaseProviderEnum = Query(...)
):
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    handlers = _get_handlers(request)
    user_ctx = handlers._build_user_ctx(request)
    resp = await handlers.get_kb_index_status(kb_name, batch_task_id, provider, user_ctx)
    return BaseResponse.success(data=resp.dict(), trace_id=trace_id)

@retrieval_router.post("/kb/segments/create", response_model=BaseResponse, summary=["新增分段"])
async def kb_add_segments(
    request: Request,
    payload: KnowledgeBaseSegmentCreateRequest,
):
    if payload.provider == KnowledgeBaseProviderEnum.DIFY:
        raise BaseBusinessException(code=RETRIEVAL_SERVICE_PROVIDER_NOT_SUPPORTED, message="实测目前dify接口能调通, 但未能成功创建分段, 暂时禁止dify调用")
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    handlers = _get_handlers(request)
    user_ctx = handlers._build_user_ctx(request)
    try:
        resp = await handlers.add_kb_segments(payload.kb_name, payload.doc_name, payload.provider, payload, user_ctx)
        return BaseResponse.success(data=resp.dict(), trace_id=trace_id)
    except NotImplementedError as e:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_PROVIDER_NOT_SUPPORTED,
            message=str(e)
        )
    except ValueError as e:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_PROVIDER_CALL_FAILED,
            message=str(e)
        )


@retrieval_router.get("/kb/segments/list", response_model=BaseResponse, summary=["分段列表"])
async def kb_list_segments(
    request: Request,
    kb_name: str,
    doc_name: str,
    page: int = 1,
    limit: int = 20,
    provider: KnowledgeBaseProviderEnum = Query(...)
):
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    handlers = _get_handlers(request)
    user_ctx = handlers._build_user_ctx(request)
    try:
        resp = await handlers.list_kb_segments(kb_name, doc_name, provider, page, limit, user_ctx)
        return BaseResponse.success(data=resp.dict(), trace_id=trace_id)
    except NotImplementedError as e:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_PROVIDER_NOT_SUPPORTED,
            message=str(e)
        )
    except ValueError as e:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_PROVIDER_CALL_FAILED,
            message=str(e)
        )


@retrieval_router.post("/kb/segments/update", response_model=BaseResponse, summary=["更新分段"])
async def kb_update_segment(
    request: Request,
    payload: KnowledgeBaseSegmentUpdateRequest,
):
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    handlers = _get_handlers(request)
    user_ctx = handlers._build_user_ctx(request)
    try:
        resp = await handlers.update_kb_segment(payload.kb_name, payload.doc_name, payload.segment_id, payload.provider, payload, user_ctx)
        return BaseResponse.success(data=resp.dict(), trace_id=trace_id)
    except NotImplementedError as e:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_PROVIDER_NOT_SUPPORTED,
            message=str(e)
        )
    except ValueError as e:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_PROVIDER_CALL_FAILED,
            message=str(e)
        )


@retrieval_router.post("/kb/segments/delete", response_model=BaseResponse, summary=["删除分段"])
async def kb_delete_segment(
    request: Request,
    payload: KnowledgeBaseSegmentDeleteRequest,
):
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    handlers = _get_handlers(request)
    user_ctx = handlers._build_user_ctx(request)
    try:
        await handlers.delete_kb_segment(payload.kb_name, payload.doc_name, payload.segment_id, payload.provider, user_ctx)
        return BaseResponse.success(data={"deleted": True}, trace_id=trace_id)
    except NotImplementedError as e:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_PROVIDER_NOT_SUPPORTED,
            message=str(e)
        )
    except ValueError as e:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_PROVIDER_CALL_FAILED,
            message=str(e)
        )


@retrieval_router.post("/kb/metadata/field/create", response_model=BaseResponse, summary=["新增元数据字段"])
async def kb_add_metadata_field(
    request: Request,
    kb_name: str = Form(...),
    meta_field_type: str = Form(default="string"),
    meta_field_name: str = Form(...),
    provider: KnowledgeBaseProviderEnum = Form(...)
):
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    handlers = _get_handlers(request)
    user_ctx = handlers._build_user_ctx(request)
    try:
        resp = await handlers.add_kb_metadata_field(kb_name, provider, meta_field_type, meta_field_name, user_ctx)
        return BaseResponse.success(data=resp.dict(), trace_id=trace_id)
    except NotImplementedError as e:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_PROVIDER_NOT_SUPPORTED,
            message=str(e)
        )
    except ValueError as e:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_PROVIDER_CALL_FAILED,
            message=str(e)
        )


@retrieval_router.post("/kb/metadata/field/update", response_model=BaseResponse, summary=["更新元数据字段"])
async def kb_update_metadata_field(
    request: Request,
    payload: KnowledgeBaseMetadataRenameRequest,
):
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    handlers = _get_handlers(request)
    user_ctx = handlers._build_user_ctx(request)
    try:
        resp = await handlers.update_kb_metadata_field(
            kb_name=payload.kb_name,
            provider=payload.provider,
            old_meta_field_name=payload.old_meta_field_name,
            new_meta_field_name=payload.new_meta_field_name,
            user_ctx=user_ctx,
        )
        return BaseResponse.success(data=resp.dict(), trace_id=trace_id)
    except NotImplementedError as e:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_PROVIDER_NOT_SUPPORTED,
            message=str(e)
        )
    except ValueError as e:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_PROVIDER_CALL_FAILED,
            message=str(e)
        )


@retrieval_router.post("/kb/metadata/field/delete", response_model=BaseResponse, summary=["删除元数据字段"])
async def kb_delete_metadata_field(
    request: Request,
    payload: KnowledgeBaseMetadataDeleteRequest,
):
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    handlers = _get_handlers(request)
    user_ctx = handlers._build_user_ctx(request)
    try:
        await handlers.delete_kb_metadata_field(
            kb_name=payload.kb_name,
            provider=payload.provider,
            meta_field_name=payload.meta_field_name,
            user_ctx=user_ctx,
        )
        return BaseResponse.success(data={"deleted": True}, trace_id=trace_id)
    except NotImplementedError as e:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_PROVIDER_NOT_SUPPORTED,
            message=str(e)
        )
    except ValueError as e:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_PROVIDER_CALL_FAILED,
            message=str(e)
        )


@retrieval_router.get("/kb/metadata/field/list", response_model=BaseResponse, summary=["元数据字段列表"])
async def kb_list_metadata_fields(
    request: Request,
    kb_name: str,
    provider: KnowledgeBaseProviderEnum = Query(KnowledgeBaseProviderEnum.LOCAL)
):
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    handlers = _get_handlers(request)
    user_ctx = handlers._build_user_ctx(request)
    try:
        resp = await handlers.list_kb_metadata_fields(kb_name, provider, user_ctx)
        return BaseResponse.success(data=resp.dict(), trace_id=trace_id)
    except NotImplementedError as e:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_PROVIDER_NOT_SUPPORTED,
            message=str(e)
        )
    except ValueError as e:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_PROVIDER_CALL_FAILED,
            message=str(e)
        )


@retrieval_router.post("/kb/metadata/built-in/toggle", response_model=BaseResponse, summary=["启用/禁用内置元数据"])
async def kb_toggle_built_in_metadata(
    request: Request,
    payload: KnowledgeBaseToggleBuiltInMetadataRequest,
):
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    handlers = _get_handlers(request)
    user_ctx = handlers._build_user_ctx(request)
    try:
        await handlers.toggle_kb_built_in_metadata(
            kb_name=payload.kb_name,
            provider=payload.provider,
            action=payload.action.value,
            user_ctx=user_ctx,
        )
        return BaseResponse.success(data={"success": True}, trace_id=trace_id)
    except NotImplementedError as e:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_PROVIDER_NOT_SUPPORTED,
            message=str(e)
        )
    except ValueError as e:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_PROVIDER_CALL_FAILED,
            message=str(e)
        )


@retrieval_router.post("/kb/metadata/assign", response_model=BaseResponse, summary=["批量赋值文档元数据"])
async def kb_assign_metadata(
    request: Request,
    payload: KnowledgeBaseMetadataAssignByNameRequest,
):
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    handlers = _get_handlers(request)
    user_ctx = handlers._build_user_ctx(request)
    try:
        await handlers.assign_kb_documents_metadata(payload, user_ctx)
        return BaseResponse.success(data={"success": True}, trace_id=trace_id)
    except NotImplementedError as e:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_PROVIDER_NOT_SUPPORTED,
            message=str(e)
        )
    except ValueError as e:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_PROVIDER_CALL_FAILED,
            message=str(e)
        )


# 凭证管理
@retrieval_router.post("/kb/credentials", response_model=BaseResponse, summary=["新增/更新知识库凭证"])
async def kb_upsert_credential(request: Request, payload: KBCredentialCreateRequest):
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    handlers = _get_handlers(request)
    user_ctx = handlers._build_user_ctx(request)
    cred = await handlers.upsert_kb_credential(payload, user_ctx)
    return BaseResponse.success(data=cred.dict(), trace_id=trace_id)


@retrieval_router.get("/kb/credentials/list", response_model=BaseResponse, summary=["知识库凭证列表"])
async def kb_list_credentials(request: Request, provider: Optional[KnowledgeBaseProviderEnum] = None):
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    handlers = _get_handlers(request)
    user_ctx = handlers._build_user_ctx(request)
    resp = await handlers.list_kb_credentials(provider, user_ctx)
    return BaseResponse.success(data=resp.dict(), trace_id=trace_id)


@retrieval_router.delete("/kb/credentials/delete", response_model=BaseResponse, summary=["删除知识库凭证"])
async def kb_delete_credential(request: Request, name: str, provider: KnowledgeBaseProviderEnum = KnowledgeBaseProviderEnum.DIFY):
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    handlers = _get_handlers(request)
    user_ctx = handlers._build_user_ctx(request)
    await handlers.delete_kb_credential(provider, name, user_ctx)
    return BaseResponse.success(data={"deleted": True}, trace_id=trace_id)


@retrieval_router.get("/build-task-status/{build_task_id}", response_model=BaseResponse, summary=["获取知识库构建任务状态"])
async def get_build_task_status(
    request: Request,
    build_task_id: str
):
    """
    查询知识库构建任务状态
    
    - **build_task_id**: 构建任务ID
    """
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Received build task status query - TraceID: {trace_id}, TaskID: {build_task_id}")
    
    # 验证参数
    if not build_task_id or not build_task_id.strip():
        raise ValidationException("构建任务ID不能为空")
    
    # 获取服务实例
    service_registry = getattr(request.app.state, 'service_registry', None)
    service = service_registry.get_service('retrieval') if service_registry else None
    handlers = service.handlers if service else None
    
    if not handlers:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_INIT_ERROR,
            message=get_service_error_message(RETRIEVAL_SERVICE_INIT_ERROR)
        )
    
    # 调用业务逻辑处理（包含任务ID格式校验）
    result = await handlers.get_build_task_status(
        task_id=build_task_id.strip(),
        trace_id=trace_id
    )
    
    if result is None:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_TASK_NOT_FOUND_ERROR,
            message=get_service_error_message(RETRIEVAL_SERVICE_TASK_NOT_FOUND_ERROR)
        )
    
    return BaseResponse.success(
        data=result,
        trace_id=trace_id
    )

@retrieval_router.post("/build-knowledge-base", response_model=BaseResponse, summary=["构建知识库"])
async def build_knowledge_base(
    request: Request,
    build_request: KnowledgeBaseBuildRequest
):
    """
    构建知识库：清洗文档并进行向量化，生成可检索的知识库
    """
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Received build knowledge base request - TraceID: {trace_id}")
    
    # 验证参数
    if not build_request.knowledge_base_name or not build_request.knowledge_base_name.strip():
        raise ValidationException("知识库名称不能为空")
    
    # 获取服务实例
    service_registry = getattr(request.app.state, 'service_registry', None)
    service = service_registry.get_service('retrieval') if service_registry else None
    handlers = service.handlers if service else None
    
    if not handlers:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_INIT_ERROR,
            message=get_service_error_message(RETRIEVAL_SERVICE_INIT_ERROR)
        )
    
    # 调用知识库构建业务逻辑处理
    result = await handlers.build_knowledge_base(
        knowledge_base_name=build_request.knowledge_base_name.strip(),
        clean_settings=build_request.clean_settings,
        trace_id=trace_id
    )
    
    return BaseResponse.success(
        data=result.dict(),
        trace_id=trace_id
    )

@retrieval_router.post("/query", response_model=BaseResponse, summary=["查询知识库"])
async def query_knowledge_base(
    request: Request,
    query_request: RetrievalQueryRequest
):
    """
    查询知识库：根据问题查询知识库
    """
    trace_id = getattr(request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"Received query knowledge base request - TraceID: {trace_id}")
    
    # 获取服务实例
    service_registry = getattr(request.app.state, 'service_registry', None)
    service = service_registry.get_service('retrieval') if service_registry else None
    handlers = service.handlers if service else None
    
    if not handlers:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_INIT_ERROR,
            message=get_service_error_message(RETRIEVAL_SERVICE_INIT_ERROR)
        )
    
    # 调用知识库查询业务逻辑处理
    result = await handlers.query_knowledge_base(
        knowledge_base_name=query_request.knowledge_base_name,
        kb_version=query_request.kb_version,
        query_text=query_request.query_text,
        trace_id=trace_id
    )
    
    return BaseResponse.success(
        data=result.dict(),
        trace_id=trace_id
    )


@retrieval_router.get("/knowledge-base/{knowledge_base_name}", 
                     response_model=BaseResponse, 
                     summary=["查询知识库版本信息"])
async def get_knowledge_base_info(
    request: Request,
    knowledge_base_name: str
):
    """
    查询知识库各版本详细信息
    
    - **knowledge_base_name**: 知识库名称
    """
    trace_id = getattr(request.state, "trace_id", str(uuid.uuid4()))
    logger.info(f"Received get knowledge base info request - TraceID: {trace_id}, KB: {knowledge_base_name}")
    
    # 验证参数
    if not knowledge_base_name or not knowledge_base_name.strip():
        raise ValidationException("知识库名称不能为空")
    
    # 获取服务实例
    service_registry = getattr(request.app.state, "service_registry", None)
    service = service_registry.get_service("retrieval") if service_registry else None
    handlers = service.handlers if service else None
    
    if not handlers:
        raise BaseBusinessException(
            code=RETRIEVAL_SERVICE_INIT_ERROR,
            message=get_service_error_message(RETRIEVAL_SERVICE_INIT_ERROR)
        )
    
    # 调用业务逻辑处理
    result = await handlers.get_knowledge_base_info(
        knowledge_base_name=knowledge_base_name.strip(),
        trace_id=trace_id
    )
    
    return BaseResponse.success(
        data=result.dict(),
        trace_id=trace_id
    )
