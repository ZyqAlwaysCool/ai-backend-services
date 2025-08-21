'''
Description: 错误码定义模块
Author: zyq
Date: 2025-01-21
'''

# 通用错误码
COMMON_ERROR_START = -10000
COMMON_ERROR_REQUEST_PARSE_ERROR = -10001  # 请求解析错误
COMMON_ERROR_INVALID_REQUEST_PARAM_ERROR = -10002  # 无效的请求参数
COMMON_ERROR_JSON_PARSE_ERROR = -10003  # json解析错误
COMMON_ERROR_END = -10199

# 文件处理错误码
FILE_ERROR_START = -10200
FILE_EEROR_TOO_LARGE = -10201  # 文件过大
FILE_ERROR_PREPROCESS_FAILED = -10202  # 文件预处理错误
FILE_ERROR_UPLOAD_TO_DIFY_FAILED = -10203  # 文件上传Dify错误
FILE_ERROR_SAVE_TO_MARKDOWN_FAILED = -10204  # 文件保存为markdown失败
FILE_ERROR_NOT_EXIST = -10205  # 文件不存在
FILE_ERROR_END = -10299

# 数据库错误码
DB_ERROR_START = -10300
DB_ERROR_QUERY_FAILED = -10301  # 数据库查询失败
DB_ERROR_INSERT_FAILED = -10302  # 数据库插入失败
DB_ERROR_UPDATE_FAILED = -10303  # 数据库更新失败
DB_ERROR_DELETE_FAILED = -10304  # 数据库删除失败
DB_ERROR_SYSTEM_ERROR = -10305  # 数据库系统错误
DB_ERROR_END = -10399


def get_error_message(code: int) -> str:
    """根据错误码获取描述信息"""
    error_messages = {
        COMMON_ERROR_REQUEST_PARSE_ERROR: "请求解析错误",
        COMMON_ERROR_INVALID_REQUEST_PARAM_ERROR: "无效的请求参数",
        COMMON_ERROR_JSON_PARSE_ERROR: "JSON解析错误",
        FILE_EEROR_TOO_LARGE: "文件过大",
        FILE_ERROR_PREPROCESS_FAILED: "文件预处理错误",
        FILE_ERROR_UPLOAD_TO_DIFY_FAILED: "文件上传Dify错误",
        FILE_ERROR_SAVE_TO_MARKDOWN_FAILED: "文件保存为markdown失败",
        FILE_ERROR_NOT_EXIST: "文件不存在",
        DB_ERROR_QUERY_FAILED: "数据库查询失败",
        DB_ERROR_INSERT_FAILED: "数据库插入失败",
        DB_ERROR_UPDATE_FAILED: "数据库更新失败",
        DB_ERROR_DELETE_FAILED: "数据库删除失败",
        DB_ERROR_SYSTEM_ERROR: "数据库系统错误",
    }
    return error_messages.get(code, "未知错误")