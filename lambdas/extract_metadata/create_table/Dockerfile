FROM public.ecr.aws/lambda/python:3.10

COPY lambda_function.py ${LAMBDA_TASK_ROOT}

# Install dependencies directly
RUN pip3 install --no-cache-dir aws-lambda-powertools

CMD [ "lambda_function.lambda_handler" ]
