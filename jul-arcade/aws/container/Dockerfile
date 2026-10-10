# Container mode: one Lambda with both readings of jul-decision-e5-small (vectors for Choice, cross for
# Noul and Score). Built by `cdk deploy -c packaging=container` from aws/build/container (scripts/build.sh).
FROM public.ecr.aws/lambda/python:3.12-arm64

COPY jul-spec.txt ./
COPY . ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir "onnxruntime>=1.18" "jinja2>=3.1" "numpy>=1.24" \
 && pip install --no-cache-dir --no-deps "tokenizers>=0.20" \
 && pip install --no-cache-dir --no-deps "$(cat jul-spec.txt)" \
 && rm -rf ${LAMBDA_TASK_ROOT}/jul-src

ENV ROLE=both
CMD ["model_handler.handler"]
