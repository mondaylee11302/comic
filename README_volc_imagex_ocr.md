# veImageX 上传 + OCR 集成说明（Python）

本目录新增了一个工程化的 `volc_imagex/` 包，用于：

1. 上传本地图片或二进制到 veImageX（SDK 内部走 `ApplyImageUpload + CommitImageUpload`）
2. 调用 `AIProcess` + `system_workflow_image_ocr` 做 OCR
3. 解析返回文本、四点坐标 `Location`、以及 `general` 场景下 `Confidence`

## 1. 安装

如果项目已安装依赖可跳过；否则安装 SDK：

```bash
uv add "volcengine-python-sdk[ark]>=5.0.9"
```

## 2. 环境变量配置

不要在代码里写死 AK/SK，使用环境变量：

```bash
export VOLC_ACCESSKEY="your_ak"
export VOLC_SECRETKEY="your_sk"
export VOLC_OCR_SERVICE_ID="your_service_id"

# 可选：当默认 API 域名解析异常时覆盖（仅 host，或完整 https URL）
export VOLC_IMAGEX_API_HOST="imagex.volcengineapi.com"
# 可选：上传域名覆盖（Apply/Commit 正常后会回传真实上传 host）
export VOLC_OCR_UPLOAD_HOST=""
```

可选：如果未设置环境变量，`new_imagex_service()` 支持从 `~/.volc/config` 尝试读取。

## 3. 最小可运行示例（本地文件 -> 上传 -> OCR）

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
from volc_imagex.uploader import upload_local_file
from volc_imagex.ocr import ocr_ai_process

local_path = "/absolute/path/to/sample.png"

upload = upload_local_file(
    service_id=None,  # 优先读取 VOLC_OCR_SERVICE_ID
    local_path=local_path,
    upload_host=None,  # 可选，必要时指定上传域名
    overwrite=None,
    max_retries=4,
)
print("upload uri:", upload.uri)
print("object_key:", upload.object_key)

ocr = ocr_ai_process(
    service_id=None,
    data_type="uri",
    object_key_or_url=upload.object_key,  # 注意：不含 tos-*-i-* 前缀
    scene="general",  # or "license"
    model_id="default",
    max_retries=4,
)
print("ocr request_id:", ocr.request_id)
print("texts:", len(ocr.texts), "fields:", len(ocr.fields))
```

## 5. URL OCR（降级入口）

当上传链路不稳定时，可直接使用公网 URL（绕过上传链路）：

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

### 6.1 ApplyImageUpload bad gateway / CodeN 201007

- 表现：上传阶段报网关错误、5xx、超时或 `201007`
- 处理建议：
  1. 保持默认重试（指数退避：`0.5, 1, 2, 4` 秒）
  2. 指定 `upload_host` 再试
  3. 上传持续失败时，短期降级为 `data_type="url"` 直接 OCR

### 6.2 参数错误（4xx）

- 场景：`service_id` 为空、`scene/data_type` 不合法等
- 策略：这类错误不会重试，直接抛出可读错误

### 6.3 Output 解析失败

- `AIProcess` 返回 `Result.Output` 通常是 JSON 字符串（转义过）
- 本实现会自动执行二次 `json.loads` 兼容
- 若 `Location` 字段存在但格式非法，会直接报错，并通过 `raw_output`/`raw_resp` 协助排障

## 7. 日志与可观测性

上传与 OCR 都会记录：

- `service_id`
- `scene`、`data_type`
- 文件名/大小（上传）
- 耗时 `elapsed_ms`
- 重试次数 `retries`
- `request_id`（可取到时）
- 错误摘要（失败时）

日志中不会输出 AK/SK。
