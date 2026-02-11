# Volc OCRPdf 集成说明（Python）

本目录包含工程化的 `volc_imagex/` 包。当前 OCR 支持：

1. `OCRPdf`（`VisualService.ocr_pdf`）
2. `MultiLanguageOCR`（`VisualService.ocr_api("MultiLanguageOCR", form)`）
3. 支持本地文件/字节数据 OCR（`image_base64`）与公网 URL OCR（`image_url`）

## 1. 安装

如果项目已安装依赖可跳过；否则安装 SDK：

```bash
uv add "volcengine-python-sdk[ark]>=5.0.9"
```

## 2. 环境变量配置（OCRPdf）

不要在代码里写死 AK/SK，使用环境变量：

```bash
export VOLC_ACCESS_KEY="your_ak"
export VOLC_SECRET_KEY="your_sk"
export VOLC_OCR_HOST="visual.volcengineapi.com"   # 可选
export VOLC_OCR_MAX_RETRIES="2"                   # 可选
export VOLC_OCR_CONNECT_TIMEOUT_SEC="8"           # 可选
export VOLC_OCR_READ_TIMEOUT_SEC="30"             # 可选
export VOLC_OCR_API_MODE="pdf"                    # pdf / multilang
export VOLC_OCR_LANG="zh"                         # zh / ko
```

## 3. 最小可运行示例（本地文件 -> OCR）

```python
from volc_imagex.pipeline import ocr_local_file

local_path = "/absolute/path/to/sample.jpg"

result = ocr_local_file(service_id=None, local_path=local_path, scene="general")
print("request_id:", result.request_id)
for t in result.texts:
    print(t.text, t.quad, t.confidence)
```

## 4. 分步调用示例（便于排障）

```python
from volc_imagex.ocr import ocr_ai_process_bytes

local_path = "/absolute/path/to/sample.png"
file_bytes = open(local_path, "rb").read()
ocr = ocr_ai_process_bytes(file_bytes=file_bytes, scene="general", file_type=1, max_retries=2)
print("ocr request_id:", ocr.request_id, "texts:", len(ocr.texts))
```

## 5. URL OCR（降级入口）

可直接使用公网 URL：

```python
from volc_imagex.ocr import ocr_ai_process

result = ocr_ai_process(
    service_id=None,
    data_type="url",
    object_key_or_url="https://example.com/public-image.jpg",
    scene="general",
)
```

## 6. 常见报错排查

### 6.1 413 / 50205 文件过大

- 表现：`Image Size Exceeds Maximum Limit`，或 HTTP 413/400/502
- 原因：`image_base64` 在 `urlencode` 后超过 8MB
- 处理建议：
  1. 使用灰度图、拆分 PDF 页数
  2. 改走 `image_url`（建议 TOS URL）
  3. 调整 `VOLC_OCR_MAX_URLENCODED_BASE64_BYTES` 做本地预检查

### 6.2 ReadTimeout / ConnectionError

- 表现：读取超时、写入超时、连接中断
- 处理建议：
  1. 增加 `VOLC_OCR_READ_TIMEOUT_SEC`
  2. 适当提高 `VOLC_OCR_MAX_RETRIES`
  3. 大文件优先走 URL 模式

### 6.3 OCR 结果解析为空

- 优先检查 `resp["data"]["detail"]` 是否为空
- `textblocks[].box` 可能是 `x0/y0/x1/y1`，实现已兼容
- 可切换 `VOLC_OCR_PARSE_MODE=ocr` 对比 `auto` 的结果

## 7. 日志与可观测性

OCR 会记录：

- `scene`、`data_type`
- 耗时 `elapsed_ms`
- 重试次数 `retries`
- `request_id`（可取到时）
- 错误摘要（失败时）

日志中不会输出 AK/SK。
