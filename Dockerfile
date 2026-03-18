FROM --platform=linux/amd64 public.ecr.aws/lambda/python:3.13

COPY handler.py llm.py slack.py pyproject.toml ${LAMBDA_TASK_ROOT}

RUN pip install anthropic boto3

CMD ["handler.ack_handler"]
