# InkFlow Feature Inventory

## 1. Core Architecture

### 1.1 Step System

- **BaseStep** - Abstract base class for all steps
- **StepRegistry** - Auto-discovery and registration
- **StepContext** - Context passed between steps
- **StepResult** - Execution result with review flag
- **Workflow Contract** - Backend-normalized step runtime/stage/source metadata
- **Writing Contract** - Unified LLM generation rules, review, and cleanup

### 1.2 Recipe System

- **RecipeLoader** - YAML recipe parser
- **Recipe** - Recipe definition model
- **Category** - social/marketing/learning/long_form

### 1.3 Pipeline Execution

- **Pipeline Router** - API for pipeline CRUD
- **In-memory storage** - (DB in future)

---

## 2. Implemented Steps

| Step Type    | Location      | Description           |
| ------------ | ------------- | --------------------- |
| text_input   | steps/input/  | User text input       |
| llm_generate | steps/llm/    | AI content generation |
| human_select | frontend      | User selection UI     |

---

## 3. Services (from Lumina)

| Service         | Source     | Adaptation            |
| --------------- | ---------- | --------------------- |
| http_client     | ✅ Adapted | Connection pooling    |
| embedding_cache | ✅ Adapted | LRU cache for vectors |
| exceptions      | ✅ Adapted | Error hierarchy       |
| llm_service     | ✅ New     | DeepSeek API          |

---

## 4. API Endpoints

```
GET  /health                  - Health check
GET  /api/recipes             - List recipes
GET  /api/recipes/{id}        - Get recipe
POST /api/actions/run         - Execute server-side step
```

---

## 5. TODO

- [x] Frontend (React + Shadcn/ui)
- [ ] Knowledge base (pgvector)
- [ ] Database (PostgreSQL)
- [ ] User auth (JWT)
