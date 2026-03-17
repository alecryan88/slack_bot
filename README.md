# Slack Lambda

Receives Slack message events and replies in-thread using AWS Lambda and API Gateway.

## Architecture

```
User       Slack      API Gateway    Ack Lambda       SQS         Process Lambda   OpenAI     Slack API
 │          │              │              │              │               │             │           │
 │─── msg ─▶│              │              │              │               │             │           │
 │          │─── POST ────▶│              │              │               │             │           │
 │          │              │── invoke ───▶│              │               │             │           │
 │          │              │              │ is thread reply? ──▶ skip    │             │           │
 │          │              │              │ is bot message? ────▶ skip   │             │           │
 │          │◀─── 200 ─────────────────── │              │               │             │           │
 │◀─ ack ───│              │              │─ send msg ──▶│               │             │           │
 │          │              │              │              │── trigger ───▶│             │           │
 │          │              │              │              │               │─── gpt-4o ─▶│           │
 │          │              │              │              │               │◀── reply ───│           │
 │          │              │              │              │               │─ postMessage ──────────▶│
 │          │◀──────────────────────────────────────────────────────────────── reply ─────────────│
 │◀─ reply ─│              │              │              │               │             │           │
```

## Prerequisites

- AWS CLI configured (`aws configure`)
- Docker
- A Slack app with Event Subscriptions enabled

## Deploy

### 1. Create ECR repository and push image

```bash
aws ecr create-repository --repository-name slack-lambda

aws ecr get-login-password --region us-east-1 | docker login --username AWS \
  --password-stdin 820242944968.dkr.ecr.us-east-1.amazonaws.com

docker build --platform linux/amd64 -t slack-lambda .
docker tag slack-lambda:latest 820242944968.dkr.ecr.us-east-1.amazonaws.com/slack-lambda:latest
docker push 820242944968.dkr.ecr.us-east-1.amazonaws.com/slack-lambda:latest
```

### 2. Deploy the CloudFormation stack

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name slack-lambda \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides ImageUri=820242944968.dkr.ecr.us-east-1.amazonaws.com/slack-lambda:latest
```

### 3. Get the Function URL

```bash
aws cloudformation describe-stacks \
  --stack-name slack-lambda \
  --query 'Stacks[0].Outputs'
```

Copy the `FunctionUrl` value — this is your Slack Request URL.

## Configure Slack

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → your app → **Event Subscriptions**
2. Enable Events and paste the `FunctionUrl` as the Request URL
3. Under **Subscribe to bot events**, add `message.channels` (or `message.im` for DMs)
4. Save and reinstall the app to your workspace

## Redeploy after code changes

```bash
docker build --platform linux/amd64 -t slack-lambda .
docker tag slack-lambda:latest 820242944968.dkr.ecr.us-east-1.amazonaws.com/slack-lambda:latest
docker push 820242944968.dkr.ecr.us-east-1.amazonaws.com/slack-lambda:latest

aws lambda update-function-code \
  --function-name slack-events-handler \
  --image-uri 820242944968.dkr.ecr.us-east-1.amazonaws.com/slack-lambda:latest
```

## Teardown

```bash
aws cloudformation delete-stack --stack-name slack-lambda
aws ecr delete-repository --repository-name slack-lambda --force
```
