# 阶段设计：Provider 实例化管理 + OpenAI 兼容协议

> 日期：2026-04-14
> 状态：已完成
> 依赖：Task 1–12 + 默认 IO 节点阶段已完成

## 1. 动机

当前 Provider 是硬编码枚举 + `.env` 里塞单一 key：

- 用户无法在 UI 里增删、切换账号。
- 同一类型只能配一份 key（不能并存个人号 / 公司号）。
- 无法接入 OpenAI 兼容协议的自建 / 第三方服务（Ollama、vLLM、DeepSeek、硅基流动等）。
- LLM 节点只能在 4 个写死的 provider type 里选，配置面板展示的模型列表是写死的常量。

本阶段把 Provider 变成**存 DB 的一等实体**，支持多实例、加密存储密钥、动态拉取模型列表、新增 `openai_compatible` 协议类型。

## 2. 范围

**In scope**

- 新表 `providers`：`{id, type, name, base_url, api_key_encrypted, enabled, extra_config, timestamps}`。
- 5 种 `type`：`openai` / `anthropic` / `google` / `deepseek` / `openai_compatible`。
- Provider CRUD API；密钥加密存储（Fernet），GET 接口返回 mask 后的尾 4 位。
- 连通性测试 = 仅鉴权：调用该 provider 的 "list models" 端点，HTTP 200 即通过。
- 模型列表动态拉取：`openai` / `openai_compatible` / `deepseek` 调 `GET {base_url}/v1/models`；`anthropic` / `google` 用内置静态列表。拉取结果缓存到 `extra_config.cached_models + cached_at`。
- LLM 节点配置从 `{provider: "openai", model: "gpt-4"}` 改为 `{provider_id: 123, model: "gpt-4"}`。
- Provider 模块重构：`BaseLLMProvider` 接口统一为 `list_models() / test_connection() / create_chat_model(model, **kwargs)`，从 DB row 实例化。

**Out of scope**

- 模型参数 schema（每个模型的可调参数白名单）——本期 LLM 节点的参数面板保持现状。
- Provider 级别的 rate limit / quota / 用量统计。
- 其它节点（TTS / Embedding）的 provider 化——本期只做 LLM。`embeddings.py` / `fish_audio.py` 沿用 `.env`。

## 3. 数据模型

### 3.1 `backend/models/provider.py`

```python
class Provider(Base):
    __tablename__ = "providers"

    id = Column(Integer, primary_key=True)
    type = Column(String(32), nullable=False)       # openai | anthropic | google | deepseek | openai_compatible
    name = Column(String(64), nullable=False, unique=True)  # 用户起的实例名
    base_url = Column(String(256), nullable=True)   # openai_compatible 必填；其它可选覆盖
    api_key_encrypted = Column(Text, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    extra_config = Column(JSON, default=dict)       # {cached_models, cached_at, headers, ...}
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

### 3.2 密钥加密 `backend/core/crypto.py`

- 用 `cryptography.fernet.Fernet`。
- 密钥源：`settings.secret_key`（新增配置，Fernet 要求的 32 字节 urlsafe base64）。启动时若未配置，在开发环境自动生成并写 `.env`；生产环境缺失直接抛错。
- 暴露 `encrypt(plaintext: str) -> str`、`decrypt(ciphertext: str) -> str`。
- 加密后的密文直接入库；API GET 返回 `mask_key(plaintext) = "sk-***" + plaintext[-4:]`。

## 4. Provider 模块重构

### 4.1 `backend/providers/base.py`

```python
class BaseLLMProvider(ABC):
    type: ClassVar[str]
    default_base_url: ClassVar[str | None] = None
    supports_list_models: ClassVar[bool] = True

    def __init__(self, api_key: str, base_url: str | None = None, extra: dict | None = None):
        self.api_key = api_key
        self.base_url = base_url or self.default_base_url
        self.extra = extra or {}

    @abstractmethod
    def list_models(self) -> list[str]: ...

    @abstractmethod
    def test_connection(self) -> None:
        """鉴权成功返回 None；失败抛 ProviderAuthError / ProviderError。"""

    @abstractmethod
    def create_chat_model(self, model: str, **kwargs) -> BaseChatModel: ...
