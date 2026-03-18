# Slack Bot

Receives Slack messages, reacts with 👀, and replies in-thread using Claude Sonnet 4.6 connected to the GitHub MCP server. Reads the full thread history before responding so it maintains conversation context. All incoming requests are verified against Slack's signing secret before processing.

## Architecture

```mermaid
flowchart LR
    User([User]) -->|message| Slack
    Slack -->|event| AWS
    AWS -->|reply| Slack
    Slack --> User

    subgraph AWS
        Ack[Ack Lambda] --> SQS --> Process[Process Lambda]
    end

    Process <-->|Claude + GitHub tools| Anthropic([Anthropic API])
```

## Detailed Sequence

```mermaid
sequenceDiagram
    actor User
    participant Slack
    participant API Gateway
    participant Ack Lambda
    participant SQS
    participant Process Lambda
    participant Slack API
    participant Anthropic
    participant GitHub MCP

    User->>Slack: sends message or @mentions bot in thread
    Slack->>API Gateway: POST event
    API Gateway->>Ack Lambda: invoke

    alt is bot message, or thread reply without @mention
        Ack Lambda-->>Slack: 200 (skip)
    else new top-level message or @mention in thread
        Ack Lambda->>Slack API: reactions.add (👀)
        Ack Lambda-->>Slack: 200
        Ack Lambda->>SQS: send message
        SQS->>Process Lambda: trigger
        Process Lambda->>Slack API: conversations.replies (fetch thread)
        Slack API-->>Process Lambda: thread history
        Process Lambda->>Anthropic: chat (claude-sonnet-4-6 + GitHub MCP + thread history)
        Anthropic->>GitHub MCP: tool calls (server-side)
        GitHub MCP-->>Anthropic: tool results
        Anthropic-->>Process Lambda: final reply
        Process Lambda->>Slack API: chat.postMessage (thread reply)
        Slack API-->>User: reply in thread
    end
```

## How it works

When a user sends a message in a Slack channel, Slack POSTs the event to an API Gateway endpoint. The **Ack Lambda** receives it, immediately reacts with 👀 to signal the message was received, and returns a `200` to Slack — all within the 3-second window Slack requires. It then drops the message onto an **SQS queue** and exits.

The **Process Lambda** is triggered by SQS and handles the slow work. It first fetches the full Slack thread history via `conversations.replies`, then sends it to **Claude Sonnet 4.6** along with access to the **GitHub MCP server**. This means the bot has full context of the thread and can search repos, read files, create issues, manage PRs, and more — all handled server-side by Anthropic's MCP connector. Claude generates a final response posted as a thread reply.

The bot responds to:
- **Top-level messages** in channels it's in
- **@mentions** anywhere, including inside existing threads

The reason we split into two Lambdas is Slack's retry behavior — if Slack doesn't receive a `200` within 3 seconds, it retries the event. By returning `200` immediately and offloading to SQS, we prevent duplicate processing.

## Demo

![Demo](example.png)

## Prerequisites

- AWS CLI configured (`aws configure`)
- Docker
- Slack app (see Configure Slack below)
- Anthropic API key
- GitHub personal access token (read-only, public repos)

## Configure Slack

### 1. Create a Slack app

Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From scratch**

### 2. Add Bot Token Scopes

**OAuth & Permissions** → **Bot Token Scopes**:

| Scope | Purpose |
|---|---|
| `channels:history` | Read messages in public channels |
| `im:history` | Read direct messages |
| `chat:write` | Post replies in threads |
| `reactions:write` | Add 👀 reaction to messages |

### 3. Install the app

**OAuth & Permissions** → **Install to Workspace** → copy the **Bot User OAuth Token** (`xoxb-...`)

### 4. Enable Event Subscriptions

**Event Subscriptions** → toggle **On** → paste your API Gateway URL as the Request URL.

Under **Subscribe to bot events** add:
- `message.channels`
- `app_mention`
- `message.im` (optional, for DMs)

### 5. Copy your Signing Secret

**Basic Information** → **App Credentials** → copy the **Signing Secret**. This is passed as `SlackSigningSecret` when deploying.

### 6. Find your Bot User ID

```bash
curl -H "Authorization: Bearer xoxb-your-token" https://slack.com/api/auth.test
```

Copy the `user_id` field (e.g. `U012AB3CD`).

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
    SlackBotUserId=U012AB3CD \
    SlackSigningSecret=your-signing-secret
```

### 4. Get the API Gateway URL

```bash
aws cloudformation describe-stacks \
  --stack-name slack-lambda \
  --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" \
  --output text
```

Paste this URL as the **Request URL** in Slack Event Subscriptions.

## Redeploy after code changes

```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS \
  --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

docker build --platform linux/amd64 -t slack-lambda .
docker tag slack-lambda:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/slack-lambda:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/slack-lambda:latest

# Update both Lambdas
aws lambda update-function-code \
  --function-name slack-ack-handler \
  --image-uri <account-id>.dkr.ecr.us-east-1.amazonaws.com/slack-lambda:latest

aws lambda update-function-code \
  --function-name slack-process-handler \
  --image-uri <account-id>.dkr.ecr.us-east-1.amazonaws.com/slack-lambda:latest
```

## Environment Variables

| Variable | Lambda | Description |
|---|---|---|
| `SLACK_BOT_TOKEN` | Both | Bot User OAuth Token (`xoxb-...`) |
| `SLACK_SIGNING_SECRET` | Ack | Slack app signing secret (Basic Information → App Credentials) |
| `SQS_QUEUE_URL` | Ack | URL of the SQS queue |
| `ANTHROPIC_API_KEY` | Process | Anthropic API key |
| `GITHUB_TOKEN` | Process | GitHub personal access token |
| `BOT_USER_ID` | Process | Slack bot user ID (e.g. `U012AB3CD`) |

## Teardown

```bash
aws cloudformation delete-stack --stack-name slack-lambda
aws ecr delete-repository --repository-name slack-lambda --force
```
