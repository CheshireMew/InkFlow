# InkFlow Feature Inventory

## 1. Core Architecture

### 1.1 Step System

- **BaseStep** - Abstract base class for all steps
- **StepRegistry** - Auto-discovery and registration
- **StepContext** - Context passed between steps
- **StepResult** - Execution result with review flag

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
| human_select | steps/output/ | User selection UI     |
| export       | steps/output/ | Content export        |

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
POST /api/pipelines/create    - Create pipeline
GET  /api/pipelines/{id}      - Get status
POST /api/pipelines/execute   - Execute step
```

---

## 5. TODO

- [x] Frontend (React + Shadcn/ui)
- [ ] Knowledge base (pgvector)
- [ ] Database (PostgreSQL)
- [ ] User auth (JWT)
