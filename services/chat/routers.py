'''
Description: Chat服务API路由定义
Author: zyq
Date: 2025-01-21
'''
import uuid
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from loguru import logger

from core.schemas.base_resp_model_define import BaseResponse
from core.config.error_codes import COMMON_ERROR_REQUEST_PARSE_ERROR
from core.exceptions import ValidationException, BaseBusinessException
from .schemas import SingleTurnChatRequest, MultiTurnChatRequest
from .handlers import ChatHandlers


chat_router = APIRouter()


async def _stream_wrapper(generator, trace_id: str):
    """流式响应包装器 - 返回原始chunk块"""
    try:
        async for chunk in generator:
            # 直接返回原始StreamChatChunk对象的字典形式
            yield f"data: {chunk.json()}\n\n"
    except Exception as e:
        logger.error(f"Stream processing error - TraceID: {trace_id} | Error: {str(e)}")
        # 流式错误也返回原始格式
        error_chunk = {
            "content": "",
            "finish_reason": "error",
            "model": "",
            "error": str(e)
        }
        yield f"data: {error_chunk}\n\n"


@chat_router.post("/single_turn_chat", response_model=BaseResponse)
async def single_turn_chat(request: SingleTurnChatRequest, http_request: Request):
    """单轮对话接口"""
    trace_id = str(uuid.uuid4())
    logger.info(f"Received single turn chat request - TraceID: {trace_id}")
    
    try:
        # 从service_registry获取chat服务的handlers实例
        service_registry = getattr(http_request.app.state, 'service_registry', None)
        chat_service = service_registry.get_service('chat') if service_registry else None
        handlers = chat_service.handlers if chat_service else None
        if not handlers:
            return BaseResponse.error(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                msg="Chat服务未初始化",
                trace_id=trace_id
            )
        
        response = await handlers.single_turn_chat(request, trace_id)
        
        return BaseResponse.success(
            data=response.dict(),
            trace_id=trace_id
        )
        
    except ValidationException as e:
        logger.warning(f"Validation error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=COMMON_ERROR_REQUEST_PARSE_ERROR,
            msg=str(e),
            trace_id=trace_id
        )
    except BaseBusinessException as e:
        logger.error(f"Business error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=e.code,
            msg=e.message,
            trace_id=trace_id
        )
    except Exception as e:
        logger.error(f"Unexpected error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=COMMON_ERROR_REQUEST_PARSE_ERROR,
            msg=f"服务内部错误: {str(e)}",
            trace_id=trace_id
        )


@chat_router.post("/multi_turn_chat", response_model=BaseResponse)
async def multi_turn_chat(request: MultiTurnChatRequest, http_request: Request):
    """多轮对话接口"""
    trace_id = str(uuid.uuid4())
    logger.info(f"Received multi turn chat request - TraceID: {trace_id}")
    
    try:
        # 从service_registry获取chat服务的handlers实例
        service_registry = getattr(http_request.app.state, 'service_registry', None)
        chat_service = service_registry.get_service('chat') if service_registry else None
        handlers = chat_service.handlers if chat_service else None
        if not handlers:
            return BaseResponse.error(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                msg="Chat服务未初始化",
                trace_id=trace_id
            )
        
        response = await handlers.multi_turn_chat(request, trace_id)
        
        return BaseResponse.success(
            data=response.dict(),
            trace_id=trace_id
        )
        
    except ValidationException as e:
        logger.warning(f"Validation error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=COMMON_ERROR_REQUEST_PARSE_ERROR,
            msg=str(e),
            trace_id=trace_id
        )
    except BaseBusinessException as e:
        logger.error(f"Business error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=e.code,
            msg=e.message,
            trace_id=trace_id
        )
    except Exception as e:
        logger.error(f"Unexpected error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=COMMON_ERROR_REQUEST_PARSE_ERROR,
            msg=f"服务内部错误: {str(e)}",
            trace_id=trace_id
        )


