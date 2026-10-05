"""Documentation for agent tools.

## terminal

- **Name**: `terminal`
- **Description**: Execute a command with full terminal model (risk, backend, verification).
- **Parameters**:
  - `request` (object): ExecutionRequest payload.
- **Returns**: ExecutionResult dict with fields `status`, `stdout`, `stderr`, etc.

## system_command

- **Name**: `system_command`
- **Description**: Run a controlled system command (guarded).
- **Parameters**: `command` (string)
- **Returns**: Output string.

## other tools ...
"