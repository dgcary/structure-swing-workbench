FROM python:3.12-slim

WORKDIR /app

# 国内部署默认走清华镜像；海外构建可用 --build-arg PIP_INDEX_URL=https://pypi.org/simple 覆盖
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

COPY pyproject.toml ./
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} ".[dev,market]"

COPY app ./app
COPY tests ./tests

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
