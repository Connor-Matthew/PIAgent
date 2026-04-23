import { useEffect, useMemo, useState } from 'react'
import { providerApi } from '../services/api'
import type { Provider, ProviderCreate, ProviderTypeInfo, ProviderUpdate } from '../types/provider'
import { getApiErrorMessage, getApiErrorStatus } from '../utils/apiErrors'

interface ProviderFormState {
  category: 'llm' | 'tts'
  type: string
  name: string
  api_key: string
  base_url: string
  enabled: boolean
  selected_models: string[]
}

export default function ProvidersPage() {
  const [providers, setProviders] = useState<Provider[]>([])
  const [types, setTypes] = useState<ProviderTypeInfo[]>([])
  const [typesLoading, setTypesLoading] = useState(false)
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState<ProviderFormState>({
    category: 'llm' as 'llm' | 'tts',
    type: '',
    name: '',
    api_key: '',
    base_url: '',
    enabled: true,
    selected_models: [] as string[],
  })
  const [formError, setFormError] = useState<string | null>(null)
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null)
  const [testStatus, setTestStatus] = useState<{ msg: string; ok: boolean } | null>(null)
  const [modelsLoading, setModelsLoading] = useState(false)
  const [cachedModels, setCachedModels] = useState<string[] | null>(null)
  const [cachedAt, setCachedAt] = useState<string | null>(null)

  const fetchProviders = async () => {
    setLoading(true)
    try {
      const data = await providerApi.list()
      setProviders(data)
    } catch {
      setProviders([])
    } finally {
      setLoading(false)
    }
  }

  const fetchTypes = async () => {
    setTypesLoading(true)
    try {
      const data = await providerApi.types()
      setTypes(data)
    } catch (error: unknown) {
      console.error('fetchTypes error', error)
    } finally {
      setTypesLoading(false)
    }
  }

  useEffect(() => {
    fetchProviders()
    fetchTypes()
  }, [])

  const selectedType = useMemo(
    () => types.find((t) => t.type === form.type) || null,
    [types, form.type]
  )

  const availableTypes = useMemo(
    () => types.filter((t) => t.category === form.category),
    [types, form.category]
  )

  const openCreate = () => {
    setEditingId(null)
    const defaultCategory: 'llm' | 'tts' = 'llm'
    const categoryTypes = types.filter((t) => t.category === defaultCategory)
    const defaultType = categoryTypes[0]?.type || ''
    setForm({
      category: defaultCategory,
      type: defaultType,
      name: '',
      api_key: '',
      base_url: defaultType
        ? (categoryTypes.find((t) => t.type === defaultType)?.default_base_url || '')
        : '',
      enabled: true,
      selected_models: [],
    })
    setFormError(null)
    setTestStatus(null)
    setCachedModels(null)
    setCachedAt(null)
    setModalOpen(true)
    if (types.length === 0) {
      fetchTypes()
    }
  }

  const openEdit = (p: Provider) => {
    setEditingId(p.id)
    setForm({
      category: p.category,
      type: p.type,
      name: p.name,
      api_key: '',
      base_url: p.base_url || '',
      enabled: p.enabled,
      selected_models: p.selected_models || [],
    })
    setFormError(null)
    setTestStatus(null)
    setCachedModels(p.extra_config?.cached_models || null)
    setCachedAt(p.extra_config?.cached_at || null)
    setModalOpen(true)
  }

  const closeModal = () => {
    setModalOpen(false)
    setEditingId(null)
    setFormError(null)
    setTestStatus(null)
    setCachedModels(null)
    setCachedAt(null)
  }

  const validate = () => {
    if (!form.type) return '请选择类型'
    if (!form.name.trim()) return '名称不能为空'
    if (editingId === null && !form.api_key.trim()) return 'API Key 不能为空'
    if (selectedType?.requires_base_url && !form.base_url.trim()) {
      return `类型 ${selectedType.type} 需要填写 Base URL`
    }
    return null
  }

  const [listCategory, setListCategory] = useState<'all' | 'llm' | 'tts'>('all')
  const filteredProviders = useMemo(() => {
    if (listCategory === 'all') return providers
    return providers.filter((p) => p.category === listCategory)
  }, [providers, listCategory])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const err = validate()
    if (err) {
      setFormError(err)
      return
    }
    setFormError(null)
    try {
      const sharedPayload = {
        type: form.type,
        category: form.category,
        name: form.name.trim(),
        enabled: form.enabled,
        ...(selectedType?.requires_base_url ? { base_url: form.base_url.trim() } : {}),
      }

      if (editingId !== null) {
        const payload: ProviderUpdate = {
          ...sharedPayload,
          ...(form.api_key.trim() ? { api_key: form.api_key.trim() } : {}),
          selected_models: form.selected_models,
        }
        await providerApi.update(editingId, payload)
      } else {
        const payload: ProviderCreate = {
          ...sharedPayload,
          api_key: form.api_key.trim(),
        }
        await providerApi.create(payload)
      }
      await fetchProviders()
      closeModal()
    } catch (error: unknown) {
      setFormError(getApiErrorMessage(error, '保存 Provider 失败'))
    }
  }

  const handleToggleEnabled = async (p: Provider) => {
    try {
      await providerApi.update(p.id, { enabled: !p.enabled })
      await fetchProviders()
    } catch (error: unknown) {
      alert(getApiErrorMessage(error, '更新 Provider 状态失败'))
    }
  }

  const handleTest = async () => {
    if (editingId === null) return
    setTestStatus(null)
    try {
      const res = await providerApi.test(editingId)
      setTestStatus({ msg: res.status || '连接成功', ok: true })
    } catch (error: unknown) {
      setTestStatus({ msg: getApiErrorMessage(error, '连接测试失败'), ok: false })
    }
  }

  const handleRefreshModels = async () => {
    if (editingId === null) return
    setModelsLoading(true)
    try {
      const res = await providerApi.models(editingId, true)
      setCachedModels(res.models)
      setCachedAt(res.cached_at || null)
    } catch (error: unknown) {
      setFormError(getApiErrorMessage(error, '刷新模型列表失败'))
    } finally {
      setModelsLoading(false)
    }
  }

  const handleDelete = async () => {
    if (confirmDeleteId === null) return
    try {
      await providerApi.delete(confirmDeleteId)
      setConfirmDeleteId(null)
      await fetchProviders()
    } catch (error: unknown) {
      alert(getApiErrorMessage(error, '删除 Provider 失败'))
      if (getApiErrorStatus(error) !== 409) {
        setConfirmDeleteId(null)
      }
    }
  }

  return (
    <div className="min-h-screen bg-[#F5F5F5] text-gray-900 p-6"
    >
      <div className="max-w-6xl mx-auto"
      >
        <div className="flex items-center justify-between mb-6"
        >
          <h1 className="text-xl font-semibold text-gray-900">Provider 管理</h1>
          <button
            onClick={openCreate}
            className="bg-red-600 text-white text-sm px-4 py-2 hover:bg-red-700"
          >
            新增 Provider
          </button>
        </div>

        <div className="flex items-center gap-2 mb-4"
        >
          {(['all', 'llm', 'tts'] as const).map((c) => (
            <button
              key={c}
              onClick={() => setListCategory(c)}
              className={`px-3 py-1.5 text-sm transition-colors ${
                listCategory === c
                  ? 'bg-black text-white'
                  : 'text-gray-500 hover:text-gray-900 hover:bg-gray-200'
              }`}
            >
              {c === 'all' ? '全部' : c.toUpperCase()}
            </button>
          ))}
        </div>

        <div className="bg-white border border-gray-200 overflow-hidden"
        >
          <table className="w-full text-left text-sm"
          >
            <thead className="bg-gray-50 border-b border-gray-200"
            >
              <tr>
                <th className="px-4 py-3 font-medium text-gray-500">名称</th>
                <th className="px-4 py-3 font-medium text-gray-500">分类</th>
                <th className="px-4 py-3 font-medium text-gray-500">类型</th>
                <th className="px-4 py-3 font-medium text-gray-500">Base URL</th>
                <th className="px-4 py-3 font-medium text-gray-500">API Key</th>
                <th className="px-4 py-3 font-medium text-gray-500">状态</th>
                <th className="px-4 py-3 font-medium text-gray-500 text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {filteredProviders.map((p) => (
                <tr key={p.id} className="border-b border-gray-100 hover:bg-gray-50"
                >
                  <td className="px-4 py-3 text-gray-900">{p.name}</td>
                  <td className="px-4 py-3 text-gray-600 uppercase text-xs">{p.category}</td>
                  <td className="px-4 py-3 text-gray-600">{p.type}</td>
                  <td className="px-4 py-3 text-gray-400">{p.base_url || '-'}</td>
                  <td className="px-4 py-3 text-gray-400 font-mono">{p.api_key}</td>
                  <td className="px-4 py-3"
                  >
                    <button
                      onClick={() => handleToggleEnabled(p)}
                      className={`inline-flex items-center px-2.5 py-1 text-xs font-medium transition-colors ${
                        p.enabled
                          ? 'bg-green-100 text-green-700 hover:bg-green-200'
                          : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                      }`}
                    >
                      {p.enabled ? '已启用' : '已禁用'}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-right"
                  >
                    <div className="inline-flex items-center gap-2"
                    >
                      <button
                        onClick={() => openEdit(p)}
                        className="text-xs px-2.5 py-1.5 bg-gray-100 text-gray-700 hover:bg-gray-200"
                      >
                        编辑
                      </button>
                      <button
                        onClick={() => setConfirmDeleteId(p.id)}
                        className="text-xs px-2.5 py-1.5 bg-red-50 text-red-700 hover:bg-red-100"
                      >
                        删除
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {filteredProviders.length === 0 && !loading && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-gray-400"
                  >
                    暂无 Provider，点击右上角新增
                  </td>
                </tr>
              )}
              {loading && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-gray-400"
                  >
                    加载中...
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
        >
          <div className="bg-white border border-black w-full max-w-lg max-h-[90vh] overflow-y-auto"
          >
            <div className="px-5 py-4 border-b border-gray-200 flex items-center justify-between"
            >
              <h2 className="text-base font-semibold text-gray-900"
              >
                {editingId !== null ? '编辑 Provider' : '新增 Provider'}
              </h2>
              <button
                onClick={closeModal}
                className="text-gray-400 hover:text-gray-700"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSubmit} className="px-5 py-4 space-y-4"
            >
              {formError && (
                <div className="bg-red-50 border border-red-200 text-red-700 px-3 py-2 text-sm"
                >
                  {formError}
                </div>
              )}

              <div className="grid grid-cols-2 gap-4"
              >
                <label className="block"
                >
                  <span className="text-xs text-gray-500 block mb-1">分类</span>
                  <select
                    value={form.category}
                    disabled={!!editingId}
                    onChange={(e) => {
                      const category = e.target.value as 'llm' | 'tts'
                      const catTypes = types.filter((t) => t.category === category)
                      const firstType = catTypes[0]?.type || ''
                      setForm((f) => ({
                        ...f,
                        category,
                        type: firstType,
                        base_url: firstType
                          ? (catTypes.find((t) => t.type === firstType)?.default_base_url || '')
                          : '',
                      }))
                    }}
                    className="w-full bg-white border border-gray-200 px-3 py-2 text-sm text-gray-900 disabled:opacity-50 focus:border-black focus:outline-none"
                  >
                    <option value="llm">LLM</option>
                    <option value="tts">TTS</option>
                  </select>
                </label>

                <label className="block"
                >
                  <span className="text-xs text-gray-500 block mb-1">类型</span>
                  <select
                    value={form.type}
                    disabled={typesLoading || availableTypes.length === 0}
                    onChange={(e) =>
                      setForm((f) => ({
                        ...f,
                        type: e.target.value,
                        base_url:
                          availableTypes.find((t) => t.type === e.target.value)?.default_base_url || '',
                      }))
                    }
                    className="w-full bg-white border border-gray-200 px-3 py-2 text-sm text-gray-900 disabled:opacity-50 focus:border-black focus:outline-none"
                  >
                    <option value="">
                      {typesLoading ? '加载中...' : availableTypes.length === 0 ? '暂无可用类型' : '请选择'}
                    </option>
                    {availableTypes.map((t) => (
                      <option key={t.type} value={t.type}
                      >
                        {t.type}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <label className="block"
              >
                <span className="text-xs text-gray-500 block mb-1">名称</span>
                <input
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                  className="w-full bg-white border border-gray-200 px-3 py-2 text-sm text-gray-900 focus:border-black focus:outline-none"
                  placeholder="例如 OpenAI 官方"
                />
              </label>

              <label className="block"
              >
                <span className="text-xs text-gray-500 block mb-1">
                  API Key {editingId !== null && '（留空表示不修改）'}
                </span>
                <input
                  type="password"
                  value={form.api_key}
                  onChange={(e) => setForm((f) => ({ ...f, api_key: e.target.value }))}
                  className="w-full bg-white border border-gray-200 px-3 py-2 text-sm text-gray-900 focus:border-black focus:outline-none"
                  placeholder="sk-..."
                />
              </label>

              {selectedType?.requires_base_url && (
                <label className="block"
                >
                  <span className="text-xs text-gray-500 block mb-1"
                  >
                    Base URL <span className="text-red-600">*</span>
                  </span>
                  <input
                    value={form.base_url}
                    onChange={(e) => setForm((f) => ({ ...f, base_url: e.target.value }))}
                    className="w-full bg-white border border-gray-200 px-3 py-2 text-sm text-gray-900 focus:border-black focus:outline-none"
                    placeholder="https://api.example.com/v1"
                  />
                </label>
              )}

              <label className="flex items-center gap-3"
              >
                <input
                  type="checkbox"
                  checked={form.enabled}
                  onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
                  className="border-gray-300 bg-white"
                />
                <span className="text-sm text-gray-700">启用</span>
              </label>

              {editingId !== null && (
                <div className="pt-2 border-t border-gray-200 space-y-3"
                >
                  <div className="flex items-center gap-3"
                  >
                    <button
                      type="button"
                      onClick={handleTest}
                      className="text-xs px-3 py-1.5 bg-gray-100 text-gray-700 hover:bg-gray-200"
                    >
                      测试连接
                    </button>
                    {testStatus && (
                      <span
                        className={`text-xs ${
                          testStatus.ok ? 'text-green-600' : 'text-red-600'
                        }`}
                      >
                        {testStatus.msg}
                      </span>
                    )}
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-2"
                    >
                      <span className="text-xs text-gray-500">模型列表</span>
                      <button
                        type="button"
                        onClick={handleRefreshModels}
                        disabled={modelsLoading}
                        className="text-xs px-2.5 py-1 bg-gray-100 text-gray-700 hover:bg-gray-200 disabled:opacity-50"
                      >
                        {modelsLoading ? '刷新中...' : '刷新'}
                      </button>
                    </div>
                    {cachedModels && cachedModels.length > 0 ? (
                      <div className="bg-white border border-gray-200 p-2 max-h-40 overflow-y-auto"
                      >
                        <div className="flex items-center justify-between mb-1"
                        >
                          <button
                            type="button"
                            onClick={() => setForm((f) => ({ ...f, selected_models: cachedModels }))}
                            className="text-[10px] text-gray-700 hover:text-black"
                          >
                            全选
                          </button>
                          <button
                            type="button"
                            onClick={() => setForm((f) => ({ ...f, selected_models: [] }))}
                            className="text-[10px] text-gray-400 hover:text-gray-700"
                          >
                            清空
                          </button>
                        </div>
                        <ul className="space-y-1"
                        >
                          {cachedModels.map((m) => (
                            <li key={m} className="flex items-center gap-2"
                            >
                              <input
                                type="checkbox"
                                checked={form.selected_models.includes(m)}
                                onChange={(e) => {
                                  const next = e.target.checked
                                    ? [...form.selected_models, m]
                                    : form.selected_models.filter((x) => x !== m)
                                  setForm((f) => ({ ...f, selected_models: next }))
                                }}
                                className="border-gray-300 bg-white"
                              />
                              <span className="text-xs text-gray-700 font-mono">{m}</span>
                            </li>
                          ))}
                        </ul>
                        {cachedAt && (
                          <div className="mt-2 text-[10px] text-gray-400"
                          >
                            缓存于 {new Date(cachedAt).toLocaleString()}
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="text-xs text-gray-400"
                      >
                        暂无模型缓存，点击刷新获取
                      </div>
                    )}

                    {form.selected_models.length > 0 && (
                      <div className="pt-2 border-t border-gray-200"
                      >
                        <div className="text-[10px] text-gray-500 mb-1">已选中的模型（节点配置可见）</div>
                        <div className="flex flex-wrap gap-1"
                        >
                          {form.selected_models.map((m) => (
                            <span
                              key={m}
                              className="inline-flex items-center gap-1 text-[10px] bg-gray-100 text-gray-700 px-1.5 py-0.5"
                            >
                              {m}
                              <button
                                type="button"
                                onClick={() =>
                                  setForm((f) => ({
                                    ...f,
                                    selected_models: f.selected_models.filter((x) => x !== m),
                                  }))
                                }
                                className="text-gray-700 hover:text-black"
                                title="移除"
                              >
                                ×
                              </button>
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              <div className="flex items-center justify-end gap-3 pt-2"
              >
                <button
                  type="button"
                  onClick={closeModal}
                  className="px-4 py-2 text-sm bg-gray-100 text-gray-700 hover:bg-gray-200"
                >
                  取消
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 text-sm bg-black text-white hover:bg-gray-800"
                >
                  保存
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirm */}
      {confirmDeleteId !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
        >
          <div className="bg-white border border-black w-full max-w-sm p-5"
          >
            <h3 className="text-base font-semibold text-gray-900 mb-2"
            >确认删除</h3>
            <p className="text-sm text-gray-500 mb-4"
            >
              删除后无法恢复，是否继续？
            </p>
            <div className="flex items-center justify-end gap-3"
            >
              <button
                onClick={() => setConfirmDeleteId(null)}
                className="px-4 py-2 text-sm bg-gray-100 text-gray-700 hover:bg-gray-200"
              >
                取消
              </button>
              <button
                onClick={handleDelete}
                className="px-4 py-2 text-sm bg-red-600 text-white hover:bg-red-700"
              >
                删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
