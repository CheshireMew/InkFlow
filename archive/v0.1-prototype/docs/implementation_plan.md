# InkFlow Architecture Optimization Plan

## Goal

Transform InkFlow from a functional prototype into a scalable, maintainable, and robust application by decoupling components, standardizing logic, and ensuring data persistence.

## Phase 1: Frontend Component Architecture (Immediate Priority)

**Problem**: `StepCard.tsx` consumes 400+ lines with tightly coupled logic for 4 different step types. Adding new steps requires modifying the core container.
**Solution**: Implement the "Strategy Pattern" for step rendering.

### Tasks

1. [ ] **Create Component Directory**: `src/components/steps/`
2. [ ] **Extract Components**:
   - `TextInput.tsx`: Handle dynamic fields (text, select) and validation.
   - `LLMGenerate.tsx`: Handle loading states and variant display.
   - `HumanSelect.tsx`: Handle variant selection UI.
   - `Export.tsx`: Handle copy/download actions.
3. [ ] **Refactor StepCard**:
   - Transform into a pure "Container" component.
   - Responsible only for: Header, Collapse/Expand logic, Status Icons.
   - Dynamically render child component based on `step.type`.

## Phase 2: Backend Core Decoupling (High Priority)

**Problem**: `routers/pipelines.py` mixes HTTP routing with complex state management (reset logic, dependency injection).
**Solution**: Extract a proper Pipeline Engine.

### Tasks

1. [ ] **Create Engine Module**: `backend/core/engine.py`
2. [ ] **Centralize Logic**:
   - Move "Reset Subsequent Steps" logic execution engine.
   - Move "Dependency Injection" (resolving `source_step` outputs) to a dedicated `ContextResolver`.
3. [ ] **Standardize Prompting**:
   - Move `DictObj` and rendering logic to `core/templating.py`.
   - Ensure ALL steps (not just LLM) can use variables like `{input_data.text}`.

## Phase 3: Data Persistence (Stability)

**Problem**: In-memory `_pipelines` dict loses data on restart.
**Solution**: SQLite + SQLModel (Pydantic-native ORM).

### Tasks

1. [ ] **Database Setup**: `backend/db/database.py` with SQLite.
2. [ ] **Models**: Define `Pipeline` and `PipelineStep` SQLModels.
3. [ ] **Migration**: Update `pipelines.py` to prompt DB instead of memory.

## Phase 4: Async Architecture (Scalability)

**Problem**: HTTP request blocks until LLM finishes (timeout risk).
**Solution**: Async Task Queue.

### Tasks

1. [ ] **Background Tasks**: Use `FastAPI.BackgroundTasks` or Redis/Celery.
2. [ ] **Polling/SSE**: Frontend updates to poll or listen for completion.

---

## Execution: Phase 1 (Frontend Refactoring)

We will begin by creating the `src/components/steps` structure and extracting the `TextInput` component functionality.
