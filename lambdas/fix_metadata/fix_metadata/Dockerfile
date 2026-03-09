FROM python:3.11-bullseye as build

# Copy and build fix_values package
COPY fix_values /tmp/fix_values
RUN pip install --upgrade pip wheel && \
    pip install --target /tmp/packages /tmp/fix_values

FROM public.ecr.aws/lambda/python:3.11

# Copy lambda function code
COPY lambda_function.py ${LAMBDA_TASK_ROOT}

# Copy built packages
COPY --from=build /tmp/packages ${LAMBDA_TASK_ROOT}

# Install runtime dependencies
RUN pip3 install --no-cache-dir aws-lambda-powertools

# Set the CMD to your handler
CMD [ "lambda_function.lambda_handler" ]
