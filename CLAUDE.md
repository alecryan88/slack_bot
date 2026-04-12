# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Slack bot that handles `@mention` events via AWS Lambda + API Gateway, passes thread context to an AI agent (using the `openai-agents` SDK), and responds using GitHub MCP tools for authenticated GitHub access.

## Rules

- Always run `ruff check .` and `ruff format --check .` before committing code. Run `ruff format .` to fix formatting, then re-check before creating a commit.

## Commands

**Dependency management (uses `uv`):**
```bash
uv sync                  # Install dependencies from uv.lock
uv add <package>         # Add a new dependency
```

**Linting and formatting:**
```bash
ruff check .             # Lint
ruff format --check .    # Check formatting
ruff format .            # Auto-format
```

**Build and run locally:**
```bash
# Build Docker image (Lambda target platform)
docker build --platform linux/amd64 -t slack-lambda .

# Run locally with Lambda Runtime Emulator
docker run -p 9000:8080 --env-file .env slack-lambda
```

**Deploy:**
```bash
# Push to ECR
docker tag slack-lambda:latest <account>.dkr.ecr.us-east-1.amazonaws.com/slack-lambda:latest
docker push <account>.dkr.ecr.us-east-1.amazonaws.com/slack-lambda:latest

# Deploy/update CloudFormation stack
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name slack-lambda \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides ImageUri=<ecr-uri>
```

## Architecture

**Request flow:**
1. Slack sends `app_mention` event → API Gateway → Lambda (`handler.py`)
2. `handler.py` initializes the Slack Bolt app and registers listeners from the `listeners/` module
3. `listeners/events/app_mentioned.py` immediately acknowledges Slack (must respond within 3 seconds), posts a "Thinking..." placeholder, then asynchronously fetches thread history (last 50 messages)
4. `listeners/utils/parse_conversation.py` formats thread messages into `[{user, text}]` context
5. `ai/agent.py` sends the formatted context + user prompt to the agent, which connects to GitHub MCP at `https://api.githubcopilot.com/mcp/` for tool use (up to 50 tool turns)
6. The "Thinking..." message is updated in-place with the final response

**Key design constraint:** Slack requires a 200 response within 3 seconds. The bot satisfies this by posting the placeholder immediately and doing all AI processing afterward.

**Response format:** The system prompt in `ai/constants.py` instructs the agent to respond using Slack `mrkdwn` syntax (not standard Markdown) — `*bold*` not `**bold**`, `_italic_` not `*italic*`, no `###` headers.

## Infrastructure

Defined in `template.yaml` (CloudFormation):
- Lambda function: image-based, 256MB, 300s timeout, IAM role allowing self-invocation
- API Gateway HTTP API routing Slack events to Lambda

Required environment variables: `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, `OPENAI_API_KEY`, `GITHUB_TOKEN`
