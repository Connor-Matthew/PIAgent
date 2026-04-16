export interface Provider {
  id: number
  type: string
  category: 'llm' | 'tts'
  name: string
  base_url?: string
  api_key: string          // masked: "sk-***xxxx"
  enabled: boolean
  extra_config?: {
    cached_models?: string[]
    cached_at?: string
  }
  selected_models?: string[]
  created_at?: string
  updated_at?: string
}

export interface ProviderCreate {
  type: string
  category?: string
  name: string
  base_url?: string
  api_key: string
  enabled?: boolean
}

export interface ProviderUpdate {
  type?: string
  category?: string
  name?: string
  base_url?: string
  api_key?: string
  enabled?: boolean
  selected_models?: string[]
}

export interface ProviderTypeInfo {
  type: string
  category: 'llm' | 'tts'
  requires_base_url: boolean
  default_base_url: string | null
  supports_list_models: boolean
}
