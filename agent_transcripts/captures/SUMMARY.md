# Capture evidence index

Sanitized HTTP captures from the Claude Agent SDK debugging session.
No secrets: auth tokens are placeholders ('ollama'); Ollama requires no key.

- `01` — CLI session-title request: 0 tools, naming prompt — proof that the CLI's 'unrecognized_model' was actually a /v1/v1/messages 404.
- `03` — The CLI turn request as captured: 6 mcp__lenny__* tools present, 3 system blocks, thinking/context_management/output_config extras. Replay proved the fields were NOT the tool-binding blocker; the model (llama3.2:3b) was.