@chat_router.post("/single_turn_chat_stream")
async def single_turn_chat_stream(request: SingleTurnChatRequest, http_request: Request):
    """单轮对话流式接口"""
    trace_id = str(uuid.uuid4())
    logger.info(f"Received single turn chat stream request - TraceID: {trace_id}")
    
    try:
        # 从service_registry获取chat服务的handlers实例
        service_registry = getattr(http_request.app.state, 'service_registry', None)
        chat_service = service_registry.get_service('chat') if service_registry else None
        handlers = chat_service.handlers if chat_service else None
        if not handlers:
            raise HTTPException(
                status_code=500,
                detail=BaseResponse.error(
                    code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                    msg="Chat服务未初始化",
                    trace_id=trace_id
                ).dict()
            )
        
        # 获取流式生成器
        stream_generator = handlers.single_turn_chat_stream(request, trace_id)
        
        # 返回流式响应 - 原始chunk块
        return StreamingResponse(
            _stream_wrapper(stream_generator, trace_id),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Trace-ID": trace_id
            }
        )
        
    except ValidationException as e:
        logger.warning(f"Validation error - TraceID: {trace_id} | Error: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=BaseResponse.error(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                msg=str(e),
                trace_id=trace_id
            ).dict()
        )
    except BaseBusinessException as e:
        logger.error(f"Business error - TraceID: {trace_id} | Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=BaseResponse.error(
                code=e.code,
                msg=e.message,
                trace_id=trace_id
            ).dict()
        )
    except Exception as e:
        logger.error(f"Unexpected error - TraceID: {trace_id} | Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=BaseResponse.error(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                msg=f"服务内部错误: {str(e)}",
                trace_id=trace_id
            ).dict()
        )


@chat_router.post("/multi_turn_chat_stream")
async def multi_turn_chat_stream(request: MultiTurnChatRequest, http_request: Request):
    """多轮对话流式接口"""
    trace_id = str(uuid.uuid4())
    logger.info(f"Received multi turn chat stream request - TraceID: {trace_id}")
    
    try:
        # 从service_registry获取chat服务的handlers实例
        service_registry = getattr(http_request.app.state, 'service_registry', None)
        chat_service = service_registry.get_service('chat') if service_registry else None
        handlers = chat_service.handlers if chat_service else None
        if not handlers:
            raise HTTPException(
                status_code=500,
                detail=BaseResponse.error(
                    code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                    msg="Chat服务未初始化",
                    trace_id=trace_id
                ).dict()
            )
        
        # 获取流式生成器
        stream_generator = handlers.multi_turn_chat_stream(request, trace_id)
        
        # 返回流式响应 - 原始chunk块
        return StreamingResponse(
            _stream_wrapper(stream_generator, trace_id),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Trace-ID": trace_id
            }
        )
        
    except ValidationException as e:
        logger.warning(f"Validation error - TraceID: {trace_id} | Error: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=BaseResponse.error(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                msg=str(e),
                trace_id=trace_id
            ).dict()
        )
    except BaseBusinessException as e:
        logger.error(f"Business error - TraceID: {trace_id} | Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=BaseResponse.error(
                code=e.code,
                msg=e.message,
                trace_id=trace_id
            ).dict()
        )
    except Exception as e:
        logger.error(f"Unexpected error - TraceID: {trace_id} | Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=BaseResponse.error(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                msg=f"服务内部错误: {str(e)}",
                trace_id=trace_id
            ).dict()
        )


@chat_router.get("/models", response_model=BaseResponse)
async def get_enabled_models(http_request: Request):
    """获取启用的模型列表"""
    trace_id = str(uuid.uuid4())
    logger.info(f"Received get enabled models request - TraceID: {trace_id}")
    
    try:
        # 从service_registry获取chat服务的handlers实例
        service_registry = getattr(http_request.app.state, 'service_registry', None)
        chat_service = service_registry.get_service('chat') if service_registry else None
        handlers = chat_service.handlers if chat_service else None
        if not handlers:
            return BaseResponse.error(
                code=COMMON_ERROR_REQUEST_PARSE_ERROR,
                msg="Chat服务未初始化",
                trace_id=trace_id
            )
        
        enabled_models = handlers.get_enabled_models()
        
        return BaseResponse.success(
            data={"models": enabled_models},
            trace_id=trace_id
        )
        
    except BaseBusinessException as e:
        logger.error(f"Business error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=e.code,
            msg=e.message,
            trace_id=trace_id
        )
    except Exception as e:
        logger.error(f"Unexpected error - TraceID: {trace_id} | Error: {str(e)}")
        return BaseResponse.error(
            code=COMMON_ERROR_REQUEST_PARSE_ERROR,
            msg=f"服务内部错误: {str(e)}",
            trace_id=trace_id
        )