```

### 4.2 每个 type 的实现

- `openai_provider.py`：`list_models()` → `httpx.get(f"{base_url}/v1/models", Authorization=Bearer)`；`create_chat_model()` → `ChatOpenAI(api_key, base_url, model, **kwargs)`。
- `openai_compatible_provider.py`：**复用 OpenAIProvider 的实现**，仅 `type = "openai_compatible"`、`default_base_url = None`（强制用户填）。也可以直接让 OpenAIProvider 作为基类，CompatibleProvider 只改 classvars。
- `anthropic_provider.py`：`list_models()` 返回静态列表 `["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001", ...]`；`test_connection()` 调一次最便宜的 `messages.count_tokens` 或直接 `GET https://api.anthropic.com/v1/models`（Anthropic 实际提供此端点，可直接用）。
- `google_provider.py`：`list_models()` 静态或调用 `genai.list_models()`；`test_connection()` 同上。
- `deepseek_provider.py`：与 `openai_provider` 同构（DeepSeek 完全 OpenAI 兼容），`default_base_url = "https://api.deepseek.com"`。

### 4.3 工厂 `backend/providers/__init__.py`

```python
PROVIDER_REGISTRY: dict[str, type[BaseLLMProvider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "google": GoogleProvider,
    "deepseek": DeepSeekProvider,
    "openai_compatible": OpenAICompatibleProvider,
}

def build_provider(row: Provider) -> BaseLLMProvider:
    cls = PROVIDER_REGISTRY[row.type]
    return cls(
        api_key=decrypt(row.api_key_encrypted),
        base_url=row.base_url,
        extra=row.extra_config or {},
    )
```

## 5. API

`backend/api/providers.py` 全面重写：

```
GET    /api/providers                       — 列表（key masked）
POST   /api/providers                       — 创建  body: {type, name, base_url?, api_key, enabled?}
GET    /api/providers/{id}                  — 详情（key masked）
PUT    /api/providers/{id}                  — 更新（api_key 省略则不改）
DELETE /api/providers/{id}                  — 删除（若有 LLM 节点引用则拒绝并返回引用列表）
POST   /api/providers/{id}/test             — 鉴权测试  → 200 ok / 401 auth_failed / 502 network
GET    /api/providers/{id}/models           — 模型列表（缓存优先，缓存过期或 ?refresh=true 时实时拉取）
GET    /api/providers/types                 — 返回 5 种 type 的元信息（是否需要 base_url、默认 base_url 等）供前端表单渲染
```

删除时的引用检查：扫描 `workflows` 表中所有 `nodes[].data.provider_id`，若命中则 409。

## 6. LLM 节点改动

- `backend/nodes/llm_node.py`：
  - 配置 schema 从 `{provider, model, temperature, system_prompt, stream}` 改为 `{provider_id, model, temperature, system_prompt, stream}`。
  - 执行时：`row = db.get(Provider, provider_id); provider = build_provider(row); chat = provider.create_chat_model(model, temperature=..., streaming=...)`。
  - 若 `provider_id` 找不到或 `enabled=false` → `NodeExecutionError` → SSE error 事件。

- Compiler 校验：所有 LLM 节点的 `provider_id` 必须存在且 enabled（校验时需要 DB session；把 session 注入 Compiler 或放到 engine 层校验都行，建议放 compiler 以便 API 层提前报错）。

## 7. 配置

`backend/config.py` 增加：

```python
secret_key: SecretStr = ""  # Fernet key, 32 bytes urlsafe base64
```

启动时 `main.py` 的 lifespan 里：若 `secret_key` 为空且处于开发环境（`ENV != "production"`），自动 `Fernet.generate_key()` 并追加到 `.env`，并记录警告日志。

