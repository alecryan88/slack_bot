FROM public.ecr.aws/lambda/python:3.13

COPY handler.py pyproject.toml ${LAMBDA_TASK_ROOT}

RUN pip install openai boto3

CMD ["handler.ack_handler"]
