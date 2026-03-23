# Slack Bot

@mention the bot in any channel or thread and it replies using Claude Sonnet 4.6 connected to the GitHub MCP server. Posts a "Thinking..." message immediately while the LLM runs, then edits it in place with the response. Reads the last 50 messages of thread history for context. All incoming requests are verified against Slack's signing secret.

## Architecture

```mermaid
flowchart LR
    User([User]) -->|"@mention"| Slack

    subgraph AWS
        direction TB
        APIGW[API Gateway] --> Lambda1[Lambda\nack]
        Lambda1 -->|async invoke| Lambda2[Lambda\nlazy]
    end

    Slack -->|POST event| APIGW
    Lambda1 -->|Thinking...| Slack
    Lambda2 -->|fetch thread| Slack
    Lambda2 -->|messages API| Anthropic([Anthropic])
    Anthropic <-->|tool calls| GitHub([GitHub MCP])
    Lambda2 -->|update message| Slack
    Slack --> User
```

## Detailed Sequence

```mermaid
sequenceDiagram
    actor User
    participant Slack
    participant API Gateway
    participant Lambda
    participant Slack API
    participant Anthropic
    participant GitHub MCP

    User->>Slack: @mentions bot
    Slack->>API Gateway: POST event
    API Gateway->>Lambda: invoke (invocation 1 — ack)

    alt Slack retry (x-slack-retry-num header)
        Lambda-->>Slack: 200 (ignored)
    else first delivery
        Lambda->>Slack API: chat.postMessage ("Thinking...")
        Lambda-->>Slack: 200
        Lambda->>Lambda: invoke self async (lazy listener)

        Note over Lambda: invocation 2 — lazy
        Lambda->>Slack API: conversations.replies (fetch thread)
        Slack API-->>Lambda: thread history (oldest 50)
        Lambda->>Anthropic: messages (claude-sonnet-4-6 + GitHub MCP + thread)
        Anthropic->>GitHub MCP: tool calls (server-side)
        GitHub MCP-->>Anthropic: tool results
        Anthropic-->>Lambda: response
        Lambda->>Slack API: chat.update ("Thinking..." → response)
        Slack API-->>User: reply appears in thread
    end
```

## How it works

Built on the [Slack Bolt](https://slack.dev/bolt-python/) framework using its **lazy listener** pattern for AWS Lambda.

When an `@mention` arrives, Slack POSTs the event to API Gateway. The **first Lambda invocation** (ack) posts "Thinking..." to the thread and immediately returns `200` to Slack — well within the 3-second window. It then re-invokes the same Lambda function asynchronously (`InvocationType=Event`) to run the lazy listener.

The **second Lambda invocation** (lazy) does the slow work: fetches the thread history via `conversations.replies`, passes the last 10 messages as context to Claude Sonnet 4.6 with access to the GitHub MCP server, and edits the "Thinking..." message in place with the final response.

Slack retries are silently dropped via middleware (`x-slack-retry-num` header check) to prevent duplicate responses.

The bot responds to **@mentions** in channels and threads. DMs are handled separately.

## Demo

![Demo](example.png)

## Prerequisites

- AWS CLI configured (`aws configure`)
- Docker
- [uv](https://docs.astral.sh/uv/) (for dependency management)
- Slack app (see Configure Slack below)
- Anthropic API key
- GitHub personal access token

## Configure Slack

### 1. Create a Slack app

Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From a manifest** → paste `manifest.json`

Or manually:

### 2. Add Bot Token Scopes

**OAuth & Permissions** → **Bot Token Scopes**:

| Scope | Purpose |
|---|---|
| `app_mentions:read` | Receive @mention events |
| `channels:history` | Read messages in public channels |
| `chat:write` | Post and edit messages |
| `im:history` | Read direct messages |
| `im:write` | Post DM replies |
| `groups:history` | Read messages in private channels |
| `reactions:write` | Add emoji reactions |

### 3. Enable Event Subscriptions

**Event Subscriptions** → toggle **On** → paste your API Gateway URL as the Request URL.

Under **Subscribe to bot events** add:
- `app_mention`
- `message.channels`
- `message.im`
- `message.groups`
- `app_home_opened`

### 4. Enable Interactivity

**Interactivity & Shortcuts** → toggle **On** → paste the same API Gateway URL.

### 5. Install the app

**OAuth & Permissions** → **Install to Workspace** → copy the **Bot User OAuth Token** (`xoxb-...`)

### 6. Copy credentials

- **Bot Token** (`xoxb-...`): OAuth & Permissions
- **Signing Secret**: Basic Information → App Credentials
- **Anthropic API key**: [console.anthropic.com](https://console.anthropic.com)
- **GitHub token**: GitHub → Settings → Developer settings → Personal access tokens

### 7. Add bot to a channel

In Slack: `/invite @your-bot-name`

## Deploy

### 1. Create ECR repository

```bash
aws ecr create-repository --repository-name slack-lambda
```

### 2. Build and push image

```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS \
  --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

docker build --platform linux/amd64 -t slack-lambda .
docker tag slack-lambda:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/slack-lambda:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/slack-lambda:latest
```

### 3. Deploy the CloudFormation stack

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name slack-lambda \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    ImageUri=<account-id>.dkr.ecr.us-east-1.amazonaws.com/slack-lambda:latest \
    SlackBotToken=xoxb-... \
    AnthropicApiKey=sk-ant-... \
    GitHubToken=github_pat_... \
    SlackSigningSecret=your-signing-secret
```

### 4. Get the API Gateway URL

```bash
aws cloudformation describe-stacks \
  --stack-name slack-lambda \
  --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" \
  --output text
```

Paste this URL as the **Request URL** in Slack Event Subscriptions and Interactivity.

## Redeploy after code changes

```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS \
  --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

docker build --platform linux/amd64 -t slack-lambda .
docker tag slack-lambda:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/slack-lambda:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/slack-lambda:latest

aws lambda update-function-code \
  --function-name slack-bolt-handler \
  --image-uri <account-id>.dkr.ecr.us-east-1.amazonaws.com/slack-lambda:latest
```

## Environment Variables

| Variable | Description |
|---|---|
| `SLACK_BOT_TOKEN` | Bot User OAuth Token (`xoxb-...`) |
| `SLACK_SIGNING_SECRET` | Slack app signing secret |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `GITHUB_TOKEN` | GitHub personal access token |

## Local development

Use the Lambda container locally with the AWS Lambda Runtime Interface Emulator:

```bash
docker build --platform linux/amd64 -t slack-lambda .
docker run -p 9000:8080 \
  -e SLACK_BOT_TOKEN=xoxb-... \
  -e SLACK_SIGNING_SECRET=... \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e GITHUB_TOKEN=github_pat_... \
  slack-lambda
```

Invoke the function locally:

```bash
curl -X POST http://localhost:9000/2015-03-31/functions/function/invocations \
  -d '{"body": "..."}'
```

## Teardown

```bash
aws cloudformation delete-stack --stack-name slack-lambda
aws ecr delete-repository --repository-name slack-lambda --force
```
