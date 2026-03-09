FROM public.ecr.aws/lambda/python:3.10

# Install the required packages
RUN pip install --no-cache-dir boto3==1.28.38 aws-lambda-powertools==2.26.0

# Copy function code
COPY lambda_function.py ${LAMBDA_TASK_ROOT}

# Set the CMD to your handler
CMD [ "lambda_function.lambda_handler" ]
