export type ModelProvider = 'ANTHROPIC' | 'OPENAI' | 'GOOGLE' | 'AZURE' | 'LOCAL';
export type ModelCapability = 'STREAMING' | 'TOOL_USE' | 'VISION' | 'THINKING' | 'STRUCTURED_OUTPUT';

export interface ModelConfig {
  id: string;
  name: string;
  provider: ModelProvider;
  endpoint: string;
  capabilities: ModelCapability[];
  context_window: number;
  max_output_tokens: number;
  cost_per_m_input: number;
  cost_per_m_output: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
}

export interface ModelConfigCreate {
  name: string;
  provider: ModelProvider;
  endpoint: string;
  capabilities?: ModelCapability[];
  context_window?: number;
  max_output_tokens?: number;
  cost_per_m_input?: number;
  cost_per_m_output?: number;
}
