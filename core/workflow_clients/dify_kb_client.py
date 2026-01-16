'''
Description: dify知识库管理api能力封装
Author: zyq
Date: 2025-12-02 15:20:47
LastEditors: zyq
LastEditTime: 2025-12-04 18:04:54
'''
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import json

import httpx
from loguru import logger


class DifyKBClientError(Exception):
    """Dify 知识库客户端异常"""

    def __init__(self, message: str, status_code: Optional[int] = None, error: Optional[Any] = None):
        super().__init__(message)
        self.status_code = status_code
        self.error = error


class DifyKBClient:
    """封装 Dify 知识库维护相关 API 的客户端"""

    def __init__(self, base_url: str, api_key: str, timeout: int = 120):
        if not base_url or not api_key:
            raise ValueError("base_url 与 api_key 均不能为空")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
        }

    @staticmethod
    def _shorten(content: Any, limit: int = 500) -> str:
        text = str(content)
        return text if len(text) <= limit else text[:limit] + "...(truncated)"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
    ) -> Any:
        url = f"{self._base_url}{path}"
        body_preview: Any = json_body if files is None else data
        files_preview = list(files.keys()) if files else None
        logger.info(
            "DifyKBClient request start method={} url={} params={} body={} files={}",
            method.upper(),
            url,
            params,
            self._shorten(body_preview),
            files_preview,
        )
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.request(
                    method=method.upper(),
                    url=url,
                    headers=self._headers(),
                    params=params,
                    json=json_body if files is None else None,
                    data=data if files is not None else data,
                    files=files,
                )
                response.raise_for_status()
                if response.status_code == 204:
                    return {}
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type:
                    return response.json()
                # 某些接口标头未声明 JSON，但实际返回 JSON 字符串，尝试兜底解析
                try:
                    return response.json()
                except Exception:
                    return response.text
        except httpx.HTTPStatusError as exc:
            body_text = exc.response.text
            logger.error(
                f"Dify KB request failed status={exc.response.status_code} url={url} body={body_text[:500]}"
            )
            raise DifyKBClientError(
                message=f"HTTP {exc.response.status_code}: {body_text}",
                status_code=exc.response.status_code,
                error=body_text,
            )
        except httpx.RequestError as exc:
            logger.error(f"Dify KB request error url={url} error={str(exc)}")
            raise DifyKBClientError(message=str(exc))

    # ================= 数据集（知识库）相关 =================
    async def create_dataset(
        self,
        name: str,
        description: Optional[str] = None,
        permission: str = "only_me",
    ) -> Dict[str, Any]:
        payload = {"name": name, "permission": permission}
        if description:
            payload["description"] = description
        return await self._request("POST", "/datasets", json_body=payload)

    async def list_datasets(self, page: int = 1, limit: int = 20) -> Dict[str, Any]:
        params = {"page": page, "limit": limit}
        return await self._request("GET", "/datasets", params=params)

    async def delete_dataset(self, dataset_id: str) -> Dict[str, Any]:
        return await self._request("DELETE", f"/datasets/{dataset_id}")

    # ================= 文档相关 =================
    async def create_document_by_text(
        self,
        dataset_id: str,
        name: str,
        text: str,
        indexing_technique: str = "high_quality",
        process_rule: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "name": name,
            "text": text,
            "indexing_technique": indexing_technique,
        }
        if process_rule:
            payload["process_rule"] = process_rule
        return await self._request(
            "POST", f"/datasets/{dataset_id}/document/create_by_text", json_body=payload
        )

    async def create_document_by_file(
        self,
        dataset_id: str,
        file_path: str | Path,
        process_rule: Optional[Dict[str, Any]] = None,
        indexing_technique: str = "high_quality",
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        file_path = Path(file_path)
        if not file_path.exists():
            raise DifyKBClientError(f"文件不存在: {file_path}")

        data_payload: Dict[str, Any] = {
            "indexing_technique": indexing_technique,
        }
        if process_rule:
            data_payload["process_rule"] = process_rule
        if name:
            data_payload["name"] = name

        filename = name or file_path.name
        files = {
            "data": (None, json.dumps(data_payload), "text/plain"),
            "file": (filename, file_path.open("rb"), "application/octet-stream"),
        }
        try:
            return await self._request(
                "POST",
                f"/datasets/{dataset_id}/document/create_by_file",
                files=files,
            )
        finally:
            # 关闭文件句柄
            file_obj = files["file"][1]
            try:
                file_obj.close()
            except Exception:
                pass

    async def update_document_by_text(
        self,
        dataset_id: str,
        document_id: str,
        name: str,
        text: str,
    ) -> Dict[str, Any]:
        payload = {"name": name, "text": text}
        return await self._request(
            "POST",
            f"/datasets/{dataset_id}/documents/{document_id}/update_by_text",
            json_body=payload,
        )

    async def update_document_by_file(
        self,
        dataset_id: str,
        document_id: str,
        file_path: str | Path,
        process_rule: Optional[Dict[str, Any]] = None,
        indexing_technique: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        file_path = Path(file_path)
        if not file_path.exists():
            raise DifyKBClientError(f"文件不存在: {file_path}")

        data_payload: Dict[str, Any] = {}
        if process_rule:
            data_payload["process_rule"] = process_rule
        if indexing_technique:
            data_payload["indexing_technique"] = indexing_technique
        if name:
            data_payload["name"] = name

        filename = name or file_path.name
        files = {
            "data": (None, json.dumps(data_payload), "text/plain"),
            "file": (filename, file_path.open("rb"), "application/octet-stream"),
        }
        try:
            return await self._request(
                "POST",
                f"/datasets/{dataset_id}/documents/{document_id}/update_by_file",
                files=files,
            )
        finally:
            file_obj = files["file"][1]
            try:
                file_obj.close()
            except Exception:
                pass

    async def list_documents(self, dataset_id: str, page: int = 1, limit: int = 20) -> Dict[str, Any]:
        params = {"page": page, "limit": limit}
        return await self._request("GET", f"/datasets/{dataset_id}/documents", params=params)

    async def delete_document(self, dataset_id: str, document_id: str) -> Dict[str, Any]:
        return await self._request("DELETE", f"/datasets/{dataset_id}/documents/{document_id}")

    async def get_indexing_status(self, dataset_id: str, batch: str) -> Dict[str, Any]:
        return await self._request(
            "GET", f"/datasets/{dataset_id}/documents/{batch}/indexing-status"
        )

    # ================= 分段相关 =================
    async def add_segments(
        self,
        dataset_id: str,
        document_id: str,
        segments: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        payload = {"segments": segments}
        return await self._request(
            "POST",
            f"/datasets/{dataset_id}/documents/{document_id}/segments",
            json_body=payload,
        )

    async def list_segments(
        self,
        dataset_id: str,
        document_id: str,
        page: int = 1,
        limit: int = 20,
    ) -> Dict[str, Any]:
        params = {"page": page, "limit": limit}
        return await self._request(
            "GET",
            f"/datasets/{dataset_id}/documents/{document_id}/segments",
            params=params,
        )

    async def update_segment(
        self,
        dataset_id: str,
        document_id: str,
        segment_id: str,
        segment: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload = {"segment": segment}
        return await self._request(
            "POST",
            f"/datasets/{dataset_id}/documents/{document_id}/segments/{segment_id}",
            json_body=payload,
        )

    async def delete_segment(
        self,
        dataset_id: str,
        document_id: str,
        segment_id: str,
    ) -> Dict[str, Any]:
        return await self._request(
            "DELETE",
            f"/datasets/{dataset_id}/documents/{document_id}/segments/{segment_id}",
        )

    # ================= 元数据相关 =================
    async def add_metadata_field(
        self,
        dataset_id: str,
        field_type: str,
        name: str,
    ) -> Dict[str, Any]:
        payload = {"type": field_type, "name": name}
        return await self._request(
            "POST",
            f"/datasets/{dataset_id}/metadata",
            json_body=payload,
        )

    async def update_metadata_field(
        self,
        dataset_id: str,
        metadata_id: str,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        return await self._request(
            "PATCH",
            f"/datasets/{dataset_id}/metadata/{metadata_id}",
            json_body=payload,
        )

    async def delete_metadata_field(self, dataset_id: str, metadata_id: str) -> Dict[str, Any]:
        return await self._request(
            "DELETE",
            f"/datasets/{dataset_id}/metadata/{metadata_id}",
        )

    async def list_metadata_fields(self, dataset_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/datasets/{dataset_id}/metadata")

    async def toggle_built_in_metadata(
        self,
        dataset_id: str,
        action: str,
    ) -> Dict[str, Any]:
        return await self._request(
            "POST",
            f"/datasets/{dataset_id}/metadata/built-in/{action}",
        )

    async def assign_documents_metadata(
        self,
        dataset_id: str,
        operation_data: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        payload = {"operation_data": operation_data}
        return await self._request(
            "POST",
            f"/datasets/{dataset_id}/documents/metadata",
            json_body=payload,
        )