旧的 `openai_api_key` / `anthropic_api_key` 等保留，作为**种子数据**：首次启动时若 `providers` 表为空且 env 中有 key，自动插入对应 Provider 行（type 与环境变量名映射，name = `"Default OpenAI"` 等）。一次性迁移，不阻断后续编辑。

## 8. 前端改动（契约定义，实际实现在前端阶段）

- 新增"Providers 管理"页 / 设置抽屉：表格列出所有实例，支持增/改/删/测/刷新模型。
- 创建 / 编辑表单：
  - `type` 下拉：5 个选项，选中后 `base_url` 字段是否可见/必填由 `/api/providers/types` 返回的元信息决定。
  - `name`、`api_key`（密码输入框）、`enabled` 开关。
  - 保存前可点"测试连接"→ 调 `/test`。
- LLM 节点配置面板：
  - `provider_id` 下拉（从 `/api/providers?enabled=true` 拉）。
  - `model` 下拉（选中 provider 后 `/api/providers/{id}/models`）。旁边一个"刷新"按钮。

## 9. 受影响文件

**后端（修改 + 新增）**

- 新增 `backend/models/provider.py`
- 新增 `backend/core/crypto.py`
- 修改 `backend/config.py`（`secret_key`）
- 修改 `backend/main.py`（开发环境自动生成 secret_key + 种子迁移）
- 修改 `backend/providers/base.py`（新接口）
- 修改 `backend/providers/openai_provider.py` / `anthropic_provider.py` / `google_provider.py` / `deepseek_provider.py`
- 新增 `backend/providers/openai_compatible_provider.py`
- 修改 `backend/providers/__init__.py`（registry + factory）
- 修改 `backend/api/providers.py`（全面重写）
- 修改 `backend/nodes/llm_node.py`（`provider_id` + DB 查询）
- 修改 `backend/core/compiler.py`（LLM 节点 provider_id 校验）
- 修改 `backend/models/__init__.py`（注册 Provider）
- 新增 `backend/tests/test_crypto.py`
- 新增 `backend/tests/test_providers_api.py`（替代 / 扩展当前 `test_providers_api`）
- 修改 `backend/tests/test_nodes.py`（LLM 节点测试改用 provider_id）
- 修改 `backend/requirements.txt`：增加 `cryptography`

**前端**

- 新增 `frontend/src/pages/Providers.tsx`
- 修改 `frontend/src/components/panels/NodeConfig.tsx`（LLM 节点）
- 修改 `frontend/src/services/api.ts`
- 修改 `frontend/src/types/provider.ts`

## 10. 验收标准

1. `pytest backend/tests` 全绿。新 `test_crypto.py` 覆盖 encrypt/decrypt roundtrip；新 `test_providers_api.py` 覆盖 CRUD、mask、测试连接、模型列表缓存、删除时引用保护。
2. Fernet 密钥在开发环境缺失时自动生成并写 `.env`，不阻断启动；生产环境（`ENV=production`）缺失直接抛错。
3. 种子迁移：清空 DB 后首次启动，若 `.env` 含旧 key，自动创建对应 Provider 行。
4. OpenAI 兼容：创建 `type=openai_compatible, base_url=http://localhost:11434/v1` 的 Provider → `/test` 返回 200（Ollama 本地服务）→ `/models` 返回本地模型列表 → LLM 节点引用该 provider_id 能跑通一次工作流。
5. 引用保护：有 LLM 节点引用某 provider 时，`DELETE /api/providers/{id}` 返回 409 + 引用列表。
6. API GET 永不返回明文 api_key；前端表单"api_key 为空时不更新"的 PUT 行为被 API 正确处理。
7. 本设计的要点已合并进主 spec。

## 11. 执行顺序建议

1. `cryptography` 依赖 + `crypto.py` + 测试
2. `models/provider.py` + Base 注册
3. `providers/base.py` 接口定型 + 各 type 实现 + registry
4. `api/providers.py` 重写 + 测试
5. `nodes/llm_node.py` + `compiler.py` 校验
6. 种子迁移 + lifespan 里 secret_key 自动生成
7. 跑全部测试
8. 回填主 spec
