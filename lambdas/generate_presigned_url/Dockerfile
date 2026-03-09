FROM public.ecr.aws/lambda/python:3.11

# Copy function code
COPY lambda_function.py ${LAMBDA_TASK_ROOT}

RUN pip install --no-cache-dir aws-lambda-powertools boto3

# Set the CMD to your handler
CMD [ "lambda_function.lambda_handler" ]
