'''
Description: MCP服务路由定义
Author: zyq
Date: 2025-12-24 10:20:00
LastEditors: zyq
LastEditTime: 2025-12-26 10:16:37
'''
import uuid
import json
from fastapi import APIRouter, Request, Depends
from fastapi.responses import StreamingResponse
from loguru import logger
from fastapi_limiter.depends import RateLimiter

from core.schemas.base_resp_model_define import BaseResponse
from core.exceptions import BaseBusinessException
from core.config.error_codes import COMMON_ERROR_REQUEST_PARSE_ERROR
from services.mcp.schemas import SyncMCPToolRequest, SyncToolMetaRequest, AskRequest, ListToolsResponse
from services.mcp.handlers import MCPHandlers
from core.config import get_mcp_runtime_config



mcp_router = APIRouter(tags=["MCP服务"])

# mcp限流配置
mcp_runtime_config = get_mcp_runtime_config().mcp
async def _mcp_rate_identifier(req: Request):
    return getattr(req.state, "user_id", None)

mcp_rater_limiter = RateLimiter(
    times=mcp_runtime_config.get("rate_limit", {}).get("times_per_day", 100),
    seconds=mcp_runtime_config.get("rate_limit", {}).get("seconds_per_day", 86400),
    identifier=_mcp_rate_identifier
)


def check_service_initialized(http_request: Request) -> MCPHandlers:
    """检查服务初始化"""
    service_registry = getattr(http_request.app.state, 'service_registry', None)
    mcp_service = service_registry.get_service('mcp') if service_registry else None
    handlers = mcp_service.handlers if mcp_service else None
    if not handlers:
        raise BaseBusinessException(
            code=COMMON_ERROR_REQUEST_PARSE_ERROR,
            message="MCP服务未初始化"
        )
    return handlers


async def _stream_wrapper(generator, trace_id: str):
    """流式包装，将事件转换为SSE行"""
    if generator is None or not hasattr(generator, "__aiter__"):
        logger.error(f"MCP流式生成器无效 generator={generator} | TraceID: {trace_id}")
        error_chunk = {
            "type": "error",
            "trace_id": trace_id,
            "agent_mode": "",
            "content": "",
            "detail": {"error": "流式生成器创建失败"}
        }
        yield f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n"
        return
    try:
        async for event in generator:
            yield f"data: {json.dumps(event.__dict__, ensure_ascii=False)}\n\n"
    except Exception as e:
        logger.error(f"MCP流式处理异常 error={str(e)} | TraceID: {trace_id}")
        error_chunk = {
            "type": "error",
            "trace_id": trace_id,
            "agent_mode": "",
            "content": "",
            "detail": {"error": str(e)}
        }
        yield f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n"


@mcp_router.post("/tools/mcp-sync", response_model=BaseResponse, summary="同步指定服务器上的MCP工具")
async def register_tool(request: SyncMCPToolRequest, http_request: Request):
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"开始同步MCP tools | TraceID: {trace_id}")
    handlers = check_service_initialized(http_request)
    data = await handlers.sync_mcp_tool(request, http_request.state.user_id, trace_id)
    logger.info(f"同步MCP tools完成 | TraceID: {trace_id}")
    return BaseResponse.success(data=data, trace_id=trace_id)

@mcp_router.get("/tools/list", response_model=BaseResponse, summary="查看工具列表", dependencies=[Depends(mcp_rater_limiter)])
async def list_tools(http_request: Request):
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"查询工具列表开始 | TraceID: {trace_id}")
    handlers = check_service_initialized(http_request)
    tools = handlers.list_tools(http_request.state.user_id, trace_id)
    logger.info(f"查询工具列表完成 | TraceID: {trace_id}")
    return BaseResponse.success(data=ListToolsResponse(tools=tools).model_dump(), trace_id=trace_id)


@mcp_router.post("/ask", summary="MCP提问入口", dependencies=[Depends(mcp_rater_limiter)])
async def ask(request: AskRequest, http_request: Request):
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    logger.info(f"mcp_agent_trace_request trace_id={trace_id} query={request.query} prompt={request.prompt}")
    handlers = check_service_initialized(http_request)
    result = await handlers.ask(request, http_request.state.user_id, trace_id, need_stream=request.stream)
    logger.info(f"mcp_agent_trace_finish trace_id={trace_id} query={request.query} prompt={request.prompt}")

    if request.stream:
        return StreamingResponse(
            _stream_wrapper(result, trace_id),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Trace-ID": trace_id
            }
        )

    final_event = result
    return BaseResponse.success(
        data={
            "trace_id": trace_id,
            "agent_mode": final_event.agent_mode,
            "type": final_event.type,
            "content": final_event.content,
            "detail": final_event.detail
        },
        trace_id=trace_id
    )


@mcp_router.get("/ask/trace", response_model=BaseResponse, summary="查询MCP运行审计记录")
async def get_mcp_trace(mcp_agent_trace_id: str, http_request: Request):
    trace_id = getattr(http_request.state, 'trace_id', str(uuid.uuid4()))
    handlers = check_service_initialized(http_request)
    data = handlers.get_run_trace(http_request.state.user_id, mcp_agent_trace_id)
    return BaseResponse.success(data=data, trace_id=trace_id)
