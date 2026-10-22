# ERPNext AI Procurement Agent

An AI-assisted procurement application that connects a Streamlit user interface to ERPNext through a FastAPI backend and a dedicated MCP tool server. Users can create and manage Material Requests (purchase requisitions), retrieve procurement document details, and move through Purchase Order (PO) conversion and submission with an explicit review-and-approval step.

The system is designed to keep ERPNext as the system of record: the agent interprets requests and coordinates workflow steps, while ERPNext remains responsible for its documents, business rules, and persisted data.

> **Security:** Never commit `.env`, `.streamlit/secrets.toml`, `tokens.json`, API keys, passwords, or session tokens. Use private environment variables or the deployment platform's secret manager. If a credential has been exposed, revoke or rotate it.

## Table of contents

- [What the application does](#what-the-application-does)
- [Architecture and request flow](#architecture-and-request-flow)
- [Technology stack](#technology-stack)
- [Repository layout](#repository-layout)
- [Prerequisites](#prerequisites)
- [Local setup](#local-setup)
- [Configuration](#configuration)
- [Run the application](#run-the-application)
- [ERPNext account preparation](#erpnext-account-preparation)
- [Procurement workflow](#procurement-workflow)
- [Deployment](#deployment)
- [Observability and troubleshooting](#observability-and-troubleshooting)
- [Important operational notes](#important-operational-notes)

## What the application does

- Provides a Streamlit procurement console with chat, structured Material Request intake, and a purchase-order review page.
- Authenticates users against ERPNext and uses the resulting ERPNext session in authenticated backend requests.
- Uses a context-aware gateway and LangGraph workflow to distinguish ordinary conversation from ERPNext operations.
- Uses a Groq-hosted language model through LangChain to interpret requests and select available ERPNext tools.
- Exposes ERPNext operations through a FastMCP server using Streamable HTTP.
- Validates tool arguments before execution and returns structured success or error responses.
- Requires users to review and explicitly approve or reject purchase-order conversion and submission actions.
- Streams assistant responses to the UI using Server-Sent Events (SSE).
- Supports bounded retry and error-recovery routing in the agent workflow.
- Integrates Langfuse callbacks and evaluation for tracing and observability.

## Architecture and request flow

```text
User
  |
  v
Streamlit UI (app.py, login_.py, pages/Approval.py)
  |  ERPNext login / authenticated application cookie
  |  POST /api/v1/chat/stream (SSE)
  |  POST /api/v1/chat/resume (approval decision)
  v
FastAPI backend (src/api/main.py)
  |-- Auth routes: /api/v2/user/auth/*
  |-- Chat and approval routes: /api/v1/chat/*
  |-- LangGraph workflow
  |     gateway classifier
  |       -> orchestrator (Groq via LangChain)
  |       -> guarded MCP execution bridge
  |       -> orchestrator / bounded recovery / response
  |
  |  MCP Streamable HTTP client
  v
FastMCP server (src/mcp_server/server.py, /mcp on port 8000)
  |
  |  Authenticated ERPNext REST API requests
  v
ERPNext

Langfuse receives workflow tracing and evaluation telemetry.
```

At backend startup, FastAPI starts the MCP server as a local subprocess, waits for it to accept connections, loads its tools using the MCP client, and compiles the LangGraph workflow. The MCP server and FastAPI API are therefore separate code components but are launched together by the API process in the current implementation.

LangGraph uses `MemorySaver` for process-local conversation checkpoints. This is convenient for local development, but it is not a shared or durable persistence layer.

## Technology stack

| Area | Technology |
|---|---|
| User interface | Streamlit |
| API and authentication endpoints | FastAPI |
| Agent workflow and routing | LangGraph |
| Language-model integration | LangChain and Groq |
| ERPNext tool interface | FastMCP and the LangChain MCP adapter |
| ERPNext integration | ERPNext REST API |
| Authentication/session handling | ERPNext login, signed application JWT cookie, and ERPNext session context |
| Streaming | Server-Sent Events (SSE) |
| Tracing and evaluation | Langfuse |
| Configuration | Environment variables and Pydantic Settings |

## Repository layout

```text
.
├── app.py                      # Main Streamlit procurement interface
├── login_.py                   # Streamlit login UI
├── pages/
│   └── Approval.py             # Human approval and review page
├── config/
│   ├── logging_config.py       # Application logging
│   └── settings.py             # Environment-backed application settings
├── src/
│   ├── agent_router/           # Intent and workflow routing
│   ├── agents/                 # Orchestrator and guarded tool execution
│   ├── api/                    # FastAPI app, routes, schemas, and SSE
│   ├── auth/                   # ERPNext session and authentication helpers
│   ├── erpnext_client/         # ERPNext client, validation schemas, exceptions
│   ├── llm_client/             # Groq model provider
│   ├── mcp_server/             # FastMCP server and MCP client
│   ├── observbility/           # Agent evaluation and observability
│   ├── prompt_library/         # Agent and recovery prompts
│   ├── state/                  # LangGraph workflow state
│   └── workflow/               # Workflow graph and approval helpers
├── tests/                      # Unit, integration, and ERPNext-related tests
├── utils/                      # Response parsing and data-cleaning helpers
└── requirements.txt            # Python dependencies
```

## Prerequisites

- Git
- Python and `pip` compatible with the packages in `requirements.txt`
- An ERPNext site and a user account authorized to perform the intended procurement actions
- A Groq API key and a model name supported by the configured Groq integration
- Langfuse credentials if tracing and evaluation are to be enabled

## Local setup

### 1. Get the code

```powershell
git clone <YOUR_REPOSITORY_URL>
cd <YOUR_REPOSITORY_DIRECTORY>
```

### 2. Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, use the activation method appropriate for your shell or run the environment's Python executable directly.

### 3. Install dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 4. Configure environment variables

Create a local `.env` file in the repository root. Use the variable names in [Configuration](#configuration), and keep all actual credentials private. Do not copy secrets into this README, source files, screenshots, or version control.

### 5. Start the backend

From the repository root, with the virtual environment active:

```powershell
python -m src.api.main
```

The API uses the `PORT` environment variable when provided and otherwise listens on port `8001`. During startup, it also starts the MCP server on port `8000` and connects to it at `http://127.0.0.1:8000/mcp`. Keep the backend process running while using the UI.

### 6. Start the Streamlit interface

Open a second terminal, activate the same virtual environment, and run:

```powershell
streamlit run app.py
```

Open the local URL printed by Streamlit. The UI reads `BASE_API_URL` to locate the backend; for a local backend, set it to `http://127.0.0.1:8001`.

## Configuration

`config/settings.py` loads settings from the process environment or a root `.env` file. The following variables are used by the application:

| Variable | Required | Purpose |
|---|---:|---|
| `ERPNEXT_BASE_URL` | Yes | ERPNext site base URL, for example `https://your-site.example.com` |
| `TOKEN_REFRESH_URL` | Yes | ERPNext OAuth token refresh endpoint URL required by settings |
| `ERPNEXT_CLIENT_ID` | Yes | ERPNext OAuth client ID required by settings |
| `ERPNEXT_CLIENT_SECRET` | Yes | ERPNext OAuth client secret required by settings |
| `GROQ_API_KEY` | Yes | Groq API key used by the language-model provider |
| `MODEL_NAME` | Yes | Groq model name to use |
| `LANGFUSE_SECRET_KEY` | Yes | Langfuse secret key |
| `LANGFUSE_PUBLIC_KEY` | Yes | Langfuse public key |
| `LANGFUSE_BASE_URL` | Yes | Langfuse host/base URL |
| `BASE_API_URL` | Yes | Backend base URL used by the UI and settings; local default example: `http://127.0.0.1:8001` |
| `JWT_SECRET_KEY` | Recommended | Strong, private signing key for the application authentication cookie; replace the development fallback |
| `ERPNEXT_SCOPE` | No | OAuth scope; defaults to `all openid` in settings |
| `APP_ENV` | No | Application environment label |
| `LOG_LEVEL` | No | Logging level; defaults to `INFO` |

The current UI login flow authenticates the user's ERPNext username and password through ERPNext's login API. The application configuration also currently requires the OAuth-related variables above when settings are initialized. Configure both sets as required by the deployment; do not assume that setting the ERPNext site URL alone is sufficient.

For local development, the Streamlit UI can read `BASE_API_URL` from the root `.env` file. In Streamlit Community Cloud, add `BASE_API_URL` under the app's **Settings → Secrets**. Set it to the public base URL of the deployed FastAPI service, without appending `/api/v1/chat/stream`.

## ERPNext account preparation

1. Create or access an ERPNext site. The application must be configured with the URL of the site you intend to use; use `https://erpnext-ai-integration.m.frappe.cloud` only when that is the site you created and control.
2. Sign in to that site and configure the company and the procurement master data needed by your workflow, including suppliers, item codes, and warehouses.
3. Ensure the ERPNext user account has permission to read and perform the intended Material Request and Purchase Order actions.
4. Use that ERPNext account's credentials to sign in through the application's login page.
5. Configure the ERPNext URL and all backend settings in the local `.env` or the deployment platform's protected environment configuration.

ERPNext master-data names and user permissions must match the documents and operations submitted through the application. ERPNext remains authoritative and may reject a request that violates its validation rules.

## Procurement workflow

1. **Authenticate:** The user signs in with ERPNext credentials. The backend authenticates against ERPNext and establishes application session context.
2. **Request:** The user enters a request in chat or supplies structured Material Request data in the UI.
3. **Classify:** The workflow gateway determines whether the latest turn is conversational or requires an ERPNext operation.
4. **Plan:** The orchestrator uses the model and registered MCP tools to decide the next step.
5. **Validate and execute:** The execution bridge validates tool arguments and passes authorized operations to the MCP server, which calls ERPNext.
6. **Review protected PO actions:** Before converting a Material Request into a draft Purchase Order or submitting a Purchase Order, the workflow fetches current document details and pauses for user review.
7. **Approve or reject:** The user reviews the displayed preview and sends a decision. The backend checks that the approval belongs to the conversation and matches the pending approval preview before resuming the workflow.
8. **Respond:** Tool results return through the workflow, and assistant output is streamed to the UI over SSE.

The MCP tools cover creating and submitting Material Requests; converting a Material Request to a draft Purchase Order; submitting, cancelling, or deleting a Purchase Order; and retrieving Material Request or Purchase Order details. Protected conversion and submission actions use the human approval workflow.

## Deployment

The code supports a split deployment model:

- **Frontend:** Deploy the Streamlit application with Streamlit Community Cloud, using `app.py` as the app entry point. Add `BASE_API_URL` to the Streamlit app's secrets and point it to the public FastAPI backend URL.
- **Backend:** Deploy the FastAPI application on a Python-compatible host such as Render. Configure all required environment variables in the backend service's private environment settings and start the service with `python -m src.api.main`. The application reads the platform-provided `PORT`.
- **MCP server:** The current backend starts `src.mcp_server.server` as a subprocess and the client connects over local Streamable HTTP at `127.0.0.1:8000/mcp`. The backend environment must allow that local process and port.
- **ERPNext and third-party services:** The backend must be able to reach the configured ERPNext and Langfuse endpoints, and it must have access to the configured Groq API.

Connect the repository to the deployment platforms and enable their supported deploy-on-push options if you want automatic deployments. No repository-level CI/CD workflow file is included, so do not assume that tests or deployments run automatically on each push unless you configure and verify that in your hosting setup.

## Observability and troubleshooting

- **Backend startup fails:** Check that all required settings are present, the ERPNext URL is valid, and port `8000` is available for the local MCP process.
- **UI cannot reach the API:** Confirm that the UI's `BASE_API_URL` contains the correct backend base URL and that the deployed service is reachable from the browser.
- **Login fails:** Verify the ERPNext site URL and user credentials, and make sure the ERPNext site accepts the account's login.
- **Tool request is rejected:** Check that the company, supplier, item code, warehouse, document IDs, and user permissions exist and are correct in ERPNext.
- **Approval does not resume:** The approval must match the current pending approval, conversation thread, and preview. A stale or mismatched approval is rejected; review the current document and request a fresh approval.
- **Tracing is unavailable:** Confirm the Langfuse host and keys are configured and reachable. Do not paste keys into issue reports or logs.

Use backend logs for API and MCP startup/runtime information. When configured, Langfuse provides traces and evaluation data for agent runs.

## Important operational notes

- `MemorySaver` stores workflow checkpoints only in process memory. Conversation state and pending approvals can be lost when the backend restarts and are not shared across multiple backend workers or instances.
- Before running multiple backend workers or scaling horizontally, replace the process-local checkpointer with a durable, shared checkpoint store and verify approval/resume behavior across instances.
- The backend launches the MCP server as a subprocess. This is the current implementation; a separately deployed MCP service would require an intentional configuration and lifecycle change.
- Configure a strong `JWT_SECRET_KEY` and keep all credentials in a secret manager. Rotate any credentials that have been exposed.
- The application's approval flow is a workflow safeguard; continue to apply least-privilege ERPNext roles and validate operations against your organization's procurement policies.
- The README describes the repository's current implementation. Verify the target environment, host configuration, ERPNext permissions, and operational requirements before using it for production procurement.

## License

No license information is specified here. Add the project's chosen license and corresponding license file before redistributing the project.
