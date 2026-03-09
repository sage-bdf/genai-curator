FROM public.ecr.aws/lambda/python:3.11

# Copy function code
COPY lambda_function.py ${LAMBDA_TASK_ROOT}

# Install dependencies
RUN pip install --no-cache-dir aws-lambda-powertools boto3 \
    && pip install -v --no-cache-dir --only-binary=:all: pandas

# Set the CMD to your handler
CMD [ "lambda_function.lambda_handler" ]
