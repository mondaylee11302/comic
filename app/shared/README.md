# app/shared

这里放共享配置、日志、校验、通用工具，不放 agent 专属逻辑。
`storyboard` 与 `director` 都只能依赖这里的通用能力。
避免把任一 agent 的业务流程放进本目录。

