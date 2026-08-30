# FDE 商机录入与分析 Agent

飞书 FDE 面试作业：`04｜商机录入与分析助手`。

当前阶段：Architecture Frozen, Business Rules Test-driven.

## Architecture Freeze

- 不增加 Multi-Agent、RAG、复杂 Agent Framework、长期 Memory、Vector DB。
- LLM 只生成 `RawExtraction`。
- `ValidatedOpportunity` 只能由 Evidence Validator、Business Rule Engine、Conflict / Completeness Validator 生成。
- 若 Golden Tests 发现官方业务规则、Stage Rule、Evidence Rule、Fact Boundary Rule 存在理解或实现错误，允许进行测试驱动的规则修正。

## Frontend Template

正式前端模板 canonical repository:

https://github.com/Kiranism/next-shadcn-dashboard-starter

实际初始化前端时必须记录采用的 tag / commit hash，避免模板后续变化影响项目复现。

## Milestone Gate

在 M1 `Schema + Rule Engine + Validators + Golden Tests` 验收通过前，不进入 Real LLM Integration。

## Local Test

```bash
PYTHONPATH=. pytest backend/tests -q
```


## M2 Mock Pipeline

M2 provides a complete local mock pipeline:

```text
Input -> Mock Provider -> RawExtraction -> Evidence Validator -> Rule Engine -> ValidatedOpportunity -> API-shaped response
```

Real LLM integration is intentionally not included in M2.

Available backend routes after dependencies are installed:

- `GET /health`
- `GET /examples`
- `POST /analyze`
- `POST /clarify`
- `GET /analyses`
- `GET /analyses/{id}`
- `GET /analyses/{id}/revisions/{revision}`
- `DELETE /analyses`
- `POST /analyses/bulk-delete`
- `DELETE /analyses/{id}`

## M4 Analysis Session History

M4 provides Analysis Session History, not a full CRM database.

```text
POST /analyze -> Session + Revision 1
POST /clarify -> Revision N+1 via Input Builder and full Pipeline re-analysis
GET /analyses -> session summaries
GET /analyses/{id} -> current result + revision summaries
GET /analyses/{id}/revisions/{revision} -> a specific revision detail
```

SQLite is used by default via `DATABASE_URL=sqlite:///./backend/data/app.db`. The local database directory is ignored by git.


## M5 Frontend

M5 provides a Chinese business-user frontend for the opportunity analysis flow. It does not expose RawExtraction JSON, provider, model, latency, pipeline version, or revision terminology to sales users.

Install frontend dependencies once:

```bash
cd frontend
npm install
```

Start backend and frontend together from the project root:

```bash
./scripts/start_m5_dev.sh
```

For a production-like local demo after dependencies are installed:

```bash
./scripts/start_m5_demo.sh
```

Open the product UI:

```text
http://127.0.0.1:3000
```

The backend API defaults to `http://127.0.0.1:8000`. Use `BACKEND_PORT`, `FRONTEND_PORT`, or `NEXT_PUBLIC_API_BASE_URL` to override local ports when needed.
