# Superadvanced MOON Capabilities — 5 new tools
# Inserted before the registration block in agent/engine.py

# Location markers for patch insertion:
# - Tool functions: insert after _tool_service_control (after line ~1888 in engine.py)
# - Registration: insert after evidence_hub registration (after line ~3995)
# - KB injection: patch generate_response to inject _memory context (line ~1344)

# NEW TOOL FUNCTIONS (5):
# 1. _tool_research_pipeline — multi-source autonomous research with LLM synthesis
# 2. _tool_reasoning_chain — chain-of-thought via sequential LLM calls
# 3. _tool_knowledge_graph — graph extraction + BFS traversal over memory
# 4. _tool_code_generator — generate+execute code via LLM + python_executor
# 5. _tool_auto_agent — auto-select best agent + tool chain for any task

# KB INJECTION PATCH:
# In generate_response (line ~1344), after system = agent.system_prompt,
# inject: if self._memory: system += "\n[Knowledge Base] " + self._summarize_kb()


# Patch plan:
# 1. Write 5 tool functions to a temp file, read engine.py lines around 1888,
#    patch to insert new functions before the blank line / registration section.
# 2. Patch registration block to add 5 new register_tool calls.
# 3. Patch generate_response to inject KB context into system prompt.