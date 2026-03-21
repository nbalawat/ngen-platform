export interface MCPServer {
  id: string;
  name: string;
  description: string;
  namespace: string;
  endpoint: string;
  transport: string;
  status: string;
  tools: ToolDefinition[];
  created_at: string;
  updated_at: string;
}

export interface ToolDefinition {
  name: string;
  description: string;
  parameters: ToolParameter[];
  tags: string[];
}

export interface ToolParameter {
  name: string;
  type: string;
  description: string;
  required: boolean;
}

export interface ToolEntry {
  id: string;
  server_id: string;
  server_name: string;
  name: string;
  description: string;
  parameters: ToolParameter[];
  tags: string[];
}

export interface ToolCallResponse {
  server_name: string;
  tool_name: string;
  result: unknown;
  error: string | null;
  duration_ms: number | null;
}
