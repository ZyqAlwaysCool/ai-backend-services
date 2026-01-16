### /document/convert Markdown→DOCX 字体与格式支持说明

- 默认样式：字体 `宋体`，字号 `12`（pt），行距 `1.5` 倍行距。
- 支持的 `convert_options`（请求体内嵌字典）：
  - `font_name`：字符串，覆盖字体名称，默认 `宋体`。
  - `font_size`：数字或字符串，可转成数字的字号（pt），默认 `12`。
  - `line_spacing`：数字或字符串，可转成数字的倍数行距，默认 `1.5`。
  - `engine`：`default`（默认，自定义解析，依赖小，保留列表/表格/行内样式）或 `pandoc`（需安装 pandoc+pypandoc，格式兼容性更强）。
- 标题样式：各级 `Heading` 同步应用 `font_name` 和 `line_spacing`（字号沿用 Word 默认层级，保持层次感）。
- Markdown 适配范围（转为 DOCX 时生效）：
  - 标题（#、## 等）、段落、粗体、斜体、行内代码、代码块
  - 无序/有序列表（含嵌套缩进）
  - 表格（Markdown 表格语法）
  - 脚注、任务列表、删除线会按 HTML 转换结果保留文本
- 样例请求（multipart form）关键字段：
  - `source_format=markdown`
  - `target_format=docx`
  - `convert_options={"font_name":"宋体","font_size":12,"line_spacing":1.5}`

以上配置无需额外依赖，保持现有接口路径与参数不变，向后兼容。
